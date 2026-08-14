"""Construye y refresca la capa de negocio (schema bnpl).

  build_bnpl.py              refresca las vistas materializadas en orden de dependencia
  build_bnpl.py --rebuild    reconstruye desde los .sql (DROP + CREATE); usar al cambiar la logica
  build_bnpl.py --solo v1,v2 limita la operacion a esas vistas

El refresh es completo, no incremental, y tiene que serlo: un pago puede llegar hasta 519 dias
despues del movimiento (recuperaciones de mora), asi que el PAR de un mes ya cerrado cambia
retroactivamente.
"""
import argparse
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from postgres_local_client import execute_sql, extract_sql

BASE_DIR = Path(__file__).resolve().parent

# Alias de postgres_local_client. Uno por schema y por nivel de permiso: el DDL de las
# vistas necesita ALLOW_DDL, la bitacora vive en otro schema y los conteos son lectura.
DB_BNPL_RW = "bnpl_rw"
DB_BNPL = "bnpl"
DB_OPS_RW = "bnpl_ops_rw"

TZ_OFFSET_HOURS = -6

# (vista, archivo DDL). El orden es el de DEPENDENCIA, no el del numero de archivo: las dims de
# ruta viven en el 11 pero se construyen antes porque grouped_orders las lee.
CAPAS = [
    (None, "02_bnpl_funciones.sql"),
    ("dim_ruta_actual", "11_bnpl_dim_ruta.sql"),
    ("dim_ruta_cliente_scd", None),  # se crea junto con dim_ruta_actual
    ("grouped_orders", "03_bnpl_grouped_orders.sql"),
    ("loss_rates", "04_bnpl_loss_rates.sql"),
    ("par_snapshot", "05_bnpl_par_snapshot.sql"),
    ("vintage_analysis", "06_bnpl_vintage_analysis.sql"),
    ("grid_bnpl", "07_bnpl_grid_bnpl.sql"),
    ("kpis_daily", "08_bnpl_kpis_daily.sql"),
    ("revenue_comision", "09_bnpl_revenue_comision.sql"),
    ("corte_venta_sku", "10_bnpl_cortes_venta.sql"),
    ("corte_venta_so", None),  # se crea junto con corte_venta_sku
]


# Capa de consumo: una vista en `pbi_bnpl` por cada tabla del modelo de Power BI. El cuerpo de
# cada una es el archivo correspondiente de sql/pbi/, sin copiarlo: se lee y se envuelve. Asi el
# .sql sigue siendo la unica fuente y la vista no puede quedar desfasada de el.
#
# El numero del archivo se descarta y el resto es el nombre de la vista, que coincide con el de la
# tabla en el modelo: 01_bnpl_grouped_orders.sql -> pbi_bnpl.bnpl_grouped_orders.
PBI_DIR = BASE_DIR / "sql" / "pbi"
PBI_SCHEMA = "pbi_bnpl"


def _ahora_mx() -> datetime:
    return (datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)).replace(tzinfo=None)


def _construir_vistas_pbi() -> None:
    """Crea pbi_bnpl.* a partir de sql/pbi/NN_<nombre>.sql."""
    execute_sql((BASE_DIR / "sql" / "15_pbi_vistas.sql").read_text(encoding="utf-8"),
                db=DB_BNPL_RW)

    # Los 90+ no son consultas del tablero sino documentacion de piezas del pipeline.
    archivos = sorted(f for f in PBI_DIR.glob("[0-8][0-9]_*.sql"))
    if not archivos:
        raise SystemExit(f"No encontre consultas en {PBI_DIR}")

    for archivo in archivos:
        vista = archivo.stem.split("_", 1)[1]
        cuerpo = archivo.read_text(encoding="utf-8").strip().rstrip(";")
        # DROP + CREATE y no CREATE OR REPLACE: este ultimo falla si cambian los nombres, el orden
        # o el tipo de las columnas, que es justo lo que pasa al corregir una consulta.
        execute_sql(
            f'DROP VIEW IF EXISTS {PBI_SCHEMA}."{vista}" CASCADE;\n'
            f'CREATE VIEW {PBI_SCHEMA}."{vista}" AS\n{cuerpo};',
            db=DB_BNPL_RW,
        )
    print(f"{PBI_SCHEMA}: {len(archivos)} vistas creadas para Power BI")

    # Despues del DROP + CREATE, no antes: el DROP se lleva los GRANT de pbi_gateway, y el USAGE
    # que otorga se deduce de las funciones que las vistas acaban de declarar. El archivo explica
    # los dos modos en que este rol pierde permisos.
    execute_sql((BASE_DIR / "sql" / "16_pbi_grants.sql").read_text(encoding="utf-8"),
                db=DB_BNPL_RW)
    print(f"{PBI_SCHEMA}: permisos de pbi_gateway aplicados")


def _registrar(vista: str, modo: str, filas, segundos: float, inicio) -> None:
    execute_sql(
        "INSERT INTO bnpl_ops.etl_runs (started_at, tabla, modo, filas, segundos) "
        "VALUES (:inicio, :tabla, :modo, :filas, :segundos) "
        "ON CONFLICT (started_at, tabla) DO NOTHING",
        {
            "inicio": inicio,
            "tabla": f"bnpl.{vista}",
            "modo": modo,
            # int() porque _filas devuelve numpy.int64 y psycopg3 no adapta tipos de numpy.
            "filas": int(filas),
            "segundos": round(segundos, 1),
        },
        db=DB_OPS_RW,
    )


def _filas(vista: str):
    return int(extract_sql(f"SELECT count(*) AS n FROM bnpl.{vista}", db=DB_BNPL)["n"].iloc[0])


def run(rebuild: bool = False, solo: list = None) -> None:
    capas = CAPAS
    if solo:
        capas = [(v, a) for v, a in CAPAS if v is None or v in solo]
        desconocidas = set(solo) - {v for v, _ in CAPAS if v}
        if desconocidas:
            raise SystemExit(f"No existen en CAPAS: {', '.join(sorted(desconocidas))}")

    for vista, archivo in capas:
        inicio, t0 = _ahora_mx(), time.time()

        if vista is None:
            # Bloque de funciones: siempre se aplica, no es una vista.
            execute_sql(
                (BASE_DIR / "sql" / archivo).read_text(encoding="utf-8"), db=DB_BNPL_RW
            )
            print(f"{archivo}: aplicado ({time.time() - t0:.1f}s)")
            continue

        if rebuild:
            if archivo is None:
                # La vista se crea dentro del .sql de otra (cortes SKU y SO comparten archivo).
                # Se registra igual aunque no se ejecute nada: si no, las vistas que comparten
                # archivo desaparecen de etl_runs en las corridas --rebuild y la bitacora miente
                # sobre que se reconstruyo.
                filas = _filas(vista)
                _registrar(vista, "rebuild", filas, time.time() - t0, inicio)
                print(f"bnpl.{vista}: {filas:,} filas (creada junto con la anterior)")
                continue
            execute_sql(
                (BASE_DIR / "sql" / archivo).read_text(encoding="utf-8"), db=DB_BNPL_RW
            )
            modo = "rebuild"
        else:
            execute_sql(f"REFRESH MATERIALIZED VIEW bnpl.{vista}", db=DB_BNPL_RW)
            modo = "refresh"

        segundos = time.time() - t0
        filas = _filas(vista)
        _registrar(vista, modo, filas, segundos, inicio)
        print(f"bnpl.{vista}: {filas:,} filas en {segundos:.1f}s ({modo})")

    # Al final y siempre: son vistas simples, crearlas es solo DDL y cuesta menos de un segundo.
    # Correrlo en cada build las deja auto-reparadas si alguien tocó una a mano.
    #
    # Tambien despues de un --rebuild --solo, aunque no se hayan tocado todas las capas: los .sql
    # de bnpl hacen DROP MATERIALIZED VIEW ... CASCADE, y el CASCADE se lleva las vistas de
    # pbi_bnpl que leen de la que se reconstruyo. Si no se recrean aqui, el tablero queda sin esas
    # tablas hasta la siguiente corrida completa. Un --solo sin --rebuild no las toca (REFRESH no
    # suelta nada), pero recrearlas cuesta menos que razonar sobre cual sobrevivio.
    if not solo or rebuild:
        _construir_vistas_pbi()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Construye la capa de negocio BNPL")
    parser.add_argument(
        "--rebuild", action="store_true", help="reconstruye las vistas desde los .sql"
    )
    parser.add_argument("--solo", help="vistas a procesar, separadas por coma")
    args = parser.parse_args()
    run(rebuild=args.rebuild, solo=args.solo.split(",") if args.solo else None)

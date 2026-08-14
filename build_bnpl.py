"""Construye y refresca la capa de negocio (schema bnpl).

  build_bnpl.py              refresca las vistas materializadas en orden de dependencia
  build_bnpl.py --rebuild    reconstruye desde los .sql (DROP + CREATE); usar al cambiar la logica
  build_bnpl.py --solo v1,v2 limita la operacion a esas vistas

El refresh es completo, no incremental, y tiene que serlo: un pago puede llegar hasta 519 dias
despues del movimiento (recuperaciones de mora), asi que el PAR de un mes ya cerrado cambia
retroactivamente.
"""
import argparse
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bnpl_version
from postgres_local_client import execute_sql, extract_sql

BASE_DIR = Path(__file__).resolve().parent

log = logging.getLogger(__name__)

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
    # DDL puro (CREATE TABLE / CREATE INDEX IF NOT EXISTS): no borra ni recarga nada, los datos
    # siguen entrando por carga_archivos_bnpl.py y carga_clientes_concurso.py a mano. Estan aqui
    # porque las vistas de consumo los leen: sql/pbi/14, 15, 16 y 17 hacen FROM archivos_bnpl.*
    # y sql/pbi/20 lee bnpl.bnpl_clientes_concurso. En una VM limpia, sin estas dos lineas, esas
    # cinco vistas fallan al crearse y pbi_bnpl queda incompleto sin que nadie se entere.
    (None, "14_archivos_bnpl.sql"),
    (None, "13_bnpl_clientes_concurso.sql"),
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

    fallidas = []
    for archivo in archivos:
        vista = archivo.stem.split("_", 1)[1]
        cuerpo = archivo.read_text(encoding="utf-8").strip().rstrip(";")
        inicio, t0 = _ahora_mx(), time.time()
        # DROP + CREATE y no CREATE OR REPLACE: este ultimo falla si cambian los nombres, el orden
        # o el tipo de las columnas, que es justo lo que pasa al corregir una consulta.
        try:
            execute_sql(
                f'DROP VIEW IF EXISTS {PBI_SCHEMA}."{vista}" CASCADE;\n'
                f'CREATE VIEW {PBI_SCHEMA}."{vista}" AS\n{cuerpo};',
                db=DB_BNPL_RW,
            )
        except Exception as e:  # noqa: BLE001 - una vista rota no puede tumbar a las otras 17
            # Una consulta rota no se puede llevar a las otras 17: el DROP ya corrio, asi que
            # abortar aqui deja esa vista borrada Y las siguientes sin crear. Se registran todas
            # y se falla al final, con la lista completa.
            fallidas.append((vista, str(e).splitlines()[0][:200]))
            continue
        # Se registra cada vista: son las unicas 18 cosas que Power BI lee y hasta ahora no
        # dejaban ni una fila de bitacora. sql_sha256 dice CUAL definicion se publico. Fuera del
        # try a proposito: el except es solo para la consulta rota, no para la bitacora.
        _registrar(f"{PBI_SCHEMA}.{vista}", "vista", None, time.time() - t0, inicio, archivo)
    log.info("%s: %d de %d vistas creadas para Power BI",
             PBI_SCHEMA, len(archivos) - len(fallidas), len(archivos))
    for vista, error in fallidas:
        log.error("    FALLO %s.%s: %s", PBI_SCHEMA, vista, error)

    # Despues del DROP + CREATE, no antes: el DROP se lleva los GRANT de pbi_gateway, y el USAGE
    # que otorga se deduce de las funciones que las vistas acaban de declarar. El archivo explica
    # los dos modos en que este rol pierde permisos.
    execute_sql((BASE_DIR / "sql" / "16_pbi_grants.sql").read_text(encoding="utf-8"),
                db=DB_BNPL_RW)
    log.info("%s: permisos de pbi_gateway aplicados", PBI_SCHEMA)

    # El raise va DESPUES de los grants, no antes. Con el try/except de arriba, una consulta rota ya
    # no detiene el bucle: las vistas siguientes se dropean y se recrean igual, y el DROP se lleva
    # sus GRANT. Si se abortara aqui arriba, 16_pbi_grants.sql no correria y pbi_gateway se quedaria
    # sin permisos sobre las vistas SANAS — o sea que una sola consulta rota tumbaria el refresh
    # entero en vez de solo su tabla, que es justo lo contrario de lo que busca el try/except.
    if fallidas:
        raise RuntimeError(
            f"{len(fallidas)} vistas de {PBI_SCHEMA} no se crearon: "
            f"{', '.join(v for v, _ in fallidas)}"
        )


def _registrar(objeto: str, modo: str, filas, segundos: float, inicio, archivo=None) -> None:
    execute_sql(
        "INSERT INTO bnpl_ops.etl_runs "
        "(started_at, tabla, modo, filas, segundos, commit_sha, sql_sha256) "
        "VALUES (:inicio, :tabla, :modo, :filas, :segundos, :commit, :sql_sha) "
        "ON CONFLICT (started_at, tabla) DO NOTHING",
        {
            "inicio": inicio,
            "tabla": objeto,
            "modo": modo,
            # int() porque _filas devuelve numpy.int64 y psycopg3 no adapta tipos de numpy.
            # None para las vistas de pbi_bnpl: son DDL, no se cuentan sus filas.
            "filas": int(filas) if filas is not None else None,
            "segundos": round(segundos, 1),
            "commit": bnpl_version.commit_sha(),
            "sql_sha": bnpl_version.sha_sql(archivo),
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
            log.info("%s: aplicado (%.1fs)", archivo, time.time() - t0)
            continue

        if rebuild:
            if archivo is None:
                # La vista se crea dentro del .sql de otra (cortes SKU y SO comparten archivo).
                # Se registra igual aunque no se ejecute nada: si no, las vistas que comparten
                # archivo desaparecen de etl_runs en las corridas --rebuild y la bitacora miente
                # sobre que se reconstruyo.
                filas = _filas(vista)
                _registrar(f"bnpl.{vista}", "rebuild", filas, time.time() - t0, inicio, None)
                log.info("bnpl.%s: %s filas (creada junto con la anterior)", vista, f"{filas:,}")
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
        _registrar(f"bnpl.{vista}", modo, filas, segundos, inicio, archivo)
        log.info("bnpl.%s: %s filas en %.1fs (%s)", vista, f"{filas:,}", segundos, modo)

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
    # Corrida suelta: sin main.py no hay logging configurado y el detalle por vista no se veria.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    run(rebuild=args.rebuild, solo=args.solo.split(",") if args.solo else None)

"""Carga manual del universo del concurso: Excel -> bnpl.bnpl_clientes_concurso.

One-shot. No cuelga de `build_bnpl.py` ni de `main.py`: el dato lo pone negocio en un Excel del
Drive, no sale de Mongo ni de Redshift. Se vuelve a correr cuando negocio publique otra version
del archivo; el DDL y el TRUNCATE + carga van en una sola transaccion, asi que una corrida fallida
no deja la tabla a medias.

    python carga_clientes_concurso.py                # carga
    python carga_clientes_concurso.py --dry-run      # solo valida y muestra el resumen
    python carga_clientes_concurso.py --archivo X    # otra ruta del libro

La hoja `bbdd` es la que se usa. El libro trae otra (`Hoja1`) con 71,298 filas: las mismas seis
columnas mas 'baja' y 'corrientes', pegadas al lado de un bloque distinto de trabajo (store_id,
lineas de julio/abril, Venta L6M). `bbdd` es subconjunto exacto de ese bloque, ya filtrado.
"""
import argparse
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from postgres_local_client import execute_sql, transaction

BASE_DIR = Path(__file__).resolve().parent

SCHEMA = "bnpl"
TABLA = "bnpl_clientes_concurso"
DB_RW = "bnpl_rw"
DB_OPS_RW = "bnpl_ops_rw"
TZ_OFFSET_HOURS = -6  # las fechas del pipeline van en hora Mexico, igual que ops/config.py:19


def _ahora_mx() -> datetime:
    return (datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)).replace(tzinfo=None)


def _registrar(tabla: str, filas: int, segundos: float, inicio) -> None:
    """Misma bitacora que el resto del pipeline. Sin esto no hay forma de saber cuando se
    cargo cada archivo: el conteo de filas es la unica senal, y no distingue recarga de
    archivo sin cambios."""
    execute_sql(
        "INSERT INTO bnpl_ops.etl_runs (started_at, tabla, modo, filas, segundos) "
        "VALUES (:inicio, :tabla, 'manual', :filas, :segundos) "
        "ON CONFLICT (started_at, tabla) DO NOTHING",
        {"inicio": inicio, "tabla": f"{SCHEMA}.{tabla}", "filas": int(filas),
         "segundos": round(segundos, 1)},
        db=DB_OPS_RW,
    )


ARCHIVO = (
    r"D:\Shared drives\Data Room - BI & Data Analytics\Dashboards\Venta"
    r"\Punto de encuentro (Compromisos)\concurso_bnpl\BBDD tablero BNPL LANZAMIENTO.xlsx"
)
HOJA = "bbdd"

# El Excel trae dos columnas que solo se distinguen por una mayuscula ("Ruta Preventa" y "Ruta
# preventa") y la segunda no es una ruta: son codigos SV*, o sea el supervisor. Verificado contra
# redshift_bnpl.estructura_comercial: la cuarta columna cuadra 100% contra `ruta` y la sexta 100%
# contra `supervisor`. Por eso el mapeo va POSICIONAL y no por nombre — leer por nombre con dos
# homonimas es justo la forma de cruzarlas sin que nadie se entere.
COLUMNAS = [
    "netsuite_id_num",  # 'Netsuite'
    "linea_nueva",      # 'Línea Nueva'
    "clasificacion",    # 'Clasificación'
    "ruta_preventa",    # 'Ruta Preventa'
    "oficina_venta",    # 'Oficina Venta'
    "supervisor",       # 'Ruta preventa'  <- supervisor, pese al nombre
]

# Cabeceras que debe traer la hoja, en orden. Si negocio reordena o renombra columnas, la carga se
# detiene en vez de escribir la ruta en la columna del supervisor.
CABECERAS_ESPERADAS = [
    "Netsuite", "Línea Nueva", "Clasificación", "Ruta Preventa", "Oficina Venta", "Ruta preventa",
]


def leer(archivo: str) -> pd.DataFrame:
    df = pd.read_excel(archivo, sheet_name=HOJA)

    reales = [str(c).strip() for c in df.columns]
    if reales != CABECERAS_ESPERADAS:
        raise SystemExit(
            f"La hoja '{HOJA}' no trae las columnas esperadas.\n"
            f"  esperado: {CABECERAS_ESPERADAS}\n"
            f"  recibido: {reales}\n"
            "Revisa el orden antes de cargar: 'Ruta Preventa' y 'Ruta preventa' son distintas."
        )

    df.columns = COLUMNAS
    df["netsuite_id_num"] = df["netsuite_id_num"].astype("int64")
    df["netsuite_id"] = df["netsuite_id_num"].astype(str)
    df["linea_nueva"] = pd.to_numeric(df["linea_nueva"], errors="coerce")

    for c in ["clasificacion", "ruta_preventa", "oficina_venta", "supervisor"]:
        df[c] = df[c].astype(str).str.strip()
        # '0' es hueco de la fuente, no una oficina. Son 65 filas, todas de APIZACO (SVAPZ01).
        # Sin esto Power BI lo pinta como una categoria mas en cualquier desglose por oficina.
        df[c] = df[c].replace({"": None, "0": None, "nan": None, "None": None})

    dup = df["netsuite_id"].duplicated().sum()
    if dup:
        raise SystemExit(
            f"{dup} netsuite_id repetidos en la hoja. La tabla lleva indice unico sobre esa "
            "columna porque es el lado 'uno' de las relaciones del modelo; hay que resolver el "
            "duplicado en el Excel antes de cargar."
        )

    return df[["netsuite_id", "netsuite_id_num", "linea_nueva", "clasificacion",
               "ruta_preventa", "oficina_venta", "supervisor"]]


def resumen(df: pd.DataFrame) -> None:
    print(f"  filas                {len(df):,}")
    print(f"  netsuite_id unicos   {df['netsuite_id'].nunique():,}")
    print(f"  linea_nueva          {df['linea_nueva'].min():,.0f} a {df['linea_nueva'].max():,.0f}"
          f" | suma {df['linea_nueva'].sum():,.0f}")
    print(f"  clasificacion        {df['clasificacion'].value_counts().to_dict()}")
    print(f"  rutas                {df['ruta_preventa'].nunique()}"
          f" | oficinas {df['oficina_venta'].nunique()}"
          f" | supervisores {df['supervisor'].nunique()}")
    nulos = df.isna().sum()
    nulos = nulos[nulos > 0]
    if len(nulos):
        print(f"  nulos                {nulos.to_dict()}")


def run(archivo: str = ARCHIVO, dry_run: bool = False) -> None:
    print(f"Leyendo {archivo} (hoja '{HOJA}')...")
    df = leer(archivo)
    resumen(df)

    if dry_run:
        print("\n--dry-run: no se escribio nada.")
        return

    # DDL + TRUNCATE + carga en una transaccion, misma razon que en etl_redshift_to_postgres.py:
    # si el COPY falla, el TRUNCATE no se confirma y la tabla no se queda vacia.
    inicio, t0 = _ahora_mx(), time.time()
    with transaction(db=DB_RW) as tx:
        tx.execute_sql((BASE_DIR / "sql" / "13_bnpl_clientes_concurso.sql").read_text(
            encoding="utf-8"))
        tx.execute_sql(f'TRUNCATE {SCHEMA}."{TABLA}"')
        tx.load_dataframe(df, TABLA, schema=SCHEMA)
    # Fuera de la transaccion a proposito: la bitacora va a otro alias.
    _registrar(TABLA, len(df), time.time() - t0, inicio)

    print(f"\n-> {SCHEMA}.{TABLA}: {len(df):,} filas")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archivo", default=ARCHIVO, help="ruta del libro de Excel")
    parser.add_argument("--dry-run", action="store_true", help="valida sin escribir")
    args = parser.parse_args()
    run(archivo=args.archivo, dry_run=args.dry_run)

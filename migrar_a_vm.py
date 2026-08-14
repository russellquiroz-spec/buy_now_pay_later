"""DEPRECADO — la migracion que este script hacia ya ocurrio y su origen ya no existe.

Copiaba las tablas base de la base local (`postgres_local_extractor`, localhost:9558) a la
VM `rabbit-bi-local`. Hoy no queda ninguna de las dos mitades de esa operacion:

  * `postgres_local_extractor` fue sustituida por `postgres_local_client` y ya no se instala.
  * El PostgreSQL de origen en el 9558 no existe: el unico servicio es postgresql-x64-17 en
    localhost:9553, que sirve `rabbit-bi-local` — el DESTINO de esta migracion, no el origen.

Migrar sus imports a `postgres_local_client` haria que origen y destino fueran la misma base
y el script se copiaria encima de si mismo. Por eso se detiene aca en vez de traducirse.

El codigo queda como referencia de como se hizo la carga del 2026-08-12 (COPY por lotes,
`credit_order_production` por meses para no repetir los 2.5 GB de RAM). Si alguna vez hay
que mover datos entre dos bases distintas, se revive definiendo dos alias separados en
`.env.postgres_local_client` y pasando `db=` a cada llamada.

    python migrar_a_vm.py --ddl        solo aplica el DDL en la VM (schemas, tablas, indices)
    python migrar_a_vm.py --datos      solo copia los datos de las tablas base
    python migrar_a_vm.py --vistas     solo crea y materializa la capa de negocio
    python migrar_a_vm.py --validar    solo compara conteos origen vs destino
    python migrar_a_vm.py              todo, en ese orden

Lo que NO se copiaba y por que:
  * Las 11 vistas materializadas de `bnpl` (663 MB). Son datos derivados: se recrean desde los
    .sql y se materializan en la VM en ~1 minuto. Mandarlas por el tunel seria gastar ancho de
    banda en algo que se calcula solo.
  * `mongo_bnpl.fintech_pre_authorization_status` (0 filas): es la tabla del nombre de coleccion
    equivocado que la Fase 1 reemplazo por `..._production`.

`credit_order_production` se copia por meses: son 1.19M filas y 498 MB, y traerla entera a
pandas consumio 2.5 GB de RAM durante el ETL.
"""
raise SystemExit(__doc__.splitlines()[0])

import argparse
import time
from pathlib import Path

import pandas as pd
from postgres_local_client import execute_sql, extract_sql as vm_sql, load_dataframe
# El origen se leia con `from postgres_local_extractor import extract_sql as local_sql`.
# Esa libreria ya no existe y no tiene reemplazo: no queda una segunda base que leer.
local_sql = None

TIPOS_ENTEROS = ("bigint", "integer", "smallint")

BASE_DIR = Path(__file__).resolve().parent
SQL_DIR = BASE_DIR / "sql"
VM = "local_rw"

# DDL de las tablas base. El de la capa de negocio se aplica en el paso --vistas.
DDL_BASE = ["00_bnpl_ops.sql", "01_staging.sql", "12_redshift_staging.sql"]

# DDL y vistas materializadas de la capa de negocio, en orden de dependencia.
DDL_NEGOCIO = [
    ("02_bnpl_funciones.sql", []),
    ("11_bnpl_dim_ruta.sql", ["dim_ruta_actual", "dim_ruta_cliente_scd"]),
    ("03_bnpl_grouped_orders.sql", ["grouped_orders"]),
    ("04_bnpl_loss_rates.sql", ["loss_rates"]),
    ("05_bnpl_par_snapshot.sql", ["par_snapshot"]),
    ("06_bnpl_vintage_analysis.sql", ["vintage_analysis"]),
    ("07_bnpl_grid_bnpl.sql", ["grid_bnpl"]),
    ("08_bnpl_kpis_daily.sql", ["kpis_daily"]),
    ("09_bnpl_revenue_comision.sql", ["revenue_comision"]),
    ("10_bnpl_cortes_venta.sql", ["corte_venta_sku", "corte_venta_so"]),
]

# (schema, tabla, crear_con_replace). Todas existen ya por el DDL, asi que ninguna necesita
# que pandas la cree: el esquema del destino no depende de lo que pandas infiera.
TABLAS = [
    ("bnpl_ops", "source_freshness", False),
    ("bnpl_ops", "freshness_history", False),
    ("bnpl_ops", "data_quality_checks", False),
    ("bnpl_ops", "etl_runs", False),
    ("redshift_bnpl", "route_mapping", False),
    ("redshift_bnpl", "ruta_cliente_scd", False),
    ("redshift_bnpl", "estructura_comercial", False),
    ("mongo_bnpl", "fintech_credit_approval_production", False),
    ("mongo_bnpl", "fintech_credit_request_production", False),
    ("mongo_bnpl", "fintech_pre_authorization_status_production", False),
    ("mongo_bnpl", "state_of_delivery_report_production", False),
    ("mongo_bnpl", "payment_report_production", False),
    ("mongo_bnpl", "propaga_transaction", False),
    ("mongo_bnpl", "revenue_orders_production", False),
    ("mongo_bnpl", "credit_limit_history_management", False),
    ("mongo_bnpl", "fintech_customers_production", False),
    ("mongo_bnpl", "credit_order_production", False),  # por lotes
]

POR_LOTES = {"credit_order_production": "createdAt"}


def aplicar_ddl() -> None:
    print("== DDL de las tablas base ==")
    execute_sql("CREATE SCHEMA IF NOT EXISTS redshift_bnpl", db=VM)
    for archivo in DDL_BASE:
        t0 = time.time()
        execute_sql((SQL_DIR / archivo).read_text(encoding="utf-8"), db=VM)
        print(f"  {archivo}: aplicado ({time.time() - t0:.1f}s)")


def _lotes_por_mes(schema: str, tabla: str, columna: str) -> list:
    """Rangos de epoch ms, un lote por mes, mas uno para los nulos."""
    filas = local_sql(f"""
        select distinct
            (extract(epoch from date_trunc('month', to_timestamp("{columna}"/1000))) * 1000)::bigint as desde,
            (extract(epoch from date_trunc('month', to_timestamp("{columna}"/1000))
                     + interval '1 month') * 1000)::bigint as hasta
        from {schema}."{tabla}" where "{columna}" is not null
        order by 1
    """)
    return [(r["desde"], r["hasta"]) for _, r in filas.iterrows()]


def _columnas_enteras(schema: str, tabla: str) -> set:
    tipos = vm_sql(f"""
        select column_name, data_type from information_schema.columns
        where table_schema = '{schema}' and table_name = '{tabla}'
    """, db="local")
    return {r["column_name"] for _, r in tipos.iterrows() if r["data_type"] in TIPOS_ENTEROS}


def _ajustar_enteros(df: pd.DataFrame, enteros: set) -> pd.DataFrame:
    """Una columna entera con nulos llega a pandas como float64, y COPY rechaza '1110531.0'
    contra un bigint. Int64 (el entero nullable de pandas) serializa como entero o NULL."""
    for col in df.columns:
        if col in enteros and pd.api.types.is_float_dtype(df[col]):
            df[col] = df[col].astype("Int64")
    return df


def copiar_tabla(schema: str, tabla: str, crear: bool) -> int:
    origen = f'{schema}."{tabla}"'
    total_origen = int(local_sql(f"select count(*) as n from {origen}")["n"].iloc[0])
    t0 = time.time()

    # La tabla destino se vacia antes de cargar para que este paso sea re-ejecutable: sin esto,
    # un reintento tras un fallo a media copia duplicaria lo ya escrito.
    enteros = set()
    if not crear:
        execute_sql(f'TRUNCATE {schema}."{tabla}"', db=VM)
        enteros = _columnas_enteras(schema, tabla)

    if tabla in POR_LOTES:
        columna = POR_LOTES[tabla]
        lotes = _lotes_por_mes(schema, tabla, columna)
        escritas = 0
        for i, (desde, hasta) in enumerate(lotes, 1):
            df = local_sql(
                f'select * from {origen} where "{columna}" >= {desde} and "{columna}" < {hasta}'
            )
            if len(df):
                escritas += load_dataframe(
                    _ajustar_enteros(df, enteros), tabla, schema=schema, db=VM, if_exists="append"
                )
            print(f"    lote {i}/{len(lotes)}: {escritas:,}/{total_origen:,} filas", end="\r")
        # Las filas sin fecha no entran en ningun rango.
        df = local_sql(f'select * from {origen} where "{columna}" is null')
        if len(df):
            escritas += load_dataframe(
                _ajustar_enteros(df, enteros), tabla, schema=schema, db=VM, if_exists="append"
            )
        print()
    else:
        df = local_sql(f"select * from {origen}")
        if not len(df):
            print(f"  {origen}: 0 filas, se omite")
            return 0
        escritas = load_dataframe(
            _ajustar_enteros(df, enteros), tabla, schema=schema, db=VM,
            if_exists="replace" if crear else "append",
            confirm=crear,
        )

    segundos = time.time() - t0
    print(f"  {origen}: {escritas:,} filas en {segundos:.1f}s")
    return escritas


def copiar_datos() -> None:
    print("== Datos de las tablas base ==")
    t0 = time.time()
    total = sum(copiar_tabla(s, t, c) for s, t, c in TABLAS)
    print(f"  total: {total:,} filas en {(time.time() - t0) / 60:.1f} min")


def crear_vistas() -> None:
    print("== Capa de negocio en la VM ==")
    for archivo, vistas in DDL_NEGOCIO:
        t0 = time.time()
        execute_sql((SQL_DIR / archivo).read_text(encoding="utf-8"), db=VM)
        if not vistas:
            print(f"  {archivo}: aplicado ({time.time() - t0:.1f}s)")
            continue
        for vista in vistas:
            n = vm_sql(f"select count(*) as n from bnpl.{vista}", db="local")["n"].iloc[0]
            print(f"  bnpl.{vista}: {int(n):,} filas ({time.time() - t0:.1f}s)")


def validar() -> None:
    print("== Validacion: conteos origen vs VM ==")
    problemas = 0
    for schema, tabla, _ in TABLAS:
        o = int(local_sql(f'select count(*) as n from {schema}."{tabla}"')["n"].iloc[0])
        try:
            d = int(vm_sql(f'select count(*) as n from {schema}."{tabla}"', db="local")["n"].iloc[0])
        except Exception:
            d = -1
        marca = "ok" if o == d else "DIFERENTE"
        if o != d:
            problemas += 1
        print(f"  {schema}.{tabla:<45} origen {o:>9,}  vm {d:>9,}  {marca}")

    print("\n== Totales de control ==")
    for etiqueta, sql in [
        ("revenue Rabbit (con IVA)",
         "select round(sum(rabbit_revenue)::numeric, 2) as v from bnpl.revenue_comision where cobrado = 1"),
        ("clientes en el grid", "select count(*) as v from bnpl.grid_bnpl"),
        ("enrolados", "select sum(bnpl_is_enrolled) as v from bnpl.grid_bnpl"),
        ("ordenes con ruta",
         "select count(ruta) as v from bnpl.grouped_orders"),
    ]:
        o = local_sql(sql)["v"].iloc[0]
        try:
            d = vm_sql(sql, db="local")["v"].iloc[0]
        except Exception as ex:
            d = f"err: {type(ex).__name__}"
        marca = "ok" if str(o) == str(d) else "DIFERENTE"
        if str(o) != str(d):
            problemas += 1
        print(f"  {etiqueta:<28} origen {o}  vm {d}  {marca}")

    print(f"\n{'Migracion validada' if problemas == 0 else f'{problemas} diferencias'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migra los datos BNPL a la VM")
    parser.add_argument("--ddl", action="store_true")
    parser.add_argument("--datos", action="store_true")
    parser.add_argument("--vistas", action="store_true")
    parser.add_argument("--validar", action="store_true")
    args = parser.parse_args()
    todo = not (args.ddl or args.datos or args.vistas or args.validar)

    if args.ddl or todo:
        aplicar_ddl()
    if args.datos or todo:
        copiar_datos()
    if args.vistas or todo:
        crear_vistas()
    if args.validar or todo:
        validar()

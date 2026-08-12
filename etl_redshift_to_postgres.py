"""Extraccion Redshift -> staging PostgreSQL (schema redshift_bnpl).

Trae lo que BNPL necesita y no existe en Mongo: la estructura comercial (ruta, supervisor,
oficina) de cada cliente, en dos versiones.

  estructura_comercial   la ruta vigente hoy. Se trae completa (~611K filas): el grid necesita
                         ruta para todos los clientes, no solo los que tienen credito.
  route_mapping          catalogo de rutas -> equipo, oficina, region. Es el dim_ruta del
                         modelo estrella.
  ruta_cliente_scd       la ruta historica, como intervalos [valido_desde, valido_hasta].

El SCD se comprime EN Redshift, no aca: la vigencia diaria son 301M filas y para el universo
BNPL 5.3M, pero comprimida por cambio de ruta baja a ~13.6K. Traer 5.3M filas por el tunel para
comprimirlas despues seria absurdo.

Alcance del SCD: solo clientes con credito BNPL (con orden o aprobados). Para el resto no hay
analisis de riesgo que atribuir, y el IN de la consulta se mantiene manejable.
"""
import argparse
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from redshift_extractor import extract_sql
from sqlalchemy import create_engine, text

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
engine = create_engine(os.environ["BD_ENGINE_RABBIT_LOCAL"].strip("'\""))

SCHEMA = "redshift_bnpl"
OPS_SCHEMA = "bnpl_ops"
REDSHIFT_DB = "data-rabbit-prod"
TZ_OFFSET_HOURS = -6

SQL_ESTRUCTURA = """
select netsuite_id, tipo_cliente, status, ruta, ruta_canon, supervisor,
       oficina, oficina_canon, region, region_canon, pais, dia, frecuencia,
       fecha_inicio, data_source
from catalog.cat_estructura_comercial_v3
where netsuite_id is not null
"""

SQL_ROUTE_MAPPING = """
select ruta, equipo, oficina, region, pais
from catalog.route_mapping
where ruta is not null
"""

# La vigencia diaria comprimida a intervalos: una fila por tramo continuo con la misma ruta.
SQL_SCD = """
with base as (
    select netsuite_id, fecha::date as fecha, ruta, supervisor, oficina, region,
           tipo_cliente, status
    from catalog.cat_estructura_comercial_vigencia_diaria
    where netsuite_id in ({ids})
      and ruta is not null
),
marcado as (
    select b.*, lag(ruta) over (partition by netsuite_id order by fecha) as ruta_prev
    from base b
),
cambios as (
    select m.*,
           case when ruta_prev is null or ruta <> ruta_prev then 1 else 0 end as es_cambio
    from marcado m
),
grupos as (
    select c.*,
           sum(es_cambio) over (
               partition by netsuite_id order by fecha
               rows between unbounded preceding and current row
           ) as tramo
    from cambios c
)
select netsuite_id,
       ruta,
       max(supervisor)   as supervisor,
       max(oficina)      as oficina,
       max(region)       as region,
       max(tipo_cliente) as tipo_cliente,
       max(status)       as status,
       min(fecha)        as valido_desde,
       max(fecha)        as valido_hasta,
       count(*)          as dias_vigencia
from grupos
group by netsuite_id, ruta, tramo
"""


def _ahora_mx() -> datetime:
    return (datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)).replace(tzinfo=None)


def _universo_bnpl() -> list:
    """Clientes con credito: con al menos una orden o con aprobacion."""
    with engine.connect() as conn:
        filas = conn.execute(text("""
            select distinct netsuite_id from bnpl.grouped_orders
            where netsuite_id is not null
            union
            select distinct "netsuiteId" from mongo_bnpl.fintech_credit_approval_production
            where "netsuiteId" is not null
        """)).fetchall()
    return [f[0].strip() for f in filas if f[0] and f[0].strip()]


def _cargar(nombre: str, df: pd.DataFrame, inicio, segundos: float) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    df.to_sql(nombre, engine, schema=SCHEMA, if_exists="replace", index=False)
    with engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {OPS_SCHEMA}.etl_runs (started_at, tabla, modo, filas, segundos) "
                f"VALUES (:inicio, :tabla, 'full', :filas, :segundos) "
                f"ON CONFLICT (started_at, tabla) DO NOTHING"
            ),
            {
                "inicio": inicio,
                "tabla": f"{SCHEMA}.{nombre}",
                "filas": len(df),
                "segundos": round(segundos, 1),
            },
        )
    print(f"  -> {SCHEMA}.{nombre}: {len(df):,} filas en {segundos:.1f}s")


def run(solo: list = None) -> None:
    tablas = solo or ["estructura_comercial", "route_mapping", "ruta_cliente_scd"]

    if "estructura_comercial" in tablas:
        print("Extrayendo estructura comercial (ruta vigente)...")
        inicio, t0 = _ahora_mx(), time.time()
        df = extract_sql(REDSHIFT_DB, SQL_ESTRUCTURA)
        df["netsuite_id"] = df["netsuite_id"].astype(str).str.strip()
        _cargar("estructura_comercial", df, inicio, time.time() - t0)

    if "route_mapping" in tablas:
        print("Extrayendo catalogo de rutas...")
        inicio, t0 = _ahora_mx(), time.time()
        df = extract_sql(REDSHIFT_DB, SQL_ROUTE_MAPPING)
        _cargar("route_mapping", df, inicio, time.time() - t0)

    if "ruta_cliente_scd" in tablas:
        universo = _universo_bnpl()
        print(f"Extrayendo ruta historica de {len(universo):,} clientes con credito...")
        inicio, t0 = _ahora_mx(), time.time()
        lista = ",".join(f"'{i}'" for i in universo)
        df = extract_sql(REDSHIFT_DB, SQL_SCD.format(ids=lista))
        df["netsuite_id"] = df["netsuite_id"].astype(str).str.strip()
        _cargar("ruta_cliente_scd", df, inicio, time.time() - t0)

    engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carga la estructura comercial desde Redshift")
    parser.add_argument("--solo", help="tablas a cargar, separadas por coma")
    args = parser.parse_args()
    run(solo=args.solo.split(",") if args.solo else None)

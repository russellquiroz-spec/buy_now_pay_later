"""Viabilidad de una dim de ruta historica (SCD) para el universo BNPL."""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from redshift_extractor import extract_sql

DB = "data-rabbit-prod"
load_dotenv(".env")
pg = create_engine(os.environ["BD_ENGINE_RABBIT_LOCAL"].strip("'\""))

with pg.connect() as c:
    rango = c.execute(text("""
        select to_timestamp(min("createdAt")/1000)::date as primera_orden,
               to_timestamp(max("createdAt")/1000)::date as ultima_orden,
               count(*) as filas
        from mongo_bnpl.credit_order_production
    """)).fetchone()
    print(f"ordenes BNPL en staging: {rango.primera_orden} -> {rango.ultima_orden} ({rango.filas} filas)")

    porano = c.execute(text("""
        select extract(year from to_timestamp("createdAt"/1000)) as anio,
               count(distinct "salesOrderId") as sos
        from mongo_bnpl.credit_order_production
        group by 1 order by 1
    """)).fetchall()
    print("SOs por año:", {int(r.anio): r.sos for r in porano})

    ids = [r[0] for r in c.execute(text("""
        select distinct "netsuiteId" from mongo_bnpl.fintech_credit_approval_production
        where "netsuiteId" is not null
    """)).fetchall()]

lista = ",".join(f"'{i}'" for i in ids)

print("\n=== vigencia_diaria: cobertura del universo BNPL ===")
print(extract_sql(DB, f"""
    select min(fecha) as desde, max(fecha) as hasta,
           count(distinct netsuite_id) as clientes, count(*) as filas
    from catalog.cat_estructura_comercial_vigencia_diaria
    where netsuite_id in ({lista})
""").to_string())

print("\n=== tamaño de la dim comprimida (SCD por cambio de ruta) ===")
print(extract_sql(DB, f"""
    with base as (
        select netsuite_id, fecha::date as fecha, ruta, supervisor, oficina, region
        from catalog.cat_estructura_comercial_vigencia_diaria
        where netsuite_id in ({lista})
    ),
    marcado as (
        select b.*,
               lag(ruta) over (partition by netsuite_id order by fecha) as ruta_prev
        from base b
    )
    select count(*) as filas_scd, count(distinct netsuite_id) as clientes
    from marcado
    where ruta_prev is null or ruta <> ruta_prev
""").to_string())

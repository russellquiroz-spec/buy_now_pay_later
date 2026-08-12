"""Cobertura de rutas en Redshift para el universo BNPL."""
import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from redshift_extractor import extract_sql

DB = "data-rabbit-prod"
load_dotenv(".env")
pg = create_engine(os.environ["BD_ENGINE_RABBIT_LOCAL"].strip("'\""))

with pg.connect() as c:
    ids = [r[0] for r in c.execute(text("""
        select distinct "netsuiteId" from mongo_bnpl.fintech_credit_approval_production
        where "netsuiteId" is not null
    """)).fetchall()]
print(f"clientes BNPL aprobados: {len(ids)}")

print("\n=== columnas cat_estructura_comercial_v3 ===")
print(extract_sql(DB, """
    select column_name from svv_columns
    where table_schema='catalog' and table_name='cat_estructura_comercial_v3'
    order by ordinal_position
""")["column_name"].tolist())

print("\n=== columnas route_mapping ===")
print(extract_sql(DB, """
    select column_name from svv_columns
    where table_schema='catalog' and table_name='route_mapping'
    order by ordinal_position
""")["column_name"].tolist())

lista = ",".join(f"'{i}'" for i in ids)
q = f"""
select count(distinct e.netsuite_id) as con_ruta,
       count(distinct case when r.ruta is not null then e.netsuite_id end) as con_supervisor
from catalog.cat_estructura_comercial_v3 e
left join catalog.route_mapping r on e.ruta = r.ruta
where e.netsuite_id::text in ({lista})
"""
print("\n=== cobertura ===")
print(extract_sql(DB, q).to_string())

print("\n=== muestra ===")
q2 = f"""
select e.netsuite_id, e.ruta, e.supervisor, e.oficina, r.equipo, r.oficina as oficina_rm, r.region
from catalog.cat_estructura_comercial_v3 e
left join catalog.route_mapping r on e.ruta = r.ruta
where e.netsuite_id::text in ({lista})
limit 5
"""
print(extract_sql(DB, q2).to_string())

"""Cuanto pesaria cada ventana de reproceso en credit-order."""
from postgres_local_client import extract_sql

DB = "mongo_bnpl"  # alias de solo lectura sobre el staging

FINALES = "('COMPLETED', 'REJECTED', 'CANCELLED', 'NO_VISITED')"

print("=== peso de la ventana por dias ===")
print(extract_sql(f"""
    select
        d.dias,
        count(*) filter (where c."createdAt" >= (extract(epoch from now() - (d.dias || ' days')::interval) * 1000)) as lineas_en_ventana,
        round(100.0 * count(*) filter (where c."createdAt" >= (extract(epoch from now() - (d.dias || ' days')::interval) * 1000)) / count(*), 1) as pct_del_total
    from mongo_bnpl.credit_order_production c
    cross join (values (15), (30), (45), (60), (90)) as d(dias)
    group by d.dias order by d.dias
""", db=DB).to_string(index=False))

print("\n=== ordenes en estado NO final fuera de la ventana de 60d (habria que refrescarlas aparte) ===")
print(extract_sql(f"""
    select "orderStatus", count(*) as lineas, count(distinct "salesOrderId") as sos
    from mongo_bnpl.credit_order_production
    where "orderStatus" not in {FINALES}
      and "createdAt" < (extract(epoch from now() - interval '60 days') * 1000)
    group by 1 order by 2 desc
""", db=DB).to_string(index=False))

print("\n=== y cuantas quedarian congeladas (estado final + fuera de la ventana) ===")
print(extract_sql(f"""
    select count(*) as lineas_congelables,
           round(100.0 * count(*) / (select count(*) from mongo_bnpl.credit_order_production), 1) as pct
    from mongo_bnpl.credit_order_production
    where "orderStatus" in {FINALES}
      and "createdAt" < (extract(epoch from now() - interval '60 days') * 1000)
""", db=DB).to_string(index=False))

print("\n=== tamano en disco del staging ===")
print(extract_sql("""
    select table_name,
           pg_size_pretty(pg_total_relation_size(('mongo_bnpl.' || quote_ident(table_name))::regclass)) as tamano
    from information_schema.tables
    where table_schema = 'mongo_bnpl'
    order by pg_total_relation_size(('mongo_bnpl.' || quote_ident(table_name))::regclass) desc
""", db=DB).to_string(index=False))

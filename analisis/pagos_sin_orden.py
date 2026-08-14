from postgres_local_client import extract_sql

DB = "mongo_bnpl"  # alias de solo lectura sobre el staging

print("=== los 276 pagos sin orden: por año y estado ===")
print(extract_sql("""
    select extract(year from to_timestamp(p."movementDate"/1000)) as anio,
           p."transactionStatus", count(*) as n, round(sum(p."totalAmount")::numeric, 2) as monto
    from mongo_bnpl.payment_report_production p
    left join (select distinct "salesOrderId" from mongo_bnpl.credit_order_production) o
           on p."transactionId" = o."salesOrderId"
    where o."salesOrderId" is null
    group by 1, 2 order by 1, 3 desc
""", db=DB).to_string(index=False))

print("\n=== muestra de transactionId ===")
print(extract_sql("""
    select p."transactionId", p."clientId", p."transactionStatus",
           to_timestamp(p."movementDate"/1000)::date as movimiento, p."totalAmount"
    from mongo_bnpl.payment_report_production p
    left join (select distinct "salesOrderId" from mongo_bnpl.credit_order_production) o
           on p."transactionId" = o."salesOrderId"
    where o."salesOrderId" is null
    order by p."movementDate" desc limit 8
""", db=DB).to_string(index=False))

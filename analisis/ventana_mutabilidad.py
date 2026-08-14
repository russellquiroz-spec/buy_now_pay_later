"""Cuanto tiempo despues de creado sigue cambiando un documento, por tabla."""
from postgres_local_client import extract_sql

DB = "mongo_bnpl"  # alias de solo lectura sobre el staging

print("=" * 78)
print("1. credit-order: dias entre createdAt y deliveryAt")
print(extract_sql("""
    with d as (
        select (("deliveryAt" - "createdAt") / 86400000.0) as dias
        from mongo_bnpl.credit_order_production
        where "deliveryAt" is not null and "createdAt" is not null
    )
    select count(*) as filas,
           round(percentile_cont(0.50) within group (order by dias)::numeric, 1) as p50,
           round(percentile_cont(0.95) within group (order by dias)::numeric, 1) as p95,
           round(percentile_cont(0.99) within group (order by dias)::numeric, 1) as p99,
           round(percentile_cont(0.9999) within group (order by dias)::numeric, 1) as p9999,
           round(max(dias)::numeric, 1) as maximo
    from d where dias >= 0
""", db=DB).to_string(index=False))

print("\n" + "=" * 78)
print("2. credit-order: estados no finales por antiguedad (los que aun pueden cambiar)")
print(extract_sql("""
    select "orderStatus",
           count(*) as filas,
           min(to_timestamp("createdAt"/1000)::date) as mas_antigua,
           max(to_timestamp("createdAt"/1000)::date) as mas_reciente,
           sum(case when "createdAt" < (extract(epoch from now() - interval '60 days') * 1000)
                    then 1 else 0 end) as con_mas_de_60d
    from mongo_bnpl.credit_order_production
    group by 1 order by 2 desc
""", db=DB).to_string(index=False))

print("\n" + "=" * 78)
print("3. payment-report: dias entre movementDate y el pago efectivo (paymentDateFromPaid)")
print(extract_sql("""
    with d as (
        select (nullif("paymentDateFromPaid", 'No Information')::timestamp
                - to_timestamp("movementDate"/1000)::timestamp) as delta
        from mongo_bnpl.payment_report_production
        where "paymentDateFromPaid" is not null
          and "paymentDateFromPaid" <> 'No Information'
          and "movementDate" is not null
    )
    select count(*) as filas,
           round(percentile_cont(0.50) within group (order by extract(epoch from delta)/86400)::numeric, 1) as p50,
           round(percentile_cont(0.95) within group (order by extract(epoch from delta)/86400)::numeric, 1) as p95,
           round(percentile_cont(0.99) within group (order by extract(epoch from delta)/86400)::numeric, 1) as p99,
           round(percentile_cont(0.9999) within group (order by extract(epoch from delta)/86400)::numeric, 1) as p9999,
           round((max(extract(epoch from delta))/86400)::numeric, 1) as maximo
    from d
""", db=DB).to_string(index=False))

print("\n" + "=" * 78)
print("4. payment-report: estados no finales por antiguedad")
print(extract_sql("""
    select "transactionStatus",
           count(*) as filas,
           min(to_timestamp("movementDate"/1000)::date) as mas_antiguo,
           sum(case when "movementDate" < (extract(epoch from now() - interval '60 days') * 1000)
                    then 1 else 0 end) as con_mas_de_60d
    from mongo_bnpl.payment_report_production
    group by 1 order by 2 desc
""", db=DB).to_string(index=False))

print("\n" + "=" * 78)
print("5. propaga-transaction: dias entre createdAt y updatedAt (mutabilidad directa)")
print(extract_sql("""
    with d as (
        select extract(epoch from ("updatedAt"::timestamp - "createdAt"::timestamp))/86400 as dias
        from mongo_bnpl.propaga_transaction
        where "updatedAt" is not null and "createdAt" is not null
    )
    select count(*) as filas,
           sum(case when dias > 1 then 1 else 0 end) as cambian_tras_1d,
           sum(case when dias > 30 then 1 else 0 end) as cambian_tras_30d,
           sum(case when dias > 60 then 1 else 0 end) as cambian_tras_60d,
           sum(case when dias > 90 then 1 else 0 end) as cambian_tras_90d,
           round(percentile_cont(0.99) within group (order by dias)::numeric, 1) as p99,
           round(max(dias)::numeric, 1) as maximo
    from d
""", db=DB).to_string(index=False))

print("\n" + "=" * 78)
print("6. credit-limit-history: antiguedad de la ultima actualizacion de linea")
print(extract_sql("""
    select count(*) as filas,
           min(to_timestamp("creditLimitUpdateDate"/1000)::date) as mas_antiguo,
           max(to_timestamp("creditLimitUpdateDate"/1000)::date) as mas_reciente,
           sum(case when "creditLimitUpdateDate" >= (extract(epoch from now() - interval '60 days') * 1000)
                    then 1 else 0 end) as actualizados_ultimos_60d
    from mongo_bnpl.credit_limit_history_management
""", db=DB).to_string(index=False))

print("\n" + "=" * 78)
print("7. Volumen por año: cuanto pesa el historico congelable")
print(extract_sql("""
    select extract(year from to_timestamp("createdAt"/1000)) as anio,
           count(*) as lineas_sku,
           count(distinct "salesOrderId") as sos
    from mongo_bnpl.credit_order_production
    group by 1 order by 1
""", db=DB).to_string(index=False))

from postgres_local_client import extract_sql

DB = "mongo_bnpl"  # alias de solo lectura sobre el staging

print("=== los 276 huerfanos: se rescatan por marketplaceOrderId = credit_order.orderId? ===")
print(extract_sql("""
    with huerfanos as (
        select p.*
        from mongo_bnpl.payment_report_production p
        left join (select distinct "salesOrderId" from mongo_bnpl.credit_order_production) o
               on p."transactionId" = o."salesOrderId"
        where o."salesOrderId" is null
    )
    select
        count(*)                                                          as huerfanos,
        count(distinct h."transactionId")                                 as ids_distintos,
        sum(case when o2."orderId" is not null then 1 else 0 end)         as rescatados_por_orderId,
        sum(case when o2."orderId" is null then 1 else 0 end)             as siguen_sin_orden
    from huerfanos h
    left join (select distinct "orderId" from mongo_bnpl.credit_order_production) o2
           on h."marketplaceOrderId" = o2."orderId"
""", db=DB).to_string(index=False))

print("\n=== y si la llave fuera transactionId contra orderId? ===")
print(extract_sql("""
    with huerfanos as (
        select p.*
        from mongo_bnpl.payment_report_production p
        left join (select distinct "salesOrderId" from mongo_bnpl.credit_order_production) o
               on p."transactionId" = o."salesOrderId"
        where o."salesOrderId" is null
    )
    select sum(case when o2."orderId" is not null then 1 else 0 end) as rescatados,
           count(*) as total
    from huerfanos h
    left join (select distinct "orderId" from mongo_bnpl.credit_order_production) o2
           on h."transactionId" = o2."orderId"
""", db=DB).to_string(index=False))

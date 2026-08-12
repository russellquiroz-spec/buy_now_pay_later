"""Unicidad de las llaves candidatas: decide PK vs indice."""
from postgres_local_extractor import extract_sql

CANDIDATAS = [
    ("credit_order_production", '"salesOrderId", "productId"'),
    ("payment_report_production", '"transactionId"'),
    ("payment_report_production", '"creditId"'),
    ("fintech_customers_production", '"netsuiteId"'),
    ("fintech_customers_production", '"customerId"'),
    ("fintech_credit_approval_production", '"netsuiteId"'),
    ("fintech_credit_request_production", '"customerId"'),
    ("fintech_credit_request_production", '"requestId"'),
    ("fintech_pre_authorization_status_production", '"netsuiteId"'),
    ("fintech_pre_authorization_status_production", '"preAuthorizationId"'),
    ("state_of_delivery_report_production", '"salesOrderId"'),
    ("propaga_transaction", '"id"'),
    ("propaga_transaction", '"salesOrderId"'),
    ("revenue_orders_production", '"transactionId"'),
    ("credit_limit_history_management", '"netsuiteId"'),
    ("credit_limit_history_management", '"customerId"'),
]

for tabla, llave in CANDIDATAS:
    cols = [c.strip().strip('"') for c in llave.split(",")]
    nulos = " or ".join(f'"{c}" is null' for c in cols)
    r = extract_sql(f"""
        select count(*) as total,
               count(*) filter (where {nulos}) as con_nulo,
               (select count(*) from (
                    select {llave} from mongo_bnpl."{tabla}"
                    where not ({nulos})
                    group by {llave} having count(*) > 1
               ) d) as claves_repetidas
        from mongo_bnpl."{tabla}"
    """).iloc[0]
    veredicto = (
        "PK" if r["con_nulo"] == 0 and r["claves_repetidas"] == 0
        else f"indice (nulos={r['con_nulo']:,}, repetidas={r['claves_repetidas']:,})"
    )
    print(f"{tabla}.{llave:<38} {r['total']:>10,}  -> {veredicto}")

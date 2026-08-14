"""Chequeos de calidad sobre el staging BNPL.

Un chequeo cuya tabla o columna no existe se registra como NO_APLICABLE en vez de fallar:
eso deja visible que a la extraccion le falta un campo.
"""
from datetime import datetime, timedelta, timezone

from postgres_local_client import extract_sql, transaction

from config import DB_OPS_RW, DB_STAGING, STAGING_SCHEMA, TZ_OFFSET_HOURS

S = STAGING_SCHEMA

CHECKS = [
    {
        "name": "credit_order_sales_order_id_nulo",
        "tabla": "credit_order_production",
        "requiere": ["salesOrderId"],
        "severidad": "CRIT",
        "detalle": "Ordenes sin salesOrderId: no se agrupan ni se unen con delivery",
        "sql": f"""select count(*) as n from {S}."credit_order_production"
                   where "salesOrderId" is null or trim("salesOrderId") = ''""",
    },
    {
        "name": "credit_order_delivery_at_nulo",
        "tabla": "credit_order_production",
        "requiere": ["deliveryAt", "orderStatus"],
        "severidad": "CRIT",
        "detalle": "Ordenes COMPLETED sin deliveryAt: no se puede derivar expectedPaymentDate",
        "sql": f"""select count(*) as n from {S}."credit_order_production"
                   where "orderStatus" = 'COMPLETED' and "deliveryAt" is null""",
    },
    {
        "name": "credit_order_sales_order_id_multi_cliente",
        "tabla": "credit_order_production",
        "requiere": ["salesOrderId", "netsuiteId"],
        "severidad": "WARN",
        "detalle": "Un salesOrderId asignado a mas de un netsuiteId",
        "sql": f"""select count(*) as n from (
                       select "salesOrderId" from {S}."credit_order_production"
                       where "salesOrderId" is not null and trim("salesOrderId") <> ''
                       group by 1 having count(distinct "netsuiteId") > 1
                   ) t""",
    },
    {
        "name": "approval_netsuite_id_duplicado",
        "tabla": "fintech_credit_approval_production",
        "requiere": ["netsuiteId"],
        "severidad": "WARN",
        "detalle": "Cliente con mas de una aprobacion: grid_bnpl debe quedarse con una",
        "sql": f"""select count(*) as n from (
                       select "netsuiteId" from {S}."fintech_credit_approval_production"
                       group by 1 having count(*) > 1
                   ) t""",
    },
    {
        "name": "aprobados_sin_customer",
        "tabla": "fintech_credit_approval_production",
        "requiere": ["netsuiteId"],
        "severidad": "WARN",
        "detalle": "Clientes aprobados sin registro en fintech-customers: grid_bnpl queda sin shopName",
        "sql": f"""select count(*) as n
                   from {S}."fintech_credit_approval_production" a
                   left join {S}."fintech_customers_production" c
                          on a."netsuiteId" = c."netsuiteId"
                   where c."netsuiteId" is null""",
    },
    {
        "name": "payment_report_transaction_id_duplicado",
        "tabla": "payment_report_production",
        "requiere": ["transactionId"],
        "severidad": "WARN",
        "detalle": "Transaccion repetida en payment-report: duplica el revenue",
        "sql": f"""select count(*) as n from (
                       select "transactionId" from {S}."payment_report_production"
                       where "transactionId" is not null
                       group by 1 having count(*) > 1
                   ) t""",
    },
    {
        "name": "ordenes_sin_delivery",
        "tabla": "state_of_delivery_report_production",
        "requiere": ["salesOrderId"],
        "severidad": "WARN",
        "detalle": "Ordenes COMPLETED sin registro en state-of-delivery",
        "sql": f"""select count(distinct o."salesOrderId") as n
                   from {S}."credit_order_production" o
                   left join {S}."state_of_delivery_report_production" d
                          on o."salesOrderId" = d."salesOrderId"
                   where o."orderStatus" = 'COMPLETED' and d."salesOrderId" is null""",
    },
    {
        "name": "pagos_sin_orden",
        "tabla": "payment_report_production",
        "requiere": ["transactionId"],
        "severidad": "WARN",
        "detalle": "Pagos cuya transaccion no existe en credit-order",
        "sql": f"""select count(*) as n
                   from {S}."payment_report_production" p
                   left join (select distinct "salesOrderId" from {S}."credit_order_production") o
                          on p."transactionId" = o."salesOrderId"
                   where o."salesOrderId" is null""",
    },
]


def _ahora_mx() -> datetime:
    return (datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)).replace(tzinfo=None)


def _columnas_por_tabla() -> dict:
    df = extract_sql(f"""
        select table_name, column_name
        from information_schema.columns
        where table_schema = '{S}'
    """, db=DB_STAGING)
    return {tabla: set(g["column_name"]) for tabla, g in df.groupby("table_name")}


def correr_checks() -> list:
    existentes = _columnas_por_tabla()
    checked_at = _ahora_mx()
    filas = []

    for check in CHECKS:
        tabla = check["tabla"]
        faltantes = [c for c in check["requiere"] if c not in existentes.get(tabla, set())]
        if faltantes:
            filas.append({
                "checked_at": checked_at,
                "check_name": check["name"],
                "tabla": tabla,
                "n_filas": None,
                "severidad": check["severidad"],
                "resultado": "NO_APLICABLE",
                "detalle": f"falta en staging: {', '.join(faltantes)}",
            })
            continue

        n = int(extract_sql(check["sql"], db=DB_STAGING)["n"].iloc[0])
        filas.append({
            "checked_at": checked_at,
            "check_name": check["name"],
            "tabla": tabla,
            "n_filas": n,
            "severidad": check["severidad"],
            "resultado": "OK" if n == 0 else "ALERTA",
            "detalle": check["detalle"],
        })
    return filas


def persistir(filas: list) -> None:
    cols = ["checked_at", "check_name", "tabla", "n_filas", "severidad", "resultado", "detalle"]
    sql = (
        f"INSERT INTO bnpl_ops.data_quality_checks ({', '.join(cols)}) "
        f"VALUES ({', '.join(':' + c for c in cols)}) "
        f"ON CONFLICT (checked_at, check_name) DO NOTHING"
    )
    # Fila por fila dentro de una transaccion: execute_sql no tiene executemany y el
    # DO NOTHING descarta upsert_dataframe, que siempre genera DO UPDATE.
    with transaction(db=DB_OPS_RW) as tx:
        for fila in filas:
            tx.execute_sql(sql, {c: fila[c] for c in cols})


def run() -> list:
    filas = correr_checks()
    persistir(filas)

    print(f"\n{'check':<45} {'filas':>10} {'resultado':>13} {'sev':>5}")
    for f in filas:
        n = f"{f['n_filas']:,}" if f["n_filas"] is not None else "-"
        print(f"{f['check_name']:<45} {n:>10} {f['resultado']:>13} {f['severidad']:>5}")
        if f["resultado"] == "NO_APLICABLE":
            print(f"    -> {f['detalle']}")
    return filas


if __name__ == "__main__":
    run()

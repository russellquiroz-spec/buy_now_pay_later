"""Chequeos de calidad sobre el staging BNPL.

Un chequeo cuya tabla o columna no existe se registra como NO_APLICABLE en vez de fallar:
eso deja visible que a la extraccion le falta un campo.
"""
from datetime import datetime, timedelta, timezone

from postgres_local_client import extract_sql, transaction

from config import DB_BNPL, DB_OPS, DB_OPS_RW, DB_STAGING, STAGING_SCHEMA, TZ_OFFSET_HOURS

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
    {
        "name": "cargas_manuales_viejas",
        "tabla": "etl_runs",
        "requiere": [],   # no depende de columnas del staging
        "db": DB_OPS,
        "severidad": "WARN",
        "detalle": "Carga manual sin correr en 90 dias (o sin registro en etl_runs)",
        "sql": """select count(*) as n from (
                       select t.tabla,
                              (select max(started_at) from bnpl_ops.etl_runs r
                                where r.tabla = t.tabla) as ultima
                       from (values ('archivos_bnpl.odds_combinations'),
                                    ('archivos_bnpl.atr_combinations_iv'),
                                    ('archivos_bnpl.ps_transactional_profile'),
                                    ('archivos_bnpl.bnpl_cac'),
                                    ('bnpl.bnpl_clientes_concurso')) as t(tabla)
                   ) x
                   where ultima is null or ultima < current_date - 90""",
    },
]


# ── Identidades entre capas ──────────────────────────────────────────────────
#
# Cada fila es un conteo que DEBE cumplirse: destino = origen * factor + delta. Si no se cumple,
# algo se quedo a medias entre dos capas y el tablero va a leer una mitad vieja.
#
# Estaban en README.md:404-435 como un bloque de SQL para copiar y pegar a mano. Un check que
# depende de que alguien se acuerde de correrlo no es un check. Aqui corren en cada pipeline y
# quedan en bnpl_ops.data_quality_checks con su historia.
#
# CRIT = si no cuadra, hay una capa incompleta y el resultado no sirve.
# WARN = el delta es real y esperado pero puede moverse (grid_bnpl) o el origen es carga manual
#        y desfasarse es normal hasta que alguien recargue (los cuatro de archivos_bnpl).
#
#              nombre                    origen                                   destino                                factor delta  sev
IDENTIDADES = [
    ("grouped_orders",           "bnpl.grouped_orders",                    "pbi_bnpl.bnpl_grouped_orders",           1,    0, "CRIT"),
    ("loss_rates",               "bnpl.loss_rates",                        "pbi_bnpl.bnpl_loss_rates",               1,    0, "CRIT"),
    ("revenue_comision",         "bnpl.loss_rates",                        "bnpl.revenue_comision",                  1,    0, "CRIT"),
    ("bnpl_par",                 "bnpl.par_snapshot",                      "pbi_bnpl.bnpl_par",                      1,    0, "CRIT"),
    ("months_closes",            "bnpl.par_snapshot",                      "pbi_bnpl.months_closes",                 1,    0, "CRIT"),
    ("vintage_analysis",         "bnpl.vintage_analysis",                  "pbi_bnpl.vintage_analysis",              1,    0, "CRIT"),
    ("grid_bnpl",                "bnpl.grid_bnpl",                         "pbi_bnpl.grid_bnpl",                     1,  -71, "WARN"),
    ("dim_ruta_actual",          "redshift_bnpl.estructura_comercial",     "bnpl.dim_ruta_actual",                   1,    0, "CRIT"),
    ("dim_ruta_cliente_scd",     "redshift_bnpl.ruta_cliente_scd",         "bnpl.dim_ruta_cliente_scd",              1,    0, "CRIT"),
    ("cosechas_agg",             "redshift_bnpl.cosechas_agg",             "pbi_bnpl.bnpl_cosechas_agg",             1,    0, "CRIT"),
    ("seasonality_delta",        "redshift_bnpl.estacionalidad_mes",       "pbi_bnpl.seasonality_delta",            11,    0, "CRIT"),
    ("odds_combinations",        "archivos_bnpl.odds_combinations",        "pbi_bnpl.odds_combinations",             1,    0, "WARN"),
    ("atr_combinations_iv",      "archivos_bnpl.atr_combinations_iv",      "pbi_bnpl.atr_combinations_iv",           1,    0, "WARN"),
    ("ps_transactional_profile", "archivos_bnpl.ps_transactional_profile", "pbi_bnpl.ps_transactional_profile",      1,    0, "WARN"),
    ("bnpl_cac",                 "archivos_bnpl.bnpl_cac",                 "pbi_bnpl.bnpl_cac",                      1,    0, "WARN"),
]

CHECKS += [
    {
        "name": f"identidad_{nombre}",
        "tabla": destino,
        "requiere": [],          # no aplica: la guarda de columnas mira solo el staging
        "db": DB_BNPL,
        "severidad": severidad,
        "detalle": f"count({destino}) debe ser count({origen}) * {factor} {delta:+d}",
        # n = filas de mas o de menos. 0 = la identidad se cumple.
        "sql": f"""select abs(
                       (select count(*) from {destino})
                       - ((select count(*) from {origen}) * {factor} + ({delta}))
                   )::bigint as n""",
    }
    for nombre, origen, destino, factor, delta, severidad in IDENTIDADES
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

        # Cada check declara contra que alias corre; los del staging no declaran nada y siguen
        # cayendo en DB_STAGING, igual que antes.
        try:
            n = int(extract_sql(check["sql"], db=check.get("db", DB_STAGING))["n"].iloc[0])
        except Exception as e:
            # Misma semantica que la guarda de columnas: una relacion que no existe se registra
            # como NO_APLICABLE y queda visible, en vez de tumbar los otros checks.
            filas.append({
                "checked_at": checked_at,
                "check_name": check["name"],
                "tabla": tabla,
                "n_filas": None,
                "severidad": check["severidad"],
                "resultado": "NO_APLICABLE",
                "detalle": str(e).splitlines()[0][:200],
            })
            continue

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

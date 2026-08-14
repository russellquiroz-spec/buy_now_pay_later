"""Tipos que infirio pandas en el staging, e indices existentes."""
from postgres_local_client import extract_sql

DB = "mongo_bnpl"  # alias de solo lectura sobre el staging

print("=== tipos por tabla ===")
df = extract_sql("""
    select table_name, column_name, data_type
    from information_schema.columns
    where table_schema = 'mongo_bnpl'
    order by table_name, ordinal_position
""", db=DB)
for tabla, g in df.groupby("table_name"):
    print(f"\n{tabla}")
    for _, r in g.iterrows():
        print(f"   {r['column_name']:<34} {r['data_type']}")

print("\n=== indices existentes en mongo_bnpl ===")
print(extract_sql("""
    select tablename, indexname, indexdef
    from pg_indexes where schemaname = 'mongo_bnpl'
""", db=DB).to_string(index=False))

print("\n=== columnas de texto que en realidad son fechas ISO ===")
for tabla, col in [
    ("payment_report_production", "paymentDateFromToPay"),
    ("payment_report_production", "paymentDateFromPaid"),
    ("fintech_credit_approval_production", "createdAt"),
    ("propaga_transaction", "createdAt"),
    ("propaga_transaction", "paidDate"),
    ("fintech_pre_authorization_status_production", "authorizationDate"),
]:
    try:
        r = extract_sql(f"""
            select count(*) as total,
                   count("{col}") as no_nulos,
                   min("{col}") as minimo, max("{col}") as maximo
            from mongo_bnpl."{tabla}"
        """, db=DB).iloc[0]
        print(f"{tabla}.{col}: {r['no_nulos']:,}/{r['total']:,} | {r['minimo']} .. {r['maximo']}")
    except Exception as ex:
        print(f"{tabla}.{col}: err {type(ex).__name__}")

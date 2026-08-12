"""Columnas y frescura de los candidatos de dimension de rutas."""
from redshift_extractor import extract_sql

DB = "data-rabbit-prod"
CANDIDATOS = [
    ("analytics", "cat_clientes_manejantes"),
    ("catalog", "catalog_clientes_current"),
    ("catalog", "route_mapping"),
    ("catalog", "cat_estructura_comercial_v3"),
]

for schema, table in CANDIDATOS:
    print(f"\n{'='*70}\n{schema}.{table}")
    q = f"""
    select column_name, data_type
    from svv_columns
    where table_schema = '{schema}' and table_name = '{table}'
    order by ordinal_position
    """
    try:
        cols = extract_sql(DB, q)
        print(", ".join(cols["column_name"].tolist()))
        n = extract_sql(DB, f"select count(*) as n from {schema}.{table}")
        print(f"filas: {n['n'].iloc[0]}")
    except Exception as ex:
        print(f"  err: {type(ex).__name__}: {ex}")

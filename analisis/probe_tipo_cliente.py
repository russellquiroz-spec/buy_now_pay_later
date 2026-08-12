from redshift_extractor import extract_sql

DB = "data-rabbit-prod"
print(extract_sql(DB, """
    select tipo_cliente, status, data_source, count(*) as n
    from catalog.cat_estructura_comercial_v3
    group by 1,2,3 order by n desc limit 20
""").to_string())

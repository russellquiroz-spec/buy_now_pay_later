"""Cobertura temporal de las fuentes de ruta historica."""
from redshift_extractor import extract_sql

DB = "data-rabbit-prod"

print("=== catalog_clientes_historico: snapshots por fecha_inicio ===")
print(extract_sql(DB, """
    select fecha_inicio, count(*) as filas, count(distinct id_interno) as clientes
    from catalog.catalog_clientes_historico
    group by 1 order by 1
""").to_string())

print("\n=== cat_estructura_comercial_vigencia_diaria: rango ===")
print(extract_sql(DB, """
    select min(fecha) as desde, max(fecha) as hasta,
           count(distinct fecha) as dias, count(*) as filas
    from catalog.cat_estructura_comercial_vigencia_diaria
""").to_string())

print("\n=== route_mapping_by_period: periodos ===")
print(extract_sql(DB, """
    select fecha_inicio, count(*) as rutas
    from catalog.route_mapping_by_period
    group by 1 order by 1
""").to_string())

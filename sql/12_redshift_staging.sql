-- Staging de Redshift: estructura comercial y catalogo de rutas.
--
-- Estas tres tablas las creaba `to_sql` a partir de los dtypes de pandas, y eso hacia que el
-- esquema dependiera de lo que pandas hubiera inferido en esa corrida: al migrar a la VM,
-- `fecha_inicio`, `valido_desde` y `valido_hasta` llegaron como text en vez de date y las vistas
-- de ruta no compilaron. Con el DDL explicito el tipo es el mismo en cualquier destino.

CREATE SCHEMA IF NOT EXISTS redshift_bnpl;

-- Ruta vigente de cada cliente (catalog.cat_estructura_comercial_v3).
CREATE TABLE IF NOT EXISTS redshift_bnpl.estructura_comercial (
    netsuite_id   text,
    tipo_cliente  text,
    status        text,
    ruta          text,
    ruta_canon    text,
    supervisor    text,
    oficina       text,
    oficina_canon text,
    region        text,
    region_canon  text,
    pais          text,
    dia           text,
    frecuencia    text,
    fecha_inicio  date,
    data_source   text
);

CREATE INDEX IF NOT EXISTS ix_estructura_netsuite
    ON redshift_bnpl.estructura_comercial (netsuite_id);
CREATE INDEX IF NOT EXISTS ix_estructura_ruta
    ON redshift_bnpl.estructura_comercial (ruta);

-- Catalogo de rutas (catalog.route_mapping) = dim_ruta del modelo estrella.
CREATE TABLE IF NOT EXISTS redshift_bnpl.route_mapping (
    ruta    text,
    equipo  text,
    oficina text,
    region  text,
    pais    text
);

CREATE INDEX IF NOT EXISTS ix_route_mapping_ruta
    ON redshift_bnpl.route_mapping (ruta);

-- Ruta historica por intervalos, ya comprimida en Redshift por cambio de ruta.
CREATE TABLE IF NOT EXISTS redshift_bnpl.ruta_cliente_scd (
    netsuite_id   text,
    ruta          text,
    supervisor    text,
    oficina       text,
    region        text,
    tipo_cliente  text,
    status        text,
    valido_desde  date,
    valido_hasta  date,
    dias_vigencia bigint
);

CREATE INDEX IF NOT EXISTS ix_scd_netsuite_rango
    ON redshift_bnpl.ruta_cliente_scd (netsuite_id, valido_desde, valido_hasta);

-- Dimensiones de estructura comercial. Son DOS, y la distincion importa:
--
--   dim_ruta_actual        la ruta que tiene el cliente hoy. Para el grid y el corte semanal,
--                          donde la pregunta es "quien atiende esta cuenta".
--   dim_ruta_cliente_scd   la ruta que tenia el cliente cuando se origino cada credito. Para la
--                          mora, donde la pregunta es "quien tenia la cuenta cuando esto se
--                          presto". Atribuir mora vieja al supervisor actual seria injusto.
--
-- La historica cubre desde 2025-01-01 (arranque de cat_estructura_comercial_vigencia_diaria).
-- Las ordenes anteriores — dic-2023 a dic-2024, ~14% del total — no tienen ruta de esa epoca:
-- el primer tramo de cada cliente se extiende hacia atras y esas filas quedan marcadas con
-- ruta_inferida = true, para que nadie las lea como dato firme.

DROP MATERIALIZED VIEW IF EXISTS bnpl.dim_ruta_actual CASCADE;

CREATE MATERIALIZED VIEW bnpl.dim_ruta_actual AS
SELECT
    e.netsuite_id,
    e.ruta,
    e.ruta_canon,
    -- supervisor de la estructura; si falta, el equipo del catalogo de rutas.
    coalesce(e.supervisor, rm.equipo)                       AS supervisor,
    coalesce(e.oficina, rm.oficina)                         AS oficina,
    e.oficina_canon,
    coalesce(e.region, rm.region)                           AS region,
    e.region_canon,
    e.pais,
    e.tipo_cliente                                          AS tipo,
    e.status,
    e.dia,
    e.frecuencia,
    e.fecha_inicio,
    e.data_source
FROM redshift_bnpl.estructura_comercial e
LEFT JOIN redshift_bnpl.route_mapping rm ON e.ruta = rm.ruta;

CREATE UNIQUE INDEX ix_dim_ruta_actual_pk ON bnpl.dim_ruta_actual (netsuite_id);
CREATE INDEX ix_dim_ruta_actual_ruta      ON bnpl.dim_ruta_actual (ruta);

DROP MATERIALIZED VIEW IF EXISTS bnpl.dim_ruta_cliente_scd CASCADE;

CREATE MATERIALIZED VIEW bnpl.dim_ruta_cliente_scd AS
WITH ordenado AS (
    SELECT
        s.*,
        row_number() OVER (PARTITION BY netsuite_id ORDER BY valido_desde)      AS tramo_asc,
        row_number() OVER (PARTITION BY netsuite_id ORDER BY valido_desde DESC) AS tramo_desc
    FROM redshift_bnpl.ruta_cliente_scd s
)
SELECT
    netsuite_id,
    ruta,
    supervisor,
    oficina,
    region,
    tipo_cliente                                            AS tipo,
    status,
    -- El primer tramo se extiende hacia atras para cubrir las ordenes previas a la vigencia
    -- diaria; el ultimo hacia adelante para cubrir las de hoy.
    CASE WHEN tramo_asc = 1 THEN '1900-01-01'::date ELSE valido_desde END       AS valido_desde,
    CASE WHEN tramo_desc = 1 THEN '9999-12-31'::date ELSE valido_hasta END      AS valido_hasta,
    valido_desde                                            AS vigencia_real_desde,
    valido_hasta                                            AS vigencia_real_hasta,
    dias_vigencia,
    tramo_asc                                               AS tramo
FROM ordenado;

CREATE UNIQUE INDEX ix_dim_ruta_scd_pk
    ON bnpl.dim_ruta_cliente_scd (netsuite_id, valido_desde);
CREATE INDEX ix_dim_ruta_scd_rango
    ON bnpl.dim_ruta_cliente_scd (netsuite_id, valido_desde, valido_hasta);

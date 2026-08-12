-- Schema de operacion del pipeline BNPL: frescura de fuentes y calidad de datos.
-- Todas las marcas de tiempo estan en hora Mexico (UTC-6).

CREATE SCHEMA IF NOT EXISTS bnpl_ops;

-- Foto actual: 1 fila por coleccion.
CREATE TABLE IF NOT EXISTS bnpl_ops.source_freshness (
    coleccion         text PRIMARY KEY,
    tabla_staging     text,
    docs_mongo        bigint,
    docs_staging      bigint,
    docs_faltantes    bigint,
    last_write_mongo  timestamp,
    last_dato_staging timestamp,
    lag_fuente_horas  numeric(12,2),
    semaforo_fuente   text,
    semaforo_staging  text,
    checked_at        timestamp
);

-- Historia: una fila por coleccion por corrida. Es lo que contesta "desde cuando".
CREATE TABLE IF NOT EXISTS bnpl_ops.freshness_history (
    checked_at        timestamp NOT NULL,
    coleccion         text      NOT NULL,
    docs_mongo        bigint,
    docs_staging      bigint,
    docs_faltantes    bigint,
    last_write_mongo  timestamp,
    last_dato_staging timestamp,
    lag_fuente_horas  numeric(12,2),
    semaforo_fuente   text,
    semaforo_staging  text,
    PRIMARY KEY (checked_at, coleccion)
);

CREATE TABLE IF NOT EXISTS bnpl_ops.data_quality_checks (
    checked_at  timestamp NOT NULL,
    check_name  text      NOT NULL,
    tabla       text,
    n_filas     bigint,
    severidad   text,
    resultado   text,
    detalle     text,
    PRIMARY KEY (checked_at, check_name)
);

-- Bitacora de cargas: de aqui sale cuando fue el ultimo full de cada tabla, que es lo
-- que dispara la recarga completa periodica.
CREATE TABLE IF NOT EXISTS bnpl_ops.etl_runs (
    started_at timestamp NOT NULL,
    tabla      text      NOT NULL,
    modo       text,
    filas      bigint,
    segundos   numeric(10,1),
    PRIMARY KEY (started_at, tabla)
);

CREATE INDEX IF NOT EXISTS ix_etl_runs_tabla_modo
    ON bnpl_ops.etl_runs (tabla, modo, started_at DESC);

CREATE INDEX IF NOT EXISTS ix_freshness_history_coleccion
    ON bnpl_ops.freshness_history (coleccion, checked_at DESC);

CREATE INDEX IF NOT EXISTS ix_dq_checks_name
    ON bnpl_ops.data_quality_checks (check_name, checked_at DESC);

-- Vista plana para Power BI: estado actual ordenado por criticidad.
CREATE OR REPLACE VIEW bnpl_ops.v_freshness_status AS
SELECT
    coleccion,
    tabla_staging,
    docs_mongo,
    docs_staging,
    docs_faltantes,
    last_write_mongo,
    last_dato_staging,
    lag_fuente_horas,
    round(lag_fuente_horas / 24, 1)                          AS lag_fuente_dias,
    semaforo_fuente,
    semaforo_staging,
    CASE
        WHEN semaforo_fuente = 'CRIT' OR semaforo_staging IN ('CRIT', 'FALTA') THEN 'CRIT'
        WHEN semaforo_fuente = 'WARN' OR semaforo_staging = 'WARN'             THEN 'WARN'
        ELSE 'OK'
    END                                                      AS semaforo,
    checked_at
FROM bnpl_ops.source_freshness
ORDER BY
    CASE
        WHEN semaforo_fuente = 'CRIT' OR semaforo_staging IN ('CRIT', 'FALTA') THEN 1
        WHEN semaforo_fuente = 'WARN' OR semaforo_staging = 'WARN'             THEN 2
        ELSE 3
    END,
    coleccion;

-- Ultima corrida de chequeos de calidad, solo lo que esta en alerta.
CREATE OR REPLACE VIEW bnpl_ops.v_quality_alerts AS
SELECT check_name, tabla, n_filas, severidad, detalle, checked_at
FROM bnpl_ops.data_quality_checks
WHERE checked_at = (SELECT max(checked_at) FROM bnpl_ops.data_quality_checks)
  AND resultado <> 'OK'
ORDER BY CASE severidad WHEN 'CRIT' THEN 1 WHEN 'WARN' THEN 2 ELSE 3 END, n_filas DESC;

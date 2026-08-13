-- bnpl.vintage_analysis — cohort de enrolamiento x meses de maduracion.
--
-- Porta `parfinal` de la celda 97 del legacy. En el plan aparecian como dos tablas separadas
-- (par_monthly y vintage_analysis); en el legacy son una sola, asi que no se duplica: esta es
-- la tabla de vintage, con conteos, saldos y tasas PAR por mes de maduracion del cohort.
--
-- Solo entran cortes ya cumplidos (corte < hoy): un mes en curso daria una tasa parcial.

DROP MATERIALIZED VIEW IF EXISTS bnpl.vintage_analysis CASCADE;

CREATE MATERIALIZED VIEW bnpl.vintage_analysis AS
WITH base AS (
    SELECT * FROM bnpl.par_snapshot WHERE corte < bnpl.hoy_mx()
),
agregado AS (
    SELECT
        enrollment_cohort,
        months_from_enrollment_to_month,
        count(DISTINCT netsuite_id)                     AS ever_activated,
        max(enrolled_customers)                         AS enrolled_customers,
        count(*)                                        AS ordenes,
        sum(original_amount)                            AS deployed_capital,
        sum(total_amount)                               AS outstanding_balance
    FROM base
    GROUP BY 1, 2
),
mora AS (
    SELECT
        enrollment_cohort,
        months_from_enrollment_to_month,
        sum(total_amount)      FILTER (WHERE par IN ('DQ 30-59', 'DQ 60-89', 'DQ 90+')) AS par30,
        count(DISTINCT netsuite_id)
                               FILTER (WHERE par IN ('DQ 30-59', 'DQ 60-89', 'DQ 90+')) AS par30_n,
        sum(total_amount)      FILTER (WHERE par IN ('DQ 60-89', 'DQ 90+'))             AS par60,
        count(DISTINCT netsuite_id)
                               FILTER (WHERE par IN ('DQ 60-89', 'DQ 90+'))             AS par60_n,
        sum(total_amount)      FILTER (WHERE par = 'DQ 90+')                            AS par90,
        count(DISTINCT netsuite_id)
                               FILTER (WHERE par = 'DQ 90+')                            AS par90_n
    FROM base
    GROUP BY 1, 2
)
SELECT
    a.enrollment_cohort,
    left(a.enrollment_cohort, 4)                        AS cohort_year,
    a.months_from_enrollment_to_month,
    to_char(
        (a.enrollment_cohort || '-01')::date
            + (a.months_from_enrollment_to_month || ' months')::interval,
        'YYYY-MM'
    )                                                   AS corte,
    a.ever_activated,
    a.enrolled_customers,
    a.ordenes,
    a.deployed_capital,
    a.outstanding_balance,
    coalesce(m.par30, 0)                                AS par30,
    coalesce(m.par60, 0)                                AS par60,
    coalesce(m.par90, 0)                                AS par90,
    coalesce(m.par30_n, 0)                              AS par30_n,
    coalesce(m.par60_n, 0)                              AS par60_n,
    coalesce(m.par90_n, 0)                              AS par90_n,
    -- Tasas sobre saldo vivo. NULL cuando no hay saldo, en vez de dividir por cero.
    CASE WHEN a.outstanding_balance > 0
         THEN coalesce(m.par30, 0) / a.outstanding_balance END      AS par30_rate,
    CASE WHEN a.outstanding_balance > 0
         THEN coalesce(m.par60, 0) / a.outstanding_balance END      AS par60_rate,
    CASE WHEN a.outstanding_balance > 0
         THEN coalesce(m.par90, 0) / a.outstanding_balance END      AS par90_rate,
    -- Tasas sobre clientes.
    CASE WHEN a.ever_activated > 0
         THEN coalesce(m.par30_n, 0)::numeric / a.ever_activated END AS par30_customers_rate,
    CASE WHEN a.ever_activated > 0
         THEN coalesce(m.par60_n, 0)::numeric / a.ever_activated END AS par60_customers_rate,
    CASE WHEN a.ever_activated > 0
         THEN coalesce(m.par90_n, 0)::numeric / a.ever_activated END AS par90_customers_rate
FROM agregado a
LEFT JOIN mora m
       ON a.enrollment_cohort = m.enrollment_cohort
      AND a.months_from_enrollment_to_month = m.months_from_enrollment_to_month;

CREATE UNIQUE INDEX ix_vintage_pk
    ON bnpl.vintage_analysis (enrollment_cohort, months_from_enrollment_to_month);
CREATE INDEX ix_vintage_cohort_year ON bnpl.vintage_analysis (cohort_year);

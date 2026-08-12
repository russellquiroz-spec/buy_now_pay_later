-- bnpl.par_snapshot — estado de cada orden en cada corte mensual.
--
-- Porta el loop de la celda 94 del legacy. Para cada corte (fin de mes del vencimiento) y cada
-- orden ya vencida a esa fecha, clasifica en cuatro casos:
--
--   PaidPrev  vencio antes del mes del corte y ya estaba pagada  -> saldo vivo = 0
--   Paid      vencio en el mes del corte y se pago a tiempo
--   mora vieja  vencio antes del mes del corte y sigue sin pagarse a esa fecha
--   mora nueva  vencio en el mes del corte y sigue sin pagarse a esa fecha
--
-- La distincion importa por el saldo: PaidPrev pone total_amount en 0 para no inflar el saldo
-- vivo del cohort, pero original_amount conserva el monto para poder medir capital desplegado.

DROP MATERIALIZED VIEW IF EXISTS bnpl.par_snapshot CASCADE;

CREATE MATERIALIZED VIEW bnpl.par_snapshot AS
WITH cortes AS (
    SELECT DISTINCT
        end_of_month_expected_payment_date                          AS corte,
        date_trunc('month', end_of_month_expected_payment_date)
            - interval '1 day'                                      AS limite_mes_anterior
    FROM bnpl.loss_rates
    WHERE end_of_month_expected_payment_date IS NOT NULL
),
cruce AS (
    SELECT
        l.netsuite_id,
        l.sales_order_id,
        l.order_status,
        l.created_at,
        l.delivery_at,
        l.order_gross_sales,
        l.quantity,
        l.bnpl_enrolled_at,
        l.enrollment_cohort,
        l.enrolled_customers,
        l.enrolled_credit_limit_cohort,
        l.transaction_id,
        l.total_amount_to_pay,
        l.interests,
        l.total_amount_default,
        l.movement_date,
        l.payment_date,
        l.paid_date,
        l.expected_payment_date,
        l.end_of_month_expected_payment_date,
        c.corte,
        c.limite_mes_anterior,
        -- El monto original nunca se anula: es el capital desplegado del cohort.
        l.total_amount                                              AS original_amount,
        CASE
            WHEN l.paid_date IS NOT NULL AND l.paid_date <= c.corte
                 AND l.expected_payment_date <= c.limite_mes_anterior
                THEN 0                       -- PaidPrev: ya no es saldo vivo
            ELSE l.total_amount
        END                                                         AS total_amount,
        CASE
            WHEN l.paid_date IS NOT NULL AND l.paid_date <= c.corte THEN 0
            ELSE c.corte::date - l.expected_payment_date::date
        END                                                         AS days_past_due,
        CASE
            WHEN l.paid_date IS NOT NULL AND l.paid_date <= c.corte THEN
                CASE WHEN l.expected_payment_date <= c.limite_mes_anterior
                     THEN 'PaidPrev' ELSE 'Paid' END
            ELSE bnpl.bucket_par(c.corte::date - l.expected_payment_date::date)
        END                                                         AS par,
        bnpl.meses_entre(l.bnpl_enrolled_at, c.corte)               AS months_from_enrollment_to_month
    FROM bnpl.loss_rates l
    JOIN cortes c ON l.expected_payment_date <= c.corte
)
SELECT *, to_char(corte, 'YYYY-MM') AS month
FROM cruce;

CREATE UNIQUE INDEX ix_par_snapshot_pk
    ON bnpl.par_snapshot (netsuite_id, sales_order_id, corte);
CREATE INDEX ix_par_snapshot_cohort
    ON bnpl.par_snapshot (enrollment_cohort, months_from_enrollment_to_month);
CREATE INDEX ix_par_snapshot_par ON bnpl.par_snapshot (par);
CREATE INDEX ix_par_snapshot_corte ON bnpl.par_snapshot (corte);

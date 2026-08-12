-- bnpl.revenue_comision — el ingreso del producto, orden por orden.
--
-- Tabla nueva: el legacy no la tenia. El negocio de Rabbit en BNPL es la comision sobre el
-- interes, y hasta ahora eso no se medía en ninguna salida.
--
-- Expone las DOS definiciones de comision que conviven en el legacy, porque la diferencia es
-- del 17.3% y sigue sin confirmarse con negocio (PENDIENTE 1):
--   rabbit_revenue           14.2% sobre el interes CON IVA  (celda 82, alimenta loss_rates)
--   rabbit_revenue_sin_iva   14.2% sobre el interes SIN IVA  (celda 70, alimenta el grid)
-- Cuando se confirme cual es la del contrato, se borra la otra columna.

DROP MATERIALIZED VIEW IF EXISTS bnpl.revenue_comision CASCADE;

CREATE MATERIALIZED VIEW bnpl.revenue_comision AS
SELECT
    l.netsuite_id,
    l.sales_order_id,
    l.transaction_id,
    l.created_at,
    l.delivery_at,
    l.expected_payment_date,
    l.paid_date,
    l.movement_date,
    to_char(coalesce(l.paid_date, l.expected_payment_date), 'YYYY-MM') AS month,
    l.transaction_status,
    l.par,
    l.enrollment_cohort,
    -- Montos
    l.total_amount                                            AS monto_financiado,
    l.total_amount_to_pay                                     AS monto_a_pagar,
    l.interests                                               AS interes_sin_iva,
    l.interests_reportado                                     AS interes_sin_iva_reportado,
    l.comision_por_cobrar                                     AS interes_con_iva,
    -- El spread es lo que el tendero paga de mas: interes con IVA.
    coalesce(l.total_amount_to_pay, 0) - coalesce(l.total_amount, 0) AS spread_cobrado,
    l.default_interest                                        AS interes_moratorio,
    l.total_amount_default                                    AS monto_en_default,
    -- Reconocimiento: solo cuenta lo efectivamente pagado.
    CASE WHEN l.paid_date IS NOT NULL THEN 1 ELSE 0 END        AS cobrado,
    l.total_revenue                                           AS interes_cobrado,
    l.rabbit_revenue                                          AS rabbit_revenue,
    -- Sobre el interes SIN IVA que reporta el pago, sin la exencion del primer pedido: es como
    -- lo calcula el grid en el legacy, y asi las dos columnas quedan comparables.
    CASE WHEN l.paid_date IS NULL THEN 0
         ELSE coalesce(l.interests_reportado, 0) * bnpl.share_rabbit()
    END                                                       AS rabbit_revenue_sin_iva,
    CASE WHEN l.paid_date IS NULL THEN 0
         ELSE coalesce(l.total_amount, 0) * bnpl.comision_sobre_monto()
    END                                                       AS comision_sobre_monto
FROM bnpl.loss_rates l;

CREATE UNIQUE INDEX ix_revenue_comision_pk ON bnpl.revenue_comision (netsuite_id, sales_order_id);
CREATE INDEX ix_revenue_comision_month     ON bnpl.revenue_comision (month);
CREATE INDEX ix_revenue_comision_cobrado   ON bnpl.revenue_comision (cobrado);

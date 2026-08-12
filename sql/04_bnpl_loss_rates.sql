-- bnpl.loss_rates — 1 fila por orden entregada, con su estado de morosidad y su revenue.
-- Base de par_monthly, vintage_analysis y revenue_comision.
--
-- Porta bnpl_loss_rates del legacy (celda 82), con dos diferencias deliberadas:
--
--   * El legacy unia con Propaga por (netsuiteId, rank) — un join por POSICION, porque el Excel
--     de conciliaciones no traia el sales order. propaga_transaction si lo trae, asi que se une
--     por salesOrderId. Elimina el riesgo de cruzar el pago con la orden equivocada.
--   * Los pagos se unen por transactionId = salesOrderId y, cuando no cruzan, por
--     marketplaceOrderId = orderId: eso recupera 193 de los 276 pagos que el legacy perdia.
--
-- Los montos siguen la misma precedencia del legacy: lo que reporta Rabbit manda y Propaga
-- rellena los huecos.

DROP MATERIALIZED VIEW IF EXISTS bnpl.loss_rates CASCADE;

CREATE MATERIALIZED VIEW bnpl.loss_rates AS
WITH llaves_orden AS (
    SELECT DISTINCT "salesOrderId" AS sales_order_id, "orderId" AS order_id
    FROM mongo_bnpl.credit_order_production
    WHERE "salesOrderId" IS NOT NULL AND trim("salesOrderId") <> ''
),
pagos AS (
    -- Llave principal: transactionId. Secundaria: marketplaceOrderId contra el orderId.
    SELECT
        coalesce(k1.sales_order_id, k2.sales_order_id)    AS sales_order_id,
        p."transactionId"                                 AS transaction_id,
        p."totalAmount"                                   AS total_amount,
        p."totalAmountToPay"                              AS total_amount_to_pay,
        p."totalAmountDefault"                            AS total_amount_default,
        p.interests                                       AS interests,
        p."comisionPorCobrar"                             AS comision_por_cobrar,
        p."creditLimit"                                   AS credit_limit,
        p."transactionStatus"                             AS transaction_status,
        bnpl.epoch_ms_a_mx(p."movementDate")              AS movement_date,
        bnpl.iso_a_mx(p."paymentDateFromToPay")           AS payment_date,
        bnpl.iso_a_mx(p."paymentDateFromPaid")            AS paid_date,
        row_number() OVER (
            PARTITION BY coalesce(k1.sales_order_id, k2.sales_order_id)
            ORDER BY p."movementDate" DESC NULLS LAST
        )                                                 AS rn
    FROM mongo_bnpl.payment_report_production p
    LEFT JOIN llaves_orden k1 ON p."transactionId" = k1.sales_order_id
    LEFT JOIN llaves_orden k2 ON p."marketplaceOrderId" = k2.order_id
                             AND k1.sales_order_id IS NULL
    WHERE coalesce(k1.sales_order_id, k2.sales_order_id) IS NOT NULL
),
propaga AS (
    SELECT
        "salesOrderId"                                    AS sales_order_id,
        "totalAmount"                                     AS total_amount,
        "totalAmountWithInterests"                        AS total_amount_to_pay,
        interests                                         AS interests,
        "amountPaid"                                      AS amount_paid,
        bnpl.iso_a_mx("movementDate")                     AS movement_date,
        bnpl.iso_a_mx("paymentDate")                      AS payment_date,
        bnpl.iso_a_mx("paidDate")                         AS paid_date,
        status                                            AS status,
        row_number() OVER (
            PARTITION BY "salesOrderId" ORDER BY "updatedAt" DESC NULLS LAST
        )                                                 AS rn
    FROM mongo_bnpl.propaga_transaction
    WHERE "salesOrderId" IS NOT NULL
),
base AS (
    SELECT
        o.netsuite_id,
        o.sales_order_id,
        o.order_id,
        o.order_status,
        o.created_at,
        o.delivery_at,
        o.order_gross_sales,
        o.quantity,
        o.credit_limit,
        o.bnpl_enrolled_at,
        o.enrollment_cohort,
        o.enrolled_customers,
        o.enrolled_credit_limit_cohort,
        o.months_since_enrollment,
        o.ruta,
        o.supervisor,
        o.oficina,
        o.region,
        o.tipo,
        o.ruta_inferida,
        o.customer_completed_order_index                  AS rank_completadas,
        coalesce(p.transaction_id, o.sales_order_id)      AS transaction_id,
        p.transaction_status,
        coalesce(p.total_amount, pr.total_amount)               AS total_amount,
        coalesce(p.total_amount_to_pay, pr.total_amount_to_pay) AS total_amount_to_pay,
        coalesce(p.total_amount_default, 0)                     AS total_amount_default,
        coalesce(p.interests, pr.interests)                     AS interests_reportado,
        pr.interests                                            AS interests_propaga,
        p.comision_por_cobrar,
        coalesce(p.movement_date, pr.movement_date)             AS movement_date,
        coalesce(p.payment_date, pr.payment_date)               AS payment_date,
        coalesce(p.paid_date, pr.paid_date)                     AS paid_date,
        pr.amount_paid                                          AS propaga_amount_paid,
        pr.status                                               AS propaga_status
    FROM bnpl.grouped_orders o
    LEFT JOIN pagos p    ON o.sales_order_id = p.sales_order_id AND p.rn = 1
    LEFT JOIN propaga pr ON o.sales_order_id = pr.sales_order_id AND pr.rn = 1
    WHERE o.order_status = 'COMPLETED'
),
fechas AS (
    SELECT
        base.*,
        -- El vencimiento se calcula sobre el DIA de entrega, no sobre el instante: en el legacy
        -- epoch_to_date() devuelve '%Y-%m-%d', asi que alla las fechas ya venian truncadas.
        bnpl.mover_a_lunes(
            date_trunc('day', delivery_at) + (bnpl.dias_credito() || ' days')::interval
        ) AS expected_payment_date
    FROM base
),
calculado AS (
    SELECT
        fechas.*,
        (date_trunc('month', expected_payment_date) + interval '1 month - 1 day')
            AS end_of_month_expected_payment_date,
        CASE
            WHEN paid_date IS NULL
                THEN current_date - expected_payment_date::date
            ELSE paid_date::date - expected_payment_date::date
        END AS days_past_due
    FROM fechas
)
SELECT
    netsuite_id,
    sales_order_id,
    order_id,
    order_status,
    created_at,
    delivery_at,
    order_gross_sales,
    quantity,
    credit_limit,
    bnpl_enrolled_at,
    enrollment_cohort,
    enrolled_customers,
    enrolled_credit_limit_cohort,
    months_since_enrollment,
    ruta,
    supervisor,
    oficina,
    region,
    tipo,
    ruta_inferida,
    rank_completadas,
    transaction_id,
    transaction_status,
    total_amount,
    total_amount_to_pay,
    total_amount_default,
    -- Exencion del primer pedido: si Propaga no cobro interes, o si es el primer pedido
    -- completado desde la fecha de exencion, el interes imputado es cero (PENDIENTE 2).
    CASE
        WHEN interests_propaga = 0 THEN 0
        WHEN rank_completadas = 1
             AND created_at >= bnpl.exencion_interes_desde() THEN 0
        ELSE interests_reportado
    END                                                       AS interests,
    -- El interes tal como lo reporta el pago, sin aplicar la exencion. El grid del legacy usa
    -- este, no el de arriba, y por eso sus dos cifras de revenue no coinciden (PENDIENTE 1).
    interests_reportado,
    comision_por_cobrar,
    movement_date,
    payment_date,
    paid_date,
    propaga_amount_paid,
    propaga_status,
    expected_payment_date,
    end_of_month_expected_payment_date,
    to_char(expected_payment_date, 'YYYY-MM')                 AS month,
    CASE WHEN paid_date <= end_of_month_expected_payment_date THEN 1 ELSE 0 END AS paid_on_month,
    days_past_due,
    CASE
        WHEN paid_date <= end_of_month_expected_payment_date THEN 0
        ELSE end_of_month_expected_payment_date::date - expected_payment_date::date
    END                                                       AS days_past_due_end_of_month,
    -- Interes moratorio: 200 por semana completa de atraso.
    CASE WHEN days_past_due <= 0 THEN 0
         ELSE bnpl.interes_moratorio_semanal() * floor(days_past_due / 7.0)
    END                                                       AS default_interest,
    -- Revenue: solo se reconoce cuando el pago ocurrio.
    CASE WHEN paid_date IS NULL THEN 0
         ELSE coalesce(total_amount_to_pay, 0) - coalesce(total_amount, 0)
    END                                                       AS total_revenue,
    CASE WHEN paid_date IS NULL THEN 0
         ELSE (coalesce(total_amount_to_pay, 0) - coalesce(total_amount, 0)) * bnpl.share_rabbit()
    END                                                       AS rabbit_revenue,
    CASE
        WHEN paid_date IS NOT NULL              THEN 'Paid'
        WHEN expected_payment_date >= now()     THEN 'Ongoing'
        ELSE bnpl.bucket_par(days_past_due)
    END                                                       AS par
FROM calculado;

CREATE UNIQUE INDEX ix_loss_rates_pk    ON bnpl.loss_rates (netsuite_id, sales_order_id);
CREATE INDEX ix_loss_rates_cohort       ON bnpl.loss_rates (enrollment_cohort);
CREATE INDEX ix_loss_rates_month        ON bnpl.loss_rates (month);
CREATE INDEX ix_loss_rates_par          ON bnpl.loss_rates (par);
CREATE INDEX ix_loss_rates_expected     ON bnpl.loss_rates (expected_payment_date);

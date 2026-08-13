-- bnpl.kpis_daily — una fila por dia, con la serie completa sin huecos.
--
-- Porta kpis_df del legacy (celdas 120 a 124). Mide lo mismo por dos fechas distintas, y la
-- distincion importa: por createdAt es cuando se levanto el pedido, por deliveryDate cuando se
-- entrego y empezo a correr el credito.
--
-- La tasa de rechazo se calcula sobre las ordenes que debian entregarse ese dia
-- (COMPLETED + REJECTED), no sobre todas: una orden que aun no vencia no puede rechazarse.

DROP MATERIALIZED VIEW IF EXISTS bnpl.kpis_daily CASCADE;

CREATE MATERIALIZED VIEW bnpl.kpis_daily AS
WITH rango AS (
    SELECT generate_series(
        (SELECT min(created_at)::date FROM bnpl.grouped_orders),
        bnpl.hoy_mx(),
        interval '1 day'
    )::date AS fecha
),
por_creacion AS (
    SELECT
        created_at::date                                            AS fecha,
        count(sales_order_id)                                       AS created_orders,
        count(*) FILTER (WHERE delivery_status = 'COMPLETED')        AS completed_orders_by_created_at,
        coalesce(sum(order_gross_sales)
                 FILTER (WHERE delivery_status = 'COMPLETED'), 0)    AS completed_sales_volume_by_created_at
    FROM bnpl.grouped_orders
    WHERE created_at IS NOT NULL
    GROUP BY 1
),
por_entrega AS (
    SELECT
        delivery_date::date                                         AS fecha,
        count(*) FILTER (WHERE delivery_status = 'COMPLETED')        AS completed_orders_by_delivery_date,
        coalesce(sum(order_gross_sales)
                 FILTER (WHERE delivery_status = 'COMPLETED'), 0)    AS completed_sales_volume_by_delivery_date
    FROM bnpl.grouped_orders
    WHERE delivery_date IS NOT NULL
    GROUP BY 1
),
entregas AS (
    -- Se mide sobre state-of-delivery, que es el registro de lo que efectivamente se entrego.
    SELECT
        bnpl.epoch_ms_a_mx("deliveryDate")::date                     AS fecha,
        count(*) FILTER (WHERE "deliveryStatus" IN ('COMPLETED', 'REJECTED'))
                                                                     AS orders_that_should_have_been_delivered,
        count(*) FILTER (WHERE "deliveryStatus" = 'REJECTED')         AS rejected_orders,
        count(*) FILTER (
            WHERE "deliveryStatus" = 'REJECTED'
              AND reason IN ('No tiene palabra clave', 'Palabra clave incorrecta')
        )                                                            AS rejected_orders_by_keyword
    FROM mongo_bnpl.state_of_delivery_report_production
    WHERE "deliveryDate" IS NOT NULL
    GROUP BY 1
),
pagos AS (
    SELECT
        paid_date::date                                              AS fecha,
        count(*)                                                     AS payments,
        coalesce(sum(total_amount), 0)                               AS payments_volume,
        coalesce(sum(total_revenue), 0)                              AS interest_collected,
        coalesce(sum(rabbit_revenue), 0)                             AS rabbit_revenue
    FROM bnpl.loss_rates
    WHERE paid_date IS NOT NULL
    GROUP BY 1
),
enrolamientos AS (
    SELECT bnpl.iso_a_mx("createdAt")::date AS fecha, count(*) AS enrollments
    FROM mongo_bnpl.fintech_credit_approval_production
    WHERE status = 'APPROVED' AND "createdAt" IS NOT NULL
    GROUP BY 1
),
activaciones AS (
    SELECT bnpl_activated_at::date AS fecha, count(*) AS activations
    FROM bnpl.grid_bnpl
    WHERE bnpl_activated_at IS NOT NULL
    GROUP BY 1
),
diario AS (
    SELECT
        r.fecha                                                      AS date,
        coalesce(c.created_orders, 0)                                AS created_orders,
        coalesce(c.completed_orders_by_created_at, 0)                AS completed_orders_by_created_at,
        coalesce(c.completed_sales_volume_by_created_at, 0)           AS completed_sales_volume_by_created_at,
        coalesce(e.completed_orders_by_delivery_date, 0)              AS completed_orders_by_delivery_date,
        coalesce(e.completed_sales_volume_by_delivery_date, 0)        AS completed_sales_volume_by_delivery_date,
        coalesce(d.orders_that_should_have_been_delivered, 0)         AS orders_that_should_have_been_delivered,
        coalesce(d.rejected_orders, 0)                                AS rejected_orders,
        coalesce(d.rejected_orders_by_keyword, 0)                     AS rejected_orders_by_keyword,
        coalesce(p.payments, 0)                                       AS payments,
        coalesce(p.payments_volume, 0)                                AS payments_volume,
        coalesce(p.interest_collected, 0)                             AS interest_collected,
        coalesce(p.rabbit_revenue, 0)                                 AS rabbit_revenue,
        coalesce(en.enrollments, 0)                                   AS enrollments,
        coalesce(ac.activations, 0)                                   AS activations
    FROM rango r
    LEFT JOIN por_creacion c   ON r.fecha = c.fecha
    LEFT JOIN por_entrega e    ON r.fecha = e.fecha
    LEFT JOIN entregas d       ON r.fecha = d.fecha
    LEFT JOIN pagos p          ON r.fecha = p.fecha
    LEFT JOIN enrolamientos en ON r.fecha = en.fecha
    LEFT JOIN activaciones ac  ON r.fecha = ac.fecha
)
SELECT
    date,
    -- Agrupadores de calendario para Power BI.
    date_trunc('week', date)::date                                    AS week_start,
    (date_trunc('week', date) + interval '6 days')::date              AS week_end,
    (date_trunc('month', date) + interval '1 month - 1 day')::date    AS month_end,
    (date_trunc('year', date) + interval '1 year - 1 day')::date      AS year_end,
    created_orders,
    completed_orders_by_created_at,
    completed_sales_volume_by_created_at,
    completed_orders_by_delivery_date,
    completed_sales_volume_by_delivery_date,
    orders_that_should_have_been_delivered,
    rejected_orders,
    rejected_orders_by_keyword,
    payments,
    payments_volume,
    interest_collected,
    rabbit_revenue,
    enrollments,
    activations,
    -- Acumulados
    sum(created_orders) OVER w                                        AS cumulative_created_orders,
    sum(completed_orders_by_created_at) OVER w                        AS cumulative_completed_orders_by_created_at,
    sum(completed_orders_by_delivery_date) OVER w                     AS cumulative_completed_orders_by_delivery_date,
    sum(completed_sales_volume_by_created_at) OVER w                  AS cumulative_completed_sales_volume_by_created_at,
    sum(completed_sales_volume_by_delivery_date) OVER w               AS cumulative_completed_sales_volume_by_delivery_date,
    sum(orders_that_should_have_been_delivered) OVER w                AS cumulative_orders_that_should_have_been_delivered,
    sum(rejected_orders) OVER w                                       AS cumulative_rejected_orders,
    sum(rejected_orders_by_keyword) OVER w                            AS cumulative_rejected_orders_by_keyword,
    sum(rabbit_revenue) OVER w                                        AS cumulative_rabbit_revenue,
    -- Tasas: NULL cuando no hubo entregas esperadas, en vez de dividir por cero.
    CASE WHEN orders_that_should_have_been_delivered > 0
         THEN rejected_orders::numeric / orders_that_should_have_been_delivered END
                                                                      AS rejected_rate,
    CASE WHEN orders_that_should_have_been_delivered > 0
         THEN rejected_orders_by_keyword::numeric / orders_that_should_have_been_delivered END
                                                                      AS rejected_rate_by_keyword,
    CASE WHEN sum(orders_that_should_have_been_delivered) OVER w > 0
         THEN sum(rejected_orders) OVER w::numeric
              / sum(orders_that_should_have_been_delivered) OVER w END AS cumulative_rejected_rate,
    CASE WHEN sum(orders_that_should_have_been_delivered) OVER w > 0
         THEN sum(rejected_orders_by_keyword) OVER w::numeric
              / sum(orders_that_should_have_been_delivered) OVER w END AS cumulative_rejected_rate_by_keyword
FROM diario
WINDOW w AS (ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW);

CREATE UNIQUE INDEX ix_kpis_daily_pk ON bnpl.kpis_daily (date);
CREATE INDEX ix_kpis_daily_month     ON bnpl.kpis_daily (month_end);

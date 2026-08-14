-- bnpl.grouped_orders — 1 fila por (cliente, sales order, order_id, order_status, sales_channel).
--
-- OJO: NO es una fila por sales order. El GROUP BY de `ordenes` va por esas cinco columnas y el
-- indice unico de abajo tambien. Una sales order con tres SKUs distintos o con dos cambios de
-- estatus son varias filas. Cualquier conteo de ordenes o suma de monto directo sobre esta vista
-- sale inflado: hay que colapsar antes por (netsuite_id, sales_order_id), como hace el CTE
-- `ordenes` de sql/pbi/20_concurso_base.sql.
--
-- Porta bnpl_orders_group del legacy (celda 78). Dos cosas que no son obvias:
--
--   * orderGrossSales y totalPrice se agregan con MAX, no SUM: el monto total de la orden
--     viene repetido en cada linea de SKU. Sumarlo infla las ventas por el numero de SKUs.
--   * enrollment_cohort sale de la APROBACION del credito (fintech-credit-approval con
--     status = APPROVED), no de la primera orden del cliente.

DROP MATERIALIZED VIEW IF EXISTS bnpl.grouped_orders CASCADE;

CREATE MATERIALIZED VIEW bnpl.grouped_orders AS
WITH enrolados AS (
    -- Clientes con credito aprobado. Es la base del cohort de enrolamiento.
    --
    -- DISTINCT ON por dos razones distintas, las dos reales:
    --   1. Este CTE entra como LEFT JOIN contra con_indices (linea 114). Un cliente con dos
    --      aprobaciones duplica TODAS sus ordenes y hace fallar CREATE UNIQUE INDEX
    --      ix_grouped_orders_pk (linea 123), que es de cinco columnas y no incluye la aprobacion.
    --   2. `cohortes` cuenta count(*) sobre este CTE para enrolled_customers. Sin deduplicar,
    --      un cliente con dos aprobaciones cuenta dos veces en el denominador del cohort.
    -- Se toma la PRIMERA aprobacion: el cohort de enrolamiento es la fecha en que el cliente
    -- entro al producto, no la de su ultimo ajuste.
    SELECT DISTINCT ON ("netsuiteId")
        "netsuiteId"                                             AS netsuite_id,
        bnpl.iso_a_mx("createdAt")                               AS bnpl_enrolled_at,
        to_char(bnpl.iso_a_mx("createdAt"), 'YYYY-MM')           AS enrollment_cohort,
        "creditLimit"                                            AS enrolled_credit_limit,
        origin                                                   AS enrollment_channel
    FROM mongo_bnpl.fintech_credit_approval_production
    WHERE status = 'APPROVED'
      AND "netsuiteId" IS NOT NULL
    ORDER BY "netsuiteId", bnpl.iso_a_mx("createdAt") ASC NULLS LAST, "approvalId"
),
cohortes AS (
    SELECT
        enrollment_cohort,
        count(*)                        AS enrolled_customers,
        sum(enrolled_credit_limit)      AS enrolled_credit_limit_cohort
    FROM enrolados
    GROUP BY 1
),
limite_por_orden AS (
    -- La linea de credito vigente al momento de la orden viene del reporte de pagos.
    SELECT "transactionId" AS sales_order_id, max("creditLimit") AS credit_limit
    FROM mongo_bnpl.payment_report_production
    WHERE "transactionId" IS NOT NULL
    GROUP BY 1
),
ordenes AS (
    SELECT
        o."netsuiteId"                                    AS netsuite_id,
        o."salesOrderId"                                  AS sales_order_id,
        o."orderId"                                       AS order_id,
        o."orderStatus"                                   AS order_status,
        coalesce(o."salesChannel", 'MARKETPLACE')         AS sales_channel,
        max(o."createdAt")                                AS created_at_ms,
        bnpl.epoch_ms_a_mx(max(o."createdAt"))            AS created_at,
        bnpl.epoch_ms_a_mx(max(o."deliveryAt"))           AS delivery_at,
        max(o."orderGrossSales")                          AS order_gross_sales,
        max(o."totalPrice")                               AS total_price,
        count(DISTINCT o."productId")                     AS skus,
        sum(o.quantity)                                   AS quantity
    FROM mongo_bnpl.credit_order_production o
    WHERE o."salesOrderId" IS NOT NULL AND trim(o."salesOrderId") <> ''
    GROUP BY 1, 2, 3, 4, 5
),
con_indices AS (
    SELECT
        ordenes.*,
        row_number() OVER (
            PARTITION BY netsuite_id ORDER BY created_at, sales_order_id
        )                                                  AS customer_order_try_index,
        CASE WHEN order_status = 'COMPLETED' THEN
            row_number() OVER (
                PARTITION BY netsuite_id, (order_status = 'COMPLETED')
                ORDER BY created_at, sales_order_id
            )
        END                                                AS customer_completed_order_index,
        -- Primera orden del cliente en un estado que cuenta como activacion.
        min(CASE WHEN order_status = ANY (bnpl.estados_activacion()) THEN created_at END)
            OVER (PARTITION BY netsuite_id)                AS bnpl_activated_at
    FROM ordenes
)
SELECT
    o.netsuite_id,
    o.sales_order_id,
    o.order_id,
    o.order_status,
    d."deliveryStatus"                                    AS delivery_status,
    o.sales_channel,
    o.created_at_ms,
    o.created_at,
    o.order_gross_sales,
    o.total_price,
    lc.credit_limit,
    o.skus,
    o.quantity,
    o.delivery_at,
    bnpl.epoch_ms_a_mx(d."deliveryDate")                  AS delivery_date,
    o.customer_order_try_index,
    o.customer_completed_order_index,
    e.bnpl_enrolled_at,
    e.enrollment_cohort,
    e.enrollment_channel,
    c.enrolled_customers,
    c.enrolled_credit_limit_cohort,
    o.bnpl_activated_at,
    to_char(o.bnpl_activated_at, 'YYYY-MM')               AS activated_cohort,
    bnpl.meses_entre(e.bnpl_enrolled_at, o.created_at)    AS months_since_enrollment,
    bnpl.meses_entre(o.bnpl_activated_at, o.created_at)   AS months_since_activation,
    to_char(o.created_at, 'YYYY-MM')                      AS month_created_at,
    -- Estructura comercial vigente CUANDO se creo la orden, no la de hoy: la mora se atribuye
    -- a quien tenia la cuenta en ese momento.
    r.ruta,
    r.supervisor,
    r.oficina,
    r.region,
    r.tipo,
    -- La vigencia diaria arranca en 2025-01-01. Para ordenes anteriores se usa el primer tramo
    -- conocido del cliente, y queda marcado como inferido.
    --
    -- El coalesce(..., true) cubre el tercer hueco, que antes salia como NULL: clientes que no
    -- tienen NINGUN tramo en dim_ruta_cliente_scd, porque la extraccion filtra `and ruta is not
    -- null` (etl_redshift_to_postgres.py:66) o porque el cliente no esta en la vigencia diaria.
    -- Con NULL, sql/pbi/20:64 hacia coalesce(bool_or(ruta_inferida), false) y esas ordenes
    -- terminaban marcadas como ruta FIRME con aliado 'SIN RUTA'. No saber la ruta es el caso
    -- mas inferido de todos, no el menos.
    coalesce(o.created_at::date < r.vigencia_real_desde, true) AS ruta_inferida
FROM con_indices o
LEFT JOIN enrolados e   ON o.netsuite_id = e.netsuite_id
LEFT JOIN cohortes c    ON e.enrollment_cohort = c.enrollment_cohort
LEFT JOIN limite_por_orden lc ON o.sales_order_id = lc.sales_order_id
LEFT JOIN mongo_bnpl.state_of_delivery_report_production d
       ON o.sales_order_id = d."salesOrderId"
LEFT JOIN bnpl.dim_ruta_cliente_scd r
       ON o.netsuite_id = r.netsuite_id
      AND o.created_at::date BETWEEN r.valido_desde AND r.valido_hasta;

CREATE UNIQUE INDEX ix_grouped_orders_pk
    ON bnpl.grouped_orders (netsuite_id, sales_order_id, order_id, order_status, sales_channel);
CREATE INDEX ix_grouped_orders_sales_order ON bnpl.grouped_orders (sales_order_id);
CREATE INDEX ix_grouped_orders_netsuite    ON bnpl.grouped_orders (netsuite_id);
CREATE INDEX ix_grouped_orders_cohort      ON bnpl.grouped_orders (enrollment_cohort);
CREATE INDEX ix_grouped_orders_created     ON bnpl.grouped_orders (created_at);

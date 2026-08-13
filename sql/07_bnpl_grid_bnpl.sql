-- bnpl.grid_bnpl — 1 fila por cliente: el maestro del producto.
--
-- Porta bnpl_main_info del legacy (celda 102). Recorre el embudo completo: cliente ->
-- preautorizado -> enrolado -> activado -> activo, con sus conteos de ordenes y su revenue.
--
-- Diferencias con el legacy, todas documentadas en PENDIENTES_NEGOCIO.md:
--   * Sin ruta/supervisor/oficina/tipo: esas columnas llegan en la Fase 4 desde Redshift.
--   * Sin manualValidation: el clean_manual_validation.csv no existe en el proyecto.
--   * inferredGender se reemplaza por el campo `gender` que Mongo ya trae; el legacy lo
--     adivinaba con gender_guesser sobre el nombre.
--   * customerAgeAtEnrollment se calcula contra la fecha de enrolamiento. El legacy usaba
--     bnplEligibleAt en ambas columnas, asi que le salia igual que customerAgeAtEligibility.
--   * bnplRevenueShare aplica el 14.2% sobre el interes SIN IVA, como el legacy en esta tabla
--     (en loss_rates lo aplica sobre el interes con IVA — ver PENDIENTE 1).

DROP MATERIALIZED VIEW IF EXISTS bnpl.grid_bnpl CASCADE;

CREATE MATERIALIZED VIEW bnpl.grid_bnpl AS
WITH ordenes_activas AS (
    -- Ordenes que cuentan como uso del credito.
    SELECT
        netsuite_id,
        min(created_at)                                     AS bnpl_first_order_at,
        max(created_at)                                     AS bnpl_last_order_at,
        min(created_at)                                     AS bnpl_activated_at,
        count(sales_order_id)                               AS bnpl_orders_count,
        avg(order_gross_sales)                              AS bnpl_avg_order_volume,
        sum(order_gross_sales)                              AS bnpl_total_order_volume,
        sum(order_gross_sales) FILTER (WHERE customer_order_try_index = 1)
                                                            AS bnpl_first_order_gross_sales
    FROM bnpl.grouped_orders
    WHERE order_status = ANY (bnpl.estados_activacion())
    GROUP BY 1
),
ordenes_completadas AS (
    SELECT
        netsuite_id,
        count(sales_order_id)                               AS bnpl_completed_orders_count,
        sum(order_gross_sales)                              AS bnpl_completed_order_volume,
        count(*) FILTER (
            WHERE delivery_at + (bnpl.dias_credito() || ' days')::interval <= bnpl.ahora_mx()
        )                                                   AS bnpl_due_for_payment_orders_count
    FROM bnpl.grouped_orders
    WHERE order_status = 'COMPLETED'
    GROUP BY 1
),
ordenes_rechazadas AS (
    SELECT netsuite_id, count(sales_order_id) AS bnpl_rejected_orders_count
    FROM bnpl.grouped_orders WHERE order_status = 'REJECTED' GROUP BY 1
),
ordenes_canceladas AS (
    SELECT netsuite_id, count(sales_order_id) AS bnpl_cancelled_orders_count
    FROM bnpl.grouped_orders WHERE order_status IN ('CANCELED', 'CANCELLED') GROUP BY 1
),
pagos AS (
    -- Solo transacciones efectivamente pagadas.
    SELECT
        "clientId"                                          AS netsuite_id,
        count("transactionId")                              AS bnpl_payments_count,
        avg(interests)                                      AS bnpl_avg_revenue,
        avg(interests * bnpl.share_rabbit())                AS bnpl_avg_revenue_share,
        sum(interests)                                      AS bnpl_revenue,
        sum(interests * bnpl.share_rabbit())                AS bnpl_revenue_share
    FROM mongo_bnpl.payment_report_production
    WHERE "transactionStatus" = 'paid'
    GROUP BY 1
),
enrolados AS (
    SELECT
        "netsuiteId"                                        AS netsuite_id,
        bnpl.iso_a_mx("createdAt")                          AS bnpl_enrolled_at,
        "creditLimit"                                       AS credit_limit,
        origin                                              AS enrollment_channel
    FROM mongo_bnpl.fintech_credit_approval_production
    WHERE status = 'APPROVED' AND "netsuiteId" IS NOT NULL
),
preautorizados AS (
    SELECT
        "netsuiteId"                                        AS netsuite_id,
        bnpl.iso_a_mx("authorizationDate")                  AS bnpl_eligible_at,
        "preAuthorized"                                     AS pre_authorized_by
    FROM mongo_bnpl.fintech_pre_authorization_status_production
    WHERE "netsuiteId" IS NOT NULL
),
lineas AS (
    SELECT
        "netsuiteId"                                        AS netsuite_id,
        "originalCreditLimit"                               AS original_credit_limit,
        "currentCreditLimit"                                AS current_credit_limit,
        "creditLimitAvailable"                              AS credit_limit_available,
        "customerStatus"                                    AS customer_status
    FROM mongo_bnpl.credit_limit_history_management
    WHERE "netsuiteId" IS NOT NULL
)
SELECT
    c."customerId"                                          AS customer_id,
    c."shopkeeperId"                                        AS shopkeeper_id,
    c."netsuiteId"                                          AS netsuite_id,
    c."shopName"                                            AS shop_name,
    -- Estructura comercial VIGENTE: aqui la pregunta es quien atiende la cuenta hoy.
    dr.ruta,
    dr.supervisor,
    dr.oficina,
    dr.region,
    dr.tipo,
    dr.status                                               AS estructura_status,
    c.business_category,
    c."address_neighborhood"                                AS shop_neighborhood,
    c."address_zipCode"                                     AS shop_zip_code,
    c."address_town"                                        AS shop_town,
    c."address_state"                                       AS shop_state,
    nullif(c."address_latitude", '')::double precision      AS shop_latitude,
    nullif(c."address_longitude", '')::double precision     AS shop_longitude,
    r.name                                                  AS customer_name,
    r."lastNames"                                           AS customer_last_names,
    coalesce(nullif(r.gender, 'NOT_DEFINED'), nullif(c.gender, 'NOT_DEFINED')) AS gender,
    r.birthdate::date                                       AS customer_birthdate,
    (bnpl.hoy_mx() - r.birthdate::date) / 365               AS customer_age,
    (pa.bnpl_eligible_at::date - r.birthdate::date) / 365   AS customer_age_at_eligibility,
    (en.bnpl_enrolled_at::date - r.birthdate::date) / 365   AS customer_age_at_enrollment,
    c."phoneNumber"                                         AS customer_phone_number,
    nullif(r.latitude, '')::double precision                AS customer_latitude,
    nullif(r.longitude, '')::double precision               AS customer_longitude,
    c."hasMarketplace"                                      AS has_marketplace,
    c."hasPresales"                                         AS has_presales,
    -- Embudo
    pa.bnpl_eligible_at,
    pa.pre_authorized_by,
    li.original_credit_limit,
    li.current_credit_limit,
    li.credit_limit_available,
    li.customer_status,
    en.credit_limit,
    en.bnpl_enrolled_at,
    CASE WHEN en.bnpl_enrolled_at IS NULL THEN 0 ELSE 1 END AS bnpl_is_enrolled,
    to_char(en.bnpl_enrolled_at, 'YYYY-MM')                 AS enrollment_cohort,
    en.enrollment_channel,
    oa.bnpl_activated_at,
    CASE WHEN oa.bnpl_activated_at IS NULL THEN 0 ELSE 1 END AS bnpl_is_activated,
    to_char(oa.bnpl_activated_at, 'YYYY-MM')                AS bnpl_activated_cohort_month,
    CASE WHEN oa.bnpl_activated_at IS NULL THEN 0
         ELSE li.original_credit_limit END                  AS bnpl_activated_line_of_credit,
    -- Ordenes
    oa.bnpl_first_order_at,
    oa.bnpl_last_order_at,
    coalesce(oa.bnpl_orders_count, 0)                       AS bnpl_orders_count,
    coalesce(oc.bnpl_completed_orders_count, 0)             AS bnpl_completed_orders_count,
    coalesce(orj.bnpl_rejected_orders_count, 0)             AS bnpl_rejected_orders_count,
    coalesce(oca.bnpl_cancelled_orders_count, 0)            AS bnpl_cancelled_orders_count,
    oa.bnpl_avg_order_volume,
    coalesce(oa.bnpl_total_order_volume, 0)                 AS bnpl_total_order_volume,
    coalesce(oc.bnpl_completed_order_volume, 0)             AS bnpl_completed_order_volume,
    coalesce(oa.bnpl_first_order_gross_sales, 0)            AS bnpl_first_order_gross_sales,
    -- Dias promedio entre pedidos.
    CASE WHEN oa.bnpl_orders_count > 0
         THEN (oa.bnpl_last_order_at::date - oa.bnpl_first_order_at::date)::numeric
              / oa.bnpl_orders_count END                    AS bnpl_order_frequency,
    coalesce(oc.bnpl_due_for_payment_orders_count, 0)       AS bnpl_due_for_payment_orders_count,
    -- Pagos y revenue
    coalesce(p.bnpl_payments_count, 0)                      AS bnpl_payments_count,
    p.bnpl_avg_revenue,
    p.bnpl_avg_revenue_share,
    coalesce(p.bnpl_revenue, 0)                             AS bnpl_revenue,
    coalesce(p.bnpl_revenue_share, 0)                       AS bnpl_revenue_share,
    -- Activo = con actividad en los ultimos dias_inactividad() dias.
    CASE WHEN bnpl.hoy_mx() - oa.bnpl_last_order_at::date <= bnpl.dias_inactividad()
         THEN 1 ELSE 0 END                                  AS bnpl_is_active
FROM mongo_bnpl.fintech_customers_production c
LEFT JOIN mongo_bnpl.fintech_credit_request_production r ON c."customerId" = r."customerId"
LEFT JOIN bnpl.dim_ruta_actual dr ON c."netsuiteId" = dr.netsuite_id
LEFT JOIN preautorizados pa      ON c."netsuiteId" = pa.netsuite_id
LEFT JOIN lineas li              ON c."netsuiteId" = li.netsuite_id
LEFT JOIN enrolados en           ON c."netsuiteId" = en.netsuite_id
LEFT JOIN ordenes_activas oa     ON c."netsuiteId" = oa.netsuite_id
LEFT JOIN ordenes_completadas oc ON c."netsuiteId" = oc.netsuite_id
LEFT JOIN ordenes_rechazadas orj ON c."netsuiteId" = orj.netsuite_id
LEFT JOIN ordenes_canceladas oca ON c."netsuiteId" = oca.netsuite_id
LEFT JOIN pagos p                ON c."netsuiteId" = p.netsuite_id
WHERE c."netsuiteId" IS NOT NULL;

CREATE UNIQUE INDEX ix_grid_bnpl_pk    ON bnpl.grid_bnpl (netsuite_id);
CREATE INDEX ix_grid_bnpl_cohort       ON bnpl.grid_bnpl (enrollment_cohort);
CREATE INDEX ix_grid_bnpl_activado     ON bnpl.grid_bnpl (bnpl_is_activated);
CREATE INDEX ix_grid_bnpl_customer     ON bnpl.grid_bnpl (customer_id);

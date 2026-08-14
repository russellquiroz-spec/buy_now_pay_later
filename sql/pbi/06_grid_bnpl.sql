-- Reemplaza: grid_bnpl.csv
-- Fuente:    bnpl.grid_bnpl
-- Grano:     cliente  (146,613 filas — TODOS los clientes, no solo los enrolados)
--
-- Es la tabla ancla del modelo: cuatro tablas cuelgan de grid_bnpl[netsuiteId]
-- (bnpl_par, bnpl_loss_rates, months_closes, overall_prev_post_bnpl_sales) mas
-- Top100InactiveCustomers en doble sentido. netsuiteId TIENE que salir como entero.
--
-- Tres columnas que no son copia directa:
--   * inferredGender <- gender. El legacy adivinaba el genero del nombre con gender_guesser;
--     la vista usa el campo `gender` que Mongo ya trae. El nombre de la columna se conserva.
--   * bnplEnrolledAtTimestamp: el CSV traia el epoch en milisegundos de Mongo. bnpl_enrolled_at
--     ya viene convertido a hora Mexico (UTC-6), asi que hay que devolverle las 6 horas para
--     reconstruir el epoch UTC original.
--   * bnplFirstOrderGrossSales sale como TEXTO. En el modelo la columna quedo tipada como string
--     (el CSV traia vacios) y no la usa ninguna medida. Cambiarla a numero es correcto, pero es
--     un cambio de modelo: hacerlo aparte y a proposito, no de rebote al cambiar el origen.
--
-- ── Por que el DISTINCT ON: netsuiteId TIENE que ser unico ──
--
-- bnpl.grid_bnpl tiene un indice unico sobre netsuite_id, pero es TEXTO: ' 351229' y '351229' son
-- dos valores distintos y el indice los acepta. Al castear a bigint colapsan, y entonces 70 ids
-- quedan duplicados — lo que rompe las cinco relaciones que apuntan a esta columna como lado
-- "uno". Power BI falla el refresh con valores duplicados en la llave.
--
-- Medido: las 70 filas con espacio estan TODAS vacias (0 ordenes, 0 enroladas, sin ruta, sin
-- shopName) y cada una tiene su gemela con datos, asi que descartarlas no pierde informacion.
-- Son registros fantasma de fintech-customers.
--
-- La regla no es "quita las que traen espacio" sino "quedate con la fila que mas sabe del
-- cliente", que sigue siendo correcta si manana el duplicado viene de otra forma:
-- enrolada > con ordenes > sin espacio > customer_id (para que sea determinista).
--
-- Se excluye tambien la fila con netsuiteId vacio. Power BI NO admite blancos en el lado "uno"
-- de una relacion varios-a-uno — falla con "contiene valores en blanco y esto no se permite" —
-- y de esta columna cuelgan cinco relaciones.
--
-- El costo es real y hay que saberlo: esa fila es un enrolamiento del cohort 2024-02 sin
-- netsuiteId, asi que el funnel cuenta 10,712 enrolados en vez de 10,713. No cruzaba con nada de
-- todos modos: sin netsuiteId no puede unirse a loss_rates, par ni months_closes.

WITH unicos AS (
    SELECT DISTINCT ON (nullif(trim(netsuite_id), '')::bigint) *
    FROM bnpl.grid_bnpl
    WHERE nullif(trim(netsuite_id), '') IS NOT NULL
    ORDER BY nullif(trim(netsuite_id), '')::bigint,
             bnpl_is_enrolled                   DESC,
             bnpl_orders_count                  DESC,
             (netsuite_id = trim(netsuite_id))  DESC,
             customer_id
)
SELECT
    nullif(trim(g.netsuite_id), '')::bigint             AS "netsuiteId",
    g.customer_id                                       AS "customerId",
    g.shopkeeper_id                                     AS "shopkeeperId",
    g.shop_name                                         AS "shopName",
    g.ruta                                              AS "ruta",
    g.supervisor                                        AS "supervisor",
    g.oficina                                           AS "oficina",
    g.tipo                                              AS "tipo",
    g.business_category                                 AS "business_category",
    g.shop_neighborhood                                 AS "shopNeighborhood",
    g.shop_zip_code                                     AS "shopZipCode",
    g.shop_town                                         AS "shopTown",
    g.shop_state                                        AS "shopState",
    g.shop_latitude                                     AS "shopLatitude",
    g.shop_longitude                                    AS "shopLongitude",
    g.customer_name                                     AS "customerName",
    g.customer_last_names                               AS "customerLastNames",
    g.gender                                            AS "inferredGender",
    g.customer_birthdate                                AS "customerBirthdate",
    g.customer_age                                      AS "customerAge",
    g.customer_age_at_eligibility                       AS "customerAgeAtEligibility",
    g.customer_age_at_enrollment                        AS "customerAgeAtEnrollment",
    g.customer_phone_number                             AS "customerPhoneNumber",
    g.customer_latitude                                 AS "customerLatitude",
    g.customer_longitude                                AS "customerLongitude",
    g.bnpl_eligible_at::date                                  AS "bnplEligibleAt",
    g.original_credit_limit::bigint                     AS "originalCreditLimit",
    g.credit_limit::bigint                              AS "creditLimit",
    (extract(epoch FROM g.bnpl_enrolled_at) + 21600) * 1000
                                                        AS "bnplEnrolledAtTimestamp",
    g.bnpl_enrolled_at::date                            AS "bnplEnrolledAt",
    g.bnpl_is_enrolled                                  AS "bnplIsEnrolled",
    g.enrollment_cohort                                 AS "enrollment_cohort",
    g.enrollment_channel                                AS "enrollmentChannel",
    g.bnpl_activated_at::date                                 AS "bnplActivatedAt",
    g.bnpl_is_activated                                 AS "bnplIsActivated",
    g.bnpl_activated_cohort_month                       AS "bnplActivatedCohortMonth",
    g.bnpl_activated_line_of_credit                     AS "bnplActivatedLineOfCredit",
    g.bnpl_first_order_at::date                               AS "bnplFirstOrderdAt",
    g.bnpl_last_order_at::date                                AS "bnplLastOrderAt",
    g.bnpl_orders_count                                 AS "bnplOrdersCount",
    g.bnpl_completed_orders_count                       AS "bnplCompletedOrdersCount",
    g.bnpl_rejected_orders_count                        AS "bnplRejectedOrdersCount",
    g.bnpl_cancelled_orders_count                       AS "bnplCancelledOrdersCount",
    g.bnpl_avg_order_volume                             AS "bnplAvgOrderVolume",
    g.bnpl_total_order_volume                           AS "bnplTotalOrderVolume",
    g.bnpl_completed_order_volume                       AS "bnplCompletedOrderVolume",
    g.bnpl_first_order_gross_sales::text                AS "bnplFirstOrderGrossSales",
    g.bnpl_order_frequency::double precision            AS "bnplOrderFrequency",
    g.bnpl_due_for_payment_orders_count                 AS "bnplDueForPaymentOrdersCount",
    g.bnpl_payments_count                               AS "bnplPaymentsCount",
    g.bnpl_avg_revenue                                  AS "bnplAvgRevenue",
    g.bnpl_avg_revenue_share                            AS "bnplAvgRevenueShare",
    g.bnpl_revenue                                      AS "bnplRevenue",
    g.bnpl_revenue_share                                AS "bnplRevenueShare",
    g.bnpl_is_active                                    AS "bnplIsActive"
FROM unicos g;

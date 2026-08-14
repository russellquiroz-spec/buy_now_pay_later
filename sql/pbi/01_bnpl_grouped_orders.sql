-- Reemplaza: bnpl_grouped_orders.csv
--            (C:\Users\RodolfoGonzalezOrta\Documents\Rabbit Analytics\Buy Now Pay Later Automation\)
-- Fuente:    bnpl.grouped_orders  +  bnpl.dim_ruta_actual
-- Grano:     cliente x sales order x order_id x status x canal  (99,019 filas)
--
-- Los alias van en camelCase entre comillas dobles a proposito: son los nombres EXACTOS de las
-- columnas del CSV. Si cambian, se rompen las 28 medidas de la tabla y las relaciones del modelo.
--
-- Dos cosas que no son obvias:
--   * netsuiteId se queda como TEXTO. En el modelo esta tabla es la unica cuyo netsuiteId es
--     string y no int64, y no tiene relacion con grid_bnpl. Convertirlo a numero cambiaria el
--     tipo de la columna en el modelo sin que nada lo pida.
--   * tipo y tipoActual son DISTINTOS y ambos existen en el CSV: `tipo` es el del momento de la
--     orden (ruta historica, ya viene en grouped_orders) y `tipoActual` es el de hoy
--     (dim_ruta_actual). El CSV traia los dos y el tablero usa tipoActual en las audiencias.

SELECT
    o.netsuite_id                                       AS "netsuiteId",
    o.sales_order_id                                    AS "salesOrderId",
    o.order_id                                          AS "orderId",
    o.order_status                                      AS "orderStatus",
    o.delivery_status                                   AS "deliveryStatus",
    o.sales_channel                                     AS "salesChannel",
    o.created_at_ms                                     AS "createdAtTimestamp",
    o.created_at::date                                  AS "createdAt",
    o.order_gross_sales                                 AS "orderGrossSales",
    o.total_price                                       AS "totalPrice",
    o.credit_limit                                      AS "creditLimit",
    o.skus                                              AS "skus",
    o.quantity::bigint                                  AS "quantity",
    o.delivery_at::date                                 AS "deliveryAt",
    o.delivery_date::date                               AS "deliveryDate",
    o.customer_order_try_index                          AS "customerOrderTryIndex",
    o.customer_completed_order_index                    AS "customerCompletedOrderIndex",
    o.bnpl_enrolled_at::date                            AS "bnplEnrolledAt",
    o.enrollment_cohort                                 AS "enrollment_cohort",
    o.enrolled_customers                                AS "EnrolledCustomers",
    o.enrolled_credit_limit_cohort                      AS "enrolledCreditLimit",
    o.bnpl_activated_at::date                           AS "bnplActivatedAt",
    o.activated_cohort                                  AS "activatedCohort",
    o.months_since_enrollment                           AS "monthsSinceEnrollment",
    o.months_since_activation                           AS "monthsSinceActivation",
    o.month_created_at                                  AS "monthCreatedAt",
    o.ruta                                              AS "ruta",
    o.supervisor                                        AS "supervisor",
    o.oficina                                           AS "oficina",
    o.tipo                                              AS "tipo",
    dr.tipo                                             AS "tipoActual"
FROM bnpl.grouped_orders o
-- Sin trim() en la llave a proposito: ambos lados vienen limpios (0 filas con espacios en las
-- dos vistas, verificado) y envolver la columna anula el indice unico de dim_ruta_actual. Con
-- trim el join se va a seq scan sobre 611K filas y el refresh se cuelga.
LEFT JOIN bnpl.dim_ruta_actual dr ON o.netsuite_id = dr.netsuite_id;

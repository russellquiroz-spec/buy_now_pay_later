-- Reemplaza: months_closes.csv
-- Fuente:    bnpl.par_snapshot  +  bnpl.loss_rates  (la MISMA fuente que 03_bnpl_par.sql)
-- Grano:     orden x corte mensual  (~1.06M filas)
--
-- months_closes y bnpl_par son la misma tabla con otra ropa. Diferencias, todas cosmeticas:
--   * la columna del bucket se llama dqBucket en vez de PAR
--   * month es una FECHA (primer dia del mes del corte), no el texto 'YYYY-MM'
--   * no trae limitToReceiveOrdersInMont
--
-- Se dejan las dos consultas porque el modelo tiene relaciones y medidas colgando de cada una
-- (months_closes.dqBucket -> dq_order.PAR, months_closes.salesOrderId ->
-- loans_matured_default_profile.salesOrderId, la medida closeMonthDenominator). Fusionarlas es
-- una limpieza que vale la pena, pero es un cambio de modelo, no de origen: ver el README.
--
-- ── Filtro opcional: quitar PaidPrev ──
--
-- 911,713 de las 1,061,120 filas (85.9%) traen dqBucket = 'PaidPrev': ordenes ya pagadas antes
-- del mes del corte. par_snapshot les pone total_amount = 0 a proposito, para no inflar el saldo
-- vivo del cohort. Como 'PaidPrev' no esta entre los 8 valores de dq_order, esas filas caen en la
-- fila en blanco de esa relacion y aparecen como una categoria mas — siempre con $0 — en el
-- slicer de dqBucket y en las leyendas.
--
-- Quitarlas NO mueve ninguna cifra: los cinco visuales que consumen esta tabla la usan solo como
-- corte / Sum(totalAmount) / dqBucket / newDQBucket / closeMonthDenominator. Ninguno cuenta filas
-- y el totalAmount de PaidPrev suma exactamente 0.00 (verificado).
--
-- No viene activo porque no se puede comprobar si el CSV original las traia: el archivo ya no
-- existe. Migra primero tal cual; si al abrir el tablero 'PaidPrev' aparece como opcion nueva del
-- slicer, agrega al final, antes del `;`:
--
--     WHERE p.par <> 'PaidPrev'
--
-- Baja la tabla de 1,061,120 a 149,407 filas.

SELECT
    nullif(trim(p.netsuite_id), '')::bigint             AS "netsuiteId",
    p.sales_order_id                                    AS "salesOrderId",
    p.order_status                                      AS "orderStatus",
    p.created_at::date                                        AS "createdAt",
    p.order_gross_sales                                 AS "orderGrossSales",
    p.quantity::bigint                                  AS "quantity",
    p.delivery_at::date                                       AS "deliveryAt",
    p.bnpl_enrolled_at::date                                  AS "bnplEnrolledAt",
    (p.enrollment_cohort || '-01')::date                AS "enrollment_cohort",
    p.enrolled_customers                                AS "EnrolledCustomers",
    p.enrolled_credit_limit_cohort::bigint              AS "enrolledCreditLimit",
    l.months_since_enrollment                           AS "monthsSinceEnrollment",
    l.ruta                                              AS "ruta",
    l.supervisor                                        AS "supervisor",
    l.oficina                                           AS "oficina",
    l.tipo                                              AS "tipo",
    l.rank_completadas                                  AS "rank",
    p.transaction_id                                    AS "transaction_id",
    p.total_amount_to_pay                               AS "totalAmountToPay",
    p.total_amount                                      AS "totalAmount",
    p.interests                                         AS "interests",
    p.total_amount_default::bigint                      AS "totalAmountDefault",
    p.movement_date::text                               AS "movementDate",
    p.payment_date::text                                AS "paymentDate",
    p.paid_date::date                                         AS "paidDate",
    p.expected_payment_date::date                             AS "expectedPaymentDate",
    p.end_of_month_expected_payment_date::date                AS "endOfTheMonthexpectedPaymentDate",
    p.corte::date                                             AS "corte",
    p.days_past_due                                     AS "daysPastDue",
    p.par                                               AS "dqBucket",
    date_trunc('month', p.corte)::date                  AS "month"
FROM bnpl.par_snapshot p
LEFT JOIN bnpl.loss_rates l
       ON p.netsuite_id = l.netsuite_id
      AND p.sales_order_id = l.sales_order_id;

-- Reemplaza: bnpl_par.csv
-- Fuente:    bnpl.par_snapshot  +  bnpl.loss_rates (para rank y estructura comercial)
-- Grano:     orden x corte mensual  (~1.06M filas)
--
-- par_snapshot ya es exactamente esta tabla: una fila por orden y por corte de fin de mes, con
-- el saldo vivo y el bucket PAR a esa fecha. Lo unico que no trae son cinco columnas que el CSV
-- si tenia y que viven en loss_rates: rank, ruta, supervisor, oficina y tipo.
--
-- monthsSinceEnrollment tambien sale de loss_rates y NO de par_snapshot: son cosas distintas.
--   loss_rates.months_since_enrollment        meses entre el enrolamiento y LA ORDEN
--   par_snapshot.months_from_enrollment_to_month  meses entre el enrolamiento y EL CORTE
-- El CSV traia el primero. El segundo es el eje del vintage y va en 05_vintage_analysis.sql.
--
-- enrollment_cohort sale como DATE (primer dia del mes), no como texto 'YYYY-MM': en esta tabla
-- y en months_closes el modelo la tiene tipada como fecha, al reves que en loss_rates.
--
-- Filtro opcional, el mismo que en 04_months_closes.sql: agregar `WHERE p.par <> 'PaidPrev'` al
-- final quita el 85.9% de las filas sin mover ninguna cifra (su totalAmount suma 0.00). Ver esa
-- consulta para el detalle y por que no viene activo.

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
    l.rank_completadas                                  AS "rank",
    p.transaction_id                                    AS "transaction_id",
    p.total_amount_to_pay                               AS "totalAmountToPay",
    p.total_amount                                      AS "totalAmount",
    p.interests                                         AS "interests",
    p.total_amount_default                              AS "totalAmountDefault",
    p.movement_date::text                               AS "movementDate",
    p.payment_date                                      AS "paymentDate",
    p.paid_date::date                                         AS "paidDate",
    p.expected_payment_date::date                             AS "expectedPaymentDate",
    p.end_of_month_expected_payment_date::date                AS "endOfTheMonthexpectedPaymentDate",
    p.limite_mes_anterior::date                               AS "limitToReceiveOrdersInMont",
    p.corte::date                                             AS "corte",
    p.days_past_due                                     AS "daysPastDue",
    p.par                                               AS "PAR",
    p.month                                             AS "month",
    l.ruta                                              AS "ruta",
    l.supervisor                                        AS "supervisor",
    l.oficina                                           AS "oficina",
    l.tipo                                              AS "tipo"
FROM bnpl.par_snapshot p
LEFT JOIN bnpl.loss_rates l
       ON p.netsuite_id = l.netsuite_id
      AND p.sales_order_id = l.sales_order_id;

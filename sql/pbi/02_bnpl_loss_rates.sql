-- Reemplaza: bnpl_loss_rates.csv
-- Fuente:    bnpl.loss_rates  +  conteo de activados por cohort (bnpl.grid_bnpl)
-- Grano:     orden entregada  (92,009 filas)
--
-- La tabla del tablero tiene 37 columnas de origen y 20 columnas calculadas en DAX
-- (stage1..stage7, loanDisbursementIndex, cac, paidAmount, lossAmount, ...). Esta consulta
-- devuelve solo las 37 de origen; las calculadas siguen viviendo en el modelo y no se tocan.
--
-- everActivatedCustomers es la unica columna que loss_rates no trae: es el conteo de clientes
-- del cohort que alguna vez activaron, repetido en cada fila del cohort. Sale del grid.
--
-- Ojo con dos tipos que el CSV traia "mal" y el modelo ya heredo. Se conservan para no cambiar
-- el tipo de la columna en el modelo:
--   movementDate / paymentDate  ->  texto (paidDate si es fecha)
--   totalAmountDefault / enrolledCreditLimit  ->  entero

WITH activados_por_cohort AS (
    SELECT enrollment_cohort, count(*) AS ever_activated_customers
    FROM bnpl.grid_bnpl
    WHERE bnpl_is_activated = 1 AND enrollment_cohort IS NOT NULL
    GROUP BY 1
)
SELECT
    nullif(trim(l.netsuite_id), '')::bigint              AS "netsuiteId",
    l.sales_order_id                                    AS "salesOrderId",
    l.order_status                                       AS "orderStatus",
    l.created_at::date                                         AS "createdAt",
    l.order_gross_sales                                  AS "orderGrossSales",
    l.credit_limit                                       AS "creditLimit",
    l.quantity::bigint                                   AS "quantity",
    l.delivery_at::date                                        AS "deliveryAt",
    l.bnpl_enrolled_at::date                                   AS "bnplEnrolledAt",
    l.enrollment_cohort                                  AS "enrollment_cohort",
    l.enrolled_customers                                 AS "EnrolledCustomers",
    coalesce(a.ever_activated_customers, 0)              AS "everActivatedCustomers",
    l.enrolled_credit_limit_cohort::bigint               AS "enrolledCreditLimit",
    l.months_since_enrollment                            AS "monthsSinceEnrollment",
    l.ruta                                               AS "ruta",
    l.supervisor                                         AS "supervisor",
    l.oficina                                            AS "oficina",
    l.tipo                                               AS "tipo",
    l.rank_completadas                                   AS "rank",
    l.transaction_id                                     AS "transaction_id",
    l.total_amount_to_pay                                AS "totalAmountToPay",
    l.total_amount                                       AS "totalAmount",
    l.interests                                          AS "interests",
    l.total_amount_default::bigint                       AS "totalAmountDefault",
    l.movement_date::text                                AS "movementDate",
    l.payment_date::text                                 AS "paymentDate",
    l.paid_date                                          AS "paidDate",
    l.expected_payment_date::date                              AS "expectedPaymentDate",
    l.end_of_month_expected_payment_date::date                 AS "endOfTheMonthexpectedPaymentDate",
    l.month                                              AS "month",
    l.paid_on_month                                      AS "paidOnMonth",
    l.days_past_due                                      AS "daysPastDue",
    l.days_past_due_end_of_month                         AS "daysPastDueEndOfTheMonth",
    l.default_interest::double precision                 AS "defaultInterest",
    l.total_revenue                                      AS "totalRevenue",
    l.rabbit_revenue                                     AS "rabbitRevenue",
    l.par                                                AS "PAR"
FROM bnpl.loss_rates l
LEFT JOIN activados_por_cohort a ON l.enrollment_cohort = a.enrollment_cohort;

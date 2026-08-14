-- Reemplaza: overall_prev_post_bnpl_sales.csv  (171 MB en SharePoint / OneDrive personal)
-- Fuente:    redshift_bnpl.ventas_cliente + bnpl.grid_bnpl + bnpl.grouped_orders
-- Grano:     cliente x sales order de Rabbit, alrededor del enrolamiento BNPL
-- Alimenta:  pagina "Cambio en Comportamiento de Compra"
--
-- Compara cuanto compraba el tendero ANTES de tener credito contra cuanto compra DESPUES. Por eso
-- son ventas Rabbit completas, no solo BNPL, y por eso `ventas_cliente` arranca en 2021: el CSV
-- llega a 57 meses antes del enrolamiento.
--
-- ── Las tres columnas que definen la comparacion ────────────────────────────────────────
--
-- monthsToOrSinceEnrollment  meses calendario entre la orden y el enrolamiento; negativo antes.
--                            Verificado contra el CSV: cuadra en el 100.00% de las filas.
-- treshold                   'prev BNPL' / 'post BNPL'. El corte NO es por mes sino por fecha
--                            exacta: dentro del mes del enrolamiento hay filas de los dos lados
--                            (21,002 post y 9,040 prev en el CSV), asi que se parte comparando
--                            created_at contra bnpl_enrolled_at.
-- type                       'bnpl' si la orden se pago con credito; si no, el canal:
--                            'pre-sales' (Fuerza de Ventas) o 'marketplace' (lo demas).
--                            En el CSV, type='bnpl' es 100% post BNPL, como debe ser.
--
-- ── Columnas que salen NULL a proposito ─────────────────────────────────────────────────
--
-- `comparable` y `externalId` no se pueden derivar. `comparable` es un flag yes/no que en el CSV
-- ni siquiera es funcion de (cliente, mes) — solo el 92.7% de esos grupos tiene un valor unico —
-- y no coincide con las dos lecturas obvias (ventana simetrica 77.3%, mes espejo 77.5%).
--
-- No estorba: se rastrearon los visuales y todo el DAX del modelo, y NADIE usa `comparable`,
-- `externalId`, `validMonth`, `maxMonthPostBNPL`, `rank`, `skus`, `quantity`, `orderStatus`,
-- `bnplEnrolledAt`, `supervisor` ni `tipo`. Las que si se usan son 11, y todas se calculan aqui.
-- Aun asi se devuelven las 22 para no alterar el modelo; las derivables van con su valor real.
--
-- ── Esta consulta devuelve MAS filas que el CSV, y es correcto ──────────────────────────
--
-- Comparado contra el archivo, acotando a sus mismos clientes y a ordenes creadas antes de su
-- fecha de corte, el error en numero de ordenes es 16.4%, repartido asi:
--
--     post BNPL  bnpl          -7.1%
--     post BNPL  marketplace  +84.7%
--     post BNPL  pre-sales    +48.6%
--     prev BNPL  marketplace  +15.9%
--     prev BNPL  pre-sales     -9.2%
--
-- El tipo `bnpl`, que es el unico que se puede cruzar contra una fuente propia, cuadra a -7%. Lo
-- que sobra son ordenes NO-BNPL posteriores al enrolamiento, y la razon es que el CSV es un
-- subconjunto ya filtrado: `validMonth` vale 1 en el 100% de sus filas, o sea que las filas que
-- no cumplian la regla de validez se borraron antes de guardarlo. La regla no se puede recuperar
-- del archivo — solo sobreviven las que la pasaron.
--
-- No es un problema para el tablero: la columna calculada `validMonths` del modelo vuelve a
-- aplicar ese filtro sobre lo que se cargue. Cargar el universo completo y dejar que el DAX
-- filtre es mas correcto que cargar un subconjunto ya recortado con una regla que nadie conoce.
--
-- Ojo: `MaxMonthsSinceEnrollmentPostBNPLMetric` se calcula sobre los datos cargados, asi que con
-- el universo completo esa medida va a dar un valor distinto al que daba con el CSV. Comparar esa
-- pagina antes y despues de conectar.
--
-- Se probo tambien filtrar por status ('ENTREGADO', o ENTREGADO + PARCIALMENTE) porque el CSV
-- trae orderStatus = COMPLETED en todas sus filas. Empeora: el error sube de 16.4% a 51.5%,
-- porque en las tablas de 2021-2022 el status no viene poblado igual y se pierde el 72% de
-- prev BNPL / pre-sales. Por eso no hay filtro de status.
--
-- ── Una diferencia inevitable ───────────────────────────────────────────────────────────
--
-- grossSales y finalPrice salen ambas de monto_venta, que es lo unico que hay en Redshift. En el
-- CSV coinciden en el 77.6% de las filas y cuando difieren la razon es 0.96 — finalPrice trae
-- descuentos aplicados. O sea: finalPrice queda sobrestimada ~4% en una de cada cinco filas.

WITH enrolados AS (
    SELECT netsuite_id, bnpl_enrolled_at, enrollment_cohort, ruta, supervisor, oficina, tipo
    FROM bnpl.grid_bnpl
    WHERE bnpl_enrolled_at IS NOT NULL
),
ordenes_bnpl AS (
    -- Para marcar type='bnpl': que sales orders se pagaron con credito.
    SELECT DISTINCT sales_order_id FROM bnpl.grouped_orders
    WHERE order_status = ANY (bnpl.estados_activacion())
),
base AS (
    SELECT
        e.netsuite_id,
        e.bnpl_enrolled_at,
        e.enrollment_cohort,
        e.ruta, e.supervisor, e.oficina, e.tipo,
        v.sales_order_id,
        v.fecha_creacion,
        v.status_pedido,
        v.skus,
        v.piezas,
        v.monto_venta,
        (b.sales_order_id IS NOT NULL)                          AS es_bnpl,
        v.clase_canal,
        (extract(year FROM v.fecha_creacion)::int - extract(year FROM e.bnpl_enrolled_at)::int) * 12
        + (extract(month FROM v.fecha_creacion)::int - extract(month FROM e.bnpl_enrolled_at)::int)
                                                                AS meses,
        (v.fecha_creacion >= e.bnpl_enrolled_at::date)          AS es_post,
        row_number() OVER (PARTITION BY e.netsuite_id
                           ORDER BY v.fecha_creacion DESC, v.sales_order_id) AS rnk
    FROM enrolados e
    JOIN redshift_bnpl.ventas_cliente v ON v.netsuite_id = e.netsuite_id
    LEFT JOIN ordenes_bnpl b            ON b.sales_order_id = v.sales_order_id
),
tope AS (
    -- El mes mas lejano con actividad DESPUES del enrolamiento. Es lo mismo que recalcula la
    -- columna DAX MaxMonthsSinceEnrollmentPostBNPL.
    SELECT netsuite_id, max(meses) AS max_post
    FROM base WHERE es_post GROUP BY 1
)
SELECT
    -- ENTERO y no texto, aunque el M lo declare `type text`. Esta columna tiene relacion contra
    -- grid_bnpl.netsuiteId, que es int64, y Power BI no cruza texto con entero. Es una
    -- inconsistencia que ya venia en el modelo: de las cinco tablas que apuntan a grid_bnpl por
    -- netsuiteId, esta era la unica declarada string. Gana la relacion.
    nullif(trim(b.netsuite_id), '')::bigint             AS "netsuiteId",
    b.sales_order_id                                    AS "salesOrderId",
    b.status_pedido                                     AS "orderStatus",
    b.fecha_creacion::timestamp                         AS "createdAt",
    b.meses                                             AS "monthsToOrSinceEnrollment",
    b.monto_venta                                       AS "grossSales",
    b.monto_venta                                       AS "finalPrice",
    b.skus                                              AS "skus",
    b.piezas::bigint                                    AS "quantity",
    b.rnk                                               AS "rank",
    CASE WHEN b.es_post THEN 'post BNPL' ELSE 'prev BNPL' END AS "treshold",
    NULL::text                                          AS "comparable",
    CASE WHEN b.es_bnpl                            THEN 'bnpl'
         WHEN b.clase_canal = 'Fuerza de Ventas'   THEN 'pre-sales'
         ELSE 'marketplace' END                         AS "type",
    b.bnpl_enrolled_at::timestamp                       AS "bnplEnrolledAt",
    b.enrollment_cohort                                 AS "enrollment_cohort",
    t.max_post                                          AS "maxMonthPostBNPL",
    1::bigint                                           AS "validMonth",
    NULL::text                                          AS "externalId",
    b.ruta                                              AS "ruta",
    b.supervisor                                        AS "supervisor",
    b.oficina                                           AS "oficina",
    b.tipo                                              AS "tipo"
FROM base b
LEFT JOIN tope t ON t.netsuite_id = b.netsuite_id;

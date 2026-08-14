-- Concurso Credito Rabbit — base unica del tablero
-- Fuente:  bnpl.grouped_orders + bnpl.dim_ruta_actual + bnpl.grid_bnpl
-- Grano:   1 fila por (cliente, sales order) creada en la ventana
--
-- Tabla plana, sin reglas del concurso: no trae brackets, ni bono, ni "cliente contado". Todo
-- eso se hace en DAX. Aqui solo estan los hechos y las dimensiones que esas reglas necesitan.
--
-- LO UNICO QUE HAY QUE SABER PARA MEDIR BIEN: el grano es la ORDEN, no el cliente. Un cliente
-- con tres pedidos son tres filas. Para contar clientes colocados va DISTINCTCOUNT, nunca
-- COUNTROWS:
--
--     Clientes colocados =
--         CALCULATE(DISTINCTCOUNT(concurso_base[netsuiteId]), concurso_base[esEntregada] = TRUE)
--
-- Ese DISTINCTCOUNT resuelve solo el "un cliente cuenta una vez" del concurso. Ojo con el
-- desglose por aliado: si un cliente compro en dos rutas distintas dentro de la ventana, la
-- suma por aliado da mas que el total. Es correcto en cada fila y no cuadra en el total — si
-- eso importa para pagar, hay que fijar la ruta de la PRIMERA orden entregada del cliente
-- (columna `esPrimeraOrdenEntregadaEnVentana`, que ya viene marcada).
--
-- La ventana trae DOS periodos del mismo largo para poder comparar:
--   'Concurso'  18 al 30 de agosto
--   'Previo'    los 13 dias inmediatos anteriores (5 al 17 de agosto)
-- `diaVentana` va 1..13 en los dos, asi que una grafica por diaVentana con leyenda `periodo`
-- compara el concurso contra su linea base sin nada de DAX. Casi todos los visuales quieren
-- filtrar periodo = 'Concurso'.
--
-- Para mover fechas: el CTE `parametros`, aqui abajo. El periodo previo se recalcula solo.

WITH parametros AS (
    SELECT '2026-08-18'::date AS vigencia_desde,
           '2026-08-30'::date AS vigencia_hasta
),
ventana AS (
    SELECT
        p.vigencia_desde,
        p.vigencia_hasta,
        (p.vigencia_hasta - p.vigencia_desde + 1)                    AS dias,
        p.vigencia_desde - (p.vigencia_hasta - p.vigencia_desde + 1) AS previo_desde,
        p.vigencia_desde - 1                                         AS previo_hasta
    FROM parametros p
),
ordenes AS (
    -- grouped_orders trae varias filas por sales order: un order_id por SKU, y una fila mas por
    -- cada cambio de status. Sin este colapso, cualquier conteo de ordenes o suma de monto sale
    -- inflado por el numero de SKUs.
    --
    -- ruta/supervisor/oficina/region son constantes dentro de la orden (se derivan de
    -- netsuite_id + created_at::date contra el SCD), asi que min() no elige: desempaqueta.
    SELECT
        o.netsuite_id,
        o.sales_order_id,
        min(o.created_at)                                          AS created_at,
        max(o.delivery_date)                                       AS delivery_date,
        min(o.ruta)                                                AS ruta,
        min(o.supervisor)                                          AS supervisor,
        min(o.oficina)                                             AS oficina,
        min(o.region)                                              AS region,
        min(o.tipo)                                                AS tipo,
        -- coalesce en todos los booleanos: bool_or() sobre puros NULL devuelve NULL, no FALSE.
        -- Una orden sin registro en el reporte de entregas no es "entrega desconocida" para el
        -- concurso, es "no entregada"; y un booleano nulo llega a Power BI como blanco, que en
        -- un slicer aparece como tercera opcion y en un filtro `= TRUE` se cae sin avisar.
        coalesce(bool_or(o.ruta_inferida), false)                  AS ruta_inferida,
        max(o.order_gross_sales)                                   AS order_gross_sales,
        max(o.total_price)                                         AS total_price,
        max(o.credit_limit)                                        AS credit_limit,
        max(o.skus)                                                AS skus,
        max(o.quantity)                                            AS quantity,
        min(o.customer_order_try_index)                            AS customer_order_try_index,
        max(o.delivery_status)                                     AS delivery_status,
        -- Estatus representativo: el mas avanzado de los que tenga la orden.
        (array_agg(o.order_status ORDER BY CASE o.order_status
             WHEN 'COMPLETED'   THEN 1
             WHEN 'IN_DELIVERY' THEN 2
             WHEN 'CREATED'     THEN 3
             ELSE 4 END))[1]                                       AS order_status,
        coalesce(bool_or(o.delivery_status = 'COMPLETED'), false)  AS entregada,
        coalesce(bool_or(o.order_status = ANY (bnpl.estados_activacion())), false) AS vigente,
        coalesce(bool_or(o.order_status IN ('CANCELED', 'CANCELLED')), false)      AS cancelada,
        coalesce(bool_or(o.order_status = 'REJECTED'), false)      AS rechazada
    FROM bnpl.grouped_orders o
    WHERE o.created_at IS NOT NULL
    GROUP BY 1, 2
),
historia_cliente AS (
    -- Contexto del cliente ANTES de que abriera el concurso. Es lo que deja separar colocacion
    -- nueva de recompra sin volver a barrer la historia desde DAX.
    SELECT
        o.netsuite_id,
        min(o.created_at::date) FILTER (WHERE o.entregada)          AS primera_entregada,
        count(*) FILTER (
            WHERE o.entregada AND o.created_at::date < v.vigencia_desde
        )                                                           AS entregadas_previas,
        max(o.created_at::date) FILTER (
            WHERE o.entregada AND o.created_at::date < v.vigencia_desde
        )                                                           AS ultima_entregada_previa
    FROM ordenes o
    CROSS JOIN ventana v
    GROUP BY 1
),
en_ventana AS (
    SELECT
        o.*,
        v.vigencia_desde,
        v.previo_desde,
        (o.created_at::date >= v.vigencia_desde)                    AS en_vigencia,
        CASE WHEN o.created_at::date >= v.vigencia_desde
             THEN 'Concurso' ELSE 'Previo' END                      AS periodo,
        CASE WHEN o.created_at::date >= v.vigencia_desde
             THEN o.created_at::date - v.vigencia_desde + 1
             ELSE o.created_at::date - v.previo_desde + 1 END       AS dia_ventana,
        -- Primera orden entregada del cliente DENTRO de su periodo. Es el ancla para atribuir
        -- el cliente a una sola ruta cuando compro en varias.
        CASE WHEN o.entregada THEN
            row_number() OVER (
                PARTITION BY o.netsuite_id,
                             (o.created_at::date >= v.vigencia_desde),
                             o.entregada
                ORDER BY o.created_at, o.sales_order_id
            )
        END                                                         AS ix_entregada_periodo
    FROM ordenes o
    CROSS JOIN ventana v
    WHERE o.created_at::date BETWEEN v.previo_desde AND v.vigencia_hasta
)
SELECT
    -- ── Llaves ───────────────────────────────────────────────────────────────
    -- netsuiteId como texto, que es como vive en grouped_orders. `netsuiteIdNum` esta al lado
    -- para relacionar contra una lista de clientes que venga de Excel con la columna numerica:
    -- Power BI no relaciona texto contra entero, y descubrirlo con el modelo ya armado cuesta.
    w.netsuite_id                                       AS "netsuiteId",
    nullif(trim(w.netsuite_id), '')::bigint             AS "netsuiteIdNum",
    w.sales_order_id                                    AS "salesOrderId",

    -- ── Cliente ──────────────────────────────────────────────────────────────
    g.shop_name                                         AS "tienda",
    g.shop_town                                         AS "municipio",
    g.shop_state                                        AS "estado",
    g.bnpl_enrolled_at::date                            AS "fechaAprobacionCredito",
    g.enrollment_cohort                                 AS "cohorteEnrolamiento",
    g.enrollment_channel                                AS "canalEnrolamiento",

    -- ── Tiempo ───────────────────────────────────────────────────────────────
    w.created_at::date                                  AS "fechaCreacion",
    w.created_at                                        AS "createdAt",
    w.delivery_date::date                               AS "fechaEntrega",
    w.periodo                                           AS "periodo",
    w.en_vigencia                                       AS "enVigencia",
    w.dia_ventana                                       AS "diaVentana",

    -- ── Estructura comercial del dia de la orden (la que colocó) ─────────────
    coalesce(w.ruta, 'SIN RUTA')                        AS "aliado",
    coalesce(w.supervisor, 'SIN SUPERVISOR')            AS "supervisor",
    coalesce(w.oficina, 'SIN OFICINA')                  AS "oficina",
    coalesce(w.region, 'SIN REGION')                    AS "region",
    w.tipo                                              AS "tipo",
    w.ruta_inferida                                     AS "rutaInferida",

    -- ── Estructura comercial de hoy (para cuadrar contra el catalogo vigente) ─
    coalesce(dr.ruta, 'SIN RUTA')                       AS "aliadoActual",
    coalesce(dr.supervisor, 'SIN SUPERVISOR')           AS "supervisorActual",
    coalesce(dr.oficina, 'SIN OFICINA')                 AS "oficinaActual",
    coalesce(dr.region, 'SIN REGION')                   AS "regionActual",
    dr.tipo                                             AS "tipoActual",

    -- ── Estado de la orden ───────────────────────────────────────────────────
    w.order_status                                      AS "estatusOrden",
    w.delivery_status                                   AS "estatusEntrega",
    w.entregada                                         AS "esEntregada",
    w.vigente                                           AS "esVigente",
    w.cancelada                                         AS "esCancelada",
    w.rechazada                                         AS "esRechazada",

    -- ── Montos ───────────────────────────────────────────────────────────────
    w.order_gross_sales                                 AS "montoOrden",
    w.total_price                                       AS "precioTotal",
    w.credit_limit                                      AS "limiteCredito",
    w.skus                                              AS "skus",
    w.quantity                                          AS "piezas",

    -- ── Contexto del cliente, para que DAX decida quien es "nuevo" ───────────
    w.customer_order_try_index                          AS "indiceOrdenCliente",
    (w.customer_order_try_index = 1)                    AS "esPrimeraOrdenDelCliente",
    h.primera_entregada                                 AS "fechaPrimerCreditoUsado",
    coalesce(h.entregadas_previas, 0)                   AS "ordenesEntregadasPrevias",
    h.ultima_entregada_previa                           AS "ultimaOrdenEntregadaPrevia",
    (coalesce(h.entregadas_previas, 0) = 0)             AS "esNuevoEnCredito",

    -- ── Marca de desempate ───────────────────────────────────────────────────
    -- TRUE en la primera orden entregada del cliente dentro de su periodo. Sirve para atribuir
    -- el cliente a una sola ruta: filtrando por esta columna, COUNTROWS por aliado suma exacto
    -- al total. Sin ella, DISTINCTCOUNT por aliado sobrecuenta a quien compro en dos rutas.
    coalesce(w.ix_entregada_periodo = 1, false)         AS "esPrimeraOrdenEntregadaEnVentana"
FROM en_ventana w
-- Sin trim() en las llaves: ambos lados vienen limpios y envolver la columna anula el indice.
LEFT JOIN bnpl.dim_ruta_actual dr ON w.netsuite_id = dr.netsuite_id
LEFT JOIN bnpl.grid_bnpl g        ON w.netsuite_id = g.netsuite_id
LEFT JOIN historia_cliente h      ON w.netsuite_id = h.netsuite_id
ORDER BY w.created_at, w.netsuite_id, w.sales_order_id;

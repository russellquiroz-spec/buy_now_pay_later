-- Reemplaza: bnpl_audiencias_agg.csv
-- Fuente:    bnpl.grouped_orders
-- Grano:     mes x estado de ciclo de vida
-- Alimenta:  pagina "Audiencias" (3 visuales, medida `valor`)
--
-- `tipoActual` NO es la ruta ni el tipo de la estructura comercial: es la clasificacion mensual
-- de ciclo de vida del cliente de Rabbit (`tipo_actual_fin` de
-- analytics.clasificacion_mensual_clientes), aplicada aqui sobre la actividad BNPL en vez de
-- sobre la venta Rabbit. Misma regla, otro universo de pedidos.
--
-- Dos consecuencias que no son obvias:
--
--   * Es un PANEL cliente x mes, no un GROUP BY sobre ordenes. Dormant, Inactivo y Dropped son
--     clientes que NO compraron ese mes: aportan clientes pero $0 y 0 ordenes. Por eso el
--     CROSS JOIN contra la lista de meses.
--   * El equivalente BNPL de `amount_completed + amount_in_progress` (lo que la version Rabbit
--     considera venta) es bnpl.estados_activacion() = COMPLETED / CREATED / IN_DELIVERY. Medido:
--     con ese filtro el gross cuadra al 6.7% contra el CSV; sin filtro de status se va al 16.2%.
--
-- ── Diferencia deliberada con la regla de Rabbit ────────────────────────────────────────
--
-- En la version Rabbit, `Nuevo` es "activo Y su primera compra fue el mes ANTERIOR". Aqui es
-- "activo Y su primera compra fue ESTE mes". No es un descuido: con el ancla original, diciembre
-- de 2023 — el primer mes de BNPL — sale con cero Nuevos, y el CSV real tiene 11. Contrastado
-- contra el CSV sobre los meses estables:
--
--     ancla original (mes anterior)  ->  28.6% de error en clientes, 36.8% en gross
--     ancla este mes                 ->  11.0% de error en clientes,  6.7% en gross
--
-- ── Que tan bien reproduce el CSV ───────────────────────────────────────────────────────
--
-- Los primeros meses dan exacto en clientes (11, 37, 84, 311, 385) y el gross queda dentro de
-- +/-0.5% en 16 de 22 meses. Lo que no cuadra tiene explicacion conocida:
--
--     2025-10   el CSV se genero el 8 de octubre, o sea medio mes. No es un error.
--     2025-08+  el CSV quedo congelado ahi; el pipeline ya trae ordenes y cambios de estado
--               posteriores. La diferencia en clientes crece a +8/+13%, que es la deriva.
--     2024-11   +21% en gross y 2025-03 -11% en clientes: sin explicar, revisar si alguien
--               los necesita al centavo.
--
-- El CSV vive en D:\Shared drives\Data Room - BI & Data Analytics\Rabbit Risk Analytics\
-- Buy Now Pay Later\bnpl_audiencias_agg.csv, por si hay que volver a cotejar.

WITH pedidos_orden AS (
    SELECT
        netsuite_id,
        sales_order_id,
        date_trunc('month', created_at)::date            AS mes_pedido,
        -- MAX y no SUM: order_gross_sales viene repetido por linea de SKU.
        max(order_gross_sales)                           AS monto_venta
    FROM bnpl.grouped_orders
    WHERE created_at IS NOT NULL
      AND order_status = ANY (bnpl.estados_activacion())
    GROUP BY 1, 2, 3
    -- El mismo umbral que usa la version Rabbit para descartar pedidos simbolicos.
    HAVING max(order_gross_sales) > 10
),
clientes AS (
    SELECT netsuite_id, min(mes_pedido) AS mes_primera_compra
    FROM pedidos_orden
    GROUP BY 1
),
meses AS (
    SELECT generate_series(
        (SELECT min(mes_primera_compra) FROM clientes),
        date_trunc('month', bnpl.hoy_mx())::date,
        interval '1 month'
    )::date AS mes_ref
),
actividad AS (
    SELECT
        cm.netsuite_id,
        cm.mes_ref,
        cm.mes_primera_compra,
        max(CASE WHEN po.mes_pedido = cm.mes_ref                              THEN 1 ELSE 0 END) AS fl_act,
        max(CASE WHEN po.mes_pedido = (cm.mes_ref - interval '1 month')::date THEN 1 ELSE 0 END) AS fl_1m,
        max(CASE WHEN po.mes_pedido = (cm.mes_ref - interval '2 month')::date THEN 1 ELSE 0 END) AS fl_2m,
        max(CASE WHEN po.mes_pedido = (cm.mes_ref - interval '3 month')::date THEN 1 ELSE 0 END) AS fl_3m,
        max(CASE WHEN po.mes_pedido = (cm.mes_ref - interval '4 month')::date THEN 1 ELSE 0 END) AS fl_4m,
        max(CASE WHEN po.mes_pedido = (cm.mes_ref - interval '5 month')::date THEN 1 ELSE 0 END) AS fl_5m,
        count(DISTINCT CASE WHEN po.mes_pedido = cm.mes_ref THEN po.sales_order_id END) AS ordenes,
        coalesce(sum(CASE WHEN po.mes_pedido = cm.mes_ref THEN po.monto_venta END), 0)  AS gross_sales
    FROM (SELECT c.netsuite_id, m.mes_ref, c.mes_primera_compra
          FROM clientes c CROSS JOIN meses m) cm
    -- Solo se leen 6 meses hacia atras: es toda la memoria que la regla necesita.
    LEFT JOIN pedidos_orden po
           ON po.netsuite_id = cm.netsuite_id
          AND po.mes_pedido BETWEEN (cm.mes_ref - interval '6 month')::date AND cm.mes_ref
    GROUP BY 1, 2, 3
),
clasificado AS (
    SELECT
        a.*,
        CASE
            WHEN a.mes_primera_compra IS NULL
              OR a.mes_primera_compra > a.mes_ref                       THEN 'Sin actividad'
            WHEN a.fl_act = 1 AND a.mes_primera_compra = a.mes_ref      THEN 'Nuevo'
            WHEN a.fl_act = 1 AND a.fl_1m = 1 AND a.fl_2m = 1           THEN 'Recurrente'
            WHEN a.fl_act = 1 AND a.fl_1m = 0 AND a.fl_2m = 0
                 AND (a.fl_3m = 1 OR a.fl_4m = 1 OR a.fl_5m = 1
                      OR a.mes_primera_compra
                         < (a.mes_ref - interval '6 month')::date)      THEN 'Reactivado'
            WHEN a.fl_act = 1
                 AND ((a.fl_1m = 1 AND a.fl_2m = 0)
                   OR (a.fl_1m = 0 AND a.fl_2m = 1))                    THEN 'Intermitente'
            WHEN a.fl_act = 0 AND (a.fl_1m = 1 OR a.fl_2m = 1)          THEN 'Dormant'
            WHEN a.fl_act = 0 AND a.fl_1m = 0 AND a.fl_2m = 0
                 AND (a.fl_3m = 1 OR a.fl_4m = 1)                       THEN 'Inactivo'
            WHEN a.fl_act = 0 AND a.fl_1m = 0 AND a.fl_2m = 0
                 AND a.fl_3m = 0 AND a.fl_4m = 0
                 AND (a.fl_5m = 1
                      OR a.mes_primera_compra
                         < (a.mes_ref - interval '6 month')::date)      THEN 'Dropped'
            ELSE 'Excluir'
        END AS tipo_actual_fin
    FROM actividad a
)
SELECT
    -- timestamp y no date: el M la declara `type datetime` y la columna del modelo trae
    -- formatString 'General Date', sin la anotacion UnderlyingDateTimeDataType = Date.
    mes_ref::timestamp                                  AS "createdAtMonth",
    tipo_actual_fin                                     AS "tipoActual",
    sum(gross_sales)                                    AS "Gross Sales",
    count(DISTINCT netsuite_id)                         AS "Clientes",
    -- ::bigint porque sum() sobre bigint devuelve numeric, y el M declara la columna Int64.
    sum(ordenes)::bigint                                AS "ordenes"
FROM clasificado
-- 'Sin actividad' son meses previos al alta del cliente y 'Excluir' es el cajon de la regla;
-- ninguno de los dos aparece en el CSV.
WHERE tipo_actual_fin NOT IN ('Sin actividad', 'Excluir')
GROUP BY 1, 2
ORDER BY 1, 2;

-- PROPUESTA de paso nuevo del pipeline. No corre hoy: la tabla destino todavia no existe.
--
-- Es la pieza que le falta a tres entradas del tablero, todas por el mismo motivo: necesitan la
-- venta Rabbit COMPLETA (no solo la BNPL), y eso vive en Redshift.
--
--   loans_matured_default_profile   ordersCount*PostLastBnplOrder -> fraudFlag -> 2 paginas
--   overall_prev_post_bnpl_sales    venta del cliente antes y despues de enrolarse
--   bnpl_cosechas_agg               cosechas de TODA la base Rabbit, con flag BNPL
--
-- No puede ser una consulta de Power BI: cruza Redshift con PostgreSQL local. Tiene que ser un
-- paso de `etl_redshift_to_postgres.py` que aterrice el agregado, y luego vistas en `bnpl.`
-- que lo combinen con la capa BNPL — el mismo patron que ya usa la estructura comercial.
--
-- Se agrega por cliente x mes x canal a proposito: al grano de orden son ~300M filas y no cabe
-- por el tunel. Agregado son ~611K clientes x ~30 meses x 2 canales, manejable, y alcanza para
-- las tres entradas (los cortes de 3M/6M/post-BNPL se calculan despues, en SQL local).
--
-- clase_canal solo tiene dos valores, medidos sobre julio-2026:
--   'Fuerza de Ventas'  -> Aliado / preventa
--   'Tienda en linea'   -> Marketplace


-- ── Parte 1: extraccion desde Redshift (data-rabbit-prod) ────────────────────────────────
-- Va en etl_redshift_to_postgres.py como SQL_VENTAS_CLIENTE_MES, destino
-- redshift_bnpl.ventas_cliente_mes.

WITH source AS (
    SELECT ns_id, so_id, fecha_creacion_mx, clase_canal,
           COALESCE(amount_completed, 0) + COALESCE(amount_in_progress, 0)     AS monto_venta,
           COALESCE(quantity_completed, 0) + COALESCE(quantity_in_progress, 0) AS cantidad
      FROM analytics.mv_pedidos_enriquecidos_2025_v2
    UNION ALL
    SELECT ns_id, so_id, fecha_creacion_mx, clase_canal,
           COALESCE(amount_completed, 0) + COALESCE(amount_in_progress, 0),
           COALESCE(quantity_completed, 0) + COALESCE(quantity_in_progress, 0)
      FROM analytics.mv_pedidos_enriquecidos_2026_v2
),
por_orden AS (
    -- El monto viene repetido por linea de SKU: primero se colapsa a orden, igual que en
    -- bnpl.grouped_orders, y solo despues se suma.
    SELECT ns_id                                        AS netsuite_id,
           so_id                                        AS sales_order_id,
           date_trunc('month', fecha_creacion_mx)::date AS mes,
           clase_canal,
           SUM(monto_venta)                             AS monto_venta,
           SUM(cantidad)                                AS cantidad
      FROM source
     WHERE ns_id IS NOT NULL
     GROUP BY 1, 2, 3, 4
    HAVING SUM(cantidad) <> 0 OR SUM(monto_venta) <> 0
)
SELECT netsuite_id,
       mes,
       clase_canal,
       COUNT(DISTINCT sales_order_id) AS ordenes,
       SUM(monto_venta)               AS gross_sales,
       SUM(cantidad)                  AS piezas
  FROM por_orden
 GROUP BY 1, 2, 3;


-- ── Parte 2: DDL del destino ─────────────────────────────────────────────────────────────
-- Va en sql/12_redshift_staging.sql, para que el tipo no dependa de lo que pandas infiera.
--
-- CREATE TABLE IF NOT EXISTS redshift_bnpl.ventas_cliente_mes (
--     netsuite_id text,
--     mes         date,
--     clase_canal text,
--     ordenes     bigint,
--     gross_sales double precision,
--     piezas      double precision
-- );
-- CREATE INDEX IF NOT EXISTS ix_ventas_cliente_mes
--     ON redshift_bnpl.ventas_cliente_mes (netsuite_id, mes);


-- ── Parte 3: como se consume ─────────────────────────────────────────────────────────────
--
-- Con esa tabla en el staging, las columnas que hoy salen NULL en
-- 08_loans_matured_default_profile.sql se resuelven asi (patron, no consulta final):
--
--   WITH ultimo_bnpl AS (
--       SELECT netsuite_id, max(created_at)::date AS ultima_orden_bnpl
--       FROM bnpl.grouped_orders GROUP BY 1
--   ),
--   post AS (
--       SELECT v.netsuite_id,
--              sum(v.gross_sales) FILTER (WHERE v.clase_canal = 'Fuerza de Ventas') AS gs_aliado,
--              sum(v.ordenes)     FILTER (WHERE v.clase_canal = 'Fuerza de Ventas') AS ord_aliado,
--              sum(v.gross_sales) FILTER (WHERE v.clase_canal = 'Tienda en linea')  AS gs_mkt,
--              sum(v.ordenes)     FILTER (WHERE v.clase_canal = 'Tienda en linea')  AS ord_mkt
--       FROM redshift_bnpl.ventas_cliente_mes v
--       JOIN ultimo_bnpl u ON v.netsuite_id = u.netsuite_id
--       WHERE v.mes > date_trunc('month', u.ultima_orden_bnpl)
--       GROUP BY 1
--   )
--
-- y las ventanas de 3 y 6 meses previos al credito, con el mismo agregado filtrado por
-- v.mes BETWEEN mes_del_credito - N months AND mes_del_credito - 1 month.
--
-- Ojo con el corte de la ventana: `mes` es el mes de CREACION del pedido. Un pedido creado el
-- ultimo dia del mes y entregado al siguiente cuenta en el mes de creacion, que es como lo
-- cuenta el resto del pipeline (bnpl.grouped_orders.month_created_at).

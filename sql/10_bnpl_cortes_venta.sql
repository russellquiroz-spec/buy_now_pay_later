-- bnpl.corte_venta_sku y bnpl.corte_venta_so — el corte de venta semanal.
--
-- Porta el notebook legacy 'Cortes de Venta.ipynb'. Ventana movil: se ancla en el jueves mas
-- reciente y toma los CORTE_DIAS anteriores.
--
-- La ruta es la VIGENTE (dim_ruta_actual), no la historica: un corte semanal se reparte al
-- equipo que atiende la cuenta hoy. El legacy la tomaba de rutas_fintech.xlsx, que ya no existe.

CREATE OR REPLACE FUNCTION bnpl.corte_dias() RETURNS int
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT 8 $$;

-- Jueves mas reciente (incluido hoy si hoy es jueves). isodow: 4 = jueves.
CREATE OR REPLACE FUNCTION bnpl.ancla_corte(hoy date DEFAULT current_date) RETURNS date
    LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT hoy - ((extract(isodow FROM hoy)::int - 4 + 7) % 7)
$$;

DROP MATERIALIZED VIEW IF EXISTS bnpl.corte_venta_sku CASCADE;

CREATE MATERIALIZED VIEW bnpl.corte_venta_sku AS
SELECT
    bnpl.ancla_corte()                                     AS fecha_corte,
    bnpl.ancla_corte() - bnpl.corte_dias()                 AS ventana_desde,
    o."netsuiteId"                                         AS netsuite_id,
    dr.ruta,
    dr.supervisor,
    dr.oficina,
    dr.region,
    dr.tipo,
    o."salesOrderId"                                       AS sales_order_id,
    o."orderId"                                            AS order_id,
    bnpl.epoch_ms_a_mx(o."createdAt")                      AS created_at,
    bnpl.epoch_ms_a_mx(o."deliveryAt")                     AS delivery_at,
    o."orderStatus"                                        AS order_status,
    coalesce(o."salesChannel", 'MARKETPLACE')              AS sales_channel,
    o."productId"                                          AS product_id,
    o."productDescription"                                 AS product_description,
    o.category,
    o.subcategory,
    o.brand,
    o.vendor,
    o.quantity,
    o."totalPrice"                                         AS total_price,
    o."orderGrossSales"                                    AS order_gross_sales,
    o.iva,
    o.ieps,
    o."couponCode"                                         AS coupon_code,
    o."couponValue"                                        AS coupon_value
FROM mongo_bnpl.credit_order_production o
LEFT JOIN bnpl.dim_ruta_actual dr ON o."netsuiteId" = dr.netsuite_id
WHERE o."salesOrderId" IS NOT NULL AND trim(o."salesOrderId") <> ''
  AND bnpl.epoch_ms_a_mx(o."createdAt")::date
      >= bnpl.ancla_corte() - bnpl.corte_dias();

CREATE INDEX ix_corte_sku_so      ON bnpl.corte_venta_sku (sales_order_id);
CREATE INDEX ix_corte_sku_netsuite ON bnpl.corte_venta_sku (netsuite_id);

DROP MATERIALIZED VIEW IF EXISTS bnpl.corte_venta_so CASCADE;

CREATE MATERIALIZED VIEW bnpl.corte_venta_so AS
SELECT
    fecha_corte,
    ventana_desde,
    netsuite_id,
    ruta,
    supervisor,
    oficina,
    region,
    tipo,
    sales_order_id,
    order_id,
    max(created_at)                                        AS created_at,
    max(delivery_at)                                       AS delivery_at,
    order_status,
    sales_channel,
    -- order_gross_sales viene repetido en cada linea del SO: se toma el maximo, no la suma.
    max(order_gross_sales)                                 AS order_gross_sales,
    max(total_price)                                       AS total_price,
    count(DISTINCT product_id)                             AS skus,
    sum(quantity)                                          AS quantity
FROM bnpl.corte_venta_sku
GROUP BY fecha_corte, ventana_desde, netsuite_id, ruta, supervisor, oficina, region, tipo,
         sales_order_id, order_id, order_status, sales_channel;

CREATE UNIQUE INDEX ix_corte_so_pk ON bnpl.corte_venta_so (netsuite_id, sales_order_id, order_id);

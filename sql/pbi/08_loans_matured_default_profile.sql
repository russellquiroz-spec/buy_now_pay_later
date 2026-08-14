-- Reemplaza: loans_matured_default_profile.csv
-- Fuente:    bnpl.loss_rates + bnpl.grid_bnpl + redshift_bnpl.ventas_cliente
-- Grano:     credito ya vencido (una fila por orden entregada cuyo vencimiento ya paso)
-- Alimenta:  paginas "Default Customer Profile" y "Fraud"
--
-- ── Ojo con el tipo de loanDisbursementIndexRange ────────────────────────────────────────
--
-- Sale como TEXTO ('1', '2', '3+'), que es lo que traen los cuatro CSV del drive compartido
-- (loans_matured, vars_and_iv, odds_table, atr_combinations_iv). Pero la columna en el modelo
-- quedo tipada como int64, porque el .pbix cargo una version anterior en la que el rango era
-- numerico. Al conectar esta consulta hay que retipar la columna a texto — y hacerlo TAMBIEN en
-- vars_and_iv, o la relacion entre las dos deja de cruzar.
--
-- ── Las 5 columnas de otros productos fintech van vacias A PROPOSITO ─────────────────────
--
-- PSOnboardedAt y TPVOnboardedAt salen NULL y los tres flags salen 0. No es que falte la fuente:
-- el CSV original las trae asi. Medido sobre sus 77,143 filas: PSOnboardedAt y TPVOnboardedAt
-- tienen CERO valores no nulos, y psrtaPreviousToBnpl / tpvPreviousToBnpl /
-- previousFintechProductToBnpl son constante 0. Nunca se calcularon.
--
-- Si algun dia se quieren de verdad, el esquema `fintech` de Redshift ya las tiene:
-- funnel_ps.enrollmentat, funnel_tpv.activationdate y transactions_ps.tipo_tx (cuyos dos valores
-- son justo 'Pago de Servicios' y 'Recarga de Tiempo Aire' — el psrta del nombre). Pero eso es
-- construir algo nuevo, no reproducir el tablero.
--
-- ── Lo que si alimenta al tablero: las 4 columnas post-BNPL ──────────────────────────────
--
-- De ellas depende fraudFlag, que estructura las dos paginas:
--     fraudFlag <- ordersAfterLastBnplOrder <- ordersCountAliado + ordersCountMarketPlace
--
-- El ancla es la ultima orden BNPL YA VENCIDA del cliente, no la ultima orden a secas. Es lo
-- coherente con el alcance de la tabla (creditos vencidos) y es lo que mas se acerca al CSV.
-- Contrastado sobre los 8,845 clientes del archivo, en el booleano que fraudFlag necesita:
--
--     ancla = ultima orden de cualquier status   78.7%
--     ancla = ultima COMPLETED                   81.1%
--     ancla = ultima COMPLETED ya vencida        90.6%   <- esta
--
-- El 9% que sobra es deriva: el CSV es del 24-feb-2026 y la base ya trae ordenes y cambios de
-- estado posteriores. Congelar el corte a esa fecha lo empeora (74.9%), asi que no es el ancla.
--
-- ── Las ventanas de 3 y 6 meses NO reproducen el CSV, y da igual ─────────────────────────
--
-- Ningun visual ni medida las usa: solo alimentan el modelo de odds/IV, que es offline. En el CSV
-- venian de un lookup pre-calculado aparte (Default Profile\prev_3_months_sales_info.csv) y traen
-- un error: grossSalesVolume3Months y grossSalesVolume6Months son la MISMA columna, identicas en
-- el 100% de las filas. Aqui se calculan bien, cada una con su ventana, ancladas en la fecha de
-- elegibilidad — que es el momento de la decision de credito. No van a cuadrar con el archivo.

WITH ultima_vencida AS (
    -- Ultima orden BNPL del cliente que ya vencio (entrega + plazo de credito < hoy).
    SELECT netsuite_id, max(created_at)::date AS ultima_bnpl
    FROM bnpl.grouped_orders
    WHERE order_status = 'COMPLETED'
      AND delivery_at + (bnpl.dias_credito() || ' days')::interval < bnpl.ahora_mx()
    GROUP BY 1
),
post_bnpl AS (
    -- Venta Rabbit posterior, partida por canal. 'Fuerza de Ventas' es el Aliado (preventa);
    -- todo lo demas —'Tienda en linea' y los residuales Whatsapp / Auto Venta— cae en Marketplace.
    SELECT
        u.netsuite_id,
        coalesce(sum(v.monto_venta) FILTER (WHERE v.clase_canal =  'Fuerza de Ventas'), 0) AS gs_aliado,
        count(DISTINCT v.sales_order_id) FILTER (WHERE v.clase_canal =  'Fuerza de Ventas') AS n_aliado,
        coalesce(sum(v.monto_venta) FILTER (WHERE v.clase_canal <> 'Fuerza de Ventas'), 0) AS gs_mkt,
        count(DISTINCT v.sales_order_id) FILTER (WHERE v.clase_canal <> 'Fuerza de Ventas') AS n_mkt
    FROM ultima_vencida u
    LEFT JOIN redshift_bnpl.ventas_cliente v
           ON v.netsuite_id = u.netsuite_id
          AND v.fecha_creacion > u.ultima_bnpl
    GROUP BY 1
),
previo AS (
    -- Comportamiento de compra en Rabbit antes de la decision de credito.
    SELECT
        g.netsuite_id,
        coalesce(sum(v.monto_venta) FILTER (
            WHERE v.fecha_creacion >= (g.bnpl_eligible_at::date - interval '3 months')), 0) AS gs3,
        count(DISTINCT v.sales_order_id) FILTER (
            WHERE v.fecha_creacion >= (g.bnpl_eligible_at::date - interval '3 months'))     AS n3,
        coalesce(sum(v.monto_venta), 0)                                                    AS gs6,
        count(DISTINCT v.sales_order_id)                                                   AS n6
    FROM bnpl.grid_bnpl g
    LEFT JOIN redshift_bnpl.ventas_cliente v
           ON v.netsuite_id = g.netsuite_id
          AND v.fecha_creacion >= (g.bnpl_eligible_at::date - interval '6 months')
          AND v.fecha_creacion <   g.bnpl_eligible_at::date
    WHERE g.bnpl_eligible_at IS NOT NULL
    GROUP BY 1
)
SELECT
    row_number() OVER (ORDER BY l.netsuite_id, l.sales_order_id)  AS "Column1",
    nullif(trim(l.netsuite_id), '')::bigint             AS "netsuiteId",
    l.sales_order_id                                    AS "salesOrderId",
    l.order_id                                          AS "orderId",
    l.order_status                                      AS "orderStatus",
    l.created_at::date                                  AS "createdAt",
    l.expected_payment_date::date                       AS "expectedPaymentDate",
    l.paid_date::date                                   AS "paidDate",
    l.total_amount                                      AS "totalAmount",
    l.total_amount_to_pay                               AS "totalAmountToPay",
    l.days_past_due                                     AS "daysPastDue",
    l.rank_completadas                                  AS "loanDisbursementIndex",
    CASE WHEN l.rank_completadas = 1 THEN '1'
         WHEN l.rank_completadas = 2 THEN '2'
         ELSE '3+' END                                  AS "loanDisbursementIndexRange",
    CASE WHEN l.days_past_due >= 15 THEN 1 ELSE 0 END   AS "flag@15DaysLate",
    CASE WHEN l.days_past_due >= 30 THEN 1 ELSE 0 END   AS "flag@30DaysLate",
    g.bnpl_eligible_at::date                            AS "bnplEligibleAt",
    l.ruta                                              AS "ruta",
    l.supervisor                                        AS "supervisor",
    l.oficina                                           AS "oficina",
    l.tipo                                              AS "tipo",
    g.business_category                                 AS "business_category",
    g.shop_neighborhood                                 AS "shopNeighborhood",
    nullif(regexp_replace(g.shop_zip_code, '\D', '', 'g'), '')::bigint
                                                        AS "shopZipCode",
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
    g.customer_latitude                                 AS "customerLatitude",
    g.customer_longitude                                AS "customerLongitude",
    -- Haversine en METROS entre el domicilio del onboarding y la ubicacion de la tienda.
    -- El radio va en metros (6 371 000) y no en km a proposito: el original mide en metros.
    -- Se detecto comparando el max_value de odds_table.csv (1.095592e7) contra el maximo de esta
    -- formula en km (10,956) — la razon es exactamente 1000.0. Con km, cualquier corte o bin
    -- que alguien haya fijado sobre esta columna quedaria mil veces desfasado.
    CASE WHEN g.customer_latitude IS NOT NULL AND g.shop_latitude IS NOT NULL
              AND g.customer_longitude IS NOT NULL AND g.shop_longitude IS NOT NULL
         THEN 6371000 * 2 * asin(sqrt(
                  power(sin(radians(g.shop_latitude - g.customer_latitude) / 2), 2)
                + cos(radians(g.customer_latitude)) * cos(radians(g.shop_latitude))
                * power(sin(radians(g.shop_longitude - g.customer_longitude) / 2), 2)))
    END                                                 AS "distanceBetweenOnboardingAndShopLocation",
    -- Vacias en el CSV original tambien (ver cabecera).
    NULL::text                                          AS "PSOnboardedAt",
    NULL::text                                          AS "TPVOnboardedAt",
    0::bigint                                           AS "psrtaPreviousToBnpl",
    0::bigint                                           AS "tpvPreviousToBnpl",
    0::bigint                                           AS "previousFintechProductToBnpl",
    -- Comportamiento previo a la elegibilidad.
    coalesce(p.gs3, 0)                                  AS "grossSalesVolume3Months",
    coalesce(p.n3, 0)                                   AS "ordersCount3Months",
    CASE WHEN p.n3 > 0 THEN (p.gs3 / p.n3)::bigint ELSE 0 END AS "avgTicket3Months",
    coalesce(p.gs6, 0)                                  AS "grossSalesVolume6Months",
    coalesce(p.n6, 0)                                   AS "ordersCount6Months",
    -- Venta posterior al ultimo credito vencido: de aqui sale fraudFlag.
    coalesce(pb.gs_aliado, 0)                           AS "grossSalesAliadoPostLastBnplOrder",
    coalesce(pb.n_aliado, 0)                            AS "ordersCountAliadoPostLastBnplOrder",
    coalesce(pb.gs_mkt, 0)                              AS "grossSalesMarketPlacePostLastBnplOrder",
    coalesce(pb.n_mkt, 0)                               AS "ordersCountMarketPlacePostLastBnplOrder"
FROM bnpl.loss_rates l
LEFT JOIN bnpl.grid_bnpl g ON l.netsuite_id = g.netsuite_id
LEFT JOIN post_bnpl pb     ON l.netsuite_id = pb.netsuite_id
LEFT JOIN previo p         ON l.netsuite_id = p.netsuite_id
-- "Matured": solo creditos cuyo vencimiento ya paso. Uno que aun no vence no puede estar en mora.
WHERE l.expected_payment_date < bnpl.ahora_mx();

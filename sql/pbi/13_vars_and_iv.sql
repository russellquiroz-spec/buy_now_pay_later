-- Reemplaza: vars_and_iv.csv  (Default Profile\)
-- Fuente:    la misma agregacion de 12_odds_table.sql
-- Grano:     rango de credito x flag de mora x atributo  ->  6 filas
--
-- Es el resumen de 12_odds_table.sql: el IV total de cada atributo, que es la suma del IV de sus
-- bins. Sirve para ordenar atributos por poder predictivo.
--
-- Como solo hay un atributo (la distancia onboarding-tienda), salen 3 rangos x 2 flags = 6 filas.
-- Si algun dia se agregan atributos al 12, esta consulta los recoge sola.
--
-- Hereda los mismos pendientes que la 12: el corte del bin esta congelado del CSV de feb-2026 y
-- hay que confirmar con riesgo si debe recalcularse. Ver PENDIENTES_NEGOCIO.md.
--
-- El tipo de loanDisbursementIndexRange es TEXTO ('1', '2', '3+'), igual que en la 08 y en los
-- CSV del drive. En el modelo esa columna quedo como int64 y hay que retiparla en las dos tablas,
-- o la relacion entre loans_matured y vars_and_iv deja de cruzar.

WITH cortes(rango, corte) AS (
    -- PENDIENTE: congelados del CSV de feb-2026, igual que en 12_odds_table.sql.
    VALUES ('1', 8.980613), ('2', 8.312551), ('3+', 7.240108)
),
base AS (
    SELECT
        CASE WHEN l.rank_completadas = 1 THEN '1'
             WHEN l.rank_completadas = 2 THEN '2'
             ELSE '3+' END                                       AS rango,
        CASE WHEN l.days_past_due >= 15 THEN 1 ELSE 0 END        AS f15,
        CASE WHEN l.days_past_due >= 30 THEN 1 ELSE 0 END        AS f30,
        CASE WHEN g.customer_latitude IS NOT NULL AND g.shop_latitude IS NOT NULL
                  AND g.customer_longitude IS NOT NULL AND g.shop_longitude IS NOT NULL
             THEN 6371000 * 2 * asin(sqrt(
                      power(sin(radians(g.shop_latitude - g.customer_latitude) / 2), 2)
                    + cos(radians(g.customer_latitude)) * cos(radians(g.shop_latitude))
                    * power(sin(radians(g.shop_longitude - g.customer_longitude) / 2), 2)))
        END                                                      AS distancia
    FROM bnpl.loss_rates l
    LEFT JOIN bnpl.grid_bnpl g ON l.netsuite_id = g.netsuite_id
    WHERE l.expected_payment_date < bnpl.ahora_mx()
),
marcado AS (
    SELECT b.rango, f.flag, f.valor,
           CASE WHEN b.distancia IS NULL THEN NULL
                WHEN b.distancia <= c.corte THEN 0 ELSE 1 END AS bin
    FROM base b
    JOIN cortes c ON c.rango = b.rango
    CROSS JOIN LATERAL (VALUES ('flag@15DaysLate', b.f15), ('flag@30DaysLate', b.f30)) f(flag, valor)
),
agregado AS (
    SELECT rango, flag, bin,
           count(*) - sum(valor) AS good,
           sum(valor)            AS bad
    FROM marcado GROUP BY 1, 2, 3
),
con_totales AS (
    SELECT a.*,
           sum(good) OVER (PARTITION BY rango, flag)::numeric AS tot_good,
           sum(bad)  OVER (PARTITION BY rango, flag)::numeric AS tot_bad
    FROM agregado a
)
SELECT
    rango                                               AS "loanDisbursementIndexRange",
    flag                                                AS "flag",
    'distanceBetweenOnboardingAndShopLocation'          AS "attribute",
    sum(CASE WHEN good > 0 AND bad > 0
             THEN (bad / tot_bad - good / tot_good)
                  * ln((bad / tot_bad) / (good / tot_good))
             ELSE 0 END)::double precision              AS "iv"
FROM con_totales
GROUP BY 1, 2, 3
ORDER BY 2, 1;

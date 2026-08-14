-- Reemplaza: odds_table.csv  (Default Profile\)
-- Fuente:    la misma poblacion de 08_loans_matured_default_profile.sql
-- Grano:     rango de credito x flag de mora x bin del atributo  ->  18 filas
--
-- Tabla de WOE/IV de un solo atributo: la distancia entre el domicilio del onboarding y la
-- tienda. Mide si esa distancia separa a los que caen en mora de los que no.
--
-- ── Las formulas estan recuperadas del CSV, al digito ───────────────────────────────────
--
--     events   filas del bin
--     bad      las que traen el flag en 1;  good = events - bad
--     bad_rate bad / events
--     %good    good / suma de good del corte (rango x flag);  %bad igual con bad
--     woe      ln(%bad / %good)        <- INVERTIDO respecto a la convencion habitual
--     iv       (%bad - %good) * woe    <- coherente con el woe invertido
--
-- Lo de invertido no es un detalle: con ln(%good/%bad) el signo sale al reves en las 18 filas.
-- Se comprobo reproduciendo el rango 1 del archivo, valor por valor.
--
-- ── PENDIENTE: el corte del bin ─────────────────────────────────────────────────────────
--
-- El CSV parte la distancia en dos bins con un corte distinto por rango — 8.98 m para el rango 1,
-- 8.31 para el 2 y 7.24 para 3+ — o sea que el original lo derivaba de los datos (un split
-- supervisado, no un cuantil fijo). Aqui esos tres numeros van congelados en el CTE `cortes`,
-- que es lo unico que reproduce el archivo.
--
-- Hay que confirmar con quien lleve el modelo de riesgo si el corte debe recalcularse en cada
-- corrida o quedarse fijo. Si se recalcula, esto deja de ser una consulta y vuelve a ser modelo.
-- Ver PENDIENTES_NEGOCIO.md.
--
-- Ojo con la unidad: la distancia va en METROS, como en el original (ver la nota de la 08). Con
-- kilometros estos cortes quedarian mil veces desfasados.

WITH cortes(rango, corte) AS (
    -- PENDIENTE: congelados del CSV de feb-2026.
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
-- Una fila por (rango, flag, bin). El flag se despliega a las dos variantes.
marcado AS (
    SELECT b.rango, f.flag, f.valor,
           CASE WHEN b.distancia IS NULL THEN NULL
                WHEN b.distancia <= c.corte THEN 0 ELSE 1 END AS bin,
           b.distancia
    FROM base b
    JOIN cortes c ON c.rango = b.rango
    CROSS JOIN LATERAL (VALUES ('flag@15DaysLate', b.f15), ('flag@30DaysLate', b.f30)) f(flag, valor)
),
agregado AS (
    SELECT rango, flag, bin,
           min(distancia)                            AS min_value,
           max(distancia)                            AS max_value,
           count(*)                                  AS events,
           count(*) - sum(valor)                     AS good,
           sum(valor)                                AS bad
    FROM marcado
    GROUP BY 1, 2, 3
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
    -- bin, min_value y max_value van como TEXTO: asi los declara el M, aunque en el CSV se vean
    -- numericos. Power Query los leia como texto porque la columna trae vacios donde el atributo
    -- es nulo, y ese tipo quedo grabado en el modelo.
    bin::text                                           AS "bin",
    min_value::text                                     AS "min_value",
    max_value::text                                     AS "max_value",
    events                                              AS "events",
    good                                                AS "good",
    bad                                                 AS "bad",
    (bad::numeric / nullif(events, 0))::double precision AS "bad_rate",
    (good / nullif(tot_good, 0))::double precision      AS "%good",
    (bad  / nullif(tot_bad, 0))::double precision       AS "%bad",
    -- ln(%bad / %good). Con good o bad en cero el log no existe: el original deja 0.
    CASE WHEN good > 0 AND bad > 0
         THEN ln((bad / tot_bad) / (good / tot_good))::double precision
         ELSE 0 END                                     AS "woe",
    CASE WHEN good > 0 AND bad > 0
         THEN ((bad / tot_bad - good / tot_good)
               * ln((bad / tot_bad) / (good / tot_good)))::double precision
         ELSE 0 END                                     AS "iv"
FROM con_totales
ORDER BY flag, rango, bin NULLS LAST;

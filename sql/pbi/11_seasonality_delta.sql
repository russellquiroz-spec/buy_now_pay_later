-- Reemplaza: seasonality_delta.csv
--            (Rabbit Analytics\Tools\db_connection\, el archivo mas viejo del tablero: oct-2024)
-- Fuente:    redshift_bnpl.estacionalidad_mes (12 filas, la llena etl_redshift_to_postgres.py)
-- Grano:     par ordenado de meses calendario -> 12 x 11 = 132 filas
--
-- Mide cuanto cambia el comportamiento de compra entre dos meses del año, para poder descontar
-- la estacionalidad al comparar cohortes que arrancaron en meses distintos.
--
-- Las cuatro formulas estan verificadas contra el CSV original, las cuatro al 100%:
--
--     seasonalityDeltaTicket      = toMonthAvgGrossSales / fromMonthAvgGrossSales
--     seasonalityDeltaTicketRate  = seasonalityDeltaTicket - 1
--     seasonalityDeltaVolume      = toAvgMonthlyVolume    / fromcAvgMonthlyVolume
--     seasonalityDeltaVolumeRate  = seasonalityDeltaVolume - 1
--
-- (El nombre `fromcAvgMonthlyVolume` trae esa `c` de mas en el CSV. Se conserva tal cual: es el
-- nombre de la columna en el modelo.)
--
-- ── Que significa cada promedio ─────────────────────────────────────────────────────────
--
--     AvgGrossSales    venta / ordenes distintas           -> el TICKET del pedido
--     AvgMonthlyVolume venta / pares cliente-mes distintos -> lo que gasta el tendero en el mes
--
-- ── Por que se calcula sobre toda la base Rabbit y no sobre el universo BNPL ─────────────
--
-- Porque no da lo mismo, y se midio: usando solo clientes con credito, los cocientes se desvian
-- 6.8% en ticket y 9.5% en volumen respecto al CSV, con una correlacion de apenas 0.66. La
-- estacionalidad de los tenderos con credito no representa a la del negocio. Por eso
-- estacionalidad_mes se agrega en Redshift sobre la base completa.
--
-- ── Los niveles NO van a coincidir con el CSV, y esta bien ───────────────────────────────
--
-- El archivo es de octubre de 2024 y solo vio los datos hasta entonces; esta consulta usa la
-- serie completa 2021-2026. Los promedios absolutos van a ser mas altos. Lo que importa son los
-- cocientes, y esos se recalculan con datos vigentes en vez de quedarse congelados hace dos años.

WITH meses AS (SELECT * FROM redshift_bnpl.estacionalidad_mes)
SELECT
    -- ::text y no int: el M los declara `type text`, y la columna DAX seasonalityDeltaVolume de
    -- bnpl_loss_rates los cruza contra enrollmentMonth, que sale de un MID() — o sea, texto.
    f.mes_calendario::text                              AS "fromMonth",
    t.mes_calendario::text                              AS "toMonth",
    f.ticket_promedio                                   AS "fromMonthAvgGrossSales",
    f.volumen_promedio                                  AS "fromcAvgMonthlyVolume",
    t.ticket_promedio                                   AS "toMonthAvgGrossSales",
    t.volumen_promedio                                  AS "toAvgMonthlyVolume",
    t.ticket_promedio / f.ticket_promedio               AS "seasonalityDeltaTicket",
    t.ticket_promedio / f.ticket_promedio - 1           AS "seasonalityDeltaTicketRate",
    t.volumen_promedio / f.volumen_promedio             AS "seasonalityDeltaVolume",
    t.volumen_promedio / f.volumen_promedio - 1         AS "seasonalityDeltaVolumeRate"
FROM meses f
CROSS JOIN meses t
-- Sin el par consigo mismo: el CSV trae 132 filas, no 144.
WHERE f.mes_calendario <> t.mes_calendario
ORDER BY 1, 2;

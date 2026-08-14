-- Reemplaza: bnpl_cosecha_agg.csv  (196 MB en SharePoint / OneDrive personal)
-- Fuente:    redshift_bnpl.cosechas_agg, que llena etl_redshift_to_postgres.py
-- Grano:     mes x cohorte de primera transaccion x mes de primera orden BNPL x flag BNPL
-- Alimenta:  pagina "Cambio en Comportamiento de Compra"
--
-- Cosechas de TODA la base Rabbit desde 2021, no solo BNPL: la pagina compara como evoluciona una
-- cosecha de clientes con credito contra una sin el. Por eso se agrega en Redshift y aterriza en
-- el staging; aqui solo se renombra.
--
-- ── 11 columnas y no 22 ─────────────────────────────────────────────────────────────────
--
-- El CSV traia canal_venta, oficina, route_name y los desgloses _bnpl / _ff de cada medida. Se
-- rastrearon las 20 medidas, las 4 columnas calculadas y todos los visuales del modelo: ninguno
-- los usa. Los que si se usan son estos 10 (mas `periodo.`).
--
-- Quitar esas dimensiones ademas ARREGLA un conteo. Con ellas en la llave, un cliente que compro
-- por dos canales el mismo mes aparecia en dos filas y se contaba dos veces tanto en
-- cliente_activo como en clientes_cosecha — y `supervivencia` es SUM(activo)/SUM(cosecha). Por
-- eso `clientes_cosecha` no era constante por cohorte en el CSV (solo el 73.5% lo era).
--
-- El costo de la decision: la tabla ya no se puede segmentar por oficina ni ruta. Hoy nada lo
-- hace. Si se quisiera, hay que reintroducirlas y definir antes que significa clientes_cosecha
-- en ese grano.
--
-- ── Que tan bien reproduce el CSV ───────────────────────────────────────────────────────
--
-- Contrastado por mes_tx x flg_cte_bnpl hasta 2025-09, que es donde el CSV tiene datos completos:
--
--     clientes activos   3.14%
--     ordenes            3.49%
--     gross sales        9.10%
--
-- El gross carga con dos diferencias conocidas y deliberadas:
--   * 2025 en adelante usa amount_completed + amount_in_progress y el CSV parece haber usado
--     monto_venta, que incluye rechazado y cancelado. De ahi el -11.6% de ese año.
--   * Diciembre-2023 va dividido entre 20 porque la fuente lo trae inflado ~25x. Sin ese parche
--     2023 se iba a +252%; con el queda en +8.2%. Ver PENDIENTES_NEGOCIO.md.

SELECT
    -- mes_tx es `type date` en el M; mes_ft_tx y mes_ft_tx_bnpl son datetimezone, y por eso van
    -- como timestamptz: el CSV los traia con offset -06.
    c.mes_tx                                            AS "mes_tx",
    c.mes_ft_tx::timestamptz                            AS "mes_ft_tx",
    c.mes_ft_tx_bnpl::timestamptz                       AS "mes_ft_tx_bnpl",
    c.flg_cte_bnpl                                      AS "flg_cte_bnpl",
    -- El punto del nombre no es un error: el M renombra `periodo` a `periodo.` y asi quedo la
    -- columna en el modelo. La medida DAX `Periodo` es otra cosa y se recalcula sola.
    c.periodo                                           AS "periodo.",
    c.clientes_cosecha                                  AS "clientes_cosecha",
    c.cliente_activo                                    AS "cliente_activo",
    c.ordenes                                           AS "ordenes",
    c.gross_sales                                       AS "gross_sales",
    c.ordenes_ft                                        AS "ordenes_ft",
    c.gross_sales_ft                                    AS "gross_sales_ft"
FROM redshift_bnpl.cosechas_agg c;

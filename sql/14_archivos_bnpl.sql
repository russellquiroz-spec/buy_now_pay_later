-- Schema `archivos_bnpl`: los CSV que el tablero necesita y que NADIE puede calcular.
--
-- Son cuatro archivos que no salen de Mongo, ni de Redshift, ni de la capa bnpl: dos son la salida
-- de un modelo de riesgo (WOE/IV por pares de atributos), uno es una clasificacion que hace el
-- equipo de Pago de Servicios y el ultimo es captura manual de negocio. Ver PENDIENTES_NEGOCIO.md
-- secciones 10 y 11.
--
-- Existen aqui por una sola razon: hasta ahora el tablero los leia del disco personal de una
-- persona (C:\Users\RodolfoGonzalezOrta\...), y eso no sobrevive a que cambie de equipo ni se
-- puede refrescar desde el Service. Al pasarlos a la base, Power BI deja de depender de rutas de
-- Windows y todo el modelo se alimenta de un solo origen.
--
-- El schema es aparte a proposito. `bnpl` es lo que reconstruye build_bnpl.py y se puede tirar y
-- rehacer sin perder nada; esto NO — si se borra, hay que volver a conseguir los archivos. Que
-- vivan separados evita que alguien los incluya en un DROP masivo por descuido.
--
-- Los carga carga_archivos_bnpl.py, a mano, cuando negocio o riesgo publiquen una version nueva.

CREATE SCHEMA IF NOT EXISTS archivos_bnpl;

-- ── Modelo de riesgo ────────────────────────────────────────────────────────────────────

-- WOE/IV de cada PAR de atributos. loan_disbursement_index_range va como TEXT y no como entero:
-- sus valores son '1', '2' y '3+'. Ese '3+' es justamente lo que revienta el cast a Int64 que
-- traen los pasos del M, y de ahi el error de comparacion Integer vs Text al cargar.
CREATE TABLE IF NOT EXISTS archivos_bnpl.odds_combinations (
    loan_disbursement_index_range text,
    flag                          text,
    atr1                          text,
    atr2                          text,
    atr1_rank                     text,
    atr2_rank                     text,
    events                        bigint,
    good                          bigint,
    bad                           bigint,
    br                            double precision,
    bad_rate                      double precision,
    pct_good                      double precision,
    pct_bad                       double precision,
    woe                           double precision,
    iv                            double precision
);

CREATE INDEX IF NOT EXISTS ix_odds_comb_slice
    ON archivos_bnpl.odds_combinations (loan_disbursement_index_range, flag);

-- IV total de cada combinacion de atributos.
CREATE TABLE IF NOT EXISTS archivos_bnpl.atr_combinations_iv (
    loan_disbursement_index_range text,
    flag                          text,
    combination                   text,
    number_of_combinations        bigint,
    iv                            double precision
);

-- ── Otros productos fintech ─────────────────────────────────────────────────────────────

-- Perfil transaccional de Pago de Servicios. Alimenta psTransactionalProfile y, por ahi,
-- crossFraudFlag en la pagina Fraud.
--
-- Se intento derivarlo del schema `fintech` de Redshift y NO alcanza. Los dos buckets altos si
-- salen de contar fintech.transactions_ps — '4 to 10 TX' y 'More than 10 TX' quedan limpios — pero
-- '01-Enrolled', '02-Potential Fraud', '03-Mostly Fraud' y '2 to 3 TX' se enciman todos entre 0 y
-- 3 transacciones. Se probaron tres separadores y ninguno distingue las etiquetas de fraude:
--
--     conteo de transacciones    los tres perfiles conviven en tx = 2 y tx = 3
--     transacciones FAILED       0.03 vs 0.01 vs 0.00 de promedio
--     bonos de funding_ps        69.7% vs 65.0% vs 69.5% con bono
--
-- O sea que la regla que separa "Potential" de "Mostly Fraud" no vive en fintech: la pone el
-- equipo de PS. Hasta que la publiquen, esta tabla sigue siendo archivo.
CREATE TABLE IF NOT EXISTS archivos_bnpl.ps_transactional_profile (
    id_cliente            bigint,
    transactional_profile text
);

CREATE INDEX IF NOT EXISTS ix_ps_perfil_cliente
    ON archivos_bnpl.ps_transactional_profile (id_cliente);

-- ── Captura manual de negocio ───────────────────────────────────────────────────────────

-- Costo de adquisicion por cohorte de enrolamiento. El gasto de marketing no vive en ninguna
-- fuente del pipeline: lo pone negocio a mano (PENDIENTE 11).
CREATE TABLE IF NOT EXISTS archivos_bnpl.bnpl_cac (
    enrollment_cohort text,
    cac               double precision
);

-- ── Vistas para Power BI ────────────────────────────────────────────────────────────────
--
-- Las tablas de arriba guardan en snake_case, que es la convencion del staging. Estas vistas
-- hacen la traduccion a los nombres EXACTOS que espera el modelo — incluidos '%good', '%bad' y
-- 'Id cliente' con su espacio — para que el paso M en Power Query sea:
--
--     Value.NativeQuery(Origen, "select * from archivos_bnpl.v_pbi_odds_combinations")
--
-- y no haya que escapar una sola comilla. Es la misma consulta que hay en sql/pbi/14 a 17; ahi
-- estan documentadas y aqui viven materializadas para que el tablero no tenga que cargarlas.

CREATE OR REPLACE VIEW archivos_bnpl.v_pbi_odds_combinations AS
SELECT loan_disbursement_index_range AS "loanDisbursementIndexRange",
       flag AS "flag", atr1 AS "atr1", atr2 AS "atr2",
       atr1_rank AS "atr1Rank", atr2_rank AS "atr2Rank",
       events AS "events", good AS "good", bad AS "bad",
       br AS "br", bad_rate AS "bad_rate",
       pct_good AS "%good", pct_bad AS "%bad", woe AS "woe", iv AS "iv"
FROM archivos_bnpl.odds_combinations;

CREATE OR REPLACE VIEW archivos_bnpl.v_pbi_atr_combinations_iv AS
SELECT loan_disbursement_index_range AS "loanDisbursementIndexRange",
       flag AS "flag", combination AS "combination",
       number_of_combinations AS "number_of_combinations", iv AS "iv"
FROM archivos_bnpl.atr_combinations_iv;

CREATE OR REPLACE VIEW archivos_bnpl.v_pbi_ps_transactional_profile AS
SELECT id_cliente AS "Id cliente", transactional_profile AS "transactionalProfile"
FROM archivos_bnpl.ps_transactional_profile;

CREATE OR REPLACE VIEW archivos_bnpl.v_pbi_bnpl_cac AS
SELECT enrollment_cohort AS "enrollmentCohort", cac AS "cac"
FROM archivos_bnpl.bnpl_cac;

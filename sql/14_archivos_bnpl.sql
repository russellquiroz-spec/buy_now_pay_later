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

-- ── Vistas para Power BI: NO van aqui ───────────────────────────────────────────────────
--
-- La traduccion de snake_case a los nombres exactos del modelo ('%good', '%bad', 'Id cliente'
-- con su espacio) vive en sql/pbi/14 a 17 y la publica build_bnpl.py como pbi_bnpl.*, igual que
-- las otras tablas del tablero. Este archivo tuvo cuatro vistas v_pbi_* con esa misma
-- traduccion; se borraron porque el mismo SQL en dos lugares es exactamente lo que sql/15 dice
-- que el proyecto no hace, y ademas nadie las consumia: PASOS_M.md apunta a pbi_bnpl.
--
-- Para tirarlas de una base que ya las tiene:
--
--     DROP VIEW IF EXISTS archivos_bnpl.v_pbi_odds_combinations;
--     DROP VIEW IF EXISTS archivos_bnpl.v_pbi_atr_combinations_iv;
--     DROP VIEW IF EXISTS archivos_bnpl.v_pbi_ps_transactional_profile;
--     DROP VIEW IF EXISTS archivos_bnpl.v_pbi_bnpl_cac;
--
-- El DROP no va dentro de este archivo a proposito: carga_archivos_bnpl.py lo ejecuta en cada
-- carga manual y un DROP repetido ahi no aporta nada. Se corre una vez a mano sobre la VM.

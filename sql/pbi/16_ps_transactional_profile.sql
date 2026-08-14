-- Reemplaza: ps_transactional_profile.csv
--            (Rabbit Analytics\Pago de Servicios Automation\)
-- Fuente:    archivos_bnpl.ps_transactional_profile
-- Grano:     cliente  ->  100,793 filas
--
-- Alimenta la columna DAX psTransactionalProfile de loans_matured_default_profile y, por ahi,
-- crossFraudFlag en la pagina Fraud.
--
-- Se intento derivarla del schema `fintech` de Redshift y no alcanza: los buckets '4 to 10 TX' y
-- 'More than 10 TX' si salen de contar transactions_ps, pero '01-Enrolled', '02-Potential Fraud',
-- '03-Mostly Fraud' y '2 to 3 TX' se enciman todos entre 0 y 3 transacciones, y ni las
-- transacciones fallidas ni los bonos de funding_ps los separan. El detalle de lo que se probo
-- esta en sql/14_archivos_bnpl.sql y en PENDIENTES_NEGOCIO.md seccion 10.
--
-- El nombre de la columna lleva espacio ("Id cliente") porque asi lo espera el modelo.

SELECT
    p.id_cliente                                        AS "Id cliente",
    p.transactional_profile                             AS "transactionalProfile"
FROM archivos_bnpl.ps_transactional_profile p;

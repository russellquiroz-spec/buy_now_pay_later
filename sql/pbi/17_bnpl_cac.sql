-- Reemplaza: bnpl_cac.csv
-- Fuente:    archivos_bnpl.bnpl_cac
-- Grano:     cohorte de enrolamiento  ->  25 filas
--
-- Costo de adquisicion por cohorte. Captura manual: el gasto de marketing no vive en ninguna
-- fuente del pipeline (PENDIENTE 11). Alimenta la columna `cac` de bnpl_loss_rates y la pagina
-- Return On Investment.
--
-- enrollmentCohort es texto 'YYYY-MM' y cruza contra bnpl_loss_rates[enrollment_cohort], que sale
-- igual de la consulta 02. La relacion con vintage_analysis existe pero esta INACTIVA.

SELECT
    c.enrollment_cohort                                 AS "enrollmentCohort",
    c.cac                                               AS "cac"
FROM archivos_bnpl.bnpl_cac c;

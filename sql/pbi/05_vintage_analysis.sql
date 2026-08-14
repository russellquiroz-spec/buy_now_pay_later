-- Reemplaza: vintage_analysis.csv
-- Fuente:    bnpl.vintage_analysis
-- Grano:     cohort de enrolamiento x meses de maduracion  (530 filas)
--
-- Correspondencia 1 a 1: las 21 columnas del CSV existen en la vista con otro nombre. La unica
-- que cambia de sentido es `n`, que en el CSV es el numero de ORDENES del cohort en ese mes de
-- maduracion (no de clientes: los clientes son everActivated).

SELECT
    v.enrollment_cohort                                 AS "enrollment_cohort",
    -- double, no int: el M lo declara `type number` y la columna del modelo es `double`. Con
    -- integer, Power Query lo tiparia Int64 y cambiaria el tipo de la columna en el modelo.
    v.cohort_year::double precision                     AS "cohortYear",
    v.months_from_enrollment_to_month                   AS "monthsFromEnrollmentToMonth",
    v.corte                                             AS "corte",
    v.ordenes                                           AS "n",
    v.ever_activated                                    AS "everActivated",
    v.enrolled_customers                                AS "enrolled_customers",
    v.deployed_capital                                  AS "deployedCapital",
    v.outstanding_balance                               AS "outstandingBalance",
    v.par30                                             AS "PAR30",
    v.par60                                             AS "PAR60",
    v.par90                                             AS "PAR90",
    v.par30_n                                           AS "PAR30N",
    v.par60_n                                           AS "PAR60N",
    v.par90_n                                           AS "PAR90N",
    v.par30_rate                                        AS "par30Rate",
    v.par60_rate                                        AS "par60Rate",
    v.par90_rate                                        AS "par90Rate",
    v.par30_customers_rate::double precision            AS "par30CustomersRate",
    v.par60_customers_rate::double precision            AS "par60CustomersRate",
    v.par90_customers_rate::double precision            AS "par90CustomersRate"
FROM bnpl.vintage_analysis v;

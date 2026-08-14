-- Reemplaza: odds_combinations.csv  (Default Profile\, 30.7 MB)
-- Fuente:    archivos_bnpl.odds_combinations, que carga carga_archivos_bnpl.py
-- Grano:     rango x flag x par de atributos x par de bins  ->  84,986 filas
--
-- NO es una consulta derivada: es el espejo del archivo. Existe para que el tablero deje de leer
-- del disco personal de una persona. La logica que produce estas filas vive en el modelo de
-- riesgo, no aqui — ver PENDIENTES_NEGOCIO.md seccion 10.
--
-- loanDisbursementIndexRange sale como TEXTO ('1', '2', '3+'). En el modelo esa columna quedo
-- como int64 y hay que retiparla a texto en las CINCO tablas que la tienen (loans_matured,
-- vars_and_iv, odds_table, odds_combinations, atr_combinations_iv), o la relacion entre
-- loans_matured y vars_and_iv falla con "no admiten comparacion Integer con Text".

SELECT
    o.loan_disbursement_index_range                     AS "loanDisbursementIndexRange",
    o.flag                                              AS "flag",
    o.atr1                                              AS "atr1",
    o.atr2                                              AS "atr2",
    o.atr1_rank                                         AS "atr1Rank",
    o.atr2_rank                                         AS "atr2Rank",
    o.events                                            AS "events",
    o.good                                              AS "good",
    o.bad                                               AS "bad",
    o.br                                                AS "br",
    o.bad_rate                                          AS "bad_rate",
    o.pct_good                                          AS "%good",
    o.pct_bad                                           AS "%bad",
    o.woe                                               AS "woe",
    o.iv                                                AS "iv"
FROM archivos_bnpl.odds_combinations o;

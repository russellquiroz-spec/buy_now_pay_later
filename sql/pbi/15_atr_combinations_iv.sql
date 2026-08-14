-- Reemplaza: atr_combinations_iv.csv  (Default Profile\)
-- Fuente:    archivos_bnpl.atr_combinations_iv
-- Grano:     rango x flag x combinacion de atributos  ->  468 filas
--
-- Espejo del archivo, igual que 14_odds_combinations.sql. Mismo pendiente y misma advertencia:
-- loanDisbursementIndexRange es TEXTO y hay que retiparla en el modelo.

SELECT
    a.loan_disbursement_index_range                     AS "loanDisbursementIndexRange",
    a.flag                                              AS "flag",
    a.combination                                       AS "combination",
    a.number_of_combinations                            AS "number_of_combinations",
    a.iv                                                AS "iv"
FROM archivos_bnpl.atr_combinations_iv a;

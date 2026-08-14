-- Reemplaza: nada. Es el denominador que le falta a concurso_base.
-- Fuente:    bnpl.bnpl_clientes_concurso  (tabla fisica, la carga carga_clientes_concurso.py
--            desde `BBDD tablero BNPL LANZAMIENTO.xlsx`; no la reconstruye build_bnpl.py)
-- Grano:     1 fila por cliente del universo de lanzamiento  (51,294 filas)
-- Pagina:    Concurso Credito Rabbit -- el lado "uno" de la relacion con concurso_base
--
-- ESTA VISTA NO SE CONSUME HOY, y es a proposito que siga aca. El tablero del concurso lee
-- `bnpl.bnpl_clientes_concurso` directo, con un SELECT explicito que le da el bloque `directos` de
-- sql/16_pbi_grants.sql. Esta es la otra salida al `42501: permission denied for table
-- bnpl_clientes_concurso` del 2026-08-14: repuntar el paso M aca y borrar ese bloque, con lo que
-- `pbi_gateway` vuelve a ver solo `pbi_bnpl`. Se deja publicada y verificada para que esa decision
-- no cueste volver a escribirla. Ver README.md -> Cuando falla el refresh.
--
-- La relacion con concurso_base va "netsuiteIdNum" (bigint) contra su homonima, no la version
-- texto: 51,294 valores unicos, sin nulos, asi que sirve de lado "uno". La columna texto se
-- conserva porque es la que trae el Excel y permite cotejar contra la fuente.
--
-- aliado / supervisor / oficina son la estructura ASIGNADA en el lanzamiento, la que trae el
-- Excel. La estructura de hoy no va aqui: vive en concurso_base como aliadoActual /
-- supervisorActual / oficinaActual. Se nombran igual que alla a proposito, para que los dos
-- lados del modelo se corten con el mismo vocabulario.

SELECT
    c.netsuite_id                       AS "netsuiteId",
    c.netsuite_id_num                   AS "netsuiteIdNum",
    c.clasificacion                     AS "clasificacion",
    -- double precision y no numeric: es como esta tipado limiteCredito en concurso_base, y las
    -- dos se comparan en el mismo visual.
    c.linea_nueva::double precision     AS "lineaNueva",
    c.ruta_preventa                     AS "aliado",
    c.supervisor                        AS "supervisor",
    c.oficina_venta                     AS "oficina"
FROM bnpl.bnpl_clientes_concurso c;

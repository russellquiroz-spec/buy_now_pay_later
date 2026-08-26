-- Reemplaza: nada. Es concurso_base mas el estado de pago de cada orden.
-- Fuente:    pbi_bnpl.concurso_base (grano y filtros intactos) + bnpl.loss_rates
-- Grano:     el mismo que concurso_base -- 1 fila por orden en ventana del concurso
-- Pagina:    Concurso Credito Rabbit -- lo lee refrescar_pbi.py y un modelo de Power BI
--
-- Existia en la base desde el 2026-08-19 creada A MANO, sin archivo en sql/pbi/, y por eso el
-- pipeline no la conocia. Eso la dejaba en un punto ciego con fecha de caducidad:
-- build_bnpl.py::_construir_vistas_pbi() hace `DROP VIEW ... CASCADE` sobre concurso_base en cada
-- corrida, y el CASCADE se lleva todo lo que cuelgue de ella. La vista sobrevivio diez dias solo
-- porque el pipeline venia abortando en el paso [4/6] y nunca llegaba al DROP. En la primera
-- corrida sana habria desaparecido sin dejar rastro, y con ella la tabla que el modelo consume:
-- el refresh del tablero habria fallado con `42P01: relation does not exist` sin que el log del
-- pipeline dijera nada, porque para el pipeline esta vista no existia.
--
-- Al vivir aqui se recrea con las otras en cada corrida y `sql/16_pbi_grants.sql` le devuelve el
-- SELECT de pbi_gateway con su `GRANT SELECT ON ALL TABLES IN SCHEMA pbi_bnpl`.
--
-- El numero 22 no es decorativo: los archivos se aplican ordenados (build_bnpl.py::PBI_DIR glob)
-- y esta lee de concurso_base, que es el 20. Renumerarla por debajo de 20 la rompe.
--
-- `bnpl.loss_rates` va calificada con su schema. La definicion hecha a mano decia `loss_rates` a
-- secas y resolvia por search_path: funcionaba desde la sesion que la creo y es una manera comoda
-- de que la vista apunte a otra tabla el dia que alguien la recree con otro search_path.
--
-- LEFT JOIN y no INNER: una orden en ventana que todavia no se paga tiene que seguir contando en
-- el denominador del concurso. `liquidado` sale de paid_date IS NOT NULL, asi que esas caen en
-- false en vez de desaparecer.
SELECT
    c.*,
    l.paid_date IS NOT NULL AS liquidado,
    l.paid_date             AS fecha_liquidacion
FROM pbi_bnpl.concurso_base c
LEFT JOIN bnpl.loss_rates l ON c."salesOrderId" = l.sales_order_id;

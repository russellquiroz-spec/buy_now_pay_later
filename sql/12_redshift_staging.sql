-- Staging de Redshift: estructura comercial y catalogo de rutas.
--
-- Estas tres tablas las creaba `to_sql` a partir de los dtypes de pandas, y eso hacia que el
-- esquema dependiera de lo que pandas hubiera inferido en esa corrida: al migrar a la VM,
-- `fecha_inicio`, `valido_desde` y `valido_hasta` llegaron como text en vez de date y las vistas
-- de ruta no compilaron. Con el DDL explicito el tipo es el mismo en cualquier destino.

CREATE SCHEMA IF NOT EXISTS redshift_bnpl;

-- Ruta vigente de cada cliente (catalog.cat_estructura_comercial_v3).
CREATE TABLE IF NOT EXISTS redshift_bnpl.estructura_comercial (
    netsuite_id   text,
    tipo_cliente  text,
    status        text,
    ruta          text,
    ruta_canon    text,
    supervisor    text,
    oficina       text,
    oficina_canon text,
    region        text,
    region_canon  text,
    pais          text,
    dia           text,
    frecuencia    text,
    fecha_inicio  date,
    data_source   text
);

CREATE INDEX IF NOT EXISTS ix_estructura_netsuite
    ON redshift_bnpl.estructura_comercial (netsuite_id);
CREATE INDEX IF NOT EXISTS ix_estructura_ruta
    ON redshift_bnpl.estructura_comercial (ruta);

-- Catalogo de rutas (catalog.route_mapping) = dim_ruta del modelo estrella.
CREATE TABLE IF NOT EXISTS redshift_bnpl.route_mapping (
    ruta    text,
    equipo  text,
    oficina text,
    region  text,
    pais    text
);

CREATE INDEX IF NOT EXISTS ix_route_mapping_ruta
    ON redshift_bnpl.route_mapping (ruta);

-- Ruta historica por intervalos, ya comprimida en Redshift por cambio de ruta.
CREATE TABLE IF NOT EXISTS redshift_bnpl.ruta_cliente_scd (
    netsuite_id   text,
    ruta          text,
    supervisor    text,
    oficina       text,
    region        text,
    tipo_cliente  text,
    status        text,
    valido_desde  date,
    valido_hasta  date,
    dias_vigencia bigint
);

CREATE INDEX IF NOT EXISTS ix_scd_netsuite_rango
    ON redshift_bnpl.ruta_cliente_scd (netsuite_id, valido_desde, valido_hasta);

-- Venta Rabbit COMPLETA de los clientes con credito, a grano de sales order.
--
-- Es lo que la capa BNPL no puede saber por si sola: que compro el tendero FUERA de BNPL. Sin
-- esto no se puede responder "¿siguio comprando despues de caer en mora?", que es de donde sale
-- `fraudFlag` en el tablero, ni comparar su venta antes y despues de enrolarse.
--
-- Alcance: solo el universo BNPL (~10.7K clientes) y desde 2021-04-01, el inicio de la serie de
-- pedidos enriquecidos. NO seis meses antes del primer credito como en la primera version:
-- overall_prev_post_bnpl_sales compara la venta del cliente antes y despues de enrolarse, y el CSV
-- historico llega a 57 meses ANTES del enrolamiento — con una ventana corta esa comparacion se
-- queda sin lado izquierdo. Traer la base completa serian ~40M filas y no hace falta.
--
-- Se guarda a grano de orden, no agregado por mes, porque overall_prev_post_bnpl_sales necesita
-- el sales order y los SKUs. Las ventanas de 3M/6M y de post-mora se agregan despues en SQL
-- local, que es barato. Medido: ~1.29M filas.
--
-- El monto sale del desglose amount_completed + amount_in_progress en las tablas _v2 (2025 en
-- adelante) y de monto_venta en las viejas, que es la unica columna que existe ahi. Hay un escalon
-- en enero-2025 por el cambio de definicion; es deliberado, para quedar consistente con cosechas_agg
-- y con analisis_one_shot. Diciembre-2023 va dividido entre 20 (fuente corrupta, ver
-- PENDIENTES_NEGOCIO.md). Es venta ordenada, no surtida — se distingue con status_pedido.
CREATE TABLE IF NOT EXISTS redshift_bnpl.ventas_cliente (
    netsuite_id    text,
    sales_order_id text,
    fecha_creacion date,
    clase_canal    text,
    status_pedido  text,
    skus           bigint,
    piezas         double precision,
    monto_venta    double precision
);

CREATE INDEX IF NOT EXISTS ix_ventas_cliente_netsuite
    ON redshift_bnpl.ventas_cliente (netsuite_id, fecha_creacion);
CREATE INDEX IF NOT EXISTS ix_ventas_cliente_so
    ON redshift_bnpl.ventas_cliente (sales_order_id);

-- Cosechas de TODA la base Rabbit por mes de primera transaccion. Alimenta la pagina
-- "Cambio en Comportamiento de Compra": compara como evoluciona una cosecha de clientes con
-- credito contra una sin el.
--
-- Se agrega en Redshift, no aca: al grano de cliente x mes son decenas de millones de filas y no
-- tiene caso moverlas. Lo que baja son ~52K filas.
--
-- Grano: mes_tx x cohorte (mes_ft_tx) x mes de primera orden BNPL x flag BNPL.
--
-- El CSV original tenia ademas canal_venta, oficina y route_name, y los desgloses _bnpl / _ff de
-- cada medida — 22 columnas contra las 11 de aqui. Se dejaron fuera a proposito: se rastrearon
-- las 20 medidas, las 4 columnas calculadas y todos los visuales del modelo, y ninguno las usa.
-- Ademas quitarlas ARREGLA un conteo: con las dimensiones del pedido en la llave, un cliente que
-- compro por dos canales el mismo mes se contaba dos veces en cliente_activo y en
-- clientes_cosecha, y la medida `supervivencia` es el cociente de esas dos sumas.
CREATE TABLE IF NOT EXISTS redshift_bnpl.cosechas_agg (
    mes_tx           date,
    mes_ft_tx        date,
    mes_ft_tx_bnpl   date,
    flg_cte_bnpl     text,
    periodo          bigint,
    clientes_cosecha bigint,
    cliente_activo   bigint,
    ordenes          bigint,
    gross_sales      double precision,
    ordenes_ft       bigint,
    gross_sales_ft   double precision
);

CREATE INDEX IF NOT EXISTS ix_cosechas_agg_mes
    ON redshift_bnpl.cosechas_agg (mes_tx, flg_cte_bnpl);
CREATE INDEX IF NOT EXISTS ix_cosechas_agg_cohorte
    ON redshift_bnpl.cosechas_agg (mes_ft_tx, periodo);

-- Estacionalidad por mes calendario sobre TODA la base Rabbit. 12 filas.
--
-- Es la base de seasonality_delta, que compara cualquier par de meses. Se calcula sobre la base
-- completa y no sobre el universo BNPL a proposito: medido, la estacionalidad de los clientes con
-- credito es distinta a la del resto — comparar los cocientes de una contra la otra da 6.8% de
-- error en ticket y 9.5% en volumen, con correlacion de apenas 0.66.
--
--   ticket_promedio    venta / ordenes distintas          (cuanto gasta el tendero por pedido)
--   volumen_promedio   venta / pares cliente-mes distintos (cuanto gasta el tendero en el mes)
CREATE TABLE IF NOT EXISTS redshift_bnpl.estacionalidad_mes (
    mes_calendario   int,
    ticket_promedio  double precision,
    volumen_promedio double precision
);

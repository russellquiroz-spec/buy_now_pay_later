-- Universo de clientes del Concurso Credito Rabbit, con la linea de credito de lanzamiento.
--
-- Fuente: "BBDD tablero BNPL LANZAMIENTO.xlsx", hoja `bbdd`, en el Drive de BI
--   (Dashboards/Venta/Punto de encuentro (Compromisos)/concurso_bnpl/).
--   Lo carga `carga_clientes_concurso.py`, a mano. `build_bnpl.py` aplica su DDL en cada
--   corrida (CREATE TABLE / CREATE INDEX IF NOT EXISTS, para que una VM limpia tenga la tabla),
--   pero NUNCA toca los datos.
--
-- Es la unica tabla de `bnpl` que NO es una vista materializada: el dato lo pone negocio en Excel
-- y no se deriva de ninguna fuente del pipeline. Por eso lleva DDL propio en vez de salir de los
-- dtypes de pandas, igual que el staging de Redshift (ver 12_redshift_staging.sql).
--
-- La hoja `bbdd` viene ya filtrada a clasificacion 'ajuste' y 'nuevo'. La otra hoja del libro
-- (`Hoja1`) trae 20,004 filas mas, de clasificacion 'baja' y 'corrientes', que quedan fuera.
--
-- netsuite_id va DOS veces a proposito, igual que en sql/pbi/20_concurso_base.sql:
--   netsuite_id      text   — como vive en bnpl.grid_bnpl y bnpl.grouped_orders; es con esto que
--                             se une del lado PostgreSQL.
--   netsuite_id_num  bigint — para relacionar en Power BI contra `netsuiteIdNum` de concurso_base.
--                             El modelo no relaciona texto contra entero.
-- En el Excel la columna llega numerica, asi que el bigint es el dato crudo y el text es el
-- derivado; en el resto del proyecto es al reves. No hay clientes con espacios ni ceros a la
-- izquierda en esta lista, asi que las dos versiones son biyectivas aqui.

CREATE TABLE IF NOT EXISTS bnpl.bnpl_clientes_concurso (
    netsuite_id     text   NOT NULL,
    netsuite_id_num bigint NOT NULL,
    linea_nueva     numeric,
    clasificacion   text,
    ruta_preventa   text,
    oficina_venta   text,
    supervisor      text
);

-- La hoja trae un netsuite_id por fila, sin repetir: la unicidad es parte de la definicion de la
-- tabla (es el universo del concurso), no una casualidad de la extraccion. Como indice unico
-- ademas sirve de lado "uno" para las relaciones del modelo.
CREATE UNIQUE INDEX IF NOT EXISTS ux_clientes_concurso_netsuite
    ON bnpl.bnpl_clientes_concurso (netsuite_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_clientes_concurso_netsuite_num
    ON bnpl.bnpl_clientes_concurso (netsuite_id_num);
CREATE INDEX IF NOT EXISTS ix_clientes_concurso_ruta
    ON bnpl.bnpl_clientes_concurso (ruta_preventa);

-- Los COMMENT van en un solo literal cada uno: la guarda de postgres_local_client parsea el SQL
-- con sqlglot antes de ejecutarlo, y sqlglot no reconoce la concatenacion por adyacencia de
-- literales que PostgreSQL si acepta.
COMMENT ON TABLE bnpl.bnpl_clientes_concurso IS 'Universo del Concurso Credito Rabbit con linea de lanzamiento. Carga manual desde Excel (carga_clientes_concurso.py); build_bnpl.py solo aplica su DDL, no sus datos.';
COMMENT ON COLUMN bnpl.bnpl_clientes_concurso.linea_nueva IS 'Linea de credito asignada para el lanzamiento, en pesos.';
COMMENT ON COLUMN bnpl.bnpl_clientes_concurso.clasificacion IS 'Origen de la linea: nuevo (cliente sin linea previa) o ajuste (cambio sobre la que ya tenia).';
COMMENT ON COLUMN bnpl.bnpl_clientes_concurso.supervisor IS 'Supervisor de la ruta. En el Excel la columna se llama "Ruta preventa", homonima de la de ruta salvo por una mayuscula; los valores son codigos SV* y cuadran contra redshift_bnpl.estructura_comercial.supervisor.';

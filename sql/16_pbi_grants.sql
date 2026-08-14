-- Permisos de lectura del rol `pbi_gateway`, el que usa el gateway para refrescar Power BI.
--
-- Corre al final de cada build, despues del DROP + CREATE de las vistas. Es idempotente y se
-- aplica siempre, no una sola vez al configurar: los permisos de este rol se pierden solos y de
-- tres maneras distintas.
--
-- ── 1. El DROP VIEW se lleva el GRANT ───────────────────────────────────────────────────
--
-- build_bnpl.py recrea las 19 vistas en cada corrida, y un GRANT vive pegado al objeto: al
-- soltarlo se va con el. El ALTER DEFAULT PRIVILEGES de aqui abajo hace que las vistas nuevas
-- nazcan legibles, y el GRANT SELECT las repara aunque alguien haya recreado una a mano, fuera
-- del pipeline, sin las default privileges puestas.
--
-- ── 2. Las funciones se cobran al que consulta ──────────────────────────────────────────
--
-- Una vista lee las TABLAS con los privilegios de su dueno, y por eso `pbi_gateway` no necesita
-- permiso sobre `bnpl` para leer las materializadas. Con las FUNCIONES no aplica: PostgreSQL las
-- cobra al que consulta (docs de CREATE VIEW, seccion Notes). Seis vistas llaman funciones de
-- `bnpl` -- ahora_mx(), hoy_mx(), estados_activacion(), dias_credito() -- asi que sin USAGE sobre
-- ese schema el refresh muere con `42501: permission denied for schema bnpl`. Paso el 2026-08-14,
-- y basta una vista para tumbar el refresh completo.
--
-- Los schemas no van escritos a mano: se leen de pg_depend, que registra que funcion usa cada
-- vista. Si manana una consulta de sql/pbi/ empieza a llamar una funcion de otro schema, el USAGE
-- sale en la siguiente corrida sin tocar este archivo. Eso es lo que evita que el error vuelva:
-- lo que hay que mantener no es una lista, es nada.
--
-- USAGE no da lectura. Permite resolver nombres dentro del schema y nada mas: `pbi_gateway` sigue
-- sin SELECT sobre las tablas de `bnpl` y sigue viendo solo `pbi_bnpl`, que es la intencion.
-- El EXECUTE de las funciones no se otorga porque en PostgreSQL nace en PUBLIC.

-- ── 3. El tablero del concurso lee dos objetos de `bnpl` directo ────────────────────────
--
-- Es la excepcion a lo de arriba, y es una decision, no un descuido: el modelo del concurso
-- (tablero aparte, no el de `pbi_new/`) apunta a `bnpl.bnpl_clientes_concurso` y
-- `bnpl.dim_ruta_actual` sin pasar por `pbi_bnpl`, asi que necesita SELECT explicito. Sin el, el
-- refresh muere en 9 segundos con `42501: permission denied for table bnpl_clientes_concurso`.
-- Paso el 2026-08-14 a las 14:28.
--
-- Esta lista SI va escrita a mano, al contrario de los schemas de arriba: la dependencia vive en un
-- modelo de Power BI, no en `pg_depend`, y no hay catalogo del que deducirla. Por eso tiene que
-- estar aca y no en un GRANT corrido una vez: `sql/11_bnpl_dim_ruta.sql` hace
-- `DROP MATERIALIZED VIEW ... CASCADE`, que se lleva el permiso en cada `--rebuild`.
--
-- Si algun dia el tablero se repunta a `pbi_bnpl.concurso_base` y `pbi_bnpl.concurso_clientes`
-- (la vista ya existe), este bloque se borra y el rol vuelve a ver solo `pbi_bnpl`.

DO $grants$
DECLARE
    rol      CONSTANT text := 'pbi_gateway';
    consumo  CONSTANT text := 'pbi_bnpl';
    -- Objetos de otros schemas que lee un modelo directo. Ver el bloque 3 del encabezado.
    directos CONSTANT text[] := ARRAY['bnpl.bnpl_clientes_concurso', 'bnpl.dim_ruta_actual'];
    dueno    text;
    sch      text;
    obj      text;
BEGIN
    -- En una base donde el rol no existe (local, o una restauracion nueva) esto es un no-op:
    -- fallar aqui detendria el pipeline entero por un rol que solo le sirve a Power BI.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rol) THEN
        RAISE NOTICE '%: el rol % no existe en esta base, no hay permisos que aplicar',
            consumo, rol;
        RETURN;
    END IF;

    EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', consumo, rol);
    EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO %I', consumo, rol);

    -- USAGE sobre cada schema del que las vistas llamen funciones. Se descubre en el catalogo,
    -- no se declara. `refclassid = pg_proc` filtra las funciones; las dependencias a tablas
    -- entran por la misma via y esas no necesitan permiso (las cubre el dueno de la vista).
    FOR sch IN
        SELECT DISTINCT fn.nspname
        FROM pg_depend d
        JOIN pg_rewrite r ON r.oid = d.objid
        JOIN pg_class v ON v.oid = r.ev_class
        JOIN pg_namespace vn ON vn.oid = v.relnamespace
        JOIN pg_proc p ON p.oid = d.refobjid
        JOIN pg_namespace fn ON fn.oid = p.pronamespace
        WHERE vn.nspname = consumo
          AND d.classid = 'pg_rewrite'::regclass
          AND d.refclassid = 'pg_proc'::regclass
          AND fn.nspname NOT IN ('pg_catalog', 'information_schema', consumo)
        ORDER BY 1
    LOOP
        EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', sch, rol);
        RAISE NOTICE '%: USAGE sobre % (las vistas llaman funciones de ahi)', rol, sch;
    END LOOP;

    -- SELECT sobre los objetos que un modelo lee sin pasar por `pbi_bnpl`. El to_regclass es para
    -- que una base sin la tabla del concurso (una restauracion nueva, o local) no detenga el
    -- pipeline: se avisa y se sigue.
    FOREACH obj IN ARRAY directos
    LOOP
        IF to_regclass(obj) IS NULL THEN
            RAISE NOTICE '%: % no existe en esta base, no hay permiso que aplicar', rol, obj;
        ELSE
            EXECUTE format('GRANT SELECT ON %s TO %I', obj, rol);
            RAISE NOTICE '%: SELECT sobre % (lo lee un modelo directo)', rol, obj;
        END IF;
    END LOOP;

    -- Que las vistas de la proxima corrida nazcan legibles sin depender de este archivo.
    -- El dueno se lee del schema y no se escribe: el FOR ROLE tiene que nombrar a quien crea las
    -- vistas, y si algun dia cambia, un valor fijo aqui dejaria de aplicar en silencio.
    SELECT pg_get_userbyid(nspowner) INTO dueno
    FROM pg_namespace WHERE nspname = consumo;

    IF pg_has_role(current_user, dueno, 'MEMBER') THEN
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT SELECT ON TABLES TO %I',
            dueno, consumo, rol);
    ELSE
        -- Sin membresia no se puede fijar, pero el GRANT SELECT de arriba ya dejo legible lo que
        -- existe: el refresh de hoy funciona. Se avisa porque el de manana depende de que alguien
        -- con la membresia corra esta linea.
        RAISE WARNING '%: no soy miembro de %, no pude fijar las default privileges', current_user, dueno;
    END IF;
END
$grants$;

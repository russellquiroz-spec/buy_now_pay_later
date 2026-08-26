-- Parametros de negocio y conversiones de fecha de la capa BNPL.
--
-- Las reglas viven aqui como funciones, no incrustadas en cada vista: cambiar una regla es
-- cambiar una funcion y refrescar. Los valores salen del notebook legacy
-- (legacy/Buy Now Pay Later Robot.ipynb, celdas 70 y 82); lo que falta confirmar con negocio
-- esta en PENDIENTES_NEGOCIO.md.

CREATE SCHEMA IF NOT EXISTS bnpl;

-- ── Parametros de negocio ────────────────────────────────────────────────────

-- Plazo del credito: el tendero paga 15 dias despues de recibir el pedido.
CREATE OR REPLACE FUNCTION bnpl.dias_credito() RETURNS int
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT 15 $$;

-- Participacion de Rabbit sobre el interes. PENDIENTE 1: el notebook la aplica sobre el
-- interes con IVA en loss_rates y sin IVA en el grid (17.3% de diferencia). Aqui se usa la
-- definicion de loss_rates, que es la que alimenta el layout final.
CREATE OR REPLACE FUNCTION bnpl.share_rabbit() RETURNS numeric
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT 0.142::numeric $$;

-- Comision sobre el monto financiado. Se calcula en el legacy pero no alimenta ninguna
-- salida final; se conserva para poder compararla (PENDIENTE 1).
CREATE OR REPLACE FUNCTION bnpl.comision_sobre_monto() RETURNS numeric
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT 0.04::numeric $$;

-- Interes moratorio: 200 pesos por cada semana completa de atraso.
CREATE OR REPLACE FUNCTION bnpl.interes_moratorio_semanal() RETURNS numeric
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT 200::numeric $$;

-- Exencion de intereses del primer pedido. PENDIENTE 2: en el legacy la condicion colapsa a
-- (primer pedido AND createdAt >= 2024-04-22); las fechas 2024-09-01 y 2024-10-13 que
-- aparecen en el codigo no tienen ningun efecto.
CREATE OR REPLACE FUNCTION bnpl.exencion_interes_desde() RETURNS date
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT '2024-04-22'::date $$;

-- Dias sin actividad tras los cuales un cliente deja de considerarse activo.
CREATE OR REPLACE FUNCTION bnpl.dias_inactividad() RETURNS int
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT 30 $$;

-- Estados de orden que cuentan como activacion del credito.
CREATE OR REPLACE FUNCTION bnpl.estados_activacion() RETURNS text[]
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$ SELECT ARRAY['COMPLETED', 'CREATED', 'IN_DELIVERY'] $$;

-- ── Conversiones de fecha ────────────────────────────────────────────────────

-- Epoch ms (UTC) -> timestamp en hora Mexico.
-- Replica epoch_to_date() del legacy: datetime.fromtimestamp(ms/1000) - 6h. Ojo: esa funcion
-- usaba la zona local de la maquina, asi que solo daba hora Mexico si corria en un host en UTC
-- (habia un notebook 'Cortes de Venta-EC2AMAZ-...'). Aqui el offset es explicito y no depende
-- de donde corra. Mexico no tiene horario de verano desde 2022, asi que -6 es fijo.
CREATE OR REPLACE FUNCTION bnpl.epoch_ms_a_mx(ms double precision) RETURNS timestamp
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE WHEN ms IS NOT NULL AND ms > 0
                THEN (to_timestamp(ms / 1000) AT TIME ZONE 'UTC') - interval '6 hours' END
$$;

-- Fecha de negocio de hoy, en hora Mexico. Existe por el mismo motivo que el offset explicito
-- de epoch_ms_a_mx(): current_date depende de la zona del servidor, no de la del negocio. En un
-- host en UTC, entre las 18:00 y las 24:00 MX current_date ya es el dia siguiente, y eso corre
-- las ventanas y la mora un dia entero.
--
-- Paso en rabbit-bi-local: estaba en UTC y el corte de venta salio con 1,077 filas en vez de
-- 2,027, porque el ancla salto del jueves 06 al 13 (2026-08-12). La base quedo en
-- America/Mexico_City, asi que current_date ya daria la fecha correcta; estas dos funciones son
-- el blindaje para que el resultado no dependa de como este configurado el host.
--
-- ahora_mx() ademas devuelve timestamp *sin* zona, que es lo que hay en las vistas: comparar un
-- timestamp naive contra now() (timestamptz) hace que Postgres interprete el naive en la zona de
-- la sesion, o sea la misma dependencia por la vuelta de los tipos.
CREATE OR REPLACE FUNCTION bnpl.ahora_mx() RETURNS timestamp
    LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT (now() AT TIME ZONE 'UTC') - interval '6 hours'
$$;

CREATE OR REPLACE FUNCTION bnpl.hoy_mx() RETURNS date
    LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT bnpl.ahora_mx()::date
$$;

-- Texto ISO 8601 -> timestamp en hora Mexico. Devuelve NULL en lugar de fallar si el valor no
-- es una fecha ('No Information' y similares aparecen en estas colecciones).
CREATE OR REPLACE FUNCTION bnpl.iso_a_mx(valor text) RETURNS timestamp
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE WHEN valor ~ '^\d{4}-\d{2}-\d{2}'
                THEN (valor::timestamptz AT TIME ZONE 'UTC') - interval '6 hours' END
$$;

-- Texto -> date, con la MISMA guarda que iso_a_mx(). Existe porque esa guarda se puso en
-- createdAt y authorizationDate pero no en birthdate, que en el staging tambien es text
-- (sql/01:152) y viene de captura libre. Un solo '00/00/0000' en una fila de
-- fintech-credit-request tumba el rebuild entero de bnpl.grid_bnpl.
--
-- Se valida el rango ademas del patron: to_date() no falla con '2024-13-45', lo desborda al
-- año siguiente, y una edad calculada sobre eso pasa desapercibida.
CREATE OR REPLACE FUNCTION bnpl.a_fecha(valor text) RETURNS date
    LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
BEGIN
    RETURN CASE
        WHEN valor ~ '^\d{4}-\d{2}-\d{2}'
             AND left(valor, 10)::date BETWEEN '1900-01-01'::date AND '2100-01-01'::date
        THEN left(valor, 10)::date
    END;
EXCEPTION WHEN others THEN
    RETURN NULL;
END
$$;

-- Texto -> coordenada. `maximo` es 90 para latitud y 180 para longitud. Devuelve NULL si el
-- texto no es numerico o si cae fuera del rango: en el staging latitude/longitude son text
-- (sql/01:131-132 y sql/01:152) y ahi han llegado cadenas vacias, comas decimales y ceros.
CREATE OR REPLACE FUNCTION bnpl.a_coord(valor text, maximo double precision)
    RETURNS double precision
    LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE v double precision;
BEGIN
    v := nullif(trim(valor), '')::double precision;
    RETURN CASE WHEN v BETWEEN -maximo AND maximo AND v <> 0 THEN v END;
EXCEPTION WHEN others THEN
    RETURN NULL;
END
$$;

-- Si la fecha de pago cae en fin de semana se corre al lunes siguiente.
CREATE OR REPLACE FUNCTION bnpl.mover_a_lunes(f timestamp) RETURNS timestamp
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE extract(isodow FROM f)
               WHEN 6 THEN f + interval '2 days'   -- sabado
               WHEN 7 THEN f + interval '1 day'    -- domingo
               ELSE f
           END
$$;

-- Diferencia en meses calendario, como la calcula el legacy:
-- (año_b - año_a) * 12 + (mes_b - mes_a).
CREATE OR REPLACE FUNCTION bnpl.meses_entre(desde timestamp, hasta timestamp) RETURNS int
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE WHEN desde IS NULL OR hasta IS NULL THEN NULL
                ELSE (extract(year FROM hasta)::int - extract(year FROM desde)::int) * 12
                     + (extract(month FROM hasta)::int - extract(month FROM desde)::int) END
$$;

-- ── Clasificacion de morosidad ───────────────────────────────────────────────

-- Bucket PAR a partir de los dias de atraso. Los cortes son los del legacy (celda 82):
-- Ongoing / DQ 1-6 / DQ 7-14 / DQ 15-29 / DQ 30-59 / DQ 60-89 / DQ 90+.
CREATE OR REPLACE FUNCTION bnpl.bucket_par(dias_atraso int) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE
               WHEN dias_atraso IS NULL   THEN NULL
               WHEN dias_atraso < 1       THEN 'Ongoing'
               WHEN dias_atraso <= 6      THEN 'DQ 1-6'
               WHEN dias_atraso <= 14     THEN 'DQ 7-14'
               WHEN dias_atraso <= 29     THEN 'DQ 15-29'
               WHEN dias_atraso <= 59     THEN 'DQ 30-59'
               WHEN dias_atraso <= 89     THEN 'DQ 60-89'
               ELSE 'DQ 90+'
           END
$$;

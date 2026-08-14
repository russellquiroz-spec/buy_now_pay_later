"""Extraccion Redshift -> staging PostgreSQL (schema redshift_bnpl).

Trae lo que BNPL necesita y no existe en Mongo: la estructura comercial (ruta, supervisor,
oficina) de cada cliente, en dos versiones.

  estructura_comercial   la ruta vigente hoy. Se trae completa (~611K filas): el grid necesita
                         ruta para todos los clientes, no solo los que tienen credito.
  route_mapping          catalogo de rutas -> equipo, oficina, region. Es el dim_ruta del
                         modelo estrella.
  ruta_cliente_scd       la ruta historica, como intervalos [valido_desde, valido_hasta].

El SCD se comprime EN Redshift, no aca: la vigencia diaria son 301M filas y para el universo
BNPL 5.3M, pero comprimida por cambio de ruta baja a ~13.6K. Traer 5.3M filas por el tunel para
comprimirlas despues seria absurdo.

Alcance del SCD: solo clientes con credito BNPL (con orden o aprobados). Para el resto no hay
analisis de riesgo que atribuir, y el IN de la consulta se mantiene manejable.
"""
import argparse
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
# Las dos librerias exportan extract_sql: la de Redshift lleva la base como primer
# argumento posicional, la de PostgreSQL la lleva en `db=`. Se importan con nombres
# distintos para que en cada llamada se vea contra que motor va.
from postgres_local_client import execute_sql as pg_execute_sql
from postgres_local_client import extract_sql as pg_extract_sql
from postgres_local_client import transaction as pg_transaction
from redshift_extractor import extract_sql

BASE_DIR = Path(__file__).resolve().parent

SCHEMA = "redshift_bnpl"
OPS_SCHEMA = "bnpl_ops"

# Alias de postgres_local_client.
DB_RS_RW = "redshift_bnpl_rw"
DB_BNPL = "bnpl"
DB_OPS_RW = "bnpl_ops_rw"
REDSHIFT_DB = "data-rabbit-prod"
TZ_OFFSET_HOURS = -6

SQL_ESTRUCTURA = """
select netsuite_id, tipo_cliente, status, ruta, ruta_canon, supervisor,
       oficina, oficina_canon, region, region_canon, pais, dia, frecuencia,
       fecha_inicio, data_source
from catalog.cat_estructura_comercial_v3
where netsuite_id is not null
"""

SQL_ROUTE_MAPPING = """
select ruta, equipo, oficina, region, pais
from catalog.route_mapping
where ruta is not null
"""

# La vigencia diaria comprimida a intervalos: una fila por tramo continuo con la misma ruta.
SQL_SCD = """
with base as (
    select netsuite_id, fecha::date as fecha, ruta, supervisor, oficina, region,
           tipo_cliente, status
    from catalog.cat_estructura_comercial_vigencia_diaria
    where netsuite_id in ({ids})
      and ruta is not null
),
marcado as (
    select b.*, lag(ruta) over (partition by netsuite_id order by fecha) as ruta_prev
    from base b
),
cambios as (
    select m.*,
           case when ruta_prev is null or ruta <> ruta_prev then 1 else 0 end as es_cambio
    from marcado m
),
grupos as (
    select c.*,
           sum(es_cambio) over (
               partition by netsuite_id order by fecha
               rows between unbounded preceding and current row
           ) as tramo
    from cambios c
)
select netsuite_id,
       ruta,
       max(supervisor)   as supervisor,
       max(oficina)      as oficina,
       max(region)       as region,
       max(tipo_cliente) as tipo_cliente,
       max(status)       as status,
       min(fecha)        as valido_desde,
       max(fecha)        as valido_hasta,
       count(*)          as dias_vigencia
from grupos
group by netsuite_id, ruta, tramo
"""

# Venta Rabbit completa (no solo BNPL) de los clientes con credito, a grano de sales order.
# Responde lo que la capa BNPL no sabe: que compro el tendero FUERA del credito.
#
# Las tablas por año no son homogeneas: 2021-2024 traen ~32 columnas y solo monto_venta; las _v2
# de 2025-2026 traen 44 y 46, con el desglose amount_completed / amount_in_progress. Se usa el
# desglose donde existe y monto_venta antes, la misma regla que en cosechas — hay un escalon en
# enero-2025 y es deliberado. Diciembre-2023 va dividido entre 20 (fuente corrupta, ver
# PENDIENTES_NEGOCIO.md). Es venta ORDENADA, no surtida; para distinguir se arrastra status_pedido.
SQL_VENTAS_CLIENTE = """
with source as (
{viejas}
    union all
{nuevas}
)
select ns_id                        as netsuite_id,
       so_id                        as sales_order_id,
       min(fecha_creacion_mx)::date as fecha_creacion,
       max(clase_canal)             as clase_canal,
       max(status_pedido)           as status_pedido,
       count(distinct item_itemid)  as skus,
       sum(cantidad_piezas)         as piezas,
       sum(monto_venta)             as monto_venta
from source
where ns_id in ({ids})
  and fecha_creacion_mx >= '{desde}'
  and so_id is not null
group by 1, 2
having sum(cantidad_piezas) <> 0 or sum(monto_venta) <> 0
"""

# Arranca en 2021-04, el inicio de la serie de pedidos enriquecidos, y no seis meses antes del
# primer credito como al principio: overall_prev_post_bnpl_sales compara la venta del cliente
# antes y despues de enrolarse, y el CSV historico llega a 57 meses ANTES del enrolamiento. Con
# una ventana corta esa comparacion se queda sin lado izquierdo.
VENTAS_DESDE = "2021-04-01"
# Las tablas _v2 con el desglose de montos solo existen desde 2025; para lo anterior se usa
# monto_venta, igual que en cosechas.
VENTAS_ANIOS_VIEJAS = ["2021", "2022", "2023", "2024"]
VENTAS_ANIOS_NUEVAS = ["2025_v2", "2026_v2"]

# Cosechas de toda la base Rabbit por mes de primera transaccion, agregadas EN Redshift.
#
# Tres decisiones que estan medidas y no son obvias:
#
#   * El monto sale de amount_completed + amount_in_progress en las tablas _v2 (2025 en adelante)
#     y de monto_venta en las viejas, que es la unica columna que existe ahi. Hay un escalon en
#     enero-2025 por el cambio de definicion; es deliberado, para quedar consistente con el resto
#     del proyecto (ver ventas_cliente y analisis_one_shot).
#   * Diciembre-2023 va dividido entre 20: mv_pedidos_enriquecidos_2023 lo trae inflado ~25x en
#     monto y en piezas. Es un parche sobre datos corruptos, no un calculo — ver
#     PENDIENTES_NEGOCIO.md. Cuando se corrija la fuente hay que quitar el `/ 20.0`.
#   * flg_cte_bnpl = 'Y' solo para clientes CON orden BNPL, no para todo el que este enrolado.
#     Contrastado contra el CSV historico: con la definicion amplia el error sube de 3.1% a 3.7%
#     en clientes activos y de 9.1% a 9.9% en gross.
SQL_COSECHAS = """
with source as (
{viejas}
    union all
{nuevas}
),
por_orden as (
    select ns_id, so_id, date_trunc('month', fecha_creacion_mx)::date as mes,
           sum(monto_venta) as monto, sum(cantidad_piezas) as piezas
    from source
    where ns_id is not null and so_id is not null
    group by 1, 2, 3
    having sum(cantidad_piezas) <> 0 or sum(monto_venta) <> 0
),
cliente_mes as (
    select ns_id, mes, count(distinct so_id) as ordenes, sum(monto) as gross
    from por_orden group by 1, 2
),
primera as (select ns_id, min(mes) as mes_ft_tx from cliente_mes group by 1),
clientes as (
    select p.ns_id, p.mes_ft_tx,
           case when p.ns_id in ({ids}) then 'Y' else 'N' end as flg_cte_bnpl,
           {case_ft} as mes_ft_tx_bnpl
    from primera p
),
cohortes as (
    select mes_ft_tx, flg_cte_bnpl, mes_ft_tx_bnpl, count(distinct ns_id) as clientes_cosecha
    from clientes group by 1, 2, 3
),
meses as (select distinct mes as mes_tx from cliente_mes),
panel as (
    select c.*, m.mes_tx,
           (extract(year from m.mes_tx) - extract(year from c.mes_ft_tx)) * 12
           + (extract(month from m.mes_tx) - extract(month from c.mes_ft_tx)) as periodo
    from cohortes c cross join meses m
    where m.mes_tx >= c.mes_ft_tx
),
actividad as (
    select cl.mes_ft_tx, cl.flg_cte_bnpl, cl.mes_ft_tx_bnpl, cm.mes as mes_tx,
           count(distinct cm.ns_id) as cliente_activo,
           sum(cm.ordenes) as ordenes, sum(cm.gross) as gross_sales
    from cliente_mes cm join clientes cl on cl.ns_id = cm.ns_id
    group by 1, 2, 3, 4
),
unido as (
    select p.mes_tx, p.mes_ft_tx, p.mes_ft_tx_bnpl, p.flg_cte_bnpl, p.periodo, p.clientes_cosecha,
           coalesce(a.cliente_activo, 0) as cliente_activo,
           coalesce(a.ordenes, 0)        as ordenes,
           coalesce(a.gross_sales, 0)    as gross_sales
    from panel p
    left join actividad a
           on a.mes_ft_tx = p.mes_ft_tx and a.flg_cte_bnpl = p.flg_cte_bnpl
          and a.mes_tx = p.mes_tx
          and coalesce(a.mes_ft_tx_bnpl, '1900-01-01') = coalesce(p.mes_ft_tx_bnpl, '1900-01-01')
),
base_ft as (
    -- La linea base de la cosecha: su valor en periodo 0. Es contra esto que rebasan las
    -- medidas de supervivencia y tendencia del tablero.
    select mes_ft_tx, flg_cte_bnpl, mes_ft_tx_bnpl,
           max(case when periodo = 0 then gross_sales end) as gross_sales_ft,
           max(case when periodo = 0 then ordenes end)     as ordenes_ft
    from unido group by 1, 2, 3
)
select u.mes_tx, u.mes_ft_tx, u.mes_ft_tx_bnpl, u.flg_cte_bnpl, u.periodo,
       u.clientes_cosecha, u.cliente_activo, u.ordenes, u.gross_sales,
       f.ordenes_ft, f.gross_sales_ft
from unido u
join base_ft f
  on f.mes_ft_tx = u.mes_ft_tx and f.flg_cte_bnpl = u.flg_cte_bnpl
 and coalesce(f.mes_ft_tx_bnpl, '1900-01-01') = coalesce(u.mes_ft_tx_bnpl, '1900-01-01')
"""

COSECHAS_ANIOS_VIEJAS = ["2021", "2022", "2023", "2024"]
COSECHAS_ANIOS_NUEVAS = ["2025_v2", "2026_v2"]

# Estacionalidad por mes calendario sobre toda la base Rabbit. Devuelve 12 filas.
SQL_ESTACIONALIDAD = """
with source as (
{viejas}
    union all
{nuevas}
),
por_orden as (
    select ns_id, so_id, date_trunc('month', fecha_creacion_mx)::date as mes,
           sum(monto_venta) as monto, sum(cantidad_piezas) as piezas
    from source
    where ns_id is not null and so_id is not null
    group by 1, 2, 3
    having sum(cantidad_piezas) <> 0 or sum(monto_venta) <> 0
)
select extract(month from mes)::int                                  as mes_calendario,
       sum(monto) / nullif(count(distinct so_id), 0)                 as ticket_promedio,
       sum(monto) / nullif(count(distinct ns_id || to_char(mes, 'YYYYMM')), 0)
                                                                     as volumen_promedio
from por_orden
group by 1
"""


def _ahora_mx() -> datetime:
    return (datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)).replace(tzinfo=None)


def _universo_bnpl() -> list:
    """Clientes con credito: con al menos una orden o con aprobacion."""
    df = pg_extract_sql("""
        select distinct netsuite_id from bnpl.grouped_orders
        where netsuite_id is not null
        union
        select distinct "netsuiteId" from mongo_bnpl.fintech_credit_approval_production
        where "netsuiteId" is not null
    """, db=DB_BNPL)
    return [v.strip() for v in df.iloc[:, 0] if v and v.strip()]


def _bloques_pedidos(viejas: list, nuevas: list, extra_cols: str = "") -> tuple:
    """Arma los SELECT por año con la definicion de monto que corresponde a cada tabla.

    Las tablas viejas solo tienen monto_venta; las _v2 traen el desglose por status. Diciembre-2023
    va entre 20 porque la fuente lo trae inflado ~25x (ver PENDIENTES_NEGOCIO.md).
    """
    v = "\n    union all\n".join(f"""    select ns_id, so_id, fecha_creacion_mx{extra_cols}, cantidad_piezas,
           case when fecha_creacion_mx >= date '2023-12-01'
                     and fecha_creacion_mx < date '2024-01-01'
                then monto_venta / 20.0 else monto_venta end as monto_venta
      from analytics.mv_pedidos_enriquecidos_{a}""" for a in viejas)
    n = "\n    union all\n".join(f"""    select ns_id, so_id, fecha_creacion_mx{extra_cols},
           coalesce(quantity_completed, 0) + coalesce(quantity_in_progress, 0) as cantidad_piezas,
           coalesce(amount_completed, 0)   + coalesce(amount_in_progress, 0)   as monto_venta
      from analytics.mv_pedidos_enriquecidos_{a}""" for a in nuevas)
    return v, n


def _sql_cosechas() -> str:
    """Arma SQL_COSECHAS con las listas de clientes BNPL embebidas.

    Redshift no acepta VALUES multi-fila en subconsulta, asi que el mes de la primera orden BNPL
    se pasa como un CASE de ~33 listas IN, una por mes.
    """
    df = pg_extract_sql("""
        select netsuite_id,
               to_char(date_trunc('month', min(created_at))::date, 'YYYY-MM-DD') AS mes
        from bnpl.grouped_orders
        where order_status = ANY (bnpl.estados_activacion())
          and netsuite_id is not null
        group by 1
    """, db=DB_BNPL)
    df["netsuite_id"] = df["netsuite_id"].astype(str).str.strip()
    df = df[df["netsuite_id"] != ""]

    ids = ",".join(f"'{i}'" for i in df["netsuite_id"])
    case_ft = "case\n" + "\n".join(
        f"               when ns_id in ({','.join(chr(39) + i + chr(39) for i in g['netsuite_id'])})"
        f" then date '{mes}'"
        for mes, g in df.groupby("mes")
    ) + "\n           end"

    viejas, nuevas = _bloques_pedidos(COSECHAS_ANIOS_VIEJAS, COSECHAS_ANIOS_NUEVAS)
    return SQL_COSECHAS.format(viejas=viejas, nuevas=nuevas, ids=ids, case_ft=case_ft)


def _cargar(nombre: str, df: pd.DataFrame, inicio, segundos: float) -> None:
    # El esquema lo gobierna sql/12_redshift_staging.sql, no los dtypes de pandas: con `replace`
    # el tipo dependia de lo que pandas hubiera inferido en la corrida, y al migrar a la VM las
    # columnas de fecha llegaron como text, rompiendo las vistas de ruta.
    # DDL, TRUNCATE y carga en una sola transaccion: antes el TRUNCATE se confirmaba
    # aparte del append, asi que un fallo del COPY dejaba la tabla vacia.
    with pg_transaction(db=DB_RS_RW) as tx:
        tx.execute_sql((BASE_DIR / "sql" / "12_redshift_staging.sql").read_text(encoding="utf-8"))
        tx.execute_sql(f'TRUNCATE {SCHEMA}."{nombre}"')
        tx.load_dataframe(df, nombre, schema=SCHEMA)
    # La bitacora vive en otro schema y por lo tanto en otro alias: va fuera de la
    # transaccion, igual que antes de la migracion.
    pg_execute_sql(
        f"INSERT INTO {OPS_SCHEMA}.etl_runs (started_at, tabla, modo, filas, segundos) "
        f"VALUES (:inicio, :tabla, 'full', :filas, :segundos) "
        f"ON CONFLICT (started_at, tabla) DO NOTHING",
        {
            "inicio": inicio,
            "tabla": f"{SCHEMA}.{nombre}",
            "filas": int(len(df)),
            "segundos": round(segundos, 1),
        },
        db=DB_OPS_RW,
    )
    print(f"  -> {SCHEMA}.{nombre}: {len(df):,} filas en {segundos:.1f}s")


def run(solo: list = None) -> None:
    tablas = solo or [
        "estructura_comercial", "route_mapping", "ruta_cliente_scd", "ventas_cliente",
        "cosechas_agg", "estacionalidad_mes",
    ]
    # El universo se consulta una sola vez aunque lo pidan las dos tablas que lo usan.
    universo = None

    if "estructura_comercial" in tablas:
        print("Extrayendo estructura comercial (ruta vigente)...")
        inicio, t0 = _ahora_mx(), time.time()
        df = extract_sql(REDSHIFT_DB, SQL_ESTRUCTURA)
        df["netsuite_id"] = df["netsuite_id"].astype(str).str.strip()
        _cargar("estructura_comercial", df, inicio, time.time() - t0)

    if "route_mapping" in tablas:
        print("Extrayendo catalogo de rutas...")
        inicio, t0 = _ahora_mx(), time.time()
        df = extract_sql(REDSHIFT_DB, SQL_ROUTE_MAPPING)
        _cargar("route_mapping", df, inicio, time.time() - t0)

    if "ruta_cliente_scd" in tablas:
        universo = universo if universo is not None else _universo_bnpl()
        print(f"Extrayendo ruta historica de {len(universo):,} clientes con credito...")
        inicio, t0 = _ahora_mx(), time.time()
        lista = ",".join(f"'{i}'" for i in universo)
        df = extract_sql(REDSHIFT_DB, SQL_SCD.format(ids=lista))
        df["netsuite_id"] = df["netsuite_id"].astype(str).str.strip()
        _cargar("ruta_cliente_scd", df, inicio, time.time() - t0)

    if "ventas_cliente" in tablas:
        universo = universo if universo is not None else _universo_bnpl()
        print(f"Extrayendo venta Rabbit completa de {len(universo):,} clientes con credito...")
        inicio, t0 = _ahora_mx(), time.time()
        lista = ",".join(f"'{i}'" for i in universo)
        v, n = _bloques_pedidos(
            VENTAS_ANIOS_VIEJAS, VENTAS_ANIOS_NUEVAS,
            extra_cols=", clase_canal, status_pedido, item_itemid",
        )
        df = extract_sql(
            REDSHIFT_DB,
            SQL_VENTAS_CLIENTE.format(viejas=v, nuevas=n, ids=lista, desde=VENTAS_DESDE),
        )
        df["netsuite_id"] = df["netsuite_id"].astype(str).str.strip()
        df["sales_order_id"] = df["sales_order_id"].astype(str).str.strip()
        _cargar("ventas_cliente", df, inicio, time.time() - t0)

    if "cosechas_agg" in tablas:
        print("Agregando cosechas de la base Rabbit completa...")
        inicio, t0 = _ahora_mx(), time.time()
        df = extract_sql(REDSHIFT_DB, _sql_cosechas())
        _cargar("cosechas_agg", df, inicio, time.time() - t0)

    if "estacionalidad_mes" in tablas:
        print("Calculando estacionalidad por mes calendario...")
        inicio, t0 = _ahora_mx(), time.time()
        v, n = _bloques_pedidos(COSECHAS_ANIOS_VIEJAS, COSECHAS_ANIOS_NUEVAS)
        df = extract_sql(REDSHIFT_DB, SQL_ESTACIONALIDAD.format(viejas=v, nuevas=n))
        _cargar("estacionalidad_mes", df, inicio, time.time() - t0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carga la estructura comercial desde Redshift")
    parser.add_argument("--solo", help="tablas a cargar, separadas por coma")
    args = parser.parse_args()
    run(solo=args.solo.split(",") if args.solo else None)

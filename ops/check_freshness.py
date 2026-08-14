"""Frescura de las fuentes BNPL: que tan al dia esta Mongo y que tan al dia esta el staging.

Una sola llamada a Mongo (los $lookup evitan abrir un tunel por coleccion) y una sola
consulta al staging. Escribe la foto en bnpl_ops.source_freshness y la historia en
bnpl_ops.freshness_history.
"""
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from mongo_extractor import extract_aggregate
from postgres_local_client import execute_sql, extract_sql, transaction

from config import (
    DB_OPS_RW,
    DB_STAGING,
    FALTANTES_WARN_PCT,
    FUENTES,
    LAG_CRIT_HORAS,
    LAG_WARN_HORAS,
    MONGO_PROFILE,
    SQL_DIR,
    STAGING_SCHEMA,
    TZ_OFFSET_HOURS,
)


def _clave(coleccion: str) -> str:
    return coleccion.replace("-", "_")


def _ahora_mx() -> datetime:
    return (datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)).replace(tzinfo=None)


def _epoch_ms_a_mx(epoch_ms):
    if epoch_ms is None or epoch_ms != epoch_ms:  # descarta None y NaN
        return None
    utc = datetime.fromtimestamp(epoch_ms / 1000, timezone.utc)
    return (utc + timedelta(hours=TZ_OFFSET_HOURS)).replace(tzinfo=None)


def aplicar_ddl() -> None:
    ddl = (SQL_DIR / "00_bnpl_ops.sql").read_text(encoding="utf-8")
    execute_sql(ddl, db=DB_OPS_RW)


def sondear_mongo() -> dict:
    """Conteo y ultima escritura de cada coleccion, en una sola llamada."""
    colecciones = list(FUENTES)
    pipeline = [{"$limit": 1}, {"$project": {"_id": 0}}]
    for coleccion in colecciones:
        clave = _clave(coleccion)
        pipeline.append({
            "$lookup": {
                "from": coleccion,
                "pipeline": [{"$collStats": {"count": {}}}, {"$project": {"_id": 0, "n": "$count"}}],
                "as": f"stats_{clave}",
            }
        })
        pipeline.append({
            "$lookup": {
                "from": coleccion,
                "pipeline": [{"$sort": {"_id": -1}}, {"$limit": 1}, {"$project": {"_id": 1}}],
                "as": f"last_{clave}",
            }
        })
        campo_update = FUENTES[coleccion]["campo_update"]
        if campo_update:
            pipeline.append({
                "$lookup": {
                    "from": coleccion,
                    "pipeline": [
                        {"$group": {"_id": None, "maxupd": {"$max": f"${campo_update}"}}},
                        {"$project": {"_id": 0, "maxupd": 1}},
                    ],
                    "as": f"upd_{clave}",
                }
            })

    df = extract_aggregate(MONGO_PROFILE, colecciones[0], pipeline)
    if df.empty:
        raise RuntimeError(f"La coleccion ancla '{colecciones[0]}' no devolvio documentos")

    fila = df.iloc[0]
    resultado = {}
    for coleccion in colecciones:
        clave = _clave(coleccion)
        stats = fila[f"stats_{clave}"]
        last = fila[f"last_{clave}"]
        oid = last[0]["_id"] if len(last) else None
        fechas = []
        if isinstance(oid, ObjectId):
            fechas.append(
                (oid.generation_time + timedelta(hours=TZ_OFFSET_HOURS)).replace(tzinfo=None)
            )
        if FUENTES[coleccion]["campo_update"]:
            upd = fila[f"upd_{clave}"]
            actualizado = _epoch_ms_a_mx(upd[0].get("maxupd")) if len(upd) else None
            if actualizado:
                fechas.append(actualizado)
        resultado[coleccion] = {
            "docs_mongo": int(stats[0]["n"]) if len(stats) else 0,
            "last_write_mongo": max(fechas) if fechas else None,
        }
    return resultado


def sondear_staging() -> dict:
    """Conteo y ultima fecha de negocio de cada tabla del staging que exista."""
    columnas = extract_sql(f"""
        select table_name, column_name
        from information_schema.columns
        where table_schema = '{STAGING_SCHEMA}'
    """, db=DB_STAGING)
    existentes = {}
    for tabla, grupo in columnas.groupby("table_name"):
        existentes[tabla] = set(grupo["column_name"])

    bloques = []
    for fuente in FUENTES.values():
        tabla, col_fecha = fuente["tabla"], fuente["col_fecha"]
        if tabla not in existentes:
            continue
        fecha = f'max("{col_fecha}")' if col_fecha and col_fecha in existentes[tabla] else "null"
        bloques.append(
            f"select '{tabla}' as tabla, count(*) as n, {fecha}::double precision as max_epoch_ms "
            f'from {STAGING_SCHEMA}."{tabla}"'
        )

    resultado = {}
    if bloques:
        df = extract_sql(" union all ".join(bloques), db=DB_STAGING)
        for row in df.to_dict("records"):
            resultado[row["tabla"]] = {
                "docs_staging": int(row["n"]),
                "last_dato_staging": _epoch_ms_a_mx(row["max_epoch_ms"]),
            }

    for fuente in FUENTES.values():
        resultado.setdefault(fuente["tabla"], None)  # tabla que todavia no existe
    return resultado


def _semaforo_fuente(lag_horas, docs_mongo) -> str:
    # Cero documentos no es "no se pudo medir la frescura": o renombraron la coleccion, o
    # el sondeo no la vio. Es el peor estado posible, porque el ETL cargaria eso encima
    # del staging. Va como CRIT para que main.py detenga la corrida en el paso [1/6] y no
    # como SIN_DATOS, que main.py:99 ignora.
    if docs_mongo == 0:
        return "CRIT"
    if lag_horas is None:
        return "SIN_DATOS"
    if lag_horas >= LAG_CRIT_HORAS:
        return "CRIT"
    if lag_horas >= LAG_WARN_HORAS:
        return "WARN"
    return "OK"


def _semaforo_staging(docs_mongo, staging) -> str:
    if staging is None:
        return "FALTA"
    if docs_mongo == 0:
        # Mismo criterio que arriba: la fuente no tiene con que alimentar al staging.
        return "CRIT"
    faltantes = docs_mongo - staging["docs_staging"]
    if faltantes <= 0:
        return "OK"
    return "WARN" if faltantes / docs_mongo <= FALTANTES_WARN_PCT else "CRIT"


def construir_filas(mongo: dict, staging: dict, checked_at: datetime) -> list:
    filas = []
    for coleccion, fuente in FUENTES.items():
        tabla = fuente["tabla"]
        m = mongo[coleccion]
        s = staging.get(tabla)
        lag_horas = None
        if m["last_write_mongo"] is not None:
            lag_horas = round(
                (checked_at - m["last_write_mongo"]).total_seconds() / 3600, 2
            )
        docs_staging = s["docs_staging"] if s else None
        filas.append({
            "coleccion": coleccion,
            "tabla_staging": tabla,
            "docs_mongo": m["docs_mongo"],
            "docs_staging": docs_staging,
            "docs_faltantes": (m["docs_mongo"] - docs_staging) if s else None,
            "last_write_mongo": m["last_write_mongo"],
            "last_dato_staging": s["last_dato_staging"] if s else None,
            "lag_fuente_horas": lag_horas,
            "semaforo_fuente": _semaforo_fuente(lag_horas, m["docs_mongo"]),
            "semaforo_staging": _semaforo_staging(m["docs_mongo"], s),
            "checked_at": checked_at,
        })
    return filas


def persistir(filas: list) -> None:
    cols = [
        "coleccion", "tabla_staging", "docs_mongo", "docs_staging", "docs_faltantes",
        "last_write_mongo", "last_dato_staging", "lag_fuente_horas", "semaforo_fuente",
        "semaforo_staging", "checked_at",
    ]
    cols_hist = [c for c in cols if c != "tabla_staging"]
    sql_snapshot = (
        f"INSERT INTO bnpl_ops.source_freshness ({', '.join(cols)}) "
        f"VALUES ({', '.join(':' + c for c in cols)})"
    )
    sql_hist = (
        f"INSERT INTO bnpl_ops.freshness_history ({', '.join(cols_hist)}) "
        f"VALUES ({', '.join(':' + c for c in cols_hist)}) "
        f"ON CONFLICT (checked_at, coleccion) DO NOTHING"
    )
    # Fila por fila: la libreria no tiene executemany (params es un dict, no una lista).
    # upsert_dataframe no sirve de reemplazo porque siempre genera DO UPDATE, y aca el
    # historico necesita DO NOTHING. La transaccion mantiene el todo-o-nada del TRUNCATE.
    with transaction(db=DB_OPS_RW) as tx:
        tx.execute_sql("TRUNCATE bnpl_ops.source_freshness")
        for fila in filas:
            tx.execute_sql(sql_snapshot, {c: fila[c] for c in cols})
            tx.execute_sql(sql_hist, {c: fila[c] for c in cols_hist})


def run() -> list:
    aplicar_ddl()

    print("Sondeando Mongo...")
    mongo = sondear_mongo()
    print("Sondeando staging...")
    staging = sondear_staging()

    checked_at = _ahora_mx()
    filas = construir_filas(mongo, staging, checked_at)
    persistir(filas)

    print(f"\n{'coleccion':<45} {'mongo':>10} {'staging':>10} {'ultima escritura':>17} {'fuente':>7} {'staging':>8}")
    for f in filas:
        ultima = f["last_write_mongo"].strftime("%Y-%m-%d %H:%M") if f["last_write_mongo"] else "-"
        staging_n = f"{f['docs_staging']:,}" if f["docs_staging"] is not None else "-"
        print(
            f"{f['coleccion']:<45} {f['docs_mongo']:>10,} {staging_n:>10} "
            f"{ultima:>17} {f['semaforo_fuente']:>7} {f['semaforo_staging']:>8}"
        )
    return filas


if __name__ == "__main__":
    run()

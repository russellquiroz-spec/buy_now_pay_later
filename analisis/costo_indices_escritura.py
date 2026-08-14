"""Cuanto cuesta escribir 99K filas con y sin los indices de credit_order.

Resultado 2026-08-12: 1.0s sin indices, 2.8s con los 4 indices. El costo es despreciable
frente a los 166-356s que tarda la extraccion desde Mongo.

Crea y borra dos tablas temporales en mongo_bnpl. No toca los datos reales.
"""
import time

from postgres_local_client import execute_sql, transaction

DB_RW = "mongo_bnpl_rw"  # crea y borra tablas temporales: necesita ALLOW_DDL

CORTE = "(extract(epoch from now() - interval '60 days') * 1000)"

with transaction(db=DB_RW) as tx:
    tx.execute_sql("DROP TABLE IF EXISTS mongo_bnpl.tmp_sin_ix")
    tx.execute_sql("DROP TABLE IF EXISTS mongo_bnpl.tmp_con_ix")
    tx.execute_sql("CREATE TABLE mongo_bnpl.tmp_sin_ix (LIKE mongo_bnpl.credit_order_production)")
    tx.execute_sql(
        "CREATE TABLE mongo_bnpl.tmp_con_ix "
        "(LIKE mongo_bnpl.credit_order_production INCLUDING INDEXES)"
    )

for destino in ("tmp_sin_ix", "tmp_con_ix"):
    t0 = time.time()
    # execute_sql devuelve las filas afectadas, que es lo que antes daba .rowcount
    n = execute_sql(f"""
        INSERT INTO mongo_bnpl.{destino}
        SELECT * FROM mongo_bnpl.credit_order_production
        WHERE "createdAt" >= {CORTE}
    """, db=DB_RW)
    print(f"{destino}: {n:,} filas en {time.time() - t0:.1f}s")

with transaction(db=DB_RW) as tx:
    tx.execute_sql("DROP TABLE IF EXISTS mongo_bnpl.tmp_sin_ix")
    tx.execute_sql("DROP TABLE IF EXISTS mongo_bnpl.tmp_con_ix")
print("temporales eliminadas")

"""Cuanto cuesta escribir 99K filas con y sin los indices de credit_order.

Resultado 2026-08-12: 1.0s sin indices, 2.8s con los 4 indices. El costo es despreciable
frente a los 166-356s que tarda la extraccion desde Mongo.

Crea y borra dos tablas temporales en mongo_bnpl. No toca los datos reales.
"""
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / ".env")
engine = create_engine(os.environ["BD_ENGINE_RABBIT_LOCAL"].strip("'\""))

CORTE = "(extract(epoch from now() - interval '60 days') * 1000)"

with engine.begin() as conn:
    conn.execute(text("DROP TABLE IF EXISTS mongo_bnpl.tmp_sin_ix"))
    conn.execute(text("DROP TABLE IF EXISTS mongo_bnpl.tmp_con_ix"))
    conn.execute(text(
        "CREATE TABLE mongo_bnpl.tmp_sin_ix (LIKE mongo_bnpl.credit_order_production)"
    ))
    conn.execute(text(
        "CREATE TABLE mongo_bnpl.tmp_con_ix "
        "(LIKE mongo_bnpl.credit_order_production INCLUDING INDEXES)"
    ))

for destino in ("tmp_sin_ix", "tmp_con_ix"):
    t0 = time.time()
    with engine.begin() as conn:
        n = conn.execute(text(f"""
            INSERT INTO mongo_bnpl.{destino}
            SELECT * FROM mongo_bnpl.credit_order_production
            WHERE "createdAt" >= {CORTE}
        """)).rowcount
    print(f"{destino}: {n:,} filas en {time.time() - t0:.1f}s")

with engine.begin() as conn:
    conn.execute(text("DROP TABLE IF EXISTS mongo_bnpl.tmp_sin_ix"))
    conn.execute(text("DROP TABLE IF EXISTS mongo_bnpl.tmp_con_ix"))
print("temporales eliminadas")

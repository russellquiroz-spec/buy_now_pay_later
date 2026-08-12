"""Los indices del staging se usan? EXPLAIN ANALYZE de las consultas que corre el pipeline.

Resultado 2026-08-12: la ventana y el lookup por salesOrderId usan Index Only Scan; el join
pagos-ordenes usa hash join (no necesita indice); localizar los estados no finales hace seq
scan de 455 ms porque un B-tree no sirve para un NOT IN.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / ".env")
engine = create_engine(os.environ["BD_ENGINE_RABBIT_LOCAL"].strip("'\""))

CONSULTAS = {
    "1. localizar ordenes en estado no final fuera de la ventana": """
        select distinct "salesOrderId" from mongo_bnpl.credit_order_production
        where "orderStatus" not in ('COMPLETED','REJECTED','CANCELLED','NO_VISITED')
          and "createdAt" < (extract(epoch from now() - interval '60 days') * 1000)
          and "salesOrderId" is not null
    """,
    "2. filas de la ventana (lo que borra el DELETE)": """
        select count(*) from mongo_bnpl.credit_order_production
        where "createdAt" >= (extract(epoch from now() - interval '60 days') * 1000)
    """,
    "3. lookup de una orden por salesOrderId": """
        select count(*) from mongo_bnpl.credit_order_production
        where "salesOrderId" = 'SO19091185'
    """,
    "4. join pagos-ordenes por llave principal (Fase 3)": """
        select count(*)
        from mongo_bnpl.payment_report_production p
        join mongo_bnpl.credit_order_production o on p."transactionId" = o."salesOrderId"
        where p."transactionStatus" = 'paid'
    """,
}

with engine.connect() as conn:
    for titulo, sql in CONSULTAS.items():
        print(f"\n{'=' * 74}\n{titulo}")
        for linea in conn.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {sql}")).fetchall():
            texto = linea[0]
            if any(k in texto for k in ("Scan", "Time:", "Join", "Aggregate", "Sort ")):
                print(f"   {texto.strip()}")

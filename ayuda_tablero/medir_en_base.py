# -*- coding: utf-8 -*-
"""Mide contra la base lo que los tooltips van a afirmar."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from postgres_local_client import extract_sql

DB = "bnpl"

def q(sql, titulo):
    print("=" * 78)
    print(titulo)
    print("=" * 78)
    df = extract_sql(sql, db=DB)
    print(df.to_string(index=False))
    print()
    return df

# 1) Alcance de la cadena grid -> loans_matured -> months_closes
q("""
SELECT
    count(*)                                                   AS filas_months_closes,
    count(DISTINCT m."salesOrderId")                           AS ordenes_distintas,
    count(DISTINCT m."salesOrderId") FILTER (WHERE l."salesOrderId" IS NOT NULL) AS ordenes_en_loans_matured,
    round(100.0 * count(*) FILTER (WHERE l."salesOrderId" IS NOT NULL) / count(*), 2) AS pct_filas_alcanzables,
    round(sum(m."totalAmount")::numeric, 2)                    AS saldo_total,
    round(sum(m."totalAmount") FILTER (WHERE l."salesOrderId" IS NOT NULL)::numeric, 2) AS saldo_alcanzable
FROM pbi_bnpl.months_closes m
LEFT JOIN pbi_bnpl.loans_matured_default_profile l
       ON m."salesOrderId" = l."salesOrderId"
""", "1. Cuanto de months_closes es alcanzable por un filtro del grid (via loans_matured)")

# 2) salesOrderId es unico en loans_matured (requisito del lado 'uno')
q("""
SELECT count(*) AS filas,
       count(DISTINCT "salesOrderId") AS ids_distintos,
       count(*) - count(DISTINCT "salesOrderId") AS duplicados
FROM pbi_bnpl.loans_matured_default_profile
""", "2. loans_matured_default_profile: unicidad de salesOrderId (lado 'uno')")

# 3) PaidPrev: filas y monto (la afirmacion de los tooltips)
q("""
SELECT "dqBucket",
       count(*)                          AS filas,
       round(100.0*count(*)/sum(count(*)) OVER (), 2) AS pct_filas,
       round(sum("totalAmount")::numeric, 2) AS suma_totalAmount
FROM pbi_bnpl.months_closes
GROUP BY 1 ORDER BY filas DESC
""", "3. months_closes por bucket: PaidPrev y su monto")

# 4) Mes en curso incompleto: ultimo corte disponible
q("""
SELECT "corte",
       count(*) AS filas,
       round(sum("totalAmount")::numeric, 2) AS saldo
FROM pbi_bnpl.months_closes
GROUP BY 1 ORDER BY 1 DESC LIMIT 4
""", "4. Ultimos cortes de months_closes (el ultimo es el mes en curso)")

# 5) PAR: los dos denominadores, con cifras
q("""
SELECT round(sum("PAR30")::numeric,2)            AS par30,
       round(sum("outstandingBalance")::numeric,2) AS saldo_vivo,
       round(sum("deployedCapital")::numeric,2)  AS capital_desplegado,
       round(100.0*sum("PAR30")/nullif(sum("outstandingBalance"),0), 2) AS tasa_sobre_saldo,
       round(100.0*sum("PAR30")/nullif(sum("deployedCapital"),0), 2)   AS tasa_sobre_capital
FROM pbi_bnpl.vintage_analysis
""", "5. PAR30: tasa sobre saldo vivo vs sobre capital desplegado")

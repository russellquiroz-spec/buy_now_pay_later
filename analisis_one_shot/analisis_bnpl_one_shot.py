"""
DEPRECADO — reemplazado por run.py + módulos separados.
Ver README.md para instrucciones.
"""
raise SystemExit("Usar run.py en su lugar.")
from __future__ import annotations

import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import sqlalchemy as sa
from dotenv import load_dotenv

from redshift_extractor import extract_sql

# ── Paths & conexiones ────────────────────────────────────────────────────────

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

OUTPUT_DIR = Path(__file__).parent
REDSHIFT_DB = "data-rabbit-prod"
PG_URL = os.environ["BD_ENGINE_RABBIT_LOCAL"].strip("'\"")

pg_engine = sa.create_engine(PG_URL)

# ── 1. Redshift: órdenes últimos 6 meses CERRADOS ────────────────────────────
# Cerrado = meses completos, excluye el mes en curso.
# Ventana: desde (trunc(mes(hoy-1)) - 6m) hasta < trunc(mes(hoy-1))
# Ejemplo hoy=2026-06-25: 2025-12-01 a 2026-05-31

SQL_ORDENES_6M = """
WITH source AS (
    SELECT v.ns_id, v.so_id, v.fecha_creacion_mx::date AS fecha_creacion,
           COALESCE(amount_completed, 0) + COALESCE(amount_in_progress, 0) AS monto_venta,
           COALESCE(quantity_completed, 0) + COALESCE(quantity_in_progress, 0) AS cantidad
      FROM analytics.mv_pedidos_enriquecidos_2025_v2 v
    UNION ALL
    SELECT v.ns_id, v.so_id, v.fecha_creacion_mx::date AS fecha_creacion,
           COALESCE(amount_completed, 0) + COALESCE(amount_in_progress, 0) AS monto_venta,
           COALESCE(quantity_completed, 0) + COALESCE(quantity_in_progress, 0) AS cantidad
      FROM analytics.mv_pedidos_enriquecidos_2026_v2 v
)
SELECT
    ns_id       AS netsuite_id,
    so_id       AS sales_order_id,
    fecha_creacion,
    SUM(monto_venta) AS monto_venta
FROM source
WHERE fecha_creacion >= (date_trunc('month', current_date - 1)::date - interval '6 month')::date
  AND fecha_creacion  < date_trunc('month', current_date - 1)::date
  AND (cantidad <> 0 OR monto_venta <> 0)
GROUP BY 1, 2, 3
HAVING SUM(monto_venta) > 10
"""

print("1/5 Extrayendo órdenes de Redshift (últimos 6 meses cerrados)...")
df_ordenes = extract_sql(REDSHIFT_DB, SQL_ORDENES_6M)
df_ordenes["netsuite_id"] = df_ordenes["netsuite_id"].astype(str)
df_ordenes["sales_order_id"] = df_ordenes["sales_order_id"].astype(str)
print(f"    {len(df_ordenes):,} filas | {df_ordenes['netsuite_id'].nunique():,} clientes | {df_ordenes['sales_order_id'].nunique():,} SOs")

# ── 2. PostgreSQL local: datos BNPL ───────────────────────────────────────────

print("2/5 Cargando datos BNPL desde PostgreSQL local...")
with pg_engine.connect() as conn:
    df_enrolled = pd.read_sql(
        sa.text(
            'SELECT "netsuiteId" AS netsuite_id, "creditLimit" AS linea_credito '
            'FROM mongo_bnpl.fintech_credit_approval_production'
        ),
        conn,
    )
    df_bnpl_orders = pd.read_sql(
        sa.text(
            'SELECT DISTINCT "salesOrderId" AS sales_order_id, "netsuiteId" AS netsuite_id '
            'FROM mongo_bnpl.credit_order_production '
            "WHERE \"orderStatus\" IN ('COMPLETED', 'CREATED', 'IN_DELIVERY')"
        ),
        conn,
    )

df_enrolled["netsuite_id"] = df_enrolled["netsuite_id"].astype(str)
df_bnpl_orders["netsuite_id"] = df_bnpl_orders["netsuite_id"].astype(str)
df_bnpl_orders["sales_order_id"] = df_bnpl_orders["sales_order_id"].astype(str)

enrolled_ids = set(df_enrolled["netsuite_id"])
bnpl_uso_ids = set(df_bnpl_orders["netsuite_id"])
bnpl_so_ids = set(df_bnpl_orders["sales_order_id"])

print(f"    Enrollados BNPL: {len(enrolled_ids):,} | Con >= 1 orden BNPL: {len(bnpl_uso_ids):,}")

# ── 3. Análisis 1: Activos Rabbit vs uso BNPL ─────────────────────────────────

print("3/5 Construyendo Análisis 1...")

activos = (
    df_ordenes.groupby("netsuite_id")
    .agg(pedidos=("sales_order_id", "nunique"), monto_total=("monto_venta", "sum"))
    .reset_index()
)
activos["fl_enrolled_bnpl"] = activos["netsuite_id"].isin(enrolled_ids).astype(int)
activos["fl_uso_bnpl"] = activos["netsuite_id"].isin(bnpl_uso_ids).astype(int)


def _segmento(row: pd.Series) -> str:
    if row["fl_uso_bnpl"]:
        return "Con uso BNPL"
    if row["fl_enrolled_bnpl"]:
        return "Enrollado sin uso"
    return "Sin BNPL"


activos["segmento_bnpl"] = activos.apply(_segmento, axis=1)

# Orden de presentación
seg_order = ["Con uso BNPL", "Enrollado sin uso", "Sin BNPL"]

analisis1 = (
    activos.groupby("segmento_bnpl")
    .agg(clientes=("netsuite_id", "count"), pedidos=("pedidos", "sum"), monto_total=("monto_total", "sum"))
    .reindex(seg_order)
    .reset_index()
)
total_clientes = analisis1["clientes"].sum()
total_pedidos = analisis1["pedidos"].sum()
total_monto = analisis1["monto_total"].sum()

analisis1["pct_clientes"] = (analisis1["clientes"] / total_clientes * 100).round(2)
analisis1["drop_size_promedio"] = (analisis1["monto_total"] / analisis1["pedidos"]).round(2)
analisis1.columns = [
    "Segmento BNPL", "Clientes Activos", "Pedidos", "Monto Total",
    "% Clientes Activos", "Drop Size Promedio",
]

total_row = pd.DataFrame([{
    "Segmento BNPL": "TOTAL",
    "Clientes Activos": total_clientes,
    "Pedidos": total_pedidos,
    "Monto Total": total_monto,
    "% Clientes Activos": 100.0,
    "Drop Size Promedio": round(total_monto / total_pedidos, 2),
}])
analisis1 = pd.concat([analisis1, total_row], ignore_index=True)

# ── 4. Análisis 2: Línea de crédito vs dropsize ───────────────────────────────

print("4/5 Construyendo Análisis 2...")

dropsize_cte = (
    df_ordenes.groupby("netsuite_id")
    .agg(venta_total_6m=("monto_venta", "sum"), pedidos_6m=("sales_order_id", "nunique"))
    .reset_index()
)
dropsize_cte["drop_size_6m"] = (dropsize_cte["venta_total_6m"] / dropsize_cte["pedidos_6m"]).round(2)

analisis2 = df_enrolled.merge(dropsize_cte, on="netsuite_id", how="left")
analisis2 = analisis2[["netsuite_id", "linea_credito", "drop_size_6m", "venta_total_6m", "pedidos_6m"]].copy()
analisis2.columns = ["netsuite_id", "Linea Credito", "Drop Size 6m", "Venta Total 6m", "Pedidos 6m"]

# ── 5. Histograma: distribución de clientes por línea de crédito ──────────────

print("5/5 Generando histograma...")

lc_vals = analisis2["Linea Credito"].dropna()
bin_max = int(np.ceil(lc_vals.max() / 1000) * 1000)
bins = list(range(0, bin_max + 1001, 1000))
labels = [f"${b:,}–${b+1000:,}" for b in bins[:-1]]

analisis2["_seg_lc"] = pd.cut(analisis2["Linea Credito"], bins=bins, labels=labels, right=False)
hist_data = analisis2.groupby("_seg_lc", observed=False)["netsuite_id"].count()

fig, ax = plt.subplots(figsize=(16, 6))
ax.bar(
    hist_data.index.astype(str),
    hist_data.values,
    color="#0277D9",
    edgecolor="#FFFFFF",
    linewidth=0.4,
)
ax.set_title("Distribución de clientes BNPL por línea de crédito", fontsize=14, fontweight="bold", pad=12)
ax.set_xlabel("Rango de línea de crédito (MXN)", fontsize=11, labelpad=8)
ax.set_ylabel("Clientes", fontsize=11)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
plt.xticks(rotation=45, ha="right", fontsize=7)
plt.tight_layout()

hist_path = OUTPUT_DIR / "histograma_linea_credito.png"
fig.savefig(hist_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"    Histograma guardado: {hist_path.name}")

# Drop columna auxiliar
analisis2 = analisis2.drop(columns=["_seg_lc"])

# ── 6. Base mínima (netsuite_id + sales_order_id) ────────────────────────────
# Base completa: todos los activos Rabbit con flags BNPL
base = df_ordenes.copy()
base["fl_bnpl_order"] = base["sales_order_id"].isin(bnpl_so_ids).astype(int)
base["fl_enrolled_bnpl"] = base["netsuite_id"].isin(enrolled_ids).astype(int)
base = base.merge(df_enrolled, on="netsuite_id", how="left")
base = base.rename(columns={"monto_venta": "Monto Venta Rabbit", "linea_credito": "Linea Credito BNPL"})

# CSV completo (1M+ filas, no cabe en Excel)
csv_path = OUTPUT_DIR / "base_minima.csv"
base.to_csv(csv_path, index=False)
print(f"    Base CSV guardada: {csv_path.name} ({len(base):,} filas)")

# Para el Excel: solo clientes enrollados BNPL (interseccion de los dos analisis)
base_excel = base[base["fl_enrolled_bnpl"] == 1].copy()
base_excel = base_excel[[
    "netsuite_id", "sales_order_id", "fecha_creacion",
    "Monto Venta Rabbit", "fl_bnpl_order", "fl_enrolled_bnpl", "Linea Credito BNPL"
]]

# ── 7. Exportar Excel ─────────────────────────────────────────────────────────

excel_path = OUTPUT_DIR / "analisis_bnpl_one_shot.xlsx"
with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
    analisis1.to_excel(writer, sheet_name="Analisis 1 - Activos vs BNPL", index=False)
    analisis2.to_excel(writer, sheet_name="Analisis 2 - LC vs DropSize", index=False)
    base_excel.to_excel(writer, sheet_name="Base Minima (BNPL)", index=False)

print(f"\nExcel guardado: {excel_path.name}")
print(f"Histograma: {hist_path.name}")
print(f"Base CSV completa: {csv_path.name}")
print("\nResumen Analisis 1:")
print(analisis1.to_string(index=False))
print(f"\nClientes enrollados BNPL en Analisis 2: {len(analisis2):,}")
print("DONE")

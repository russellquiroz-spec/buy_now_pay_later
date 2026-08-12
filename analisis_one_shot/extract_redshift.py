"""
Extracción de órdenes Rabbit desde Redshift para los últimos 6 meses cerrados.

"Cerrado" = meses completos, excluye el mes en curso.
Ventana dinámica: [trunc(mes(today-1)) - 6m, trunc(mes(today-1)))
Ejemplo con 2026-06-25 → 2025-12-01 a 2026-05-31.
"""
import pandas as pd
from redshift_extractor import extract_sql
from config import REDSHIFT_DB

SQL_ORDENES_6M_CERRADOS = """
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
    ns_id            AS netsuite_id,
    so_id            AS sales_order_id,
    fecha_creacion,
    SUM(monto_venta) AS monto_venta
FROM source
WHERE fecha_creacion >= (date_trunc('month', current_date - 1)::date - interval '6 month')::date
  AND fecha_creacion  < date_trunc('month', current_date - 1)::date
  AND (cantidad <> 0 OR monto_venta <> 0)
GROUP BY 1, 2, 3
HAVING SUM(monto_venta) > 10
"""


def get_ordenes_6m_cerrados() -> pd.DataFrame:
    """
    Devuelve órdenes de Redshift de los últimos 6 meses cerrados.

    Granularidad: 1 fila por (netsuite_id, sales_order_id, fecha_creacion).
    Si el mismo SO aparece duplicado en el resultado, se conserva la fila
    con mayor monto_venta.

    Returns:
        DataFrame con columnas: netsuite_id (str), sales_order_id (str),
                                fecha_creacion (date), monto_venta (float)
    """
    df = extract_sql(REDSHIFT_DB, SQL_ORDENES_6M_CERRADOS)
    df["netsuite_id"] = df["netsuite_id"].astype(str).str.strip()
    df["sales_order_id"] = df["sales_order_id"].astype(str).str.strip()

    n_raw = len(df)
    df = (
        df.sort_values("monto_venta", ascending=False)
        .drop_duplicates(subset=["netsuite_id", "sales_order_id"])
    )
    if len(df) < n_raw:
        print(f"  AVISO redshift: {n_raw - len(df)} filas duplicadas eliminadas")

    return df.reset_index(drop=True)

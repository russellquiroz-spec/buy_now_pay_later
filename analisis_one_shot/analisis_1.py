"""
Análisis 1: Clientes activos en Rabbit (últimos 6 meses cerrados)
segmentados por uso de BNPL.

Segmentos:
  Con uso BNPL      → netsuite_id tiene ≥1 orden activa en credit_order_production
  Enrollado sin uso → aprobado en fintech_credit_approval pero sin órdenes activas
  Sin BNPL          → no aparece en fintech_credit_approval_production
"""
import pandas as pd

_SEG_CON_USO = "Con uso BNPL"
_SEG_ENROLLADO = "Enrollado sin uso"
_SEG_SIN_BNPL = "Sin BNPL"
_SEG_ORDER = [_SEG_CON_USO, _SEG_ENROLLADO, _SEG_SIN_BNPL]


def _asignar_segmento(fl_uso: int, fl_enrolled: int) -> str:
    if fl_uso:
        return _SEG_CON_USO
    if fl_enrolled:
        return _SEG_ENROLLADO
    return _SEG_SIN_BNPL


def build_analisis_1(
    df_ordenes: pd.DataFrame,
    enrolled_ids: set[str],
    bnpl_uso_ids: set[str],
) -> pd.DataFrame:
    """
    Resumen de clientes activos Rabbit por segmento BNPL.

    Args:
        df_ordenes:    Órdenes de los últimos 6m (netsuite_id, sales_order_id, monto_venta).
        enrolled_ids:  Set de netsuite_ids aprobados en BNPL.
        bnpl_uso_ids:  Set de netsuite_ids con ≥1 orden BNPL activa.

    Returns:
        DataFrame con una fila por segmento + fila TOTAL.
        Columnas: Segmento BNPL, Clientes Activos, Pedidos, Monto Total,
                  % Clientes Activos, Drop Size Promedio
    """
    activos = (
        df_ordenes.groupby("netsuite_id")
        .agg(pedidos=("sales_order_id", "nunique"), monto_total=("monto_venta", "sum"))
        .reset_index()
    )
    activos["fl_enrolled"] = activos["netsuite_id"].isin(enrolled_ids).astype(int)
    activos["fl_uso"] = activos["netsuite_id"].isin(bnpl_uso_ids).astype(int)
    activos["segmento"] = activos.apply(
        lambda r: _asignar_segmento(r["fl_uso"], r["fl_enrolled"]), axis=1
    )

    resumen = (
        activos.groupby("segmento")
        .agg(
            clientes=("netsuite_id", "count"),
            pedidos=("pedidos", "sum"),
            monto_total=("monto_total", "sum"),
        )
        .reindex(_SEG_ORDER)
        .reset_index()
    )

    total_clientes = resumen["clientes"].sum()
    total_pedidos = resumen["pedidos"].sum()
    total_monto = resumen["monto_total"].sum()

    resumen["pct_clientes"] = (resumen["clientes"] / total_clientes * 100).round(2)
    resumen["drop_size_promedio"] = (resumen["monto_total"] / resumen["pedidos"]).round(2)

    total_row = pd.DataFrame([{
        "segmento": "TOTAL",
        "clientes": int(total_clientes),
        "pedidos": int(total_pedidos),
        "monto_total": round(total_monto, 2),
        "pct_clientes": 100.0,
        "drop_size_promedio": round(total_monto / total_pedidos, 2),
    }])

    out = pd.concat([resumen, total_row], ignore_index=True)
    out.columns = [
        "Segmento BNPL", "Clientes Activos", "Pedidos",
        "Monto Total", "% Clientes Activos", "Drop Size Promedio",
    ]
    return out

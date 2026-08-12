"""
Análisis 2: Clientes enrollados en BNPL — línea de crédito vs drop size.

Línea de crédito: creditLimit de fintech_credit_approval_production.
Drop size:        sum(monto_venta) / count(distinct sales_order_id) en los últimos
                  6 meses cerrados desde Redshift.

Clientes sin compras en el período → drop_size_6m = NaN (no tienen actividad en Rabbit
en la ventana analizada, pero siguen siendo parte del universo BNPL).
"""
import pandas as pd


def _calcular_dropsize(df_ordenes: pd.DataFrame) -> pd.DataFrame:
    """Drop size = monto total / pedidos únicos, por cliente, en el período."""
    return (
        df_ordenes.groupby("netsuite_id")
        .agg(
            venta_total_6m=("monto_venta", "sum"),
            pedidos_6m=("sales_order_id", "nunique"),
        )
        .assign(drop_size_6m=lambda d: (d["venta_total_6m"] / d["pedidos_6m"]).round(2))
        .reset_index()
    )


def build_analisis_2(
    df_enrolled: pd.DataFrame,
    df_ordenes: pd.DataFrame,
) -> pd.DataFrame:
    """
    Tabla cliente-nivel para clientes enrollados en BNPL.

    Args:
        df_enrolled: 1 fila por netsuite_id (columnas: netsuite_id, linea_credito).
                     Debe venir deduplicado desde extract_bnpl_postgres.get_enrolled_clients().
        df_ordenes:  Órdenes Redshift de los últimos 6m cerrados.

    Returns:
        DataFrame con columnas:
            netsuite_id, Linea Credito, Drop Size 6m, Venta Total 6m, Pedidos 6m
    """
    if df_enrolled["netsuite_id"].duplicated().any():
        n_dup = df_enrolled["netsuite_id"].duplicated().sum()
        raise ValueError(
            f"df_enrolled tiene {n_dup} netsuite_ids duplicados. "
            "Revisar extract_bnpl_postgres.get_enrolled_clients()."
        )

    dropsize = _calcular_dropsize(df_ordenes)
    out = df_enrolled.merge(dropsize, on="netsuite_id", how="left")
    out = out[["netsuite_id", "linea_credito", "drop_size_6m", "venta_total_6m", "pedidos_6m"]].copy()
    out.columns = ["netsuite_id", "Linea Credito", "Drop Size 6m", "Venta Total 6m", "Pedidos 6m"]
    return out

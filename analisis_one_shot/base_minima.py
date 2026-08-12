"""
Base mínima a nivel netsuite_id + sales_order_id que alimenta ambos análisis.

Columnas:
    netsuite_id        ID del cliente en NetSuite
    sales_order_id     ID de la orden Rabbit
    fecha_creacion     Fecha de la orden
    monto_venta        Monto en MXN (órdenes completadas + en proceso)
    fl_bnpl_order      1 si esa SO específica fue pagada con BNPL
    fl_enrolled_bnpl   1 si el cliente está aprobado en BNPL
    linea_credito      Límite de crédito BNPL (NULL si no está enrollado)

Nota: la base completa supera 1M filas y se exporta como CSV.
      El tab de Excel solo incluye clientes BNPL enrolled.
"""
import pandas as pd


def build_base_minima(
    df_ordenes: pd.DataFrame,
    enrolled_ids: set[str],
    bnpl_so_ids: set[str],
    df_enrolled: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construye la base detalle a nivel orden para todos los activos Rabbit.

    Args:
        df_ordenes:   Órdenes Redshift (netsuite_id, sales_order_id, fecha_creacion, monto_venta).
        enrolled_ids: Set de netsuite_ids aprobados en BNPL.
        bnpl_so_ids:  Set de sales_order_ids que son órdenes BNPL activas.
        df_enrolled:  DataFrame (netsuite_id, linea_credito) para enriquecer la base.

    Returns:
        DataFrame con todos los activos Rabbit + flags BNPL.
    """
    base = df_ordenes.copy()
    base["fl_bnpl_order"] = base["sales_order_id"].isin(bnpl_so_ids).astype(int)
    base["fl_enrolled_bnpl"] = base["netsuite_id"].isin(enrolled_ids).astype(int)
    base = base.merge(
        df_enrolled[["netsuite_id", "linea_credito"]],
        on="netsuite_id",
        how="left",
    )
    return base


def filtrar_para_excel(base: pd.DataFrame) -> pd.DataFrame:
    """
    Versión reducida para el tab de Excel: solo clientes BNPL enrolled.

    Es la intersección directa entre los dos análisis:
    activos Rabbit que además son clientes BNPL.
    """
    return base[base["fl_enrolled_bnpl"] == 1].reset_index(drop=True)

"""
Extracción de datos BNPL desde PostgreSQL local (schema mongo_bnpl).

Casos de calidad conocidos que se tratan aquí:
  - credit_order_production: 1,425 filas con salesOrderId NULL → se excluyen
  - credit_order_production: 1 salesOrderId asignado a 2 netsuiteIds → se asigna
    al netsuiteId con más órdenes (el otro es probable error de datos)
  - fintech_credit_approval_production: sin duplicados actuales, pero se aplica
    dedup por max(creditLimit) como protección ante recargas futuras
"""
import shutil
import tempfile
from pathlib import Path

import pandas as pd
from postgres_local_client import extract_sql

from config import PG_DB, LC_EXCEL_PATH, LC_EXCEL_SHEET


def get_enrolled_clients() -> pd.DataFrame:
    """
    Clientes aprobados en BNPL con su línea de crédito vigente.

    Deduplicación: si un netsuiteId aparece con múltiples filas,
    se conserva la de mayor creditLimit.

    Returns:
        DataFrame 1:1 por netsuite_id.
        Columnas: netsuite_id (str), linea_credito (int)
    """
    df = extract_sql(
        'SELECT "netsuiteId" AS netsuite_id, "creditLimit" AS linea_credito '
        "FROM mongo_bnpl.fintech_credit_approval_production",
        db=PG_DB,
    )

    df["netsuite_id"] = df["netsuite_id"].astype(str).str.strip()
    df = df[df["netsuite_id"].str.match(r"^\d+$")]  # excluir IDs basura

    n_raw = len(df)
    df = df.groupby("netsuite_id", as_index=False)["linea_credito"].max()
    if len(df) < n_raw:
        print(f"  Dedup enrolled: {n_raw} -> {len(df)} ({n_raw - len(df)} duplicados)")

    return df.reset_index(drop=True)


# V1: reemplaza get_enrolled_clients() como fuente de línea de crédito.
# Razón: la propuesta de Propaga (Excel) refleja los ajustes del mes actual
# antes de que se carguen a MongoDB; permite analizar el impacto previo al despliegue.
# Columna usada: linea_nueva (propuesta de Propaga).
# Dedup: si external_id aparece más de una vez, se conserva el mayor linea_nueva.
# Nota: 110 duplicados detectados en el Excel de Abril 2026.
def get_credit_line_from_excel() -> pd.DataFrame:
    """
    Lee la nueva línea de crédito desde el Excel de Propuesta Propaga.

    Columna fuente: linea_nueva — propuesta de Propaga por cliente.
    Clientes con linea_nueva = NaN se excluyen (no tienen propuesta activa).

    Returns:
        DataFrame 1:1 por netsuite_id.
        Columnas: netsuite_id (str), linea_credito (float), clasificacion (str)
    """
    # Si el archivo está abierto en Excel (lock), se copia al temp antes de leer
    try:
        src = Path(LC_EXCEL_PATH)
        df = pd.read_excel(src, sheet_name=LC_EXCEL_SHEET,
                           usecols=["external_id", "linea_nueva", "clasificacion"])
    except PermissionError:
        tmp = Path(tempfile.gettempdir()) / src.name
        shutil.copy2(src, tmp)
        print(f"  Archivo bloqueado, leyendo desde copia temporal: {tmp.name}")
        df = pd.read_excel(tmp, sheet_name=LC_EXCEL_SHEET,
                           usecols=["external_id", "linea_nueva", "clasificacion"])
    df = df.rename(columns={"external_id": "netsuite_id", "linea_nueva": "linea_credito"})
    df["netsuite_id"] = df["netsuite_id"].astype(str).str.strip()
    df = df[df["netsuite_id"].str.match(r"^\d+$")]
    df = df.dropna(subset=["linea_credito"])

    n_raw = len(df)
    df = df.groupby("netsuite_id", as_index=False).agg(
        linea_credito=("linea_credito", "max"),
        clasificacion=("clasificacion", "first"),
    )
    if len(df) < n_raw:
        print(f"  Dedup Excel LC: {n_raw} -> {len(df)} ({n_raw - len(df)} duplicados)")

    return df.reset_index(drop=True)


def get_bnpl_orders() -> pd.DataFrame:
    """
    Órdenes BNPL con status activo (COMPLETED / CREATED / IN_DELIVERY).

    Tratamiento de calidad:
      - Excluye filas con salesOrderId NULL (1,425 registros conocidos).
      - Un salesOrderId puede estar asociado a más de un netsuiteId por error;
        en ese caso se asigna al netsuiteId con más órdenes totales.

    Returns:
        DataFrame sin duplicados en (netsuite_id, sales_order_id).
        Columnas: netsuite_id (str), sales_order_id (str)
    """
    df = extract_sql(
        'SELECT "netsuiteId" AS netsuite_id, "salesOrderId" AS sales_order_id '
        "FROM mongo_bnpl.credit_order_production "
        "WHERE \"orderStatus\" IN ('COMPLETED', 'CREATED', 'IN_DELIVERY') "
        "  AND \"salesOrderId\" IS NOT NULL "
        "  AND trim(\"salesOrderId\") <> ''",
        db=PG_DB,
    )

    df["netsuite_id"] = df["netsuite_id"].astype(str).str.strip()
    df["sales_order_id"] = df["sales_order_id"].astype(str).str.strip()

    # Resolver 1 salesOrderId → múltiples netsuiteIds: conservar el que tiene más pedidos
    pedidos_por_cliente = df.groupby("netsuite_id")["sales_order_id"].count().rename("n_pedidos")
    df = df.merge(pedidos_por_cliente, on="netsuite_id")
    df = (
        df.sort_values("n_pedidos", ascending=False)
        .drop_duplicates(subset=["sales_order_id"])
        .drop(columns=["n_pedidos"])
    )

    return df.reset_index(drop=True)

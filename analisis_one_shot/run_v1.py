"""
Análisis BNPL One-Shot — V1: línea de crédito desde Propuesta Propaga (Excel).

Cambios respecto a run.py:
  - Análisis 2 usa linea_nueva del Excel (Elegibles BNPL Abril 2026 / Propuesta Propaga)
    en lugar de creditLimit de fintech_credit_approval_production (MongoDB).
  - Agrega tab "Comparador LC" en el Excel: contrasta LC Excel vs LC MongoDB por cliente.
  - Outputs en output_v1/ con sufijo _v1.

Uso:
    .venv\\Scripts\\python.exe analisis_one_shot\\run_v1.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from config import OUTPUT_DIR_V1
from extract_redshift import get_ordenes_6m_cerrados
from extract_bnpl_postgres import get_enrolled_clients, get_bnpl_orders, get_credit_line_from_excel
from analisis_1 import build_analisis_1
from analisis_2 import build_analisis_2
from base_minima import build_base_minima, filtrar_para_excel
from exportar import exportar_histograma

OUTPUT_DIR_V1.mkdir(exist_ok=True)


def _build_comparador(df_mongo: pd.DataFrame, df_excel: pd.DataFrame) -> pd.DataFrame:
    """
    Contrasta la línea de crédito MongoDB vs Propaga Excel por cliente.

    Incluye todos los clientes presentes en al menos una de las dos fuentes.
    Columnas: netsuite_id, LC_MongoDB, LC_Excel, diferencia, clasificacion_propaga, origen
    """
    comp = pd.merge(
        df_mongo.rename(columns={"linea_credito": "LC_MongoDB"}),
        df_excel[["netsuite_id", "linea_credito", "clasificacion"]].rename(
            columns={"linea_credito": "LC_Excel", "clasificacion": "clasificacion_propaga"}
        ),
        on="netsuite_id",
        how="outer",
        indicator=True,
    )
    comp["diferencia"] = comp["LC_Excel"] - comp["LC_MongoDB"]
    comp["origen"] = comp["_merge"].map({
        "both": "Ambas fuentes",
        "left_only": "Solo MongoDB",
        "right_only": "Solo Excel",
    })
    return comp[["netsuite_id", "LC_MongoDB", "LC_Excel", "diferencia",
                  "clasificacion_propaga", "origen"]].reset_index(drop=True)


def _exportar_excel_v1(
    analisis1: pd.DataFrame,
    analisis2: pd.DataFrame,
    base_excel: pd.DataFrame,
    comparador: pd.DataFrame,
    output_dir: Path,
) -> Path:
    path = output_dir / "analisis_bnpl_one_shot_v1.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        analisis1.to_excel(writer, sheet_name="Analisis 1 - Activos vs BNPL", index=False)
        analisis2.to_excel(writer, sheet_name="Analisis 2 - LC vs DropSize", index=False)
        base_excel.to_excel(writer, sheet_name="Base Minima (BNPL)", index=False)
        comparador.to_excel(writer, sheet_name="Comparador LC", index=False)
    return path


def main() -> None:
    # ── Extracción ────────────────────────────────────────────────────────────
    print("1/7 Ordenes Redshift (ultimos 6 meses cerrados)...")
    df_ordenes = get_ordenes_6m_cerrados()
    print(f"    {len(df_ordenes):,} SOs | {df_ordenes['netsuite_id'].nunique():,} clientes")

    print("2/7 Datos BNPL desde PostgreSQL (ordenes + LC MongoDB)...")
    df_mongo_lc = get_enrolled_clients()          # LC original (MongoDB)
    df_bnpl_orders = get_bnpl_orders()
    enrolled_ids: set[str] = set(df_mongo_lc["netsuite_id"])
    bnpl_uso_ids: set[str] = set(df_bnpl_orders["netsuite_id"])
    bnpl_so_ids: set[str] = set(df_bnpl_orders["sales_order_id"])
    print(f"    LC MongoDB: {len(df_mongo_lc):,} clientes")

    print("3/7 LC desde Excel Propuesta Propaga (V1)...")
    df_excel_lc = get_credit_line_from_excel()    # LC nueva (Excel)
    # V1: enrolled_ids se amplía con los clientes del Excel que aún no están en MongoDB
    enrolled_ids_v1: set[str] = enrolled_ids | set(df_excel_lc["netsuite_id"])
    print(f"    LC Excel: {len(df_excel_lc):,} clientes con propuesta activa")

    # ── Análisis ──────────────────────────────────────────────────────────────
    print("4/7 Analisis 1 - Activos Rabbit vs BNPL...")
    # Análisis 1 no cambia: los segmentos BNPL se basan en órdenes activas, no en la LC
    analisis1 = build_analisis_1(df_ordenes, enrolled_ids, bnpl_uso_ids)

    print("5/7 Analisis 2 - LC Propaga Excel vs Drop Size (V1)...")
    # V1: df_enrolled viene del Excel en lugar de MongoDB
    analisis2 = build_analisis_2(df_excel_lc.drop(columns=["clasificacion"]), df_ordenes)

    # ── Comparador LC ─────────────────────────────────────────────────────────
    print("6/7 Comparador LC MongoDB vs Excel...")
    comparador = _build_comparador(df_mongo_lc, df_excel_lc)
    n_ambas = (comparador["origen"] == "Ambas fuentes").sum()
    n_solo_mongo = (comparador["origen"] == "Solo MongoDB").sum()
    n_solo_excel = (comparador["origen"] == "Solo Excel").sum()
    print(f"    Ambas fuentes: {n_ambas:,} | Solo MongoDB: {n_solo_mongo:,} | Solo Excel: {n_solo_excel:,}")

    # ── Base mínima ───────────────────────────────────────────────────────────
    base_full = build_base_minima(df_ordenes, enrolled_ids_v1, bnpl_so_ids, df_excel_lc.drop(columns=["clasificacion"]))
    base_excel = filtrar_para_excel(base_full)
    csv_path = OUTPUT_DIR_V1 / "base_minima_v1.csv"
    base_full.to_csv(csv_path, index=False)

    # ── Outputs ───────────────────────────────────────────────────────────────
    print("7/7 Exportando outputs V1...")
    excel_path = _exportar_excel_v1(analisis1, analisis2, base_excel, comparador, OUTPUT_DIR_V1)
    hist_path = exportar_histograma(analisis2, OUTPUT_DIR_V1)
    # Renombrar histograma a _v1
    hist_path_v1 = OUTPUT_DIR_V1 / "histograma_linea_credito_v1.png"
    hist_path.rename(hist_path_v1)

    print(f"    {excel_path.name}")
    print(f"    {hist_path_v1.name}")
    print(f"    {csv_path.name}")

    print("\n--- Analisis 1 (sin cambios respecto a v0) ---")
    print(analisis1.to_string(index=False))
    print(f"\nClientes BNPL en Analisis 2 (Excel): {len(analisis2):,}")
    print("DONE")


if __name__ == "__main__":
    main()

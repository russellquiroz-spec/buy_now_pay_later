"""
Análisis BNPL One-Shot — orquestador principal.

Uso:
    .venv\\Scripts\\python.exe analisis_one_shot\\run.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import OUTPUT_DIR
from extract_redshift import get_ordenes_6m_cerrados
from extract_bnpl_postgres import get_enrolled_clients, get_bnpl_orders
from analisis_1 import build_analisis_1
from analisis_2 import build_analisis_2
from base_minima import build_base_minima, filtrar_para_excel
from exportar import exportar_excel, exportar_histograma

OUTPUT_DIR.mkdir(exist_ok=True)


def main() -> None:
    # ── Extracción ────────────────────────────────────────────────────────────
    print("1/6 Ordenes Redshift (ultimos 6 meses cerrados)...")
    df_ordenes = get_ordenes_6m_cerrados()
    print(f"    {len(df_ordenes):,} SOs | {df_ordenes['netsuite_id'].nunique():,} clientes")

    print("2/6 Datos BNPL desde PostgreSQL local...")
    df_enrolled = get_enrolled_clients()
    df_bnpl_orders = get_bnpl_orders()
    enrolled_ids: set[str] = set(df_enrolled["netsuite_id"])
    bnpl_uso_ids: set[str] = set(df_bnpl_orders["netsuite_id"])
    bnpl_so_ids: set[str] = set(df_bnpl_orders["sales_order_id"])
    print(f"    Enrollados: {len(enrolled_ids):,} | Con uso BNPL: {len(bnpl_uso_ids):,}")

    # ── Análisis ──────────────────────────────────────────────────────────────
    print("3/6 Analisis 1 - Activos Rabbit vs BNPL...")
    analisis1 = build_analisis_1(df_ordenes, enrolled_ids, bnpl_uso_ids)

    print("4/6 Analisis 2 - Linea de credito vs Drop Size...")
    analisis2 = build_analisis_2(df_enrolled, df_ordenes)

    # ── Base mínima ───────────────────────────────────────────────────────────
    print("5/6 Base minima...")
    base_full = build_base_minima(df_ordenes, enrolled_ids, bnpl_so_ids, df_enrolled)
    base_excel = filtrar_para_excel(base_full)
    csv_path = OUTPUT_DIR / "base_minima.csv"
    base_full.to_csv(csv_path, index=False)
    print(f"    CSV completo: {len(base_full):,} filas | Excel (BNPL enrolled): {len(base_excel):,} filas")

    # ── Outputs ───────────────────────────────────────────────────────────────
    print("6/6 Exportando...")
    excel_path = exportar_excel(analisis1, analisis2, base_excel, OUTPUT_DIR)
    hist_path = exportar_histograma(analisis2, OUTPUT_DIR)
    print(f"    {excel_path.name}")
    print(f"    {hist_path.name}")
    print(f"    {csv_path.name}")

    print("\n--- Analisis 1 ---")
    print(analisis1.to_string(index=False))
    print(f"\nClientes BNPL en Analisis 2: {len(analisis2):,}")
    print("\nDONE")


if __name__ == "__main__":
    main()

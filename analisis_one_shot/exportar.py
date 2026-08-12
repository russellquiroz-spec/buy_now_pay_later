"""
Generación de outputs: Excel con 3 pestañas + histograma PNG.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd


def exportar_excel(
    analisis1: pd.DataFrame,
    analisis2: pd.DataFrame,
    base_excel: pd.DataFrame,
    output_dir: Path,
) -> Path:
    """
    Escribe el Excel con 3 pestañas.

    Pestañas:
        Analisis 1 - Activos vs BNPL  → resumen segmentado
        Analisis 2 - LC vs DropSize   → cliente-nivel BNPL
        Base Minima (BNPL)            → detalle SO-nivel, clientes BNPL enrolled

    Returns: ruta del archivo .xlsx generado.
    """
    path = output_dir / "analisis_bnpl_one_shot.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        analisis1.to_excel(writer, sheet_name="Analisis 1 - Activos vs BNPL", index=False)
        analisis2.to_excel(writer, sheet_name="Analisis 2 - LC vs DropSize", index=False)
        base_excel.to_excel(writer, sheet_name="Base Minima (BNPL)", index=False)
    return path


def exportar_histograma(analisis2: pd.DataFrame, output_dir: Path) -> Path:
    """
    Histograma de distribución de clientes BNPL por línea de crédito.

    Bins de $1,000 en $1,000 desde $0 hasta el máximo de 'Linea Credito'.
    Clientes con linea_credito NaN quedan fuera del histograma.

    Returns: ruta del archivo .png generado.
    """
    lc = analisis2["Linea Credito"].dropna()
    bin_max = int(np.ceil(lc.max() / 1000) * 1000)
    bins = list(range(0, bin_max + 1001, 1000))
    labels = [f"${b:,}-${b + 1_000:,}" for b in bins[:-1]]

    tmp = analisis2.copy()
    tmp["_seg"] = pd.cut(tmp["Linea Credito"], bins=bins, labels=labels, right=False)
    counts = tmp.groupby("_seg", observed=False)["netsuite_id"].count()

    fig, ax = plt.subplots(figsize=(16, 6))
    ax.bar(
        counts.index.astype(str),
        counts.values,
        color="#0277D9",
        edgecolor="#FFFFFF",
        linewidth=0.4,
    )
    ax.set_title(
        "Distribucion de clientes BNPL por linea de credito",
        fontsize=14, fontweight="bold", pad=12,
    )
    ax.set_xlabel("Rango linea de credito (MXN)", fontsize=11, labelpad=8)
    ax.set_ylabel("Clientes", fontsize=11)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    plt.xticks(rotation=45, ha="right", fontsize=7)
    plt.tight_layout()

    path = output_dir / "histograma_linea_credito.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    return path

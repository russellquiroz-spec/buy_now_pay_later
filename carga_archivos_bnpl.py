"""Carga los CSV irreducibles del tablero: Drive compartido -> schema archivos_bnpl.

Cuatro archivos que ninguna consulta puede reemplazar: dos son la salida de un modelo de riesgo,
uno es la clasificacion de Pago de Servicios y el otro es captura manual de negocio. Ver
PENDIENTES_NEGOCIO.md secciones 10 y 11.

Existe para que Power BI deje de leerlos del disco personal de una persona
(C:\\Users\\RodolfoGonzalezOrta\\...), que no sobrevive a que cambie de equipo y no se puede
refrescar desde el Service. Con esto todo el modelo se alimenta de un solo origen: la base.

No cuelga de main.py ni de build_bnpl.py: se corre a mano cuando riesgo o negocio publiquen una
version nueva de algun archivo. El DDL, el TRUNCATE y la carga van en una sola transaccion, asi
que una corrida fallida no deja tablas a medias.

    python carga_archivos_bnpl.py                     # carga los cuatro
    python carga_archivos_bnpl.py --dry-run           # valida y muestra el resumen, sin escribir
    python carga_archivos_bnpl.py --solo bnpl_cac     # uno solo
"""
import argparse
from pathlib import Path

import pandas as pd
from postgres_local_client import transaction

BASE_DIR = Path(__file__).resolve().parent

SCHEMA = "archivos_bnpl"
DB_RW = "bnpl_rw"

DRIVE = Path(r"D:\Shared drives\Data Room - BI & Data Analytics")
RIESGO = DRIVE / "Rabbit Risk Analytics" / "Buy Now Pay Later"

# Cada entrada: archivo, y el mapeo posicion -> nombre de columna en la tabla.
#
# El mapeo va por NOMBRE de origen y no por posicion porque los cuatro archivos traen encabezado
# estable. Se renombra a snake_case, que es la convencion del resto del staging; los nombres que
# espera Power BI (camelCase, '%good', 'Id cliente') los pone la consulta de sql/pbi/.
ARCHIVOS = {
    "odds_combinations": {
        "ruta": RIESGO / "Default Profile" / "odds_combinations.csv",
        "columnas": {
            "loanDisbursementIndexRange": "loan_disbursement_index_range",
            "flag": "flag", "atr1": "atr1", "atr2": "atr2",
            "atr1Rank": "atr1_rank", "atr2Rank": "atr2_rank",
            "events": "events", "good": "good", "bad": "bad",
            "br": "br", "bad_rate": "bad_rate",
            "%good": "pct_good", "%bad": "pct_bad", "woe": "woe", "iv": "iv",
        },
    },
    "atr_combinations_iv": {
        "ruta": RIESGO / "Default Profile" / "atr_combinations_iv.csv",
        "columnas": {
            "loanDisbursementIndexRange": "loan_disbursement_index_range",
            "flag": "flag", "combination": "combination",
            "number_of_combinations": "number_of_combinations", "iv": "iv",
        },
    },
    "ps_transactional_profile": {
        "ruta": DRIVE / "Rabbit Analytics" / "Pago de Servicios Automation"
                / "ps_transactional_profile.csv",
        "columnas": {"Id cliente": "id_cliente", "transactionalProfile": "transactional_profile"},
    },
    "bnpl_cac": {
        "ruta": RIESGO / "bnpl_cac.csv",
        "columnas": {"enrollmentCohort": "enrollment_cohort", "cac": "cac"},
    },
}


def _leer(nombre: str, cfg: dict) -> pd.DataFrame:
    if not cfg["ruta"].exists():
        raise FileNotFoundError(f"{nombre}: no existe {cfg['ruta']}")
    df = pd.read_csv(cfg["ruta"], low_memory=False)

    faltan = [c for c in cfg["columnas"] if c not in df.columns]
    if faltan:
        raise ValueError(
            f"{nombre}: al archivo le faltan columnas {faltan}. "
            f"Trae: {list(df.columns)}"
        )

    # Los CSV de riesgo traen el indice de pandas como primera columna sin nombre. Se descarta
    # aqui igual que lo descartaba el M del tablero.
    df = df[list(cfg["columnas"])].rename(columns=cfg["columnas"])

    # loan_disbursement_index_range es TEXTO ('1', '2', '3+'). Ese '3+' es justo lo que hace
    # fallar el cast a entero que traian los pasos del M; si alguien lo vuelve a tipar numerico,
    # aqui se ve.
    if "loan_disbursement_index_range" in df.columns:
        df["loan_disbursement_index_range"] = (
            df["loan_disbursement_index_range"].astype(str).str.strip()
        )
    return df


def run(solo: list = None, dry_run: bool = False) -> None:
    tablas = solo or list(ARCHIVOS)
    ddl = (BASE_DIR / "sql" / "14_archivos_bnpl.sql").read_text(encoding="utf-8")

    for nombre in tablas:
        if nombre not in ARCHIVOS:
            raise SystemExit(f"No conozco '{nombre}'. Opciones: {', '.join(ARCHIVOS)}")
        cfg = ARCHIVOS[nombre]
        df = _leer(nombre, cfg)
        print(f"{nombre}: {len(df):,} filas x {len(df.columns)} columnas  <- {cfg['ruta'].name}")

        if dry_run:
            print(f"    (dry-run) tipos: {dict(df.dtypes.astype(str))}")
            continue

        with transaction(db=DB_RW) as tx:
            tx.execute_sql(ddl)
            tx.execute_sql(f'TRUNCATE {SCHEMA}."{nombre}"')
            tx.load_dataframe(df, nombre, schema=SCHEMA)
        print(f"    -> {SCHEMA}.{nombre} cargada")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Carga los CSV irreducibles del tablero BNPL")
    p.add_argument("--solo", help="tablas a cargar, separadas por coma")
    p.add_argument("--dry-run", action="store_true", help="valida sin escribir")
    a = p.parse_args()
    run(solo=a.solo.split(",") if a.solo else None, dry_run=a.dry_run)

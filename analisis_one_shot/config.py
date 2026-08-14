from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
REDSHIFT_DB = "data-rabbit-prod"
PG_DB = "mongo_bnpl"  # alias de solo lectura de postgres_local_client

# V1: fuente alternativa de línea de crédito (reemplaza fintech_credit_approval_production).
# Razón: Propaga actualiza las líneas mensualmente en este archivo antes de cargarlas a MongoDB.
LC_EXCEL_PATH = Path(__file__).parent.parent / "data" / "input" / "Elegibles BNPL Abril 2026.xlsx"
LC_EXCEL_SHEET = "Propuesta Propaga"
OUTPUT_DIR_V1 = Path(__file__).parent / "output_v1"

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

OUTPUT_DIR = Path(__file__).parent / "output"
REDSHIFT_DB = "data-rabbit-prod"
PG_URL = os.environ["BD_ENGINE_RABBIT_LOCAL"].strip("'\"")

# V1: fuente alternativa de línea de crédito (reemplaza fintech_credit_approval_production).
# Razón: Propaga actualiza las líneas mensualmente en este archivo antes de cargarlas a MongoDB.
LC_EXCEL_PATH = Path(__file__).parent.parent / "data" / "input" / "Elegibles BNPL Abril 2026.xlsx"
LC_EXCEL_SHEET = "Propuesta Propaga"
OUTPUT_DIR_V1 = Path(__file__).parent / "output_v1"

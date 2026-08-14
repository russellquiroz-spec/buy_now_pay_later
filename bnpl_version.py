"""Identidad de la version que produjo cada carga: commit del repo y hash del .sql.

Va en la raiz y no en ops/ para que lo puedan importar tanto main.py (que agrega ops/ al
path) como build_bnpl.py y los dos ETL corridos sueltos, donde la raiz es sys.path[0].
"""
import hashlib
import subprocess
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def commit_sha() -> str:
    """Commit corto del repo, con sufijo '+sucio' si hay cambios sin commitear.

    El sufijo importa: sin el, una fila de etl_runs diria que la produjo un commit que no
    contiene el codigo que corrio. Si no hay git, devuelve 'sin-git' y no lanza.
    """
    try:
        sha = subprocess.run(
            ["git", "-C", str(BASE_DIR), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        sucio = subprocess.run(
            ["git", "-C", str(BASE_DIR), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        return f"{sha}+sucio" if sucio else sha
    except Exception:  # noqa: BLE001 - la bitacora nunca debe tumbar la carga
        return "sin-git"


def sha_sql(archivo) -> str:
    """SHA-256 corto del .sql que definio el objeto. None si no hay archivo."""
    if archivo is None:
        return None
    ruta = Path(archivo)
    if not ruta.is_absolute():
        ruta = BASE_DIR / "sql" / ruta
    try:
        return hashlib.sha256(ruta.read_bytes()).hexdigest()[:12]
    except Exception:  # noqa: BLE001
        return None

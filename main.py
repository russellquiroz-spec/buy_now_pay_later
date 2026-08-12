"""Orquestador del pipeline BNPL. Es el unico punto de entrada para la corrida desatendida.

    python main.py                corrida normal
    python main.py --full         fuerza recarga completa del staging
    python main.py --sin-redshift omite la estructura comercial (no cambia a diario)
    python main.py --rebuild      reconstruye las vistas desde los .sql en vez de refrescarlas

Orden y por que:
  1. frescura      antes de cargar, para saber si vale la pena. Si una fuente CRITICA esta en
                   CRIT se detiene aca: cargar datos viejos sobre el tablero es peor que no
                   cargar. Las fuentes no criticas en CRIT solo avisan.
  2. staging Mongo
  3. estructura comercial (Redshift)
  4. capa de negocio
  5. calidad       despues de cargar, sobre los datos nuevos.
  6. frescura      otra vez, para dejar registrado que el staging quedo sincronizado.

Todo queda en logs/ y en bnpl_ops (source_freshness, freshness_history, data_quality_checks,
etl_runs). El codigo de salida es 0 si termino bien y 1 si algo fallo, para que el Task
Scheduler lo reporte.
"""
import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "ops"))

import build_bnpl
import etl_mongo_to_postgres
import etl_redshift_to_postgres
from config import FUENTES_CRITICAS, TZ_OFFSET_HOURS, get_engine
from sqlalchemy import text

import check_freshness
import quality_checks

LOG_DIR = BASE_DIR / "logs"


def _ahora_mx() -> datetime:
    return (datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)).replace(tzinfo=None)


def _configurar_log() -> Path:
    LOG_DIR.mkdir(exist_ok=True)
    archivo = LOG_DIR / f"pipeline_{_ahora_mx():%Y-%m}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(archivo, encoding="utf-8"),
            # A stdout, no al stderr por defecto: PowerShell trata todo lo que llega por stderr
            # como error y marca la corrida como fallida aunque haya ido bien.
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )
    return archivo


def _registrar_corrida(inicio, segundos: float, resultado: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO bnpl_ops.etl_runs (started_at, tabla, modo, filas, segundos) "
                "VALUES (:inicio, 'pipeline', :modo, NULL, :segundos) "
                "ON CONFLICT (started_at, tabla) DO NOTHING"
            ),
            {"inicio": inicio, "modo": resultado, "segundos": round(segundos, 1)},
        )
    engine.dispose()


def _revisar_frescura(log) -> bool:
    """Devuelve True si se puede continuar."""
    filas = check_freshness.run()
    criticas_caidas = [
        f for f in filas
        if f["coleccion"] in FUENTES_CRITICAS and f["semaforo_fuente"] == "CRIT"
    ]
    otras_caidas = [
        f for f in filas
        if f["coleccion"] not in FUENTES_CRITICAS and f["semaforo_fuente"] == "CRIT"
    ]

    for f in otras_caidas:
        log.warning(
            "%s sin escrituras desde %s (%.0f h). No es critica: el pipeline continua.",
            f["coleccion"],
            f["last_write_mongo"],
            f["lag_fuente_horas"] or 0,
        )

    if criticas_caidas:
        for f in criticas_caidas:
            log.error(
                "FUENTE CRITICA CAIDA: %s sin escrituras desde %s (%.0f h)",
                f["coleccion"],
                f["last_write_mongo"],
                f["lag_fuente_horas"] or 0,
            )
        return False
    return True


def run(full: bool = False, sin_redshift: bool = False, rebuild: bool = False) -> int:
    archivo = _configurar_log()
    log = logging.getLogger("bnpl")
    inicio, t0 = _ahora_mx(), time.time()

    log.info("=" * 70)
    log.info("Pipeline BNPL — inicio (log: %s)", archivo.name)

    try:
        log.info("[1/6] Frescura de las fuentes")
        if not _revisar_frescura(log):
            log.error("Pipeline detenido: hay fuentes criticas sin actualizarse.")
            _registrar_corrida(inicio, time.time() - t0, "abortado_frescura")
            return 1

        log.info("[2/6] Staging desde Mongo%s", " (recarga completa)" if full else "")
        etl_mongo_to_postgres.run(full=full)

        if sin_redshift:
            log.info("[3/6] Estructura comercial: omitida por --sin-redshift")
        else:
            log.info("[3/6] Estructura comercial desde Redshift")
            etl_redshift_to_postgres.run()

        log.info("[4/6] Capa de negocio%s", " (reconstruccion)" if rebuild else "")
        build_bnpl.run(rebuild=rebuild)

        log.info("[5/6] Chequeos de calidad")
        alertas = [f for f in quality_checks.run() if f["resultado"] == "ALERTA"]
        for a in alertas:
            log.warning("calidad — %s: %s filas (%s)", a["check_name"], a["n_filas"], a["detalle"])

        log.info("[6/6] Frescura final")
        finales = check_freshness.run()
        desincronizadas = [f for f in finales if f["semaforo_staging"] in ("CRIT", "FALTA")]
        for f in desincronizadas:
            log.warning(
                "%s quedo desincronizada: %s en Mongo vs %s en staging",
                f["coleccion"], f["docs_mongo"], f["docs_staging"],
            )

        segundos = time.time() - t0
        log.info("Pipeline terminado en %.1f min", segundos / 60)
        _registrar_corrida(inicio, segundos, "ok")
        return 0

    except Exception:
        log.exception("Pipeline abortado por un error")
        _registrar_corrida(inicio, time.time() - t0, "error")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Corre el pipeline BNPL completo")
    parser.add_argument("--full", action="store_true", help="recarga completa del staging")
    parser.add_argument(
        "--sin-redshift", action="store_true", help="omite la estructura comercial"
    )
    parser.add_argument(
        "--rebuild", action="store_true", help="reconstruye las vistas desde los .sql"
    )
    args = parser.parse_args()
    sys.exit(run(full=args.full, sin_redshift=args.sin_redshift, rebuild=args.rebuild))

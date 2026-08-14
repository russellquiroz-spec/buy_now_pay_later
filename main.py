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
from config import DB_OPS, DB_OPS_RW, FUENTES_CRITICAS, TZ_OFFSET_HOURS
from postgres_local_client import execute_sql, extract_sql

import check_freshness
import notificar
import quality_checks

LOG_DIR = BASE_DIR / "logs"


def _ahora_mx() -> datetime:
    return (datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)).replace(tzinfo=None)


def _hora_mx(segundos: float) -> time.struct_time:
    """Convertidor para logging: estampa hora Mexico y no la del reloj del sistema."""
    return (
        datetime.fromtimestamp(segundos, timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)
    ).timetuple()


def _configurar_log() -> Path:
    LOG_DIR.mkdir(exist_ok=True)
    archivo = LOG_DIR / f"pipeline_{_ahora_mx():%Y-%m}.log"
    # El asctime de logging usa el reloj del SO, que en la VM esta en UTC. Sin el converter el
    # log estampaba 12:53 el mismo evento que _ahora_mx() guarda como 06:53 en etl_runs: seis
    # horas de diferencia entre las dos cosas que se leen lado a lado al depurar. El nombre del
    # archivo ya iba en hora Mexico, asi que el log tampoco coincidia con su propio nombre.
    formato = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    formato.converter = _hora_mx
    manejadores = [
        logging.FileHandler(archivo, encoding="utf-8"),
        # A stdout, no al stderr por defecto: PowerShell trata todo lo que llega por stderr
        # como error y marca la corrida como fallida aunque haya ido bien.
        logging.StreamHandler(sys.stdout),
    ]
    # El formatter va puesto antes de basicConfig: solo se lo asigna a los handlers que no
    # traigan uno, asi que ponerlo aca es lo que evita que lo pise con el de por defecto.
    for manejador in manejadores:
        manejador.setFormatter(formato)
    logging.basicConfig(level=logging.INFO, handlers=manejadores, force=True)
    # postgres_local_client emite un INFO por cada llamada (config_loaded, query_start,
    # query_done, tx_begin/commit) y config_loaded vuelca la lista entera de alias. Medido
    # con 3 de 10 colecciones: 110 de 142 lineas del log eran suyas. El log del pipeline es
    # lo que se lee para saber que paso, asi que se sube el umbral de esa libreria a WARNING.
    # Se ajusta aca y no en su .env (que es compartido con los otros proyectos) ni tocandola.
    logging.getLogger("postgres_local_client").setLevel(logging.WARNING)
    return archivo


def _registrar_corrida(inicio, segundos: float, resultado: str) -> None:
    execute_sql(
        "INSERT INTO bnpl_ops.etl_runs (started_at, tabla, modo, filas, segundos) "
        "VALUES (:inicio, 'pipeline', :modo, NULL, :segundos) "
        "ON CONFLICT (started_at, tabla) DO NOTHING",
        {"inicio": inicio, "modo": resultado, "segundos": round(segundos, 1)},
        db=DB_OPS_RW,
    )


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


def _alertas_previas() -> set:
    """Checks que ya estaban en alerta en la corrida ANTERIOR.

    quality_checks.run() ya persistio la corrida de hoy, asi que la anterior es el
    segundo checked_at mas alto. Sirve para distinguir las dos alertas cronicas
    (README.md:392-397) de una que aparecio hoy.
    """
    df = extract_sql(
        "SELECT check_name FROM bnpl_ops.data_quality_checks "
        "WHERE resultado <> 'OK' AND checked_at = ("
        "    SELECT max(checked_at) FROM bnpl_ops.data_quality_checks "
        "    WHERE checked_at < (SELECT max(checked_at) FROM bnpl_ops.data_quality_checks))",
        db=DB_OPS,
    )
    return set(df["check_name"])


def _reportar_calidad(log, filas: list) -> None:
    """Reporta las alertas con el nivel que les toca y el orden de v_quality_alerts.

    Antes todo salia como log.warning sin mirar `severidad`, y dos de los ocho checks son
    CRIT (ops/quality_checks.py:19 y :28). El criterio y el orden son los mismos de
    bnpl_ops.v_quality_alerts (sql/00_bnpl_ops.sql:97-102) para que el log y la vista que
    manda consultar README.md:375 digan lo mismo: CRIT primero, luego por n_filas.
    Tambien entra NO_APLICABLE, que es como la vista trata a un check sin su columna.
    """
    alertas = [f for f in filas if f["resultado"] != "OK"]
    if not alertas:
        log.info("calidad: los %d chequeos en OK", len(filas))
        return

    previas = _alertas_previas()
    orden = {"CRIT": 0, "WARN": 1}
    for a in sorted(alertas, key=lambda x: (orden.get(x["severidad"], 2), -(x["n_filas"] or 0))):
        emisor = log.error if a["severidad"] == "CRIT" else log.warning
        emisor(
            "calidad %s%s — %s: %s filas (%s)",
            a["severidad"],
            "" if a["check_name"] in previas else " NUEVA",
            a["check_name"],
            f"{a['n_filas']:,}" if a["n_filas"] is not None else "-",
            a["detalle"],
        )

    nuevas = [a["check_name"] for a in alertas if a["check_name"] not in previas]
    if nuevas:
        log.error("calidad: %d alerta(s) que no estaban ayer: %s", len(nuevas), ", ".join(nuevas))
    log.info("Detalle ordenado: select * from bnpl_ops.v_quality_alerts;")


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
            notificar.avisar_fallo("abortado_frescura", archivo, log)
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
        calidad = quality_checks.run()
        _reportar_calidad(log, calidad)
        # Las identidades entre capas son distintas del resto: no describen basura del origen sino
        # una capa que se quedo a medias. Si una no cuadra, el tablero va a leer numeros que no
        # cruzan entre si. NO_APLICABLE cuenta como rota: una identidad CRIT que no se pudo medir
        # (la relacion no existe, o el alias no la alcanza) tampoco esta comprobada.
        rotas = [a for a in calidad
                 if a["check_name"].startswith("identidad_") and a["severidad"] == "CRIT"
                 and a["resultado"] in ("ALERTA", "NO_APLICABLE")]
        if rotas:
            log.error(
                "%d identidad(es) entre capas sin comprobar: %s. La corrida sale con codigo 1.",
                len(rotas), ", ".join(a["check_name"] for a in rotas),
            )

        log.info("[6/6] Frescura final")
        finales = check_freshness.run()
        desincronizadas = [f for f in finales if f["semaforo_staging"] in ("CRIT", "FALTA")]
        for f in desincronizadas:
            log.warning(
                "%s quedo desincronizada: %s en Mongo vs %s en staging",
                f["coleccion"], f["docs_mongo"], f["docs_staging"],
            )

        segundos = time.time() - t0
        # Se termina la corrida completa (la frescura final ya quedo registrada) pero se sale con
        # 1 para que el Task Scheduler la marque como fallida. Un pipeline que devuelve 0 con una
        # identidad rota es un pipeline que miente.
        resultado = "ok" if not rotas else "ok_identidades_rotas"
        log.info("Pipeline terminado en %.1f min", segundos / 60)
        _registrar_corrida(inicio, segundos, resultado)
        return 0 if not rotas else 1

    except Exception:
        log.exception("Pipeline abortado por un error")
        _registrar_corrida(inicio, time.time() - t0, "error")
        notificar.avisar_fallo("error", archivo, log)
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

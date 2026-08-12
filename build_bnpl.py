"""Construye y refresca la capa de negocio (schema bnpl).

  build_bnpl.py              refresca las vistas materializadas en orden de dependencia
  build_bnpl.py --rebuild    reconstruye desde los .sql (DROP + CREATE); usar al cambiar la logica
  build_bnpl.py --solo v1,v2 limita la operacion a esas vistas

El refresh es completo, no incremental, y tiene que serlo: un pago puede llegar hasta 519 dias
despues del movimiento (recuperaciones de mora), asi que el PAR de un mes ya cerrado cambia
retroactivamente.
"""
import argparse
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
engine = create_engine(os.environ["BD_ENGINE_RABBIT_LOCAL"].strip("'\""))

TZ_OFFSET_HOURS = -6

# (vista, archivo DDL). El orden es el de dependencia: cada una puede leer de las anteriores.
CAPAS = [
    (None, "02_bnpl_funciones.sql"),
    ("grouped_orders", "03_bnpl_grouped_orders.sql"),
    ("loss_rates", "04_bnpl_loss_rates.sql"),
    ("par_snapshot", "05_bnpl_par_snapshot.sql"),
    ("vintage_analysis", "06_bnpl_vintage_analysis.sql"),
    ("grid_bnpl", "07_bnpl_grid_bnpl.sql"),
    ("kpis_daily", "08_bnpl_kpis_daily.sql"),
    ("revenue_comision", "09_bnpl_revenue_comision.sql"),
    ("corte_venta_sku", "10_bnpl_cortes_venta.sql"),
    ("corte_venta_so", None),  # se crea junto con corte_venta_sku
]


def _ahora_mx() -> datetime:
    return (datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)).replace(tzinfo=None)


def _registrar(vista: str, modo: str, filas, segundos: float, inicio) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO bnpl_ops.etl_runs (started_at, tabla, modo, filas, segundos) "
                "VALUES (:inicio, :tabla, :modo, :filas, :segundos) "
                "ON CONFLICT (started_at, tabla) DO NOTHING"
            ),
            {
                "inicio": inicio,
                "tabla": f"bnpl.{vista}",
                "modo": modo,
                "filas": filas,
                "segundos": round(segundos, 1),
            },
        )


def _filas(vista: str):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM bnpl.{vista}")).scalar()


def run(rebuild: bool = False, solo: list = None) -> None:
    capas = CAPAS
    if solo:
        capas = [(v, a) for v, a in CAPAS if v is None or v in solo]
        desconocidas = set(solo) - {v for v, _ in CAPAS if v}
        if desconocidas:
            raise SystemExit(f"No existen en CAPAS: {', '.join(sorted(desconocidas))}")

    for vista, archivo in capas:
        inicio, t0 = _ahora_mx(), time.time()

        if vista is None:
            # Bloque de funciones: siempre se aplica, no es una vista.
            with engine.begin() as conn:
                conn.execute(text((BASE_DIR / "sql" / archivo).read_text(encoding="utf-8")))
            print(f"{archivo}: aplicado ({time.time() - t0:.1f}s)")
            continue

        if rebuild:
            if archivo is None:
                # La vista se crea dentro del .sql de otra (cortes SKU y SO comparten archivo).
                print(f"bnpl.{vista}: creada junto con la anterior")
                continue
            with engine.begin() as conn:
                conn.execute(text((BASE_DIR / "sql" / archivo).read_text(encoding="utf-8")))
            modo = "rebuild"
        else:
            with engine.begin() as conn:
                conn.execute(text(f"REFRESH MATERIALIZED VIEW bnpl.{vista}"))
            modo = "refresh"

        segundos = time.time() - t0
        filas = _filas(vista)
        _registrar(vista, modo, filas, segundos, inicio)
        print(f"bnpl.{vista}: {filas:,} filas en {segundos:.1f}s ({modo})")

    engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Construye la capa de negocio BNPL")
    parser.add_argument(
        "--rebuild", action="store_true", help="reconstruye las vistas desde los .sql"
    )
    parser.add_argument("--solo", help="vistas a procesar, separadas por coma")
    args = parser.parse_args()
    run(rebuild=args.rebuild, solo=args.solo.split(",") if args.solo else None)

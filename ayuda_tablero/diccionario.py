# -*- coding: utf-8 -*-
"""Genera DICCIONARIO.md desde conocimiento.py. No inventa nada: solo formatea T, C y M.

    .venv\\Scripts\\python.exe ayuda_tablero\\diccionario.py             # dice si cambiaria
    .venv\\Scripts\\python.exe ayuda_tablero\\diccionario.py --escribir  # escribe DICCIONARIO.md
"""
import argparse
from datetime import date
from pathlib import Path

import conocimiento as kb

DESTINO = Path(__file__).resolve().parent.parent / "DICCIONARIO.md"


def _tabla_md(filas, encabezados):
    sep = "|" + "|".join("---" for _ in encabezados) + "|"
    cuerpo = ["| " + " | ".join(str(c).replace("|", "\\|") for c in f) + " |" for f in filas]
    return "\n".join(["| " + " | ".join(encabezados) + " |", sep] + cuerpo)


def componer() -> str:
    tablas = _tabla_md(
        [(f"`{n}`", d.get("grano", ""), d.get("fuente", ""), " ".join(d.get("notas", [])))
         for n, d in sorted(kb.T.items())],
        ["Tabla del modelo", "Grano", "De dónde sale", "Advertencias"],
    )
    campos = _tabla_md([(f"`{k}`", v) for k, v in sorted(kb.C.items())], ["Campo", "Qué es"])
    medidas = _tabla_md(
        [(f"`{k}`", v if isinstance(v, str) else " ".join(v)) for k, v in sorted(kb.M.items())],
        ["Medida DAX", "Qué calcula"],
    )
    return "\n".join([
        "# Diccionario de datos del tablero BNPL",
        "",
        "**Generado. No se edita a mano.** Sale de `ayuda_tablero/conocimiento.py`, que es la misma",
        "fuente de los 168 tooltips del tablero: si el diccionario y el tooltip dijeran cosas",
        "distintas, uno de los dos estaria mintiendo. Para corregir algo, edita ese archivo y corre",
        "`.venv\\Scripts\\python.exe ayuda_tablero\\diccionario.py --escribir`.",
        "",
        f"Regenerado el {date.today():%Y-%m-%d} · {len(kb.T)} tablas · {len(kb.C)} campos · "
        f"{len(kb.M)} medidas.",
        "",
        "El grano y las filas de cada vista de `pbi_bnpl` estan en `sql/pbi/README.md`; las 11 vistas",
        "de la capa de negocio, en `README.md`. Esto es la capa de columna y medida.",
        "", "## Tablas del modelo", "", tablas,
        "", "## Campos", "", campos,
        "", "## Medidas DAX", "", medidas, "",
    ])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Genera el diccionario de datos desde conocimiento.py")
    p.add_argument("--escribir", action="store_true", help="escribe DICCIONARIO.md")
    a = p.parse_args()
    nuevo = componer()
    actual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
    if a.escribir:
        DESTINO.write_text(nuevo, encoding="utf-8")
        print(f"{DESTINO}: escrito ({len(nuevo):,} bytes)")
    else:
        estado = "sin cambios" if nuevo == actual else "CAMBIARIA"
        print(f"{DESTINO.name}: {estado} — {len(kb.T)} tablas, {len(kb.C)} campos, "
              f"{len(kb.M)} medidas")

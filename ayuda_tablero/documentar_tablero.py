# -*- coding: utf-8 -*-
"""Regenera el texto de ayuda de todos los visuales del tablero y lo escribe en el PBIP.

    .venv\\Scripts\\python.exe ayuda_tablero\\documentar_tablero.py            # ver que cambiaria
    .venv\\Scripts\\python.exe ayuda_tablero\\documentar_tablero.py --aplicar   # escribirlo
    .venv\\Scripts\\python.exe ayuda_tablero\\documentar_tablero.py --aplicar --portada

Es idempotente: correrlo dos veces seguidas deja los archivos igual. Por eso el modo por
defecto es el de diagnostico — muestra cuantos visuales cambiarian y no toca nada.

El detalle de por que hacen falta DOS propiedades para que Power BI muestre el texto esta
en el README de esta carpeta.
"""
import argparse, json, subprocess, sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DATOS = AQUI / "_datos"
PY = sys.executable


def corre(script):
    r = subprocess.run([PY, str(AQUI / script)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=str(AQUI))
    if r.returncode != 0:
        print(f"--- fallo {script} ---")
        print(r.stdout or "")
        print(r.stderr or "")
        sys.exit(1)
    return (r.stdout or "").strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true",
                    help="escribe los textos en los visual.json (por defecto solo diagnostica)")
    ap.add_argument("--portada", action="store_true",
                    help="ademas regenera la pagina 'Como leer este tablero'")
    args = ap.parse_args()

    print("1/3  leyendo el PBIP (modelo + 192 visuales)...")
    print("     " + corre("inventario.py").replace("\n", "\n     "))

    print("2/3  componiendo los textos...")
    print("     " + corre("componer.py").replace("\n", "\n     "))

    textos = json.load(open(DATOS / "textos.json", encoding="utf-8"))

    # que cambiaria realmente
    sys.path.insert(0, str(AQUI))
    from aplicar import apply_to_file  # noqa: E402
    cambian = []
    for item in textos:
        actual = None
        try:
            d = json.load(open(item["file"], encoding="utf-8"))
            vco = d.get("visual", {}).get("visualContainerObjects", {})
            actual = vco.get("visualHeaderTooltip", [{}])[0].get(
                "properties", {}).get("text", {}).get("expr", {}).get("Literal", {}).get("Value")
        except Exception:
            pass
        nuevo = "'" + item["text"].replace("'", "''") + "'"
        if actual != nuevo:
            cambian.append(item)

    print(f"3/3  {len(textos)} visuales con texto · {len(cambian)} cambiarian")
    for c in cambian[:10]:
        print(f'       - [{c["page"]}] {c["type"]} {c["id"]}')
    if len(cambian) > 10:
        print(f"       ... y {len(cambian)-10} mas")

    if not args.aplicar:
        print("\n(modo diagnostico: no se escribio nada. Agrega --aplicar para escribirlo)")
        return

    for item in textos:
        apply_to_file(item["file"], item["text"], item.get("alt"))
    print(f"\nescritos {len(textos)} textos de ayuda en el PBIP")

    if args.portada:
        print(corre("portada.py"))


if __name__ == "__main__":
    main()

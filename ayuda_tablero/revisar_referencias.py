# -*- coding: utf-8 -*-
"""Resuelve cada campo de cada visual contra el modelo. Reporta los que no existen."""
import json, sys, collections
sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path
DATOS = Path(__file__).resolve().parent / "_datos"
inv = json.load(open(DATOS / "inventario.json", encoding="utf-8"))
model = inv["model"]

# indice: tabla -> set(columnas) / set(medidas)
cols = {t: set(v["columns"]) for t, v in model.items()}
meas = {t: set(v["measures"]) for t, v in model.items()}
all_meas = {}          # nombre de medida -> tabla (las medidas son globales en DAX)
for t, v in model.items():
    for m in v["measures"]:
        all_meas.setdefault(m, []).append(t)

roto = []
por_pagina = collections.Counter()
for v in inv["visuals"]:
    for f in v["fields"]:
        ent, prop, kind = f["entity"], f["property"], f["kind"]
        if not prop:
            continue
        # entidades que son alias de consulta (b, o, etc.) se ignoran
        if ent not in model:
            # puede ser un alias de SourceRef Source, o una tabla inexistente
            roto.append((v, f, "tabla-inexistente" if ent and len(ent) > 3 else "alias"))
            continue
        if kind == "Measure":
            if prop not in meas[ent]:
                # medida puede vivir en otra tabla y aun asi referenciarse
                if prop in all_meas:
                    continue
                roto.append((v, f, "medida-inexistente"))
        elif kind in ("Column", "HierarchyLevel"):
            if prop not in cols[ent] and prop not in meas[ent]:
                roto.append((v, f, "columna-inexistente"))

print("=" * 78)
print("REFERENCIAS QUE NO RESUELVEN CONTRA EL MODELO")
print("=" * 78)
reales = [r for r in roto if r[2] != "alias"]
if not reales:
    print("  ninguna")
for v, f, motivo in reales:
    por_pagina[v["page"]] += 1
    print(f'  [{motivo}] {f["entity"]}.{f["property"]}  ({f["kind"]}, rol {f["role"]})')
    print(f'        pagina "{v["page"]}" · visual {v["id"]} ({v["type"]}) · titulo: {v["title"]!r}')
print()
print("por pagina:", dict(por_pagina))

# visuales sin ningun campo (decorativos o vacios)
print()
print("=" * 78)
print("VISUALES SIN CAMPOS DE DATOS")
print("=" * 78)
sin = collections.Counter()
for v in inv["visuals"]:
    if not v["fields"]:
        sin[v["type"]] += 1
for k, n in sin.most_common():
    print(f"  {n:4d}  {k}")

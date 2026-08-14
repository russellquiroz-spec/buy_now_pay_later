# -*- coding: utf-8 -*-
"""Resuelve cada referencia de cada visual contra el modelo. Reporta las que no existen.

Cubre las cinco fuentes de referencias del PBIP, no solo el queryState:
    query           el campo esta en la grafica
    filtro-visual   filtro del visual (filterConfig del visual.json)
    filtro-pagina   filtro de pagina (filterConfig del page.json)
    filtro-reporte  filtro de reporte (filterConfig del report.json)
    objects         valor dinamico dentro de un objeto del visual (textbox, titulo, etc.)

Un filtro sobre una columna que no existe NO vacia el visual: lo deja SIN FILTRAR. Por eso
esa clase es la que rompe en silencio y la que hay que revisar.
"""
import json, sys, collections
sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path
DATOS = Path(__file__).resolve().parent / "_datos"
inv = json.load(open(DATOS / "inventario.json", encoding="utf-8"))
model = inv["model"]

cols = {t: set(v["columns"]) for t, v in model.items()}
meas = {t: set(v["measures"]) for t, v in model.items()}
all_meas = set()
for t, v in model.items():
    all_meas |= set(v["measures"])   # las medidas son globales en DAX

CTX_REPORTE = {"page": "(reporte)", "id": "-", "type": "filterConfig", "title": None}


def revisar(ref, ctx, roto):
    ent, prop, kind = ref["entity"], ref["property"], ref["kind"]
    if not prop:
        return
    if ent is None:
        # SourceRef.Source que no aparece en ningun bloque From del mismo ambito
        if ref.get("alias"):
            roto.append((ctx, ref, "alias-sin-resolver"))
        return
    if ent not in model:
        roto.append((ctx, ref, "tabla-inexistente"))
        return
    if kind == "Measure":
        if prop not in meas[ent] and prop not in all_meas:
            roto.append((ctx, ref, "medida-inexistente"))
    elif kind in ("Column", "HierarchyLevel"):
        if prop not in cols[ent] and prop not in meas[ent]:
            roto.append((ctx, ref, "columna-inexistente"))


roto = []
for ref in inv.get("report_refs", []):
    revisar(ref, CTX_REPORTE, roto)
for pid, p in inv["pages"].items():
    ctx = {"page": p["name"], "id": pid, "type": "page.json", "title": None}
    for ref in p.get("refs", []):
        revisar(ref, ctx, roto)
for v in inv["visuals"]:
    for ref in v.get("refs", []):
        revisar(ref, v, roto)

print("=" * 78)
print("REFERENCIAS QUE NO RESUELVEN CONTRA EL MODELO")
print("=" * 78)
if not roto:
    print("  ninguna")
por_pagina = collections.Counter()
por_origen = collections.Counter()
for ctx, f, motivo in roto:
    por_pagina[ctx["page"]] += 1
    por_origen[f["origen"]] += 1
    quien = f["entity"] or f'?{f["alias"]}'
    print(f'  [{motivo}] {quien}.{f["property"]}  ({f["kind"]}, origen {f["origen"]}, rol {f["role"]})')
    print(f'        pagina "{ctx["page"]}" · visual {ctx["id"]} ({ctx["type"]}) · titulo: {ctx["title"]!r}')
print()
print("por pagina:", dict(por_pagina))
print("por origen:", dict(por_origen))

# ---- jerarquias de fecha automaticas (dependen de __PBI_TimeIntelligenceEnabled) ----
print()
print("=" * 78)
print("VISUALES ATADOS A UNA JERARQUIA DE FECHAS AUTOMATICA")
print("=" * 78)
jer = collections.defaultdict(set)
for v in inv["visuals"]:
    for f in v.get("refs", []):
        if f["kind"] == "HierarchyLevel" and f.get("hierarchy"):
            jer[(f["entity"], f["property"])].add((v["page"], v["id"]))
tot = set()
for (ent, prop), vis in sorted(jer.items()):
    print(f"  {ent}[{prop}]  ->  {len(vis)} visuales")
    for pg, vid in sorted(vis):
        print(f"        {pg} · {vid}")
    tot |= vis
print(f"  TOTAL: {len(tot)} visuales sobre {len(jer)} columnas base")

# visuales sin ningun campo de datos (decorativos o vacios)
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

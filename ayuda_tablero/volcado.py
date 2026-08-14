# -*- coding: utf-8 -*-
"""Volcado compacto de todos los visuales, pagina por pagina."""
import json, sys, re
sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path
DATOS = Path(__file__).resolve().parent / "_datos"
inv = json.load(open(DATOS / "inventario.json", encoding="utf-8"))
model = inv["model"]
meas = {}
for t, v in model.items():
    for m, mm in v["measures"].items():
        meas[m] = (t, " ".join((mm["expr"] or "").split()))
calc_cols = {}
for t, v in model.items():
    for c, cc in v["columns"].items():
        if cc.get("expr"):
            calc_cols[f"{t}.{c}"] = " ".join((cc["expr"] or "").split())

def src(tbl):
    t = model.get(tbl)
    if not t:
        return "?"
    return t["source"][0] if t["source"] else "DAX"

pages = sorted({v["page"]: v["page_order"] for v in inv["visuals"]}.items(), key=lambda x: x[1])
target = sys.argv[1] if len(sys.argv) > 1 else None

for pname, _ in pages:
    if target and pname != target:
        continue
    vs = [v for v in inv["visuals"] if v["page"] == pname]
    vs.sort(key=lambda v: (round(v["pos"].get("y", 0)), round(v["pos"].get("x", 0))))
    print(f'\n########## {pname} ({len(vs)}) ##########')
    for v in vs:
        t = v["title"] or ""
        st = f' // {v["subtitle"]}' if v["subtitle"] else ""
        print(f'\n[{v["id"]}] {v["type"]} :: {t}{st}')
        if v["textbox"]:
            print(f'    TEXTO: {v["textbox"][:200]}')
        tabs = set()
        for p in v["projections"]:
            qr = p.get("queryRef") or ""
            nm = p.get("nativeQueryRef") or ""
            if p.get("agg"):
                real = f'{p["agg"]}({p.get("aggEntity")}.{p.get("aggProperty")})'
                aviso = "" if p["agg"].lower() in qr.lower() else "   <-- ALIAS DESACTUALIZADO"
                print(f'    <{p["role"]}> {nm} = {real}{aviso}')
                if aviso:
                    print(f'        (queryRef dice: {qr})')
            else:
                print(f'    <{p["role"]}> {nm} <= {qr}')
            if p.get("calcExpr"):
                print(f'        CALC {p["calcName"]} = {p["calcExpr"]}')
            base = qr.split(".")[0].replace("Sum(", "").replace("Count(", "").replace("CountNonNull(", "")
            tabs.add(base)
            mname = qr.split(".")[-1]
            if mname in meas:
                print(f'        DAX = {meas[mname][:300]}')
            if qr in calc_cols:
                print(f'        COLCALC = {calc_cols[qr][:220]}')
        for fd in v.get("filterDetail", []):
            print(f'    FILTRO {fd["campo"]}: {fd["desc"]}')
        srcs = sorted({src(x) for x in tabs if x in model})
        if srcs:
            print(f'    ORIGEN: {srcs}')

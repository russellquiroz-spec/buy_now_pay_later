# -*- coding: utf-8 -*-
"""Inventario del PBIP: modelo semantico (tablas/columnas/medidas/DAX) + todos los visuales."""
import json, glob, os, re, sys, io

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent   # raiz del repo
PBIP     = BASE_DIR / "pbi_new"
DATOS    = Path(__file__).resolve().parent / "_datos"
DATOS.mkdir(exist_ok=True)
ROOT = str(PBIP)
MODEL = os.path.join(ROOT, "Buy Now Pay Later.SemanticModel", "definition")
RPT = os.path.join(ROOT, "Buy Now Pay Later.Report", "definition")

# ---------------- modelo ----------------
def strip_name(s):
    s = s.strip()
    if s.startswith("'") and s.endswith("'"):
        s = s[1:-1]
    return s

def parse_tmdl(path):
    """Devuelve dict de tabla con columnas y medidas (incl. expresion DAX)."""
    txt = open(path, encoding="utf-8").read()
    lines = txt.split("\n")
    tname = None
    cols, meas = {}, {}
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = re.match(r"^table\s+(.+?)\s*$", ln)
        if m:
            tname = strip_name(m.group(1))
            i += 1
            continue
        m = re.match(r"^\t(measure|column|hierarchy)\s+(.*?)(\s*=\s*(.*))?$", ln)
        if m:
            kind, nm, _, rest = m.groups()
            nm = strip_name(nm)
            expr = None
            if rest is not None:
                rest = rest.strip()
                if rest.startswith("```"):
                    # bloque multilinea delimitado por ```
                    buf = []
                    i += 1
                    while i < len(lines) and "```" not in lines[i]:
                        buf.append(lines[i])
                        i += 1
                    expr = "\n".join(x.strip() for x in buf).strip()
                elif rest == "":
                    # TMDL tambien admite expresion multilinea SIN backticks:
                    # las lineas de la expresion van con >=3 tabs; las propiedades con 2.
                    buf = []
                    j = i + 1
                    while j < len(lines):
                        l = lines[j]
                        if l.strip() == "":
                            buf.append("")
                            j += 1
                            continue
                        if l.startswith("\t\t\t"):
                            buf.append(l.strip())
                            j += 1
                            continue
                        break
                    expr = "\n".join(buf).strip()
                    i = j - 1
                else:
                    expr = rest
            # propiedades del objeto (dataType, formatString...)
            props = {}
            j = i + 1
            while j < len(lines) and (lines[j].startswith("\t\t") or lines[j].strip() == ""):
                pm = re.match(r"^\t\t(\w+):\s*(.*)$", lines[j])
                if pm:
                    props[pm.group(1)] = pm.group(2).strip()
                j += 1
            if kind == "measure":
                meas[nm] = {"expr": expr, "props": props}
            elif kind == "column":
                cols[nm] = {"expr": expr, "props": props}
        i += 1
    # fuente
    src = re.findall(r"from\s+(pbi_bnpl\.[a-zA-Z_0-9]+)", txt)
    is_calc = bool(re.search(r"partition\s+.+?=\s*calculated", txt))
    return {"table": tname, "columns": cols, "measures": meas,
            "source": sorted(set(src)), "calculated": is_calc,
            "raw_len": len(txt)}

model = {}
for f in sorted(glob.glob(os.path.join(MODEL, "tables", "*.tmdl"))):
    b = os.path.basename(f)[:-5]
    t = parse_tmdl(f)
    if not t["table"]:
        continue
    t["file"] = b
    t["is_localdate"] = b.startswith(("LocalDateTable", "DateTableTemplate"))
    model[t["table"]] = t

# ---------------- visuales ----------------
def walk_fields(o, out, path=""):
    """Recolecta referencias Column/Measure/etc de una estructura de query."""
    if isinstance(o, dict):
        for k in ("Column", "Measure", "HierarchyLevel", "Aggregation",
                  "NativeVisualCalculation", "SparklineData"):
            if k in o:
                node = o[k]
                ent = None
                prop = node.get("Property") if isinstance(node, dict) else None
                if isinstance(node, dict):
                    e = node.get("Expression", {})
                    if isinstance(e, dict):
                        sr = e.get("SourceRef") or {}
                        if isinstance(sr, dict):
                            ent = sr.get("Entity") or sr.get("Source")
                if k == "Aggregation":
                    walk_fields(node, out, path)
                    continue
                out.append({"kind": k, "entity": ent, "property": prop, "role": path})
        for kk, vv in o.items():
            walk_fields(vv, out, path or kk)
    elif isinstance(o, list):
        for v in o:
            walk_fields(v, out, path)

def lit(node):
    """Extrae valor literal de un expr."""
    try:
        return node["expr"]["Literal"]["Value"]
    except Exception:
        return None

def unq(v):
    if v is None:
        return None
    v = str(v)
    if v.startswith("'") and v.endswith("'"):
        return v[1:-1]
    return v

pages = {}
pj = json.load(open(os.path.join(RPT, "pages", "pages.json"), encoding="utf-8"))
order = pj["pageOrder"]

visuals = []
for pdir in sorted(glob.glob(os.path.join(RPT, "pages", "*", "page.json"))):
    p = json.load(open(pdir, encoding="utf-8"))
    pid = p["name"]
    pages[pid] = {"name": p.get("displayName"), "id": pid,
                  "order": order.index(pid) if pid in order else 999,
                  "dir": os.path.dirname(pdir)}
    for vf in sorted(glob.glob(os.path.join(os.path.dirname(pdir), "visuals", "*", "visual.json"))):
        v = json.load(open(vf, encoding="utf-8"))
        vis = v.get("visual", {})
        vtype = vis.get("visualType")
        # titulo
        vco = vis.get("visualContainerObjects", {})
        title = None
        if "title" in vco:
            title = unq(lit(vco["title"][0].get("properties", {}).get("text", {})))
        subtitle = None
        if "subTitle" in vco:
            subtitle = unq(lit(vco["subTitle"][0].get("properties", {}).get("text", {})))
        # texto de cuadros de texto
        tbox = None
        objs = vis.get("objects", {})
        if "general" in objs:
            try:
                pr = objs["general"][0]["properties"]
                if "paragraphs" in pr:
                    frag = []
                    for para in pr["paragraphs"]:
                        for run in para.get("textRuns", []):
                            frag.append(run.get("value", ""))
                    tbox = " ".join(frag).strip()
            except Exception:
                pass
        # --- proyecciones por rol, con queryRef/nativeQueryRef y calculos visuales ---
        projs = []
        for role, body in (vis.get("query", {}).get("queryState", {}) or {}).items():
            if not isinstance(body, dict):
                continue
            for proj in body.get("projections", []) or []:
                fld = proj.get("field", {}) or {}
                kind = next(iter(fld), None)
                node = fld.get(kind) if kind else None
                entry = {
                    "role": role,
                    "kind": kind,
                    "queryRef": proj.get("queryRef"),
                    "nativeQueryRef": proj.get("nativeQueryRef"),
                    "hidden": proj.get("hidden", False),
                }
                if kind == "NativeVisualCalculation" and isinstance(node, dict):
                    entry["calcExpr"] = node.get("Expression")
                    entry["calcName"] = node.get("Name")
                # La agregacion REAL vive en Aggregation.Function; queryRef es un alias
                # que puede quedar desactualizado (p.ej. dice Min y en realidad es DistinctCount).
                AGG = {0: "Sum", 1: "Avg", 2: "DistinctCount", 3: "Min", 4: "Max",
                       5: "Count", 6: "Median", 7: "StdDev", 8: "Var", 9: "CountNonNull"}
                if kind == "Aggregation" and isinstance(node, dict):
                    entry["agg"] = AGG.get(node.get("Function"), node.get("Function"))
                    inner = node.get("Expression", {}) or {}
                    ik = next(iter(inner), None)
                    innode = inner.get(ik) if ik else None
                    if isinstance(innode, dict):
                        entry["aggProperty"] = innode.get("Property")
                        e2 = innode.get("Expression", {}) or {}
                        sr = e2.get("SourceRef") or {}
                        if isinstance(sr, dict):
                            entry["aggEntity"] = sr.get("Entity") or sr.get("Source")
                        entry["kind"] = ik
                projs.append(entry)
        vdict = {}

        fields = []
        walk_fields(vis.get("query", {}).get("queryState", {}), fields)
        # dedup preservando orden
        seen, uf = set(), []
        for f in fields:
            key = (f["kind"], f["entity"], f["property"], f["role"])
            if key not in seen:
                seen.add(key)
                uf.append(f)
        # --- filtros del visual, legibles ---
        CMP = {0: "=", 1: "<>", 2: ">", 3: ">=", 4: "<", 5: "<="}
        fdet = []
        for flt in (v.get("filterConfig", {}) or {}).get("filters", []) or []:
            fld = json.dumps(flt.get("field", {}), ensure_ascii=False)
            m = re.search(r'"Property":\s*"([^"]+)"', fld)
            campo = m.group(1) if m else "?"
            body = flt.get("filter", {}) or {}
            js = json.dumps(body, ensure_ascii=False)
            vals = re.findall(r'"Literal":\s*\{\s*"Value":\s*"([^"]*)"', js)
            negado = '"Not"' in js
            cmpk = re.search(r'"ComparisonKind":\s*(\d+)', js)
            if cmpk:
                desc = f'{CMP.get(int(cmpk.group(1)), "?")} {", ".join(vals[:6])}'
            elif vals:
                desc = ("EXCLUYE " if negado else "solo ") + ", ".join(vals[:12])
                if len(vals) > 12:
                    desc += f' (+{len(vals)-12})'
            else:
                desc = flt.get("type", "?")
            if flt.get("isHiddenInViewMode"):
                desc += "  [oculto en lectura]"
            fdet.append({"campo": campo, "desc": desc, "tipo": flt.get("type")})

        filters = []
        walk_fields(v.get("filterConfig", {}), filters)
        walk_fields(objs.get("general", [{}])[0].get("properties", {}).get("filter", {}) if "general" in objs else {}, filters)
        visuals.append({
            "page": p.get("displayName"), "page_id": pid,
            "page_order": pages[pid]["order"],
            "id": v.get("name"), "type": vtype,
            "title": title, "subtitle": subtitle, "textbox": tbox,
            "fields": uf, "projections": projs, "filterDetail": fdet,
            "filters": [f for f in filters if f.get("property")],
            "file": vf,
            "has_tooltip": "visualHeaderTooltip" in vco,
            "pos": v.get("position", {}),
            "parentGroup": v.get("parentGroupName"),
            "isGroup": "visualGroup" in v,
        })

out = {"model": model, "pages": pages, "visuals": visuals}
with open(DATOS / "inventario.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)

print("tablas modelo (reales):", len([t for t in model.values() if not t["is_localdate"]]))
print("visuales:", len(visuals))
print("paginas:", len(pages))
print("visuales tipo group:", sum(1 for v in visuals if v["isGroup"]))
print("tipos de visual:")
import collections
for k, n in collections.Counter(v["type"] for v in visuals).most_common():
    print(f"   {n:4d}  {k}")

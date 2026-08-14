# -*- coding: utf-8 -*-
"""Aplica texto de ayuda a visuales PBIP.

Mecanismo verificado contra el motor instalado (DESKTOP.MIN.JS v2.148):
    setHeaderTooltip(){ var e=visualHeader, t=visualHeaderTooltip;
                        this.headerTooltip = e && e.showTooltipButton && t ? t : void 0 }
=> hace falta visualHeader.showTooltipButton = true  Y  visualHeaderTooltip.text.

Escribe ademas general.altText (lectores de pantalla).
Preserva cualquier propiedad existente; solo agrega/actualiza las suyas.
"""
import json, os, sys, io, shutil

def _lit(value):
    """Envuelve un valor en la forma expr/Literal que usa PBIP."""
    return {"expr": {"Literal": {"Value": value}}}

def _sql_str(s):
    """Literal de texto PBIP: comillas simples, escapando las internas."""
    return "'" + s.replace("'", "''") + "'"

def _upsert(container, obj_name, props):
    """Inserta/actualiza properties dentro de visualContainerObjects[obj_name][0]."""
    arr = container.setdefault(obj_name, [])
    if not arr:
        arr.append({"properties": {}})
    entry = arr[0]
    entry.setdefault("properties", {}).update(props)

def apply_to_file(path, text, alt_text=None, dry_run=False):
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    vis = doc.get("visual")
    if vis is None:
        return "sin-visual"
    vco = vis.setdefault("visualContainerObjects", {})

    # 1) encender el icono de informacion en el encabezado
    _upsert(vco, "visualHeader", {"showTooltipButton": _lit("true")})
    # 2) el texto del tooltip (type Default = texto plano)
    _upsert(vco, "visualHeaderTooltip", {
        "type": _lit("'Default'"),
        "text": _lit(_sql_str(text)),
    })
    # 3) alt text para lectores de pantalla
    _upsert(vco, "general", {"altText": _lit(_sql_str(alt_text or text))})

    if dry_run:
        return "ok(dry)"
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
    return "ok"

if __name__ == "__main__":
    # uso: apply_tooltips.py mapping.json   (mapping: [{file, text, alt?}, ...])
    mapping = json.load(open(sys.argv[1], encoding="utf-8"))
    dry = "--dry" in sys.argv
    counts = {}
    for item in mapping:
        r = apply_to_file(item["file"], item["text"], item.get("alt"), dry_run=dry)
        counts[r] = counts.get(r, 0) + 1
    print("resultado:", counts)

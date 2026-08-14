# -*- coding: utf-8 -*-
"""Compone el texto de ayuda de cada visual a partir de lo que el visual REALMENTE hace.

Estructura fija en tres partes, que es la que se valido:
    Que mide: ...
    Universo y corte: ...
    De donde sale: ...
Cada parte termina en punto y se separa con salto de linea, para que se lea bien
tanto si Power BI respeta el salto como si lo colapsa.
"""
import json, re, sys, unicodedata
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import conocimiento as kb
from textos_a_mano import OVERRIDES

DATOS = Path(__file__).resolve().parent / "_datos"

inv = json.load(open(DATOS / "inventario.json", encoding="utf-8"))
model = inv["model"]
MEAS = {m for t, v in model.items() for m in v["measures"]}

DECORATIVOS = {"shape", "actionButton", "image", "textbox", None}

AGGV = {"Sum": "La suma de", "Avg": "El promedio de", "Min": "El minimo de",
        "Max": "El maximo de", "Median": "La mediana de",
        "DistinctCount": "El numero de", "Count": "El conteo de",
        "CountNonNull": "El conteo de", "StdDev": "La desviacion de", "Var": "La varianza de"}

def humaniza(nombre):
    """camelCase / snake_case -> frase legible."""
    if not nombre:
        return "el campo"
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(nombre)).replace("_", " ")
    return s.strip().lower()

def campo(prop):
    prop = str(prop).rstrip(") ") if prop else prop
    return kb.C.get(prop) or humaniza(prop)

def medida(nombre):
    return kb.M.get(nombre) or humaniza(nombre)

def tabla_de(p):
    if p.get("agg"):
        return p.get("aggEntity")
    qr = p.get("queryRef") or ""
    return qr.split(".")[0]

def es_medida(p):
    qr = p.get("queryRef") or ""
    return (qr.split(".")[-1].rstrip(") ") in MEAS) or (p.get("kind") == "Measure")

def nom_medida(p):
    return (p.get("queryRef") or "").split(".")[-1].rstrip(") ")

def jerarquia(qr):
    """bnpl_par.corte.Variacion.Jerarquia de fechas.Mes -> (corte, Mes)"""
    partes = qr.split(".")
    if len(partes) >= 3:
        return partes[1], partes[-1]
    return None, None

def frase_que_mide(v):
    vals, cats, series = [], [], []
    for p in v["projections"]:
        role = (p.get("role") or "").lower()
        if p.get("calcExpr"):
            vals.append(f'{p.get("calcName") or "un calculo del visual"} ({p["calcExpr"]})')
            continue
        if p.get("agg"):
            txt = f'{AGGV.get(p["agg"], p["agg"])} {campo(p.get("aggProperty"))}'
            if p["agg"] == "DistinctCount":
                txt = f'El numero de {campo(p.get("aggProperty"))} distintos'
        elif es_medida(p):
            txt = medida(nom_medida(p))
        elif p.get("kind") == "HierarchyLevel":
            base, niv = jerarquia(p.get("queryRef") or "")
            txt = f'{campo(base)} por {str(niv).lower()}'
        else:
            txt = campo((p.get("queryRef") or "").split(".")[-1])
        if role in ("values", "y", "y2", "value", "data", "size"):
            vals.append(txt)
        elif role in ("category", "x", "axis", "rows"):
            cats.append(txt)
        elif role in ("series", "legend", "columns", "group"):
            series.append(txt)
    # dedup preservando orden
    def dd(xs):
        out, seen = [], set()
        for x in xs:
            if x not in seen:
                seen.add(x); out.append(x)
        return out
    vals, cats, series = dd(vals), dd(cats), dd(series)
    if not vals and cats:
        vals, cats = cats, []
    if not vals:
        return None
    s = " y ".join(vals[:3]) if len(vals) <= 3 else ", ".join(vals[:3]) + f" y {len(vals)-3} columnas mas"
    if cats:
        s += ", por " + " y ".join(cats[:2])
    if series:
        s += ", abierto por " + " y ".join(series[:2])
    return s[0].upper() + s[1:] + "."

def universo(v):
    tabs = []
    for p in v["projections"]:
        t = tabla_de(p)
        if t in kb.T and t not in tabs:
            tabs.append(t)
    partes, notas = [], []
    if tabs:
        info = kb.T[tabs[0]]
        partes.append(f'El grano es {info["grano"]}.')
        for n in info["notas"]:
            if n not in notas:
                notas.append(n)
        for t in tabs[1:]:
            for n in kb.T[t]["notas"]:
                if n not in notas:
                    notas.append(n)
    # filtros propios del visual
    fl = []
    for fd in v.get("filterDetail", []):
        d = fd["desc"]
        if fd["campo"] == "?" or d in ("Advanced", "Categorical", "TopN", "RelativeDate",
                                        "VisualTopN", "Include", "Exclude"):
            continue
        d = re.sub(r"[^\s,;:]+", lambda m: limpia_literal(m.group(0)), d)
        if "null" in d and d.startswith("EXCLUYE") and len(d) < 26:
            continue
        fl.append(f'{campo(fd["campo"])}: {d}')
    if fl:
        partes.append("El visual filtra por " + "; ".join(fl[:3]) + ".")
    partes.extend(notas)
    return " ".join(partes)

def fuente(v):
    tabs = []
    for p in v["projections"]:
        t = tabla_de(p)
        if t in kb.T and t not in tabs:
            tabs.append(t)
    if not tabs:
        return None
    fs = [kb.T[t]["fuente"] for t in tabs[:2]]
    return "Sale de " + " y de ".join(fs) + "."

def limpia(s):
    return acentua(" ".join(str(s).split()))

def texto_de(v):
    if v["id"] in OVERRIDES:
        t = OVERRIDES[v["id"]].strip()
        # respeta los saltos entre las tres partes
        partes = []
        for etq in ("Que mide:", "Universo y corte:", "De donde sale:"):
            i = t.find(etq)
            if i >= 0:
                partes.append(i)
        trozos, partes = [], sorted(partes)
        for k, i in enumerate(partes):
            j = partes[k + 1] if k + 1 < len(partes) else len(t)
            trozos.append(limpia(t[i:j]))
        r = chr(10).join(trozos) if trozos else limpia(t)
        return r.replace("Que mide:", "Qué mide:").replace("De donde sale:", "De dónde sale:")
    if v["type"] in DECORATIVOS or not v["projections"]:
        return None
    qm = frase_que_mide(v)
    if not qm:
        return None
    if v["type"] == "slicer":
        campos = []
        for p in v["projections"]:
            campos.append(campo((p.get("queryRef") or "").split(".")[-1]))
        qm = f'No es una métrica, es un filtro: acota la página por {" y ".join(dict.fromkeys(campos))}.'
    u = universo(v)
    f = fuente(v)
    out = f"Qué mide: {limpia(qm)}"
    if u:
        out += f"\nUniverso y corte: {limpia(u)}"
    if f:
        out += f"\nDe dónde sale: {limpia(f)}"
    return out

# ---------------------------------------------------------------- correcciones
ACENTOS = {
 "metrica":"métrica","Metrica":"Métrica","historica":"histórica","Historica":"Histórica",
 "historico":"histórico","numero":"número","Numero":"Número","credito":"crédito",
 "Credito":"Crédito","maduracion":"maduración","informacion":"información",
 "proporcion":"proporción","transaccion":"transacción","transacciones":"transacciones",
 "categoria":"categoría","categorias":"categorías","aun":"aún","segun":"según",
 "estan":"están","esta incompleto":"está incompleto","tenia":"tenía","habia":"había",
 "origino":"originó","enrolo":"enroló","division":"división","relacion":"relación",
 "clasificacion":"clasificación","desviacion":"desviación","mediana":"mediana",
 "minimo":"mínimo","maximo":"máximo","ultimo":"último","dias":"días","dia":"día",
 "mas":"más","asi":"así","tambien":"también","aqui":"aquí",
 "vencidos":"vencidos","atras":"atrás","despues":"después","antes":"antes",
 "linea":"línea","Linea":"Línea","practica":"práctica","automatico":"automático",
 "unico":"único","unica":"única","pagina":"página","Pagina":"Página",
 "calculo":"cálculo","Calculo":"Cálculo","calculada":"calculada","genero":"género",
 "vigencia":"vigencia","reparticion":"repartición","extraccion":"extracción",
 "estructura":"estructura","comision":"comisión","Comision":"Comisión",
 "interes":"interés","Interes":"Interés","porcentaje":"porcentaje",
 "desplegado":"desplegado","denominador":"denominador","cohorte":"cohorte",
 "activacion":"activación","enrolamiento":"enrolamiento","preventa":"preventa",
 "sugieren":"sugieren","definicion":"definición","definiciones":"definiciones",
}
_ACC_RE = re.compile(r"\b(" + "|".join(sorted(ACENTOS, key=len, reverse=True)) + r")\b")

def acentua(s):
    return _ACC_RE.sub(lambda m: ACENTOS[m.group(1)], s)

def limpia_literal(v):
    """-1L -> -1 ; datetime'2025-08-01T00:00:00' -> 2025-08-01 ; 'X' -> X"""
    v = str(v).strip()
    v = re.sub(r"^datetime'([0-9-]{10}).*'$", r"\1", v)
    v = re.sub(r"^'(.*)'$", r"\1", v)
    v = re.sub(r"^(-?\d+)L$", r"\1", v)
    v = re.sub(r"^(-?\d+(?:\.\d+)?)D$", r"\1", v)
    return v


if __name__ == "__main__":
    salida, sin_texto = [], []
    for v in inv["visuals"]:
        t = texto_de(v)
        if t:
            salida.append({"file": v["file"], "text": t, "id": v["id"],
                           "page": v["page"], "type": v["type"], "title": v["title"]})
        else:
            sin_texto.append(v)
    json.dump(salida, open(DATOS / "textos.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"visuales con texto : {len(salida)}")
    print(f"sin texto (decorativos/sin datos): {len(sin_texto)}")
    import collections
    print("  ", dict(collections.Counter(v["type"] for v in sin_texto)))
    print(f"con override escrito a mano: {sum(1 for v in inv['visuals'] if v['id'] in OVERRIDES)}")


# -*- coding: utf-8 -*-
"""Crea la pagina de portada 'Como leer este tablero' y la pone primero."""
import json, os, sys, shutil
sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
RPT = str(BASE_DIR / "pbi_new" / "Buy Now Pay Later.Report" / "definition")
PAGES = os.path.join(RPT, "pages")
PID = "00portada0bnpl0lectura"[:20]
AZUL = "#00AEEF"
GRIS = "#3B3B3B"

def run(txt, size=11, bold=False, color=GRIS):
    st = {"fontSize": f"{size}pt", "color": color}
    if bold:
        st["fontWeight"] = "bold"
    return {"value": txt, "textStyle": st}

def parrafos(bloques):
    out = []
    for b in bloques:
        if b is None:
            out.append({"textRuns": [run(" ", 6)]})
        else:
            out.append({"textRuns": b if isinstance(b, list) else [b]})
    return out

def textbox(name, x, y, w, h, bloques, z=1000):
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.3.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
        "visual": {
            "visualType": "textbox",
            "objects": {"general": [{"properties": {"paragraphs": parrafos(bloques)}}]},
            "drillFilterOtherVisuals": True,
        },
    }

# ------------------------------------------------------------------ contenido
T_TITULO = [
    [run("Cómo leer este tablero", 28, True, AZUL)],
    None,
    [run("BNPL es el crédito que Rabbit ofrece a los tenderos para que surtan su tienda hoy y "
         "paguen después. ", 12),
     run("Quien presta el dinero es Propaga", 12, True),
     run(", no Rabbit. El tendero recibe su pedido y tiene ", 12),
     run("15 días", 12, True),
     run(" para pagarlo. Sobre el interés que cobra Propaga, Rabbit gana una comisión del ", 12),
     run("14.2%", 12, True),
     run(". Por eso en este tablero conviven dos ideas de \"ingreso\": el interés total del "
         "crédito y la parte que le toca a Rabbit.", 12)],
]

T_ORDEN = [
    [run("En qué orden conviene leerlo", 16, True, AZUL)],
    None,
    [run("1. Resumen Ejecutivo", 11, True), run("  ·  ¿Cuánto hemos prestado, cuánto nos deben y "
        "cuánto ganamos? Es la foto de hoy.", 11)],
    [run("2. KPI's Tracking", 11, True), run("  ·  ¿Cómo se mueven esos números mes a mes?", 11)],
    [run("3. Funnel", 11, True), run("  ·  De los tenderos elegibles, ¿cuántos se enrolan y "
        "cuántos llegan a usar el crédito?", 11)],
    [run("4. Survival Matrix", 11, True), run("  ·  De los que ya usaron el crédito, ¿cuántos "
        "siguen comprando conforme pasan los meses?", 11)],
    [run("5. Salud del Portafolio", 11, True), run("  ·  ¿Cuánto de lo prestado está en mora y "
        "cómo se mueve entre tramos de atraso?", 11)],
    [run("6. Cambio en Comportamiento de Compra", 11, True), run("  ·  ¿El crédito hace que el "
        "tendero compre más, más seguido o se quede más tiempo?", 11)],
    [run("7. Vintage Analysis", 11, True), run("  ·  ¿Las cosechas nuevas se comportan mejor o "
        "peor que las viejas, a la misma edad?", 11)],
    [run("8. Audiencias", 11, True), run("  ·  ¿En qué momento de su vida como cliente está cada "
        "tendero?", 11)],
    [run("9. Fraud, Top users, Clientes con Crédito Activo", 11, True),
     run("  ·  Listas operativas para trabajar caso por caso.", 11)],
    None,
    [run("Return On Investment, Default Customer Profile y Search están ocultas en modo lectura: "
         "quien abre el tablero publicado no las ve.", 10)],
]

T_TRAMPAS = [
    [run("Seis definiciones que hay que tener presentes", 16, True, AZUL)],
    None,
    [run("Cada gráfica trae su propia explicación: pasa el mouse por el ícono ⓘ de su encabezado. "
         "Estas seis cruzan varias páginas y explican por qué dos números que parecen lo mismo no "
         "coinciden.", 11)],
    None,
    [run("Hay dos rutas y no dan lo mismo. ", 11, True),
     run("La mora usa la ruta histórica: quién tenía la cuenta cuando se originó el crédito. El "
         "grid de clientes usa la vigente: quién la atiende hoy. Atribuir mora vieja al supervisor "
         "actual sería injusto, por eso conviven las dos.", 11)],
    None,
    [run("La tasa PAR tiene dos denominadores. ", 11, True),
     run("Las medidas del vintage dividen entre capital desplegado ($1,760M) y dan 6.0%. Las "
         "columnas de la misma tabla dividen entre saldo vivo ($276M) y dan 38.4%. Las gráficas de "
         "cierre mensual de Salud del Portafolio también usan saldo. Cada tooltip dice cuál usa "
         "su gráfica.", 11)],
    None,
    [run("El mes en curso está incompleto. ", 11, True),
     run("Las tablas de corte mensual llegan hasta el cierre del mes actual, pero con datos "
         "parciales. La última barra de cualquier serie mensual siempre va a verse baja.", 11)],
    None,
    [run("El 85.9% de las filas de mora traen saldo cero. ", 11, True),
     run("En bnpl_par y months_closes, los pedidos ya pagados en cortes anteriores se guardan como "
         "'PaidPrev' con saldo cero, para no inflar el saldo del cohorte. No mueven ningún monto, "
         "pero aparecen como una categoría más en leyendas y slicers.", 11)],
    None,
    [run("La comisión de Rabbit se calcula sobre dos bases. ", 11, True),
     run("En bnpl_loss_rates el 14.2% se aplica sobre el interés con IVA; en el grid, sobre el "
         "interés sin IVA. Son 17.3% de diferencia. El Resumen Ejecutivo muestra por defecto la "
         "versión sin IVA, dividiendo entre 1.16.", 11)],
    None,
    [run("No todos los filtros llegan a todas las gráficas. ", 11, True),
     run("Los slicers de oficina, ruta, edad y género salen del grid de clientes. Alcanzan las "
         "gráficas de mora, pero no las de cosechas, audiencias ni roll rates, que no tienen "
         "relación con el grid. El tooltip de cada gráfica lo indica.", 11)],
]

T_PIE = [
    [run("Los datos salen del esquema pbi_bnpl de la base rabbit-bi-local: una vista por tabla del "
         "modelo, definida en sql/pbi/. Cada tooltip nombra la vista y su fuente original.", 10)],
]

def main():
    d = os.path.join(PAGES, PID)
    os.makedirs(os.path.join(d, "visuals"), exist_ok=True)
    page = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
        "name": PID,
        "displayName": "Cómo leer este tablero",
        "displayOption": "ActualSize",
        "height": 1180,
        "width": 1800,
    }
    json.dump(page, open(os.path.join(d, "page.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    cajas = [
        ("p0titulo000000000001", 40, 30, 1720, 190, T_TITULO),
        ("p0orden0000000000002", 40, 240, 830, 560, T_ORDEN),
        ("p0trampas00000000003", 900, 240, 860, 840, T_TRAMPAS),
        ("p0pie000000000000004", 40, 820, 830, 90, T_PIE),
    ]
    for name, x, y, w, h, cont in cajas:
        vd = os.path.join(d, "visuals", name)
        os.makedirs(vd, exist_ok=True)
        json.dump(textbox(name, x, y, w, h, cont),
                  open(os.path.join(vd, "visual.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

    pj = os.path.join(PAGES, "pages.json")
    meta = json.load(open(pj, encoding="utf-8"))
    meta["pageOrder"] = [PID] + [p for p in meta["pageOrder"] if p != PID]
    meta["activePageName"] = PID
    json.dump(meta, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"portada creada: {PID} con {len(cajas)} cuadros de texto")
    print("pageOrder ahora empieza por la portada")

if __name__ == "__main__":
    main()

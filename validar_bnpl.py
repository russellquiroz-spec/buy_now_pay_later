"""Validacion post-pipeline BNPL: extraccion, volumen, integridad y permisos.

    python validar_bnpl.py      despues de main.py; sale con codigo 1 si hay hallazgos

No repite lo que el pipeline ya calcula: lee lo que dejo en bnpl_ops (source_freshness,
etl_runs, data_quality_checks) y le agrega las dos cosas que nadie comprueba hoy.

La primera son los permisos de pbi_gateway, y no se conforma con has_table_privilege: abre una
conexion COMO pbi_gateway y planea cada vista. Un GRANT SELECT correcto no basta si a la vista le
falta USAGE sobre el schema de una funcion que llama -- PostgreSQL cobra las funciones al que
consulta, no al dueno de la vista (CREATE VIEW, seccion Notes) -- y eso solo sale conectandose de
verdad. Es el `42501: permission denied for schema bnpl` del 2026-08-14.

La segunda es el inventario: objetos vivos en la base que ningun archivo del repo produce. Ahi
aparecio pbi_bnpl.concurso_base_liquidado, creada a mano el 2026-08-19, que el CASCADE del
siguiente build habria borrado sin recrear.

Reemplaza a diag_conn.py, diag_fresh.py y refrescar_vistas.py: el refresco ya lo hace
build_bnpl.py en el paso [4/6] de main.py, y los diagnosticos sueltos son un subconjunto de esto.
"""
import sys
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
from postgres_local_client import extract_sql as q

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

DB_OPS = "bnpl_ops"
DB_BNPL = "bnpl"
ROL = "pbi_gateway"

# Los dos objetos de `bnpl` que el modelo del concurso lee sin pasar por pbi_bnpl.
# Misma lista que la constante `directos` de sql/16_pbi_grants.sql.
DIRECTOS = ["bnpl.bnpl_clientes_concurso", "bnpl.dim_ruta_actual"]

# Schemas que pbi_gateway DEBE alcanzar. El resto tiene que estar denegado: las vistas leen sus
# tablas con los privilegios del dueno, asi que un USAGE de mas seria acceso que nadie necesita.
SCHEMAS_REQUERIDOS = ["pbi_bnpl", "bnpl"]
SCHEMAS_VEDADOS = ["archivos_bnpl", "mongo_bnpl", "redshift_bnpl"]

fallos = []


def titulo(t):
    print(f"\n{'=' * 78}\n  {t}\n{'=' * 78}")


def marca(ok):
    return "  ok " if ok else "FALLA"


def _int(v):
    """None y el NaN con que pandas representa un NULL numerico son lo mismo aqui."""
    return None if v is None or pd.isna(v) else int(v)


# ── A. Extraccion ─────────────────────────────────────────────────────────────
def extraccion():
    titulo("A. EXTRACCION — Mongo contra staging")
    df = q("""
        SELECT coleccion, docs_mongo, docs_staging, docs_faltantes,
               last_write_mongo, semaforo_fuente, semaforo_staging, checked_at
        FROM bnpl_ops.source_freshness ORDER BY coleccion
    """, db=DB_OPS)
    print(f"{'coleccion':<45}{'mongo':>11}{'staging':>11}{'falta':>8}"
          f"{'fuente':>8}{'staging':>9}")
    for _, r in df.iterrows():
        if r["semaforo_staging"] in ("CRIT", "FALTA"):
            fallos.append(f"staging desincronizado: {r['coleccion']} "
                          f"({r['docs_faltantes']:,} docs de diferencia)")
        print(f"{r['coleccion']:<45}{r['docs_mongo']:>11,}{r['docs_staging']:>11,}"
              f"{r['docs_faltantes']:>8,}{r['semaforo_fuente']:>8}"
              f"{r['semaforo_staging']:>9}")
    print(f"\n  medido el {df['checked_at'].max()}")


# ── B. Volumen e inventario ───────────────────────────────────────────────────
def volumen():
    titulo("B. VOLUMEN — filas cargadas en la ultima corrida")
    df = q("""
        WITH ultima AS (SELECT max(started_at) AS t FROM bnpl_ops.etl_runs
                        WHERE tabla = 'pipeline')
        SELECT tabla, modo, filas, segundos
        FROM bnpl_ops.etl_runs
        WHERE started_at >= (SELECT t FROM ultima)
        ORDER BY tabla
    """, db=DB_OPS)
    if df.empty:
        fallos.append("etl_runs no registro nada en la ultima corrida")
        print("  sin registros")
        return
    print(f"{'objeto':<48}{'modo':>10}{'filas':>13}{'seg':>8}")
    for _, r in df.iterrows():
        n = _int(r["filas"])
        print(f"{r['tabla']:<48}{r['modo']:>10}{(f'{n:,}' if n is not None else '-'):>13}"
              f"{r['segundos']:>8}")
        if n == 0:
            fallos.append(f"{r['tabla']} quedo en 0 filas")


def inventario():
    titulo("B2. INVENTARIO — la base contra lo que el repo produce")
    import build_bnpl

    esperadas = {f.stem.split("_", 1)[1]
                 for f in (BASE_DIR / "sql" / "pbi").glob("[0-8][0-9]_*.sql")}
    vivas = set(q("""SELECT table_name FROM information_schema.views
                     WHERE table_schema = 'pbi_bnpl'""", db=DB_BNPL)["table_name"])
    print(f"  vistas pbi_bnpl: {len(vivas)} en la base, {len(esperadas)} con archivo en sql/pbi/")

    if esperadas - vivas:
        fallos.append(f"vistas con .sql que no existen en la base (fallo su CREATE): "
                      f"{', '.join(sorted(esperadas - vivas))}")
        print(f"    FALTAN en la base: {', '.join(sorted(esperadas - vivas))}")

    # Huerfanas: vivas en la base, sin archivo que las produzca. No es cosmetico.
    # _construir_vistas_pbi() dropea con CASCADE, asi que una huerfana que cuelgue de una vista
    # gestionada se borra sola en la proxima corrida y nadie la recrea; y si no cuelga de ninguna,
    # sobrevive congelada mientras el resto se actualiza. En los dos casos el tablero lee algo que
    # el pipeline no sabe que existe.
    if vivas - esperadas:
        fallos.append(f"vistas en pbi_bnpl sin archivo en sql/pbi/ (fuera del pipeline): "
                      f"{', '.join(sorted(vivas - esperadas))}")
        print(f"    HUERFANAS (sin .sql): {', '.join(sorted(vivas - esperadas))}")

    en_capas = {v for v, _ in build_bnpl.CAPAS if v}
    mvs = set(q("SELECT matviewname FROM pg_matviews WHERE schemaname = 'bnpl'",
                db=DB_BNPL)["matviewname"])
    print(f"  materializadas bnpl: {len(mvs)} en la base, {len(en_capas)} en build_bnpl.CAPAS")
    if mvs - en_capas:
        fallos.append(f"materializadas en bnpl fuera de CAPAS (nadie las refresca): "
                      f"{', '.join(sorted(mvs - en_capas))}")
        print(f"    SIN REFRESCO: {', '.join(sorted(mvs - en_capas))}")
    if en_capas - mvs:
        fallos.append(f"vistas de CAPAS que no existen en la base: "
                      f"{', '.join(sorted(en_capas - mvs))}")
        print(f"    DECLARADAS PERO AUSENTES: {', '.join(sorted(en_capas - mvs))}")

    print(f"\n{'objeto':<52}{'filas':>14}")
    objetos = q("""
        SELECT table_schema || '.' || table_name AS obj
        FROM information_schema.views WHERE table_schema = 'pbi_bnpl'
        UNION ALL SELECT 'bnpl.' || matviewname FROM pg_matviews WHERE schemaname = 'bnpl'
        UNION ALL SELECT 'bnpl.bnpl_clientes_concurso'
        ORDER BY 1
    """, db=DB_BNPL)["obj"].tolist()
    for o in objetos:
        try:
            n = int(q(f"SELECT count(*) AS n FROM {o}", db=DB_BNPL)["n"].iloc[0])
            print(f"{o:<52}{n:>14,}")
            if n == 0:
                fallos.append(f"{o} esta vacia")
        except Exception as e:
            fallos.append(f"{o} no se pudo contar: {str(e).splitlines()[0][:120]}")
            print(f"{o:<52}{'ERROR':>14}  {str(e).splitlines()[0][:70]}")


# ── C. Integridad ─────────────────────────────────────────────────────────────
def integridad():
    titulo("C. INTEGRIDAD — chequeos de calidad e identidades entre capas")
    df = q("""
        SELECT check_name, n_filas, severidad, resultado, detalle
        FROM bnpl_ops.data_quality_checks
        WHERE checked_at = (SELECT max(checked_at) FROM bnpl_ops.data_quality_checks)
        ORDER BY CASE resultado WHEN 'OK' THEN 3 ELSE 1 END,
                 CASE severidad WHEN 'CRIT' THEN 1 ELSE 2 END, check_name
    """, db=DB_OPS)
    print(f"{'check':<46}{'filas':>12}{'resultado':>14}{'sev':>6}")
    for _, r in df.iterrows():
        n = _int(r["n_filas"])
        print(f"{r['check_name']:<46}{(f'{n:,}' if n is not None else '-'):>12}"
              f"{r['resultado']:>14}{r['severidad']:>6}")
        if r["resultado"] != "OK" and r["severidad"] == "CRIT":
            fallos.append(f"integridad CRIT: {r['check_name']} — {r['detalle']}")
    print(f"\n  {(df['resultado'] == 'OK').sum()} de {len(df)} en OK")


# ── D. Permisos ───────────────────────────────────────────────────────────────
def _url_pbi():
    """URL del rol pbi_gateway, del .env del proyecto."""
    for linea in (BASE_DIR / ".env").read_text(encoding="utf-8").splitlines():
        if linea.strip().startswith("BD_ENGINE_RABBIT_LOCAL_PBI"):
            return linea.split("=", 1)[1].strip().strip("'\"")
    return None


def permisos():
    titulo(f"D. PERMISOS — {ROL}")

    if q(f"SELECT count(*) AS n FROM pg_roles WHERE rolname = '{ROL}'",
         db=DB_BNPL)["n"].iloc[0] == 0:
        fallos.append(f"el rol {ROL} no existe en esta base")
        print(f"  el rol {ROL} no existe")
        return

    print("\n  D1. Catalogo\n")
    todos = SCHEMAS_REQUERIDOS + SCHEMAS_VEDADOS
    sch = dict(zip(*q(f"""
        SELECT nspname, has_schema_privilege('{ROL}', nspname, 'USAGE') AS usage
        FROM pg_namespace WHERE nspname IN ({','.join("'" + s + "'" for s in todos)})
    """, db=DB_BNPL).values.T))
    for s in SCHEMAS_REQUERIDOS:
        if not sch.get(s):
            fallos.append(f"{ROL} no tiene USAGE sobre {s}")
        print(f"    {marca(sch.get(s))}  USAGE {s:<16} (requerido)")
    for s in SCHEMAS_VEDADOS:
        # Denegado es lo correcto: las vistas leen esas tablas con los privilegios del dueno.
        print(f"    {marca(not sch.get(s))}  USAGE {s:<16} "
              f"({'denegado, correcto' if not sch.get(s) else 'CONCEDIDO DE MAS'})")
        if sch.get(s):
            fallos.append(f"{ROL} tiene USAGE de mas sobre {s}")

    objetos = q(f"""
        SELECT table_schema || '.' || table_name AS obj,
               has_table_privilege('{ROL}', table_schema || '.' || table_name, 'SELECT') AS sel
        FROM information_schema.views WHERE table_schema = 'pbi_bnpl'
        UNION ALL
        SELECT c, has_table_privilege('{ROL}', c, 'SELECT')
        FROM unnest(ARRAY[{','.join("'" + o + "'" for o in DIRECTOS)}]) AS c
        ORDER BY 1
    """, db=DB_BNPL)
    print()
    for _, r in objetos.iterrows():
        if not r["sel"]:
            fallos.append(f"{ROL} SIN SELECT sobre {r['obj']}")
        print(f"    {marca(r['sel'])}  SELECT {r['obj']}")

    # D2. La prueba real: conectarse como el rol y planear cada vista. Es lo que hace el gateway
    # al refrescar, y es lo unico que detecta un USAGE faltante sobre el schema de una funcion:
    # has_table_privilege dice que si y el refresh muere igual.
    url = _url_pbi()
    if not url:
        fallos.append("no encontre BD_ENGINE_RABBIT_LOCAL_PBI en .env: D2 no se pudo correr")
        print("\n  D2. omitida: falta BD_ENGINE_RABBIT_LOCAL_PBI en .env")
        return

    print(f"\n  D2. Conectado COMO {ROL}: planeando cada vista (lo que hace el gateway)\n")
    eng = sa.create_engine(url)
    try:
        with eng.connect() as c:
            print(f"    current_user = {c.execute(sa.text('SELECT current_user')).scalar()}\n")
            for o in list(objetos["obj"]):
                try:
                    c.execute(sa.text(f"EXPLAIN SELECT * FROM {o}"))
                    print(f"    {marca(True)}  plan  {o}")
                except Exception as e:
                    msg = str(e.__cause__ or e).splitlines()[0][:110]
                    fallos.append(f"{ROL} no puede leer {o}: {msg}")
                    print(f"    {marca(False)}  plan  {o}\n            -> {msg}")

            # El concurso aparte y de verdad, no solo planeado: es el que se rompio el
            # 2026-08-14 y el unico que lee objetos fuera de pbi_bnpl.
            print()
            for o in ["pbi_bnpl.concurso_base", "pbi_bnpl.concurso_clientes",
                      "pbi_bnpl.concurso_base_liquidado"] + DIRECTOS:
                try:
                    n = c.execute(sa.text(f"SELECT count(*) FROM {o}")).scalar()
                    print(f"    {marca(True)}  SELECT real  {o:<40}{n:>12,} filas")
                    if n == 0:
                        fallos.append(f"{o} devuelve 0 filas para {ROL}")
                except Exception as e:
                    msg = str(e.__cause__ or e).splitlines()[0][:110]
                    fallos.append(f"{ROL} no puede leer {o}: {msg}")
                    print(f"    {marca(False)}  SELECT real  {o}\n            -> {msg}")
    finally:
        eng.dispose()


if __name__ == "__main__":
    for f in (extraccion, volumen, inventario, integridad, permisos):
        try:
            f()
        except Exception as e:
            fallos.append(f"la seccion {f.__name__} reviento: {str(e).splitlines()[0][:150]}")
            print(f"\n  ERROR en {f.__name__}: {str(e).splitlines()[0][:150]}")

    titulo("RESUMEN")
    if not fallos:
        print("  Sin hallazgos. Extraccion, volumen, integridad y permisos en orden.")
    else:
        print(f"  {len(fallos)} hallazgo(s):\n")
        for i, f in enumerate(fallos, 1):
            print(f"   {i:>2}. {f}")
    sys.exit(1 if fallos else 0)

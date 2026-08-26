# Plan técnico BNPL — lo que se arregla sin preguntarle a nadie

> ## Convención de nombres del PBIP
>
> | Carpeta | Estado | Qué es |
> |---|---|---|
> | **`pbi_new/`** | **PRODUCTIVO** | El modelo publicado. Sus 17 tablas leen de `pbi_bnpl` y refresca desde el Service por `Gateway_BI`. **Es el único que se toca y el único que se publica.** |
> | **`pbi/`** | **DEPRECADO** | El modelo viejo, con 18 orígenes de archivo (`Csv.Document` contra un disco local y `SharePoint.Files` contra un OneDrive personal). No se refresca por gateway. **No se abre ni se publica.** |
>
> Las dos carpetas comparten el mismo `reportId` (`d36d2832-…`) y el mismo `datasetId` (`a9b8b79d-…`),
> así que **abrir el `.pbip` de `pbi/` y darle Publicar sobrescribe el artefacto productivo** con el
> modelo de archivos, y el gateway lo seguiría refrescando sin avisar. Ése es el riesgo que cierra O0.2.
>
> Cuando en este documento se lee «el modelo», «el productivo» o una ruta `…\Buy Now Pay Later.…`
> sin prefijo, es **`pbi_new/`**.

Derivado de [AUDITORIA.md](AUDITORIA.md), 2026-08-14. **68 acciones, nueve a diez jornadas.**
De ellas, **36 son de minutos**: se pueden ir cerrando entre cosas.

## Revisión del 2026-08-14, 16:47 — qué cambió desde la auditoría

Se volvió a verificar contra el árbol y la VM. **Las 68 acciones siguen vigentes**; lo que cerró
fueron tres hallazgos de la auditoría que ya no necesitan acción, y una afirmación quedó refutada.

### Cerrado y verificado

| Hallazgo | Estado hoy | Evidencia |
|---|---|---|
| **A3** · el pipeline nunca corrió programado | **Cerrado.** Existe `\BNPL Pipeline`, `Enabled`, disparador `13:30` UTC = **07:30 CDMX**, corre como `Administrator` con `LogonType S4U` y `RunLevel Highest` | `Get-ScheduledTaskInfo`: `LastTaskResult 0`, `NextRunTime 2026-08-15 13:30` |
| **A3b** · la ruta desatendida nunca se probó | **Cerrado.** Dos corridas reales por `run_pipeline.bat`: 07:28 (manual) y 13:30 (programada), las dos «terminado correctamente», 20.9 y 22.2 min | `logs/scheduler.log`, que antes no existía |
| **A14** · el paso 3 nunca corrió con sus seis tablas | **Cerrado.** Las seis salen en las dos corridas: `estructura_comercial` 611,315 · `route_mapping` 340 · `ruta_cliente_scd` 13,897 · `ventas_cliente` 1,295,091 · `cosechas_agg` 51,737 · `estacionalidad_mes` 12 | `logs/scheduler.log` |
| **D4 (parcial)** · `plan_implementacion.md` desfasado | **La hora quedó corregida** y razonada (07:30 CDMX contra refresh 08:30 = 40 min de margen) | commit `57b1c87` |

### Cambió de severidad

- **C16 / O2.14** (`print()` en vez de `logging`) baja de *bajo* a **cosmético**. El detalle por tabla
  ya no se pierde: `run_pipeline.bat` redirige stdout y queda completo en `logs/scheduler.log`. Sigue
  sin estar en `pipeline_YYYY-MM.log`, que es lo único que queda del hallazgo.
- **A5 / O2.6-O2.7** (duplicados sin dedup) sigue siendo riesgo **latente, no activo**: en las dos
  corridas de hoy `approval_netsuite_id_duplicado` = 0 y `aprobados_sin_customer` = 0.
- **B1** (el aprobado sin ficha desaparece del grid) sigue siendo **estructural**, pero hoy no está
  mordiendo: `aprobados_sin_customer` = 0.

### Refutado

- **C10** · «`expressions.tmdl` de `pbi_new` es byte a byte idéntico al de `pbi/`, con 8 `Csv.Document`
  y 4 `SharePoint.Files`». **Falso hoy.** El de `pbi_new/` tiene 69 líneas y **cero** de ambos: sólo
  quedan tres consultas huérfanas `Errores en…` de 2024. El de `pbi/` sí conserva los 8 y los 4.
  La limpieza ya está registrada en `PENDIENTES_NEGOCIO.md` como hecha el 2026-08-14.
  **O3.1 se mantiene** pero con el alcance reducido que ya trae escrito: borrar tres consultas muertas.

### Y esto sube la prioridad de la Ola 1

`README.md:35` ahora declara la **Fase 7 lista**: *«Power BI Service + Gateway — refresh desde el
Service por `Gateway_BI`»*. O sea que el modelo **ya está publicado y refrescando solo**. Eso cambia
dos cosas:

1. Los tres defectos de la Ola 1 que viven en el modelo —`bnplMinimumTenure` sin guardia de blanco,
   y las dos relaciones que la migración perdió— **están en producción ahora mismo**, refrescándose
   todos los días, no esperando a que alguien publique.
2. El choque de `reportId`/`datasetId` entre `pbi/` y `pbi_new/` (O0.2) pasa de riesgo latente a
   riesgo **activo**: hay un artefacto productivo vivo que una publicación equivocada sobrescribe,
   y el gateway seguiría refrescándolo sin avisar que ahora lee de archivos CSV locales.

### Lo que se re-verificó y sigue igual

`.pbi/cache.abf` sin ignorar · `pbi/` y `pbi_new/` conviviendo con sus dos `.pbix` (122 MB y 144 MB) ·
706 archivos sin rastrear · `master` ahead 3 sin empujar · `README.md:819` sigue afirmando que las
carpetas del PBIP se versionan · `bnplMinimumTenure` sin guardia · `with_lead → grid_bnpl` ausente ·
`TODAY() - 115` en siete columnas · `concurso_base` sin leer `clientes_concurso` · `14_archivos_bnpl.sql`
fuera de `CAPAS` · sin `requirements.txt` · sin notificación · sin respaldo · el markup de herramienta
al final de los dos README · la tabla partida de `PENDIENTES:1067` · el conteo de páginas en 14/11 ·
`plan_implementacion.md:22` todavía dice «No hay repo git» y la Fase 6 sigue sin marcar.

---

Cada acción trae el código de hoy, el código que queda y el comando para comprobarlo. Todas se
especificaron leyendo el archivo real y se revisaron contra él: donde el revisor encontró una cita
inexacta o un efecto colateral, queda anotado como *Ajuste del revisor*.

Lo que **no** está aquí es lo que depende de que Finanzas, Riesgo, Comercial o Ingeniería contesten:
eso va a `PENDIENTES_NEGOCIO.md` y está listado al final. Cuando de un pendiente de negocio se puede
hacer ya la mitad técnica —renombrar un visual sin tocar su fórmula, medir un escenario, dejar algo
escrito— esa mitad sí aparece como acción, marcada.

**Dos reglas de orden que evitan retrabajo:**

1. Las ediciones de un mismo `.md` se aplican **de abajo hacia arriba**, y localizando el texto, no la
   línea: el README creció ~700 líneas sin commitear, así que los números de línea de la auditoría y los
   del archivo de hoy no coinciden.
2. La Ola 0 va completa antes que nada. No por importancia: porque sin repo, ningún cambio de las otras
   olas es revisable ni recuperable.

---

## OLA 0 — Git y consolidación del PBIP

Desbloquea todo lo demás. Hoy el tablero entero vive fuera de control de versiones y las dos copias del modelo comparten `reportId`: publicar la equivocada sobrescribe producción. **Riesgo de no hacerlo: si se pierde la VM se pierde el tablero.** Esfuerzo ≈ 1 jornada.

### O0.1 · Blindar .gitignore contra .pbi/ ANTES de cualquier git add: cache.abf pesa 142 MB y hoy no esta ignorado

`.gitignore:11-27` · sin riesgo · minutos

`git check-ignore -v "pbi_new/Buy Now Pay Later.SemanticModel/.pbi/cache.abf"` sale sin match: el archivo NO esta ignorado y pesa 142,021,062 bytes (el de pbi/ pesa 123,449,660). El remoto es GitHub (https://github.com/russellquiroz-spec/buy_now_pay_later.git), que rechaza en duro cualquier archivo de mas de 100 MB. Es decir: `git add pbi_new/` seguido de `git push` no falla al agregar — falla al empujar, con el commit ya hecho y un objeto de 135 MiB atorado en el historial que hay que sacar con filter-repo. Esto no aparece en AUDITORIA.md y es el verdadero desbloqueante del paquete: sin este cambio, todo lo demas se cae en el ultimo paso.

**Hoy:**

```
# Datos y salidas (el respaldo primario vive en OneDrive, no en el repo)
data/
logs/
analisis_one_shot/output/
analisis_one_shot/output_v1/
*.csv
*.xlsx
*.parquet
*.pbix

# Notebooks legacy: contienen credenciales en texto plano
legacy/
.ipynb_checkpoints/

# Derivados del generador de ayuda del tablero (se regeneran)
ayuda_tablero/_datos/
```

**Queda:**

```
# Datos y salidas (el respaldo primario vive en OneDrive, no en el repo)
data/
logs/
analisis_one_shot/output/
analisis_one_shot/output_v1/
*.csv
*.xlsx
*.parquet
*.pbix

# Notebooks legacy: contienen credenciales en texto plano
legacy/
.ipynb_checkpoints/

# Derivados del generador de ayuda del tablero (se regeneran)
ayuda_tablero/_datos/

# Estado local del PBIP: NADA de .pbi/ se versiona.
#  - cache.abf: 135 MiB del modelo cargado. GitHub rechaza cualquier blob > 100 MB.
#  - localSettings.json: reportId/datasetId del artefacto PRODUCTIVO + firma DPAPI
#    atada a esta maquina y usuario. Versionarlo es como cualquiera que clone
#    publica encima de produccion sin darse cuenta.
#  - editorSettings.json: preferencias del Desktop de quien abrio el archivo.
.pbi/
*.abf
```

**Verificar:**

```
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later; git check-ignore -v "pbi_new/Buy Now Pay Later.SemanticModel/.pbi/cache.abf"; git check-ignore -v "pbi_new/Buy Now Pay Later.Report/.pbi/localSettings.json"   # ambos deben imprimir '.gitignore:NN:.pbi/'
```

> **Nota.** Verificado en disco hoy: los cuatro localSettings.json existen y los dos de .Report/ traen el MISMO reportId d36d2832-baa9-4d61-a031-b303715a6480, y los dos de .SemanticModel/ el MISMO datasetId a9b8b79d-6049-4e42-b331-ec69ac184a40. Confirmado el hallazgo. Ignorar `.pbi/` cierra el riesgo de raiz: el PBIP se re-vincula solo la primera vez que alguien lo publica.

### O0.2 · Sacar `pbi/` del repo como deprecado. `pbi_new/` se queda con su nombre: es el productivo

`pbi/, pbi_new/ (raiz del repo)` · riesgo medio · ~1 h · depende de: O0.1 (el .gitignore ya tiene que traer `.pbi/` y `*.abf`, o el `git add` posterior arrastra el cache)

> **Corregido el 2026-08-14.** La versión anterior de esta acción hacía `Rename-Item "pbi_new" "pbi"`,
> siguiendo el «hay que consolidar» de `README.md:610`. **Se canceló el renombre**: la convención del
> equipo es que `pbi/` está **deprecado** y `pbi_new/` es el **productivo**, y renombrar invertía
> justamente eso. Sólo sale `pbi/`; `pbi_new/` no se toca.
>
> Efecto secundario bueno: **O0.3 deja de ser necesaria.** `ayuda_tablero/inventario.py:7` y
> `portada.py:8` ya apuntan a `pbi_new`, que bajo esta convención es lo correcto.

Los dos .pbip apuntan al mismo reportId y al mismo datasetId: mientras existan las dos carpetas, abrir la equivocada y darle Publicar sobrescribe el artefacto productivo con el modelo de origenes CSV, que ademas ya no se puede refrescar por gateway. Los .pbix se borran porque (a) estan gitignoreados, o sea nunca viajan y solo existen para confundir; (b) el de pbi_new es de las 01:49 y su model.tmdl de las 06:58 — 5h09m de rezago, y segun README:588 todavia trae las consultas auxiliares que bloquean el refresh: quien lo abra y publique rompe produccion. Se publica el .pbip. Si algun dia hace falta un .pbix, se abre pbi\Buy Now Pay Later.pbip en Desktop y Archivo > Guardar como. El cache.abf (265 MB entre los dos) se regenera solo al abrir el .pbip; el costo es una carga completa desde PostgreSQL (~32 s de lectura + carga del modelo, README:683).

**Hoy:**

```
(estado en disco, no es codigo)
pbi/     334 archivos, incl. 'Buy Now Pay Later.pbix' 116.6 MiB (2026-08-14 01:56) y .pbi/cache.abf 117.7 MiB
pbi_new/ 335 archivos, incl. 'Buy Now Pay Later.pbix' 137.9 MiB (2026-08-14 01:49) y .pbi/cache.abf 135.4 MiB
pbi/...\definition\model.tmdl      2026-08-14 03:37
pbi_new/...\definition\model.tmdl  2026-08-14 06:58
```

**Queda:**

```
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later

# 1) El modelo DEPRECADO sale del repo. NO se borra todavia: es la unica copia de las dos
#    relaciones que la migracion perdio (O1.4 y O1.5).
Move-Item "pbi" "..\_deprecado_pbi_origenes_csv_2026-08-14"

# 2) pbi_new/ NO se toca: conserva su nombre y es el productivo.
#    (Aqui iba un Rename-Item que se cancelo: ver la nota de arriba.)

# 3) Estado local del productivo, que no debe viajar ni ocupar disco
Remove-Item "pbi_new\Buy Now Pay Later.SemanticModel\.pbi\cache.abf" -Force
Remove-Item "pbi_new\Buy Now Pay Later.pbix" -Force

# 3b) El deprecado pierde TODO su .pbi/: comparte reportId d36d2832-... y datasetId
#     a9b8b79d-... con el productivo. Si se queda, abrir ese .pbip y publicar
#     sobrescribe produccion con el modelo de origenes CSV.
Remove-Item "..\_deprecado_pbi_origenes_csv_2026-08-14\Buy Now Pay Later.pbix" -Force
Remove-Item "..\_deprecado_pbi_origenes_csv_2026-08-14\Buy Now Pay Later.Report\.pbi" -Recurse -Force
Remove-Item "..\_deprecado_pbi_origenes_csv_2026-08-14\Buy Now Pay Later.SemanticModel\.pbi" -Recurse -Force
Rename-Item "..\_deprecado_pbi_origenes_csv_2026-08-14\Buy Now Pay Later.pbip" "NO_PUBLICAR_Buy Now Pay Later.pbip.bak"

# 4) Comprobar que no quedo un solo origen de archivo en el productivo
Get-ChildItem "pbi_new\Buy Now Pay Later.SemanticModel" -Recurse -Include *.tmdl,*.json -Force |
  Select-String -Pattern "Csv\.Document|SharePoint\.Files|File\.Contents|excludeFromModelRefresh"
```

**Verificar:**

```
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later
Test-Path pbi        # False: el deprecado ya no esta en el repo
Test-Path pbi_new    # True: el productivo se queda con su nombre
Get-ChildItem pbi_new -Force | Select-Object Name   # solo .Report, .SemanticModel y el .pbip
Get-ChildItem pbi_new -Recurse -File -Force | Measure-Object Length -Sum | ForEach-Object { "{0:N1} MB" -f ($_.Sum/1MB) }   # ~5.7 MB
Get-ChildItem "..\_deprecado_pbi_origenes_csv_2026-08-14" -Recurse -Filter localSettings.json -Force   # sin resultados
```

> **Nota.** Decisión razonada sobre el deprecado: NO se borra ni se conserva dentro del repo. Se mueve fuera. Meterlo al repo aunque sea sin `localSettings.json` agrega 332 archivos de un modelo muerto y duplica la superficie de revisión de cada diff futuro; borrarlo hoy tira la única copia de `relationships.tmdl:169-171` (`bnpl_loss_rates_with_lead.netsuiteId -> grid_bnpl.netsuiteId`) y de la relación a `enrollment_dates`, que O1.4 y O1.5 mandan recrear. Fuera del repo cumple las dos cosas. Se puede borrar del disco después de que O1.4 y O1.5 aterricen. Verificado además que la medida `bnpl_cosechas_agg[bnplGrossReal]` (`:446`) tiene 0 referencias en los `.json` de ambos reportes: se puede perder sin consecuencia.

### ~~O0.3 · Quitar la ruta 'pbi_new' hardcodeada en los tres archivos de ayuda_tablero~~ — CANCELADA

`ayuda_tablero/inventario.py:7, portada.py:8, README.md:134` · sin riesgo · **sin trabajo**

> **Cancelada el 2026-08-14.** Esta acción existía sólo para acompañar el renombre `pbi_new/` → `pbi/`
> de O0.2. Como el renombre se canceló —`pbi_new/` conserva su nombre porque es el productivo—, los
> tres archivos **ya están correctos** y no hay nada que tocar:
>
> ```
> ayuda_tablero/inventario.py:7    PBIP = BASE_DIR / "pbi_new"          ✓ apunta al productivo
> ayuda_tablero/portada.py:8       RPT  = str(BASE_DIR / "pbi_new" / …) ✓ apunta al productivo
> ayuda_tablero/README.md:134      `pbi_new\…\pages\<página>\visuals\`   ✓ nombra al productivo
> ```
>
> **Verificar que sigue así:** `Select-String -Path ayuda_tablero\*.py -Pattern 'BASE_DIR / "pbi"'`
> debe salir vacío — si algún día aparece, alguien reintrodujo el renombre.
>
> El plan baja de 68 a **67 acciones**.

<details>
<summary>Contenido original de O0.3, por si algún día se decide consolidar el nombre</summary>

```
ayuda_tablero/inventario.py:7
    PBIP     = BASE_DIR / "pbi"

ayuda_tablero/portada.py:8
    RPT = str(BASE_DIR / "pbi" / "Buy Now Pay Later.Report" / "definition")

ayuda_tablero/README.md:134
      nombre de su carpeta en `pbi\Buy Now Pay Later.Report\definition\pages\<página>\visuals\`, y
```

**Verificar:**

```
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later; Select-String -Path ayuda_tablero\*.py,ayuda_tablero\*.md -Pattern "pbi_new"   # sin resultados
.venv\Scripts\python.exe ayuda_tablero\inventario.py   # debe regenerar ayuda_tablero\_datos\inventario.json
```

Nota del original: `inventario.py` deriva `MODEL` y `RPT` de `PBIP` (líneas 10-12), así que con cambiar
la línea 7 bastaría; `portada.py` sí tiene la ruta completa en la 8.

</details>

### O0.4a · Corregir la afirmacion falsa del README sobre que .Report/ y .SemanticModel/ sí se versionan

`README.md:737-738` · sin riesgo · minutos · depende de: Accion 6 (aplicar el texto ya, pero solo es cierto una vez commiteado el PBIP)

Hoy la frase esta escrita en presente y es falsa: `git ls-files pbi_new` no devuelve nada, los 333 archivos del PBIP estan sin rastrear. Despues de la accion 6 la primera mitad pasa a ser cierta, pero la frase sigue incompleta porque no dice que `.pbi/` queda fuera — que es justo el archivo que rompe el push. La redaccion nueva enuncia las dos exclusiones con su motivo, para que nadie lo 'arregle' quitando la regla del .gitignore.

**Hoy:**

```
Los `.pbix` **no se versionan** (`.gitignore`); sí se versionan el `.pbip` y las carpetas
`.Report/` / `.SemanticModel/`, que son texto y sí se pueden revisar en un diff.
```

**Queda:**

```
Del PBIP se versionan el `.pbip` y las carpetas `.Report/` / `.SemanticModel/`: son texto y sí se
pueden revisar en un diff. **No** se versionan el `.pbix` ni la carpeta `.pbi/`, y las dos razones
importan: `cache.abf` pesa ~135 MiB y GitHub rechaza en duro cualquier archivo de más de 100 MB, y
`localSettings.json` guarda el `reportId`/`datasetId` del artefacto **productivo** más una firma
atada a la máquina que lo abrió — versionarlo es lo que hace que un clon cualquiera pueda publicar
encima de producción sin enterarse.
```

**Verificar:**

```
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later; git ls-files pbi_new | Measure-Object -Line   # >0 despues de la accion 6, coherente con lo que afirma el README
Select-String -Path README.md -Pattern "sí se versionan el ``.pbip``"
```

> **Ajuste del revisor.** archivo: README.md:769-770

verificacion:
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later; git ls-files pbi_new | Measure-Object -Line   # >0 despues de la accion 6, coherente con lo que afirma el README
Select-String -Path README.md -Pattern 'No\*\* se versionan el `\.pbix` ni la carpeta `\.pbi/`'   # 1 resultado: la redaccion nueva
Select-String -Path README.md -Pattern 'Los `\.pbix` \*\*no se versionan\*\* \(`\.gitignore`\)'      # 0 resultados: la vieja ya no esta

> **Nota.** El hallazgo apunta a README.md:702-703; en la copia de trabajo de hoy el bloque esta en 737-738 (el README creció +700 líneas sin commitear). El texto citado es literal del archivo actual. Aplicar las ediciones del README de abajo hacia arriba (737, luego 728, luego 576) para que los numeros de linea no se corran.

### O0.4b · Reescribir la seccion 'Power BI' del README: ya no hay dos carpetas ni .pbix en el repo

`README.md:576-589` · sin riesgo · minutos · depende de: Accion 2

Despues de la accion 2 la tabla de dos carpetas describe un estado que ya no existe, y lo peligroso es que le dice a quien llegue que 'hay que consolidar' cuando ya se consolido — la unica forma de volver a tener dos copias es que alguien siga esta instruccion. Ademas el texto actual nunca dice POR QUE importaba (mismo reportId/datasetId), que es el dato que evita que alguien recupere el respaldo y lo meta de vuelta al repo.

**Hoy:**

```
El modelo vive en `pbi/`. Hoy hay **dos copias** y no son la misma:

| Carpeta | Estado |
|---|---|
| `pbi/` | modelo **original**: los 18 orígenes son archivos (15 CSV en el disco local de una persona, 2 en su OneDrive, 1 consulta muerta `Consulta1`) |
| `pbi_new/` | modelo **migrado**: las 17 tablas leen de `pbi_bnpl`, sin un solo `Csv.Document`, sin `Table.TransformColumnTypes`, sin `excludeFromModelRefresh` y sin `Consulta1` |

`pbi_new/` es el bueno y **es el que está publicado**. **Hay que consolidar**: renombrarlo a `pbi/` y
borrar el original, o quedará la duda de cuál se publica — y ahora eso importa más, porque el original
no se puede refrescar por gateway. (`concurso_base` no está en ninguno de los dos: es un tablero
aparte, todavía sin construir.)

**Se publica el `.pbip`, no el `.pbix`.** El `.pbix` de `pbi_new/` quedó congelado antes de la limpieza
del 2026-08-14 y todavía trae las consultas auxiliares que bloquean el refresh.
```

**Queda:**

```
El modelo productivo es **`pbi_new/`**, y es el que está publicado: sus 17 tablas leen de `pbi_bnpl`,
sin un solo `Csv.Document`, sin `SharePoint.Files`, sin `Table.TransformColumnTypes`, sin
`excludeFromModelRefresh` y sin `Consulta1`. Refresca desde el Service por `Gateway_BI`.
(`concurso_base` no está en el modelo: es un tablero aparte, todavía sin construir.)

**`pbi/` está deprecado** y desde el 2026-08-14 ya no vive en el repo: es el modelo viejo, con 18
orígenes de archivo (`Csv.Document` contra un disco local y `SharePoint.Files` contra un OneDrive
personal), y no se puede refrescar por gateway. Quedó fuera, en
`..\_deprecado_pbi_origenes_csv_2026-08-14`, para una sola cosa: recuperar las dos relaciones que la
migración perdió. Cuando eso esté hecho, se borra.

**No se abre ni se publica el deprecado.** Las dos carpetas comparten el mismo `reportId` y el mismo
`datasetId`, así que abrir su `.pbip` y darle Publicar sobrescribe el artefacto productivo con el
modelo de archivos — y el gateway lo seguiría refrescando sin avisar. Por eso al deprecado se le
quitó su `.pbi/` y su `.pbip` quedó renombrado a `NO_PUBLICAR_…bak`.

**Se publica el `.pbip`, no el `.pbix`** — y ya no hay `.pbix` en el repo. El que había estaba 5 horas
rezagado de su propio TMDL y todavía traía las consultas auxiliares que bloquean el refresh, así que
abrirlo y publicarlo rompía producción. Si alguien necesita uno, abre el `.pbip` en Desktop y
*Archivo → Guardar como*.
```

**Verificar:**

```
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later
Select-String -Path README.md,sql\pbi\README.md -Pattern "renombrarlo a|Hay que consolidar"   # sin resultados
Select-String -Path README.md -Pattern "pbi_new"   # varias: es el nombre del productivo, debe aparecer
```

### O0.4c · Actualizar el arbol de estructura del README: marcar cuál es el productivo

`README.md:728-729` · sin riesgo · minutos · depende de: Accion 2

Es la unica otra parte del README que nombra pbi_new/ y que sigue anunciando la consolidacion como pendiente. Si se corrige la seccion de Power BI y no esta, el documento se contradice a si mismo dos paginas mas abajo.

**Hoy:**

```
pbi/                        Modelo original (orígenes CSV)
pbi_new/                    Modelo migrado a pbi_bnpl — el bueno; consolidar
```

**Queda:**

```
pbi_new/                    PRODUCTIVO. El PBIP publicado: .pbip + .Report/ + .SemanticModel/, sobre pbi_bnpl
                            (pbi/ era el modelo deprecado de orígenes CSV; salió del repo el 2026-08-14)
```

**Verificar:**

```
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later; Select-String -Path README.md -Pattern "^pbi"
```

> **Ajuste del revisor.** archivo: README.md:760-761

verificacion:
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later; (Select-String -Path README.md -Pattern "^pbi").Count   # 1 (hoy son 2)
Select-String -Path README.md -Pattern "^pbi_new"   # vacio

### O0.4d · Actualizar 'Estado de la migracion' en sql/pbi/README.md: ya esta consolidado y la verificacion cubre todo el SemanticModel

`sql/pbi/README.md:121-126` · sin riesgo · minutos · depende de: Accion 2

La afirmacion 'no queda un solo Csv.Document' era la que AUDITORIA:290 acusaba de falsa. Hoy es cierta, pero solo se puede sostener si se dice sobre que se verifico: el barrido que documentaba este mismo README miraba unicamente definition\tables\, y las consultas huerfanas viven en expressions.tmdl. Sin ese matiz, la frase vuelve a ser una promesa sin respaldo. Y 'Falta consolidar los dos directorios' queda obsoleto tras la accion 2.

**Hoy:**

```
### Estado de la migración

El modelo migrado es **`pbi_new/`** en la raíz del repo: sus 17 tablas leen de `pbi_bnpl`, no queda un
solo `Csv.Document`, ni `Table.TransformColumnTypes`, ni `excludeFromModelRefresh`, ni la consulta
muerta `Consulta1`. `pbi/` es el modelo original con orígenes de archivo. **Falta consolidar los dos
directorios en uno.**
```

**Queda:**

```
### Estado de la migración

El modelo **productivo** es **`pbi_new/`** en la raíz del repo: sus 17 tablas leen de `pbi_bnpl`, no
queda un solo `Csv.Document`, ni `SharePoint.Files`, ni `Table.TransformColumnTypes`, ni
`excludeFromModelRefresh`, ni la consulta muerta `Consulta1` — verificado sobre **todo** el
`.SemanticModel/`, no sólo sobre `definition\tables\` (ver [Pasos M que sobran](#2-pasos-m-que-sobran)).

**`pbi/` está deprecado**: es la copia con orígenes de archivo, no se refresca por gateway y **no se
abre ni se publica**. Salió del repo el 2026-08-14 a `..\_deprecado_pbi_origenes_csv_2026-08-14`, sin
su `.pbi/` y con el `.pbip` renombrado, para que nadie lo publique por error sobre el mismo `reportId`.
```

**Verificar:**

```
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later; Get-ChildItem "pbi\Buy Now Pay Later.SemanticModel" -Recurse -Include *.tmdl,*.json -Force | Select-String -Pattern "Csv\.Document|SharePoint\.Files|File\.Contents|excludeFromModelRefresh"   # vacio
```

> **Ajuste del revisor.** Ademas del reemplazo de :121-126 tal como esta propuesto, sustituir la linea 135:

  ANTES  **Se publica el `.pbip`, no el `.pbix`**: el `.pbix` de `pbi_new/` es anterior a esa limpieza.

  DESPUES  **Se publica el `.pbip`, no el `.pbix`** — y ya no hay `.pbix` en el repo: el que habia era
  anterior a esta limpieza y publicarlo la deshacia. Si hace falta uno, se abre el `.pbip` en Desktop y
  *Archivo -> Guardar como*.

verificacion:
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later; Get-ChildItem "pbi\Buy Now Pay Later.SemanticModel" -Recurse -Include *.tmdl,*.json -Force | Select-String -Pattern "Csv\.Document|SharePoint\.Files|File\.Contents|excludeFromModelRefresh"   # vacio
Select-String -Path sql\pbi\README.md -Pattern "pbi_new"   # vacio: ni en :121-126 ni en :135

> **Nota.** OJO: el hallazgo apunta a sql/pbi/README.md:122-124; el bloque real esta en 121-126 (encabezado incluido). Citado literal del archivo.

### O0.4e · Ampliar el comando de verificacion de sql/pbi/README.md para que barra todo el SemanticModel, no solo definition\tables

`sql/pbi/README.md:294-301` · sin riesgo · minutos · depende de: Accion 2 (para que la ruta pbi\ del comando sea la correcta)

Es el hueco que dejo pasar el problema real. El comando actual apunta a definition\tables (22 archivos) y el modelo tiene ademas expressions.tmdl, model.tmdl, relationships.tmdl, cultures\es-MX.tmdl y diagramLayout.json. Verificado hoy sobre pbi/: el barrido completo da 56 coincidencias solo en cultures\es-MX.tmdl y 16 en expressions.tmdl — cero de ellas visibles para el comando documentado. Sobre pbi_new/ el barrido completo da 0 (salvo un 'Consulta1' residual en diagramLayout.json, que es solo la posicion de un nodo en el diagrama y no ejecuta nada).

**Hoy:**

```
Para detectar los residuales en el modelo, sobre el `.SemanticModel/` descomprimido:

```powershell
Get-ChildItem "pbi_new\Buy Now Pay Later.SemanticModel\definition\tables" -Filter *.tmdl |
  Select-String -Pattern "TransformColumnTypes|RemoveColumns|Csv.Document|File.Contents"
```

Hoy no devuelve nada, y así debe quedarse.
```

**Queda:**

```
Para detectar los residuales en el modelo, sobre **todo** el `.SemanticModel/` — no sólo sobre
`definition\tables\`: las consultas huérfanas (las que no cargan ninguna tabla) viven en
`definition\expressions.tmdl`, y un barrido acotado a `tables\` nunca las ve. Es exactamente cómo
sobrevivieron 16 consultas auxiliares con `SharePoint.Files` a una OneDrive personal:

```powershell
Get-ChildItem "pbi\Buy Now Pay Later.SemanticModel" -Recurse -Include *.tmdl,*.json -Force |
  Select-String -Pattern "TransformColumnTypes|RemoveColumns|Csv\.Document|File\.Contents|SharePoint\.Files|excludeFromModelRefresh"
```

Hoy no devuelve nada, y así debe quedarse. Dos detalles del comando: el `-Recurse` es lo que lo lleva a
`expressions.tmdl` y a `cultures\`, y los puntos van escapados (`Csv\.Document`) porque `Select-String`
toma el patrón como regex — sin escapar, `Csv.Document` también casa con `CsvXDocument`.
```

**Verificar:**

```
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later; # pegar el comando nuevo tal cual: debe salir vacio sobre pbi/
Get-ChildItem "pbi\Buy Now Pay Later.SemanticModel" -Recurse -Include *.tmdl,*.json -Force | Select-String -Pattern "TransformColumnTypes|RemoveColumns|Csv\.Document|File\.Contents|SharePoint\.Files|excludeFromModelRefresh"
```

> **Nota.** El hallazgo apunta a sql/pbi/README.md:287-291; el bloque real esta en 294-301. En 286-289 hay una tabla distinta (los dos pasos M a borrar y el error que produce cada uno), que no hay que tocar.

### O0.4f · Borra el markup de herramienta pegado al final de README.md y sql/pbi/README.md

`README.md:756-757 y sql/pbi/README.md:472-473` · sin riesgo · minutos

Son etiquetas XML de la herramienta que generó el archivo; en cualquier visor de Markdown se ven como texto suelto al final del documento y delatan que el README no se revisó después de escribirlo.

**Hoy:**

```
README.md:755-757
- Las credenciales de los notebooks en `legacy/` estuvieron en texto plano en OneDrive. **Se deben
  considerar comprometidas y rotarse.**
</content>
</invoke>

sql/pbi/README.md:471-473
  `externalId` no se pueden derivar y ningún visual ni medida los usa. Están documentados en el
  encabezado de cada archivo.
</content>
</invoke>
```

**Queda:**

```
Borrar las dos últimas líneas de cada archivo. README.md debe terminar en:

- Las credenciales de los notebooks en `legacy/` estuvieron en texto plano en OneDrive. **Se deben
  considerar comprometidas y rotarse.**

y sql/pbi/README.md en:

  `externalId` no se pueden derivar y ningún visual ni medida los usa. Están documentados en el
  encabezado de cada archivo.
```

**Verificar:**

```
Select-String -Path .\README.md,.\sql\pbi\README.md -Pattern '</content>|</invoke>'   # cero resultados
```

> **Ajuste del revisor.** Anclajes reales:

- README.md: 816 líneas. Borrar :815 (`</content>`) y :816 (`</invoke>`). El archivo debe terminar en la línea 814, «  considerar comprometidas y rotarse.»
- sql/pbi/README.md: 473 líneas. Borrar :472 y :473. El archivo debe terminar en la línea 471, «  encabezado de cada archivo.»

El texto propuesto y la verificación quedan igual.

> **Nota.** Las líneas son las 756-757 y 472-473, no las 721-722 y 436-437 del informe: la auditoría contó líneas no vacías. El contenido del hallazgo es correcto.

### O0.5 · Commitear los 25 archivos ya modificados, en cuatro commits tematicos, antes de tocar nada nuevo

`raiz del repo (indice de git)` · riesgo bajo · media jornada · depende de: Accion 1 (el contenido del .gitignore) y Accion 7-11 si se quiere que README y sql/pbi/README ya salgan corregidos en el commit 4/4 — recomendado

Los 25 modificados no son un solo cambio: 18 son la sustitucion mecanica de postgres_local_extractor por postgres_local_client (verificado en el diff de analisis/tipos_actuales.py: cambia el import y agrega `db=DB`), 2 son la tabla nueva de venta Rabbit completa (+86 lineas en sql/12, +310 en etl_redshift), 2 son documentacion (+700 y +906 lineas) y 1 es el .gitignore. Mezclados en un commit, el diff de 2,181 inserciones es irrevisable y un revert del refactor se lleva la tabla nueva. Van antes que lo nuevo porque asi `git add` de las carpetas nuevas no puede arrastrar por accidente un archivo modificado.

**Hoy:**

```
$ git status --porcelain
 M .gitignore
 M PENDIENTES_NEGOCIO.md
 M README.md
 M analisis/*.py (10 archivos)
 M analisis_one_shot/*.py (3 archivos)
 M build_bnpl.py
 M etl_mongo_to_postgres.py
 M etl_redshift_to_postgres.py
 M main.py
 M migrar_a_vm.py
 M ops/*.py (3 archivos)
 M sql/12_redshift_staging.sql
$ git status -sb
## master...origin/master [ahead 2]
```

**Queda:**

```
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later

# --- 1/4: el blindaje del .gitignore va SOLO y va primero ---
git add .gitignore
git commit -m "chore(bnpl): no versiona .pbi/ del PBIP (cache.abf de 135 MiB y el reportId productivo)"

# --- 2/4: la migracion de libreria, que toca 18 scripts y no cambia comportamiento ---
git add analisis/ analisis_one_shot/ ops/ build_bnpl.py etl_mongo_to_postgres.py main.py migrar_a_vm.py
git commit -m "refactor(bnpl): migra los scripts de postgres_local_extractor a postgres_local_client con alias db= explicito"

# --- 3/4: la venta Rabbit completa (tabla nueva de Redshift), que sí cambia datos ---
git add etl_redshift_to_postgres.py sql/12_redshift_staging.sql
git commit -m "feat(bnpl): trae la venta Rabbit completa del universo BNPL a grano de sales order"

# --- 4/4: la documentacion, al final, para que el diff se lea contra el codigo ya commiteado ---
git add README.md PENDIENTES_NEGOCIO.md
git commit -m "docs(bnpl): actualiza README y PENDIENTES tras la migracion a la VM y el alta del gateway"
```

**Verificar:**

```
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later; git status --porcelain | Where-Object { $_ -match '^ ?M' }   # vacio
git log --oneline -4
```

> **Ajuste del revisor.** Cambiar el mensaje del commit 2/4 y anotar el alcance real en el 3/4:

# --- 2/4: la migracion de libreria, que toca 20 scripts y no cambia comportamiento ---
git add analisis/ analisis_one_shot/ ops/ build_bnpl.py etl_mongo_to_postgres.py main.py migrar_a_vm.py
git commit -m "refactor(bnpl): migra 20 scripts de postgres_local_extractor a postgres_local_client con alias db= explicito"

# --- 3/4: la venta Rabbit completa (tabla nueva de Redshift), que si cambia datos.
#     etl_redshift_to_postgres.py trae ademas su parte de la migracion a postgres_local_client. ---
git add etl_redshift_to_postgres.py sql/12_redshift_staging.sql
git commit -m @'
feat(bnpl): trae la venta Rabbit completa del universo BNPL a grano de sales order

Este archivo cierra ademas la migracion a postgres_local_client (alias
pg_execute_sql / pg_extract_sql / pg_transaction), que en el resto de los
scripts va en el commit anterior.
'@

> **Nota.** El diff de etl_redshift_to_postgres.py trae las dos cosas (imports de postgres_local_client Y las funciones nuevas _bloques_pedidos/_sql_cosechas). No se puede separar limpio sin `git add -p`; por eso va con sql/12 en el commit de la tabla nueva, que es el cambio dominante. Correr `git diff --stat` antes de empezar para confirmar que la lista no cambio.

### O0.6 · Commitear lo nuevo que NO es el modelo: sql/13-15, sql/pbi/, las dos cargas manuales, ayuda_tablero y la auditoria

`raiz del repo (indice de git)` · riesgo bajo · ~1 h · depende de: Accion 4

sql/pbi/ son las 18 consultas que build_bnpl.py convierte en las vistas de pbi_bnpl: si la VM se pierde, sin ellas no hay tablero que reconstruir, y hoy viven solo en el disco de una maquina. carga_archivos_bnpl.py y carga_clientes_concurso.py estan documentadas en README:711-712 como parte de la estructura del proyecto, pero no existen para git. ayuda_tablero/_datos/ ya esta cubierto por el .gitignore, asi que `git add ayuda_tablero/` mete los 11 fuentes y ninguno de los dos JSON derivados (747 KB y 134 KB). Se separan del PBIP porque son cambios de codigo revisables; el PBIP son 333 archivos generados por una herramienta y merece su propio commit.

**Hoy:**

```
$ git ls-files --others --exclude-standard | (agrupado por carpeta)
333  pbi_new
332  pbi
 24  sql        (sql/pbi/ = 21, sql/13-15 = 3)
 11  ayuda_tablero
  1  AUDITORIA.md
  1  carga_archivos_bnpl.py
  1  carga_clientes_concurso.py
  = 705 archivos sin rastrear
```

**Queda:**

```
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later

# --- 5: las 18 consultas que SON el tablero, mas el DDL que faltaba ---
git add sql/pbi/ sql/13_bnpl_clientes_concurso.sql sql/14_archivos_bnpl.sql sql/15_pbi_vistas.sql
git commit -m "feat(bnpl): versiona las 18 consultas de pbi_bnpl y el DDL de concurso, archivos y schema"

# --- 6: las dos cargas manuales ---
git add carga_archivos_bnpl.py carga_clientes_concurso.py
git commit -m "feat(bnpl): agrega las dos cargas manuales (4 CSV del Drive y el Excel del concurso)"

# --- 7: el generador de ayuda del tablero (sus _datos/ ya estan ignorados) ---
git add ayuda_tablero/
git commit -m "feat(bnpl): agrega el generador de ayuda del tablero (inventario, portada y tooltips)"

# --- 8: el informe de auditoria ---
git add AUDITORIA.md
git commit -m "docs(bnpl): agrega el informe de auditoria del 2026-08-14"
```

**Verificar:**

```
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later; git ls-files --others --exclude-standard | Measure-Object -Line   # debe bajar de 705 a 333 (solo el PBIP)
git ls-files ayuda_tablero | Measure-Object -Line   # 11, sin _datos/
```

> **Ajuste del revisor.** verificacion:
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later; git ls-files --others --exclude-standard | Measure-Object -Line   # 330: solo el PBIP, ya sin .pbi/ (ignorado en la accion 1) ni .pbix (borrado en la accion 2)
git ls-files ayuda_tablero | Measure-Object -Line   # 11, sin _datos/
git ls-files --others --exclude-standard | Select-String -Pattern "^\"?pbi/" -NotMatch   # vacio: no debe quedar nada fuera del PBIP

depende_de: Acciones 1, 2 y 4 (sin la 1 el .pbi/ sigue contando; sin la 2 quedan las dos carpetas de modelo y el residuo es 667, no 330)

> **Nota.** Los conteos de AUDITORIA.md:33 (704 sin rastrear, pbi_new 334 / pbi 333) estan uno arriba porque en ese momento AUDITORIA.md todavia no existia y porque el conteo por carpeta incluia el .pbix ya ignorado. Hoy git reporta 705 y 333/332. La conclusion no cambia.

### O0.7 · Commitear el PBIP consolidado y empujar los 2 commits rezagados junto con los 8 nuevos

`raiz del repo (indice de git)` · riesgo medio · ~1 h · depende de: Acciones 1, 2 y 5

master lleva `ahead 2` desde los dos fixes de hora Mexico: ese trabajo solo existe en esta maquina. Y el `git add --dry-run` filtrado es el ultimo seguro contra el cache.abf: si el .gitignore de la accion 1 no quedo bien, ese comando lo delata ANTES de crear el commit, en vez de que lo delate GitHub al rechazar el push con el objeto ya en el historial.

**Hoy:**

```
$ git status -sb
## master...origin/master [ahead 2]
$ git log --oneline "@{u}..HEAD"
b4979cc fix(bnpl): estampa el log del pipeline en hora Mexico
5057118 fix(bnpl): ancla la fecha de negocio a hora Mexico, no a la zona del servidor
```

**Queda:**

```
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later

# --- 9: el modelo, ya consolidado. Comprobar ANTES que .pbi/ no entra ---
git add --dry-run pbi_new/ | Select-String -Pattern "\.pbi/|\.abf|\.pbix"   # tiene que salir vacio
git add pbi_new/
git status --porcelain | Measure-Object -Line   # ~333 archivos en staging
git commit -m @'
feat(bnpl): versiona el PBIP del tablero, ya migrado a pbi_bnpl

Es el modelo que esta publicado y que refresca por Gateway_BI: 17 tablas
sobre las vistas de pbi_bnpl, sin Csv.Document ni SharePoint.Files.

Era pbi_new/. La copia con origenes CSV compartia reportId y datasetId con
esta, asi que publicar la equivocada sobrescribia produccion con el modelo
de archivos; quedo fuera del repo como respaldo hasta recuperar las dos
relaciones que se perdieron en la migracion.

No entran ni el .pbix (gitignoreado, y ademas 5h rezagado del TMDL) ni
.pbi/ (cache.abf de 135 MiB y el reportId productivo).
'@

# --- 10: empujar. Van los 2 rezagados + los 8 de este paquete ---
git log --oneline "@{u}..HEAD"   # revisar la lista antes de empujar
git push origin master
```

**Verificar:**

```
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later; git status -sb | Select-Object -First 1   # '## master...origin/master' sin ahead
git ls-files pbi_new | Measure-Object -Line   # ~333
git ls-files pbi_new | Select-String -Pattern "\.pbi/|\.abf|\.pbix"   # vacio
git cat-file -s (git rev-parse HEAD^{tree}) > $null; git count-objects -vH | Select-String "size-pack"
```

> **Ajuste del revisor.** Reemplazar el paso 9 y la verificacion:

git add --dry-run pbi_new/ | Select-String -Pattern "\.pbi/|\.abf|\.pbix"   # tiene que salir vacio
git add pbi_new/
git status --porcelain | Measure-Object -Line   # 330 archivos en staging

verificacion:
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later; git status -sb | Select-Object -First 1   # '## master...origin/master' sin ahead
git ls-files pbi_new | Measure-Object -Line   # 330
git ls-files pbi_new | Select-String -Pattern "\.pbi/|\.abf|\.pbix"   # vacio
git count-objects -vH | Select-String "size:|size-pack:"   # 'size' son los objetos sueltos del commit nuevo; 'size-pack' no se mueve hasta un gc
# El blob mas grande que se subio, para confirmar que ninguno pasa de 100 MB:
git rev-list --objects HEAD | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' | Where-Object { $_ -like 'blob*' } | Sort-Object { [int]($_ -split ' ')[1] } -Descending | Select-Object -First 3

> **Nota.** El archivo mas grande que va a entrar es pbi\Buy Now Pay Later.SemanticModel\definition\cultures\es-MX.tmdl con 2.96 MB — pasa sin problema (GitHub avisa a partir de 50 MB y rechaza a los 100). El total del arbol pbi/ sin cache ni pbix es ~5.7 MB.

---

## OLA 1 — El tablero deja de mentir

Todo lo que hoy hace que se muestren cifras falsas o viejas sin que nadie se entere. Esfuerzo ≈ 1.5 jornadas.

### O1.1 · Extraer antes de borrar en el ETL de Mongo, meter borrado y carga en una transaccion, y abortar si la coleccion devuelve 0 documentos

`etl_mongo_to_postgres.py:403-438 (_preparar_destino) y :477-499 (run)` · riesgo medio · media jornada

Hoy una coleccion vacia deja la tabla del staging en cero, las 11 matviews se refrescan sobre eso, main.py escribe modo='ok' y devuelve 0. Nadie se entera y el tablero amanece en ceros. Ademas el TRUNCATE va en autocommit 75 lineas antes de la extraccion: cualquier fallo del tunel SSM entre esas dos lineas deja la tabla vacia sin forma de revertir.

**Hoy:**

```
def _preparar_destino(defn: dict, full: bool, corte_ms) -> tuple:
    """Deja la tabla lista para el append. Devuelve (modo efectivo, llaves a refrescar)."""
    tabla = defn["table"]
    completa = full

    if defn["modo"] == "ventana" and not completa:
        dias = _dias_desde_ultimo_full(tabla)
        if dias is None or dias >= FULL_CADA_DIAS:
            motivo = "sin registro de full previo" if dias is None else f"ultimo full hace {dias}d"
            print(f"  recarga completa programada ({motivo})")
            completa = True

    if completa:
        execute_sql(f'TRUNCATE {SCHEMA}."{tabla}"', db=DB_STAGING_RW)
        return "full", []

    if defn["modo"] == "ventana":
        campo = defn["campo_ventana"]
        llaves = _llaves_no_finales(defn, corte_ms)
        # Los dos DELETE siguen compartiendo transaccion: borrar la ventana sin borrar
        # las llaves atrasadas dejaria el staging a medio refrescar.
        with transaction(db=DB_STAGING_RW) as tx:
            tx.execute_sql(
                f'DELETE FROM {SCHEMA}."{tabla}" WHERE "{campo}" >= :corte',
                {"corte": int(corte_ms)},
            )
            if llaves:
                tx.execute_sql(
                    f'DELETE FROM {SCHEMA}."{tabla}" '
                    f'WHERE "{defn["llave_refresco"]}" = ANY(:llaves)',
                    {"llaves": llaves},
                )
        return "ventana", llaves

    execute_sql(f'TRUNCATE {SCHEMA}."{tabla}"', db=DB_STAGING_RW)
    return "full", []

[... en run() ...]

        modo, llaves = _preparar_destino(defn, full or recrear, corte_ms)
        pipeline = list(defn["pipeline"])
        if modo == "ventana":
            condiciones = [{defn["campo_ventana"]: {"$gte": corte_ms}}]
            if llaves:
                condiciones.append({defn["llave_refresco"]: {"$in": llaves}})
                print(
                    f"  ventana {VENTANA_DIAS}d + {len(llaves):,} "
                    f"{defn['llave_refresco']} en estado no final"
                )
            else:
                print(f"  ventana {VENTANA_DIAS}d")
            pipeline.insert(0, {"$match": {"$or": condiciones}})

        df = extract_aggregate(MONGO_PROFILE, defn["collection"], pipeline)
        filas = len(df)
        if filas:
            df = _flatten(df)
            load_dataframe(df, defn["table"], schema=SCHEMA, db=DB_STAGING_RW)

        segundos = time.time() - t0
        _registrar_corrida(defn["table"], modo, filas, segundos, inicio)
        print(f"  -> {SCHEMA}.{defn['table']}: {filas:,} filas en {segundos:.0f}s ({modo})")
```

**Queda:**

```
# --- reemplaza _preparar_destino por estas DOS funciones ---

def _decidir_modo(defn: dict, full: bool, corte_ms) -> tuple:
    """Decide como se cargara la tabla y que llaves hay que refrescar. NO toca el destino.

    El TRUNCATE/DELETE se movio a _escribir(), que corre DESPUES de que la extraccion
    trajo datos. Antes se borraba aqui, 75 lineas antes del extract_aggregate y en
    autocommit: si Mongo devolvia cero (coleccion renombrada, tunel caido, filtro roto)
    la tabla quedaba vacia, las matviews se refrescaban en ceros y la corrida salia 'ok'.
    Es el mismo arreglo que ya tiene _cargar() en etl_redshift_to_postgres.py:318-323.
    """
    tabla = defn["table"]
    completa = full

    if defn["modo"] == "ventana" and not completa:
        dias = _dias_desde_ultimo_full(tabla)
        if dias is None or dias >= FULL_CADA_DIAS:
            motivo = "sin registro de full previo" if dias is None else f"ultimo full hace {dias}d"
            print(f"  recarga completa programada ({motivo})")
            completa = True

    if completa or defn["modo"] != "ventana":
        return "full", []
    return "ventana", _llaves_no_finales(defn, corte_ms)


def _escribir(defn: dict, modo: str, llaves: list, df: pd.DataFrame, corte_ms) -> None:
    """Borra lo que se reemplaza y carga lo nuevo, todo en UNA transaccion.

    Si el COPY falla, el TRUNCATE/DELETE se revierte y el staging conserva la carga
    anterior: datos de ayer es mucho mejor que una tabla vacia.
    """
    tabla = defn["table"]
    with transaction(db=DB_STAGING_RW) as tx:
        if modo == "full":
            tx.execute_sql(f'TRUNCATE {SCHEMA}."{tabla}"')
        else:
            # Los dos DELETE comparten transaccion con la carga: borrar la ventana sin
            # borrar las llaves atrasadas dejaria el staging a medio refrescar.
            tx.execute_sql(
                f'DELETE FROM {SCHEMA}."{tabla}" WHERE "{defn["campo_ventana"]}" >= :corte',
                {"corte": int(corte_ms)},
            )
            if llaves:
                tx.execute_sql(
                    f'DELETE FROM {SCHEMA}."{tabla}" '
                    f'WHERE "{defn["llave_refresco"]}" = ANY(:llaves)',
                    {"llaves": llaves},
                )
        tx.load_dataframe(df, tabla, schema=SCHEMA)


# --- y en run(), reemplaza el bloque del ciclo por esto ---

        modo, llaves = _decidir_modo(defn, full or recrear, corte_ms)
        pipeline = list(defn["pipeline"])
        if modo == "ventana":
            condiciones = [{defn["campo_ventana"]: {"$gte": corte_ms}}]
            if llaves:
                condiciones.append({defn["llave_refresco"]: {"$in": llaves}})
                print(
                    f"  ventana {VENTANA_DIAS}d + {len(llaves):,} "
                    f"{defn['llave_refresco']} en estado no final"
                )
            else:
                print(f"  ventana {VENTANA_DIAS}d")
            pipeline.insert(0, {"$match": {"$or": condiciones}})

        df = extract_aggregate(MONGO_PROFILE, defn["collection"], pipeline)
        filas = len(df)
        # Cero documentos NO es un caso normal: las 10 colecciones tienen datos en
        # produccion y credit-order siempre tiene filas en una ventana de 60 dias. Se
        # aborta la etapa nombrando la coleccion (era lo que pedia el diseno original) en
        # vez de dejar el staging vacio y la corrida en verde.
        if filas == 0:
            raise RuntimeError(
                f"{defn['collection']} devolvio 0 documentos (modo {modo}). No se toca "
                f"{SCHEMA}.{defn['table']}: se conserva la carga anterior. Revisa si la "
                "coleccion cambio de nombre, si el tunel SSM se cayo o si el $match quedo mal."
            )

        _escribir(defn, modo, llaves, _flatten(df), corte_ms)

        segundos = time.time() - t0
        _registrar_corrida(defn["table"], modo, filas, segundos, inicio)
        print(f"  -> {SCHEMA}.{defn['table']}: {filas:,} filas en {segundos:.0f}s ({modo})")

# --- y en el import de arriba, quita load_dataframe (ya no se usa suelto) ---
from postgres_local_client import (
    execute_sql,
    extract_sql,
    table_exists,
    transaction,
)
```

**Verificar:**

```
Simula la extraccion vacia sin tocar Mongo y comprueba que la tabla NO se vacia:
  .venv\Scripts\python.exe -c "import etl_mongo_to_postgres as e, pandas as pd; e.extract_aggregate=lambda *a,**k: pd.DataFrame(); e.run(solo=['revenue-orders-production'])"
Debe morir con RuntimeError nombrando la coleccion. Antes y despues:
  select count(*) from mongo_bnpl.revenue_orders_production;  -- el mismo numero
```

> **Nota.** Dos cosas que aparecieron al leer el archivo: (1) _tabla_existe() (:350-351) es codigo muerto, no lo llama nadie; si quitas load_dataframe del import, aprovecha y valora quitar tambien table_exists y esa funcion. (2) El raise por 0 filas hace que el pipeline se detenga para siempre si alguna vez una coleccion queda legitimamente vacia; es el comportamiento que pedia .kiro/.../design.md:643, pero si en algun momento se agrega una coleccion nueva y chica, hay que exceptuarla con una bandera en COLLECTIONS.

### O1.2 · Hacer que cero documentos en Mongo se reporte como CRIT y no como SIN_DATOS, para que la compuerta de frescura lo atrape

`ops/check_freshness.py:144-162 y :186` · riesgo bajo · minutos

Es la segunda mitad del hallazgo A1: la compuerta que deberia frenar el pipeline devuelve SIN_DATOS cuando docs_mongo==0 y main.py:99 solo bloquea con CRIT. Con esto, una coleccion critica renombrada o vaciada detiene la corrida ANTES de cargar nada, en vez de despues de haber truncado.

**Hoy:**

```
def _semaforo_fuente(lag_horas) -> str:
    if lag_horas is None:
        return "SIN_DATOS"
    if lag_horas >= LAG_CRIT_HORAS:
        return "CRIT"
    if lag_horas >= LAG_WARN_HORAS:
        return "WARN"
    return "OK"


def _semaforo_staging(docs_mongo, staging) -> str:
    if staging is None:
        return "FALTA"
    if docs_mongo == 0:
        return "SIN_DATOS"
    faltantes = docs_mongo - staging["docs_staging"]
    if faltantes <= 0:
        return "OK"
    return "WARN" if faltantes / docs_mongo <= FALTANTES_WARN_PCT else "CRIT"

[... en construir_filas ...]
            "semaforo_fuente": _semaforo_fuente(lag_horas),
```

**Queda:**

```
def _semaforo_fuente(lag_horas, docs_mongo) -> str:
    # Cero documentos no es "no se pudo medir la frescura": o renombraron la coleccion, o
    # el sondeo no la vio. Es el peor estado posible, porque el ETL cargaria eso encima
    # del staging. Va como CRIT para que main.py detenga la corrida en el paso [1/6] y no
    # como SIN_DATOS, que main.py:99 ignora.
    if docs_mongo == 0:
        return "CRIT"
    if lag_horas is None:
        return "SIN_DATOS"
    if lag_horas >= LAG_CRIT_HORAS:
        return "CRIT"
    if lag_horas >= LAG_WARN_HORAS:
        return "WARN"
    return "OK"


def _semaforo_staging(docs_mongo, staging) -> str:
    if staging is None:
        return "FALTA"
    if docs_mongo == 0:
        # Mismo criterio que arriba: la fuente no tiene con que alimentar al staging.
        return "CRIT"
    faltantes = docs_mongo - staging["docs_staging"]
    if faltantes <= 0:
        return "OK"
    return "WARN" if faltantes / docs_mongo <= FALTANTES_WARN_PCT else "CRIT"

[... en construir_filas, la linea 186 ...]
            "semaforo_fuente": _semaforo_fuente(lag_horas, m["docs_mongo"]),
```

**Verificar:**

```
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'ops'); import check_freshness as c; print(c._semaforo_fuente(1.0,0), c._semaforo_fuente(1.0,5), c._semaforo_staging(0,{'docs_staging':0}))"
Debe imprimir: CRIT OK CRIT
```

> **Nota.** Para las fuentes NO criticas (ops/config.py:31-35) esto solo agrega un log.error informativo, no detiene nada; la parada real la da la accion 1. Las dos capas son complementarias y conviene tener ambas: esta corta antes de gastar 20 minutos de extraccion.

### O1.3 · Agregar la guardia de blanco a bnplMinimumTenure

`pbi_new/Buy Now Pay Later.SemanticModel/definition/tables/grid_bnpl.tmdl:124` · riesgo medio · minutos

sql/pbi/06_grid_bnpl.sql:3 declara el grano: "cliente (146,613 filas — TODOS los clientes, no solo los enrolados)" y :83 mapea bnpl_enrolled_at::date, así que el NULL llega al modelo como blanco. DAX coacciona el blanco a 1899-12-30 y DATEDIFF da ~1,500 meses: la bandera queda en 1 para los ~137 mil que nunca se enrolaron. Los dos visuales que la filtran con In {1L} — pages/f384ed5188290d63776a/visuals/7d5e7258b21f913fd163 y 3f57b402a0115b201aa2 — dicen "For customers who have at least 4 months of tenure" arrancando en ~146,542 en vez de ~9,283.

**Hoy:**

```
column bnplMinimumTenure = IF(DATEDIFF([bnplEnrolledAt], TODAY(), MONTH) > 4, 1, 0)
		formatString: 0
		lineageTag: c3286926-b147-4ef1-a651-e06ac342a780
		summarizeBy: sum
```

**Queda:**

```
column bnplMinimumTenure = IF(ISBLANK([bnplEnrolledAt]), 0, IF(DATEDIFF([bnplEnrolledAt], TODAY(), MONTH) > 4, 1, 0))
		formatString: 0
		lineageTag: c3286926-b147-4ef1-a651-e06ac342a780
		summarizeBy: sum
```

**Verificar:**

```
Tarjeta temporal en Desktop con SUM(grid_bnpl[bnplMinimumTenure]): antes ~146,542, después ~9,283. Contrastar contra: select count(*) from bnpl.grid_bnpl where bnpl_enrolled_at is not null and bnpl_enrolled_at < (current_date - interval '4 months');
```

> **Nota.** Es un cambio de una línea pero cambia dos cifras que hoy se ven en pantalla, así que la tarjeta de verificación va ANTES de aplicarlo, no después. El bug es idéntico en pbi/ (grid_bnpl.tmdl:340), o sea que no lo introdujo la migración: la cifra mala ya está publicada. Aparte y sin resolver: el corte ">4 meses" no está justificado en ningún documento y no coincide con el TODAY()-115 de bnpl_loss_rates.tmdl — eso sí necesita dueño, pero el arreglo del blanco no espera a nadie.

### O1.4 · Restaurar la relación grid_bnpl[bnplEnrolledAt] -> enrollment_dates[Date] que se perdió en la migración

`pbi_new/Buy Now Pay Later.SemanticModel/definition/relationships.tmdl:388-391 (agregar al final del archivo)` · riesgo bajo · minutos

Verificado: pbi/relationships.tmdl:31-33 tiene esa relación con ese mismo GUID y pbi_new no la tiene. Sin ella enrollment_dates queda de isla: la cadena dynamic_enrollment_dates[visual_date] -> dynamic_enrollment_dates[Date] -> enrollment_dates[Date] (relación bf25262b, bothDirections) no llega a grid_bnpl. Los visuales 5507f6d55f9cc3ab1075 ("Clientes Enrolados Vs Clientes Activados") y 07b82a305c395408c175 ("Línea de Crédito Enrolada Vs Activada"), ambos en pages/f384ed5188290d63776a, ponen dynamic_enrollment_dates[visual_date] en Category y Count(grid_bnpl.netsuiteId) / Sum(grid_bnpl.originalCreditLimit) en Y: sin relación no dan error, pintan el total repetido en cada periodo.

**Hoy:**

```
relationship AutoDetected_6265ddac-ae80-4117-9530-2d40b886dec5
	fromColumn: overall_prev_post_bnpl_sales.netsuiteId
	toColumn: grid_bnpl.netsuiteId

(fin del archivo — no existe ninguna relación contra enrollment_dates.Date salvo la de dynamic_enrollment_dates de las líneas 228-231)
```

**Queda:**

```
relationship AutoDetected_6265ddac-ae80-4117-9530-2d40b886dec5
	fromColumn: overall_prev_post_bnpl_sales.netsuiteId
	toColumn: grid_bnpl.netsuiteId

relationship ec74a7f6-1c6d-bad4-f6a3-35e92f5e362f
	fromColumn: grid_bnpl.bnplEnrolledAt
	toColumn: enrollment_dates.Date
```

**Verificar:**

```
1) grep -c "fromColumn: grid_bnpl.bnplEnrolledAt" en relationships.tmdl debe dar 2 (la nueva + la 8896a09d contra el LocalDateTable). 2) En Desktop, abrir Funnel: las barras de "Clientes Enrolados" deben variar por periodo y su suma dar ~9,283, no 9,283 repetido 20 veces. Comparar contra: select date_trunc('month', bnpl_enrolled_at), count(*) from bnpl.grid_bnpl where bnpl_enrolled_at is not null group by 1.
```

> **Nota.** El hallazgo culpa a la variation de grid_bnpl.tmdl:429-432 de haberse "comido" la relación. Verificado que las dos pueden coexistir: son relaciones a tablas distintas (enrollment_dates vs LocalDateTable_1b940f1c) y no forman ciclo. Si Desktop la rechaza igual, borrar el bloque `variation Variación` de grid_bnpl.tmdl:429-432 es seguro: grepeé los 196 visuales y NINGUNO usa la jerarquía de bnplEnrolledAt — el único visual que toca esa columna (8505eb30b87398e823d9, slicer del Funnel) la usa como Column plano. Ojo con el tipo: sql/pbi/06_grid_bnpl.sql:83 mapea bnpl_enrolled_at::date, así que no hay componente de hora y el join contra CALENDAR() casa. Editable en el .tmdl; Desktop lo respeta al abrir.

### O1.5 · Restaurar la relación bnpl_loss_rates_with_lead[netsuiteId] -> grid_bnpl[netsuiteId] para que los roll rates vuelvan a filtrarse

`pbi_new/Buy Now Pay Later.SemanticModel/definition/relationships.tmdl:388-391 (agregar al final del archivo)` · riesgo bajo · minutos

pbi/relationships.tmdl:169-171 la tiene con ese GUID; pbi_new no. Los 6 visuales de Salud del Portafolio (pages/609cf54aea15d518c8e3/visuals/{329dfe5f21b4a710974a, 43181269a4927887c058, bee6d8c159bacc355305, c1dd49270127c6c601ca, cbceea75131872e0738b, e61d48d8360b398620ad}) consumen esa tabla, y en esa misma página hay 4 slicers sobre grid_bnpl (081d5bbd59eed40b9036 enrollment_cohort, 1f928a2c9dcdabe1d16a inferredGender, 7bff25e9edb4546672da ruta/oficina, 98ce88ad882121ecb9b5 customerAgeRangeAtEligibility). Hoy mueves cualquiera de los cuatro y los roll rates no se mueven.

**Hoy:**

```
relationship AutoDetected_6265ddac-ae80-4117-9530-2d40b886dec5
	fromColumn: overall_prev_post_bnpl_sales.netsuiteId
	toColumn: grid_bnpl.netsuiteId

(no existe ninguna relación con fromColumn: bnpl_loss_rates_with_lead.netsuiteId en todo el archivo)
```

**Queda:**

```
relationship eef16e8f-1e0e-de16-83c2-3deae3d69a3f
	fromColumn: bnpl_loss_rates_with_lead.netsuiteId
	toColumn: grid_bnpl.netsuiteId
```

**Verificar:**

```
En Desktop, página Salud del Portafolio: seleccionar una oficina en el slicer 7bff25e9edb4546672da y confirmar que las 4 matrices de "Roll rates between Delinquency Buckets" y las 2 multiRowCard cambian de valor. Antes del cambio no cambian.
```

> **Ajuste del revisor.** El bloque de relationships.tmdl queda igual (correcto tal cual):

relationship eef16e8f-1e0e-de16-83c2-3deae3d69a3f
	fromColumn: bnpl_loss_rates_with_lead.netsuiteId
	toColumn: grid_bnpl.netsuiteId

Y se agregan estos pasos, sin los cuales el tablero se contradice:

(a) ayuda_tablero/textos_a_mano.py — en las 5 ocurrencias (líneas 197, 207, 215, 224, 233) sustituir la frase
  'La tabla no tiene relacion con el grid: los slicers de la pagina no la afectan.'
por
  'La tabla si se filtra con los slicers del grid (oficina, ruta, edad y genero) por netsuiteId.'
(la de :197 trae la variante larga 'La tabla no tiene relacion con el grid: los slicers de oficina, ruta, edad y genero de la pagina…', misma sustitución).

(b) Regenerar los tooltips con el flujo de ayuda_tablero para que ayuda_tablero/_datos/textos.json y los visualHeaderTooltip de los 6 visuales queden alineados. Si se hace a mano, hay que editar el literal en cada uno de los 6 visual.json de pages/609cf54aea15d518c8e3.

(c) pbi_new/Buy Now Pay Later.Report/definition/pages/00portada0bnpl0lectu/visuals/p0trampas00000000003/visual.json:225 — reemplazar el valor del textRun por:
                    "value": "Los slicers de oficina, ruta, edad y género salen del grid de clientes. Alcanzan las gráficas de mora y las de roll rates, pero no las de cosechas ni audiencias, que no tienen relación con el grid. El tooltip de cada gráfica lo indica.",

Verificación adicional: grep -rn 'no tienen relación con el grid' pbi_new/ debe dejar de mencionar roll rates, y grep -rn 'no tiene relacion con el grid' ayuda_tablero/ debe dar 0.

> **Nota.** Verificado que no crea ambigüedad: with_lead solo tiene relaciones contra dq_order_roll_rates[stage], dq_order_roll_rates_lead[stage] y un LocalDateTable — ningún camino alterno a grid_bnpl. También verificado que la columna calculada bnpl_loss_rates_with_lead.tmdl:115-119 usa LOOKUPVALUE (no RELATED), así que hoy funciona sin relación y no se rompe al agregarla. Si Desktop tira "se detectó una dependencia circular" al crearla (pasa con LOOKUPVALUE entre tablas relacionadas), el arreglo es sustituir esa columna por `column customerAgeRangeAtEligibility = RELATED(grid_bnpl[customerAgeRangeAtEligibility])`, que además es más barata. Aparte: hay que corregir la portada — pages/00portada0bnpl0lectu/visuals/p0trampas00000000003 declara como característica del modelo que los roll rates "no tienen relación con el grid". Esa frase deja de ser cierta con este cambio.

### O1.6 · Agregar el filtro flg_cte_bnpl="N" al Y0 de tendenciaNoEnroladosDropProyectada

`pbi_new/Buy Now Pay Later.SemanticModel/definition/tables/bnpl_cosechas_agg.tmdl:317-322` · riesgo bajo · minutos

Su gemela tendenciaEnroladosDropProyectada filtra flg_cte_bnpl="Y" en las dos puntas de la recta: Y0 en :251 y Yref en :261. En la de no enrolados el Yref (:331) sí filtra "N" pero el Y0 (:321) no filtra nada, y como el ALLSELECTED barre el filtro del visual, ese origen promedia enrolados y no enrolados. La recta de no enrolados arranca de un punto que mezcla los dos grupos, en b063e42593e592cc0a31 ("Comparativo del Drop Size"), que es la página que existe para argumentar cuánto más compra un cliente por tener BNPL.

**Hoy:**

```
-- Y0: primer valor del indicador (ventas/órdenes) en MesInicio
			VAR Y0 =
			    CALCULATE(
			        DIVIDE( SUM( bnpl_cosechas_agg[gross_sales] ), SUM( bnpl_cosechas_agg[ordenes] ) ),
			        FILTER( ALLSELECTED( bnpl_cosechas_agg ), bnpl_cosechas_agg[mes_tx] = MesInicio )
			    )
```

**Queda:**

```
-- Y0: primer valor del indicador (ventas/órdenes) en MesInicio
			VAR Y0 =
			    CALCULATE(
			        DIVIDE( SUM( bnpl_cosechas_agg[gross_sales] ), SUM( bnpl_cosechas_agg[ordenes] ) ),
			        FILTER( ALLSELECTED( bnpl_cosechas_agg ), bnpl_cosechas_agg[mes_tx] = MesInicio && bnpl_cosechas_agg[flg_cte_bnpl] = "N" )
			    )
```

**Verificar:**

```
grep -c 'flg_cte_bnpl' bnpl_cosechas_agg.tmdl debe subir de 3 a 4 ocurrencias dentro de las dos medidas de tendencia. En Desktop: en "Comparativo del Drop Size" la recta de no enrolados debe arrancar en el mismo valor que la serie real de no enrolados del primer mes; hoy arranca entre las dos series.
```

> **Ajuste del revisor.** El cambio_propuesto se queda tal cual (correcto):

			-- Y0: primer valor del indicador (ventas/órdenes) en MesInicio
			VAR Y0 =
			    CALCULATE(
			        DIVIDE( SUM( bnpl_cosechas_agg[gross_sales] ), SUM( bnpl_cosechas_agg[ordenes] ) ),
			        FILTER( ALLSELECTED( bnpl_cosechas_agg ), bnpl_cosechas_agg[mes_tx] = MesInicio && bnpl_cosechas_agg[flg_cte_bnpl] = "N" )
			    )

Verificación corregida (Git Bash, desde la raíz del proyecto):

1) El conteo global sube de 33 a 34:
   grep -c 'flg_cte_bnpl' 'pbi_new/Buy Now Pay Later.SemanticModel/definition/tables/bnpl_cosechas_agg.tmdl'

2) La comprobación que de verdad importa: que la línea del Y0 de la medida de NO enrolados quede filtrada, y siga siendo la única con "N" en ese bloque:
   sed -n '318,322p' 'pbi_new/Buy Now Pay Later.SemanticModel/definition/tables/bnpl_cosechas_agg.tmdl'
   -> la línea 321 debe terminar en: bnpl_cosechas_agg[mes_tx] = MesInicio && bnpl_cosechas_agg[flg_cte_bnpl] = "N" )

3) En Desktop, página del visual b063e42593e592cc0a31 ("Comparativo del Drop Size"): la recta de no enrolados debe arrancar en el mismo punto que la serie real de no enrolados del primer mes; hoy arranca entre las dos series.

> **Nota.** El MesReferencia de esta medida (:290-298) también filtra "Y" y eso está bien: define la fecha de corte a partir del primer enrolamiento, y tiene que ser la misma para las dos series. No tocarlo. Editable en el .tmdl.

### O1.7 · Corregir el SWITCH de bnpl_audiencia_agg[valor] y darle formato

`pbi_new/Buy Now Pay Later.SemanticModel/definition/tables/bnpl_audiencia_agg.tmdl:4-15` · riesgo bajo · minutos

'Medidas Audiencia'.tmdl:43-46 define la partición como {("Clientes", ..., 0), ("Gross Sales", ..., 1)}. La rama 2 del SWITCH no corresponde a ningún valor: es código muerto, y Clientes acierta solo por caer en el default. El día que se agregue una tercera medida devolverá Clientes en silencio, que es el mismo bug que PENDIENTES:127-145 documenta para dynamicTotalRevenue. Y sin formatString los dos visuales de la página Audiencias (49e8cfe327f3ff31d85e/visuals/b83e4baf9c86d5b79fd0 "Activos" y 85b6027ded541d834e4e "Inactivos") pintan millones de pesos como número pelón.

**Hoy:**

```
measure valor =
			
			VAR med = SELECTEDVALUE('Medidas Audiencia'[Medidas Audiencia Orden])
			RETURN
			SWITCH(med,
			    1, SUM(bnpl_audiencia_agg[Gross Sales]),
			    2, SUM(bnpl_audiencia_agg[Clientes]),
			    SUM(bnpl_audiencia_agg[Clientes])
			    )
		lineageTag: 9b0ce37c-a766-44c1-996c-cae7588fe4d0

		annotation PBI_FormatHint = {"isGeneralNumber":true}
```

**Queda:**

```
measure valor =
			
			VAR med = SELECTEDVALUE('Medidas Audiencia'[Medidas Audiencia Orden])
			RETURN
			SWITCH(med,
			    0, SUM(bnpl_audiencia_agg[Clientes]),
			    1, SUM(bnpl_audiencia_agg[Gross Sales]),
			    BLANK()
			    )
		formatString: #,0
		lineageTag: 9b0ce37c-a766-44c1-996c-cae7588fe4d0
```

**Verificar:**

```
En Desktop, página Audiencias: mover el slicer 12fd3d47b57c80522d92 entre "Clientes" y "Gross Sales" y confirmar que el valor cambia en los dos sentidos y que ambos salen con separador de miles. Con el SWITCH viejo, "Clientes" también funciona (por el default), así que la prueba que importa es que "Gross Sales" siga dando el mismo número que antes.
```

> **Nota.** formatString: #,0 sirve para las dos ramas (conteo y pesos sin centavos) y es lo mínimo que arregla la legibilidad. Si se quiere el símbolo de peso solo en Gross Sales hace falta una cadena de formato dinámica (formatStringDefinition), que es más trabajo y hay que hacerla en Desktop. Hay que borrar la annotation PBI_FormatHint {"isGeneralNumber":true}: convive mal con un formatString explícito y Desktop la regenera sola si hace falta.

### O1.8 · Alinea los tipos de months_closes con bnpl_par y corrige la cabecera que jura que son cosmeticos

`sql/pbi/04_months_closes.sql:5-8 y 57-59` · riesgo medio · ~1 h

totalAmountDefault::bigint redondea los centavos del monto en default en una tabla y no en la otra, asi que las dos vistas dan totales distintos sobre la misma columna de par_snapshot. La cabecera declara que todas las diferencias son cosmeticas y con eso desactiva la sospecha de quien compare las dos cifras.

**Hoy:**

```
-- months_closes y bnpl_par son la misma tabla con otra ropa. Diferencias, todas cosmeticas:
--   * la columna del bucket se llama dqBucket en vez de PAR
--   * month es una FECHA (primer dia del mes del corte), no el texto 'YYYY-MM'
--   * no trae limitToReceiveOrdersInMont

[lineas 57-59]
    p.total_amount_default::bigint                      AS "totalAmountDefault",
    p.movement_date::text                               AS "movementDate",
    p.payment_date::text                                AS "paymentDate",
```

**Queda:**

```
-- months_closes y bnpl_par son la misma tabla con otra ropa. Diferencias, todas de presentacion:
--   * la columna del bucket se llama dqBucket en vez de PAR
--   * month es una FECHA (primer dia del mes del corte), no el texto 'YYYY-MM'
--   * no trae limitToReceiveOrdersInMont
--
-- Los TIPOS de las columnas compartidas son identicos a los de 03_bnpl_par.sql, y tienen que
-- serlo: son la misma columna de bnpl.par_snapshot leida dos veces. Hasta ahora no lo eran —
-- totalAmountDefault salia ::bigint aqui y double alla (redondeando los centavos de la mora, o
-- sea perdiendo dinero en una de las dos tablas) y paymentDate salia ::text aqui y timestamp
-- alla. Si hace falta cambiar el tipo de una, se cambian LAS DOS en el mismo commit.

[lineas 57-59]
    p.total_amount_default                              AS "totalAmountDefault",
    p.movement_date::text                               AS "movementDate",
    p.payment_date                                      AS "paymentDate",
```

**Verificar:**

```
select (select sum("totalAmountDefault") from pbi_bnpl.bnpl_par) as par, (select sum("totalAmountDefault") from pbi_bnpl.months_closes) as closes; -- despues del rebuild los dos numeros deben ser identicos, con centavos
```

> **Ajuste del revisor.** El cambio a sql/pbi/04_months_closes.sql queda como se propone, y ADEMAS hay que retipar el modelo en el mismo commit.

pbi_new\Buy Now Pay Later.SemanticModel\definition\tables\months_closes.tmdl:220-225 — reemplazar (indentacion con TABs, como el resto del archivo):

	column totalAmountDefault
		dataType: int64
		formatString: 0
		lineageTag: 12faf484-5640-4618-9ebb-c291d1772348
		summarizeBy: sum
		sourceColumn: totalAmountDefault

por:

	column totalAmountDefault
		dataType: double
		lineageTag: 12faf484-5640-4618-9ebb-c291d1772348
		summarizeBy: sum
		sourceColumn: totalAmountDefault

		annotation PBI_FormatHint = {"isGeneralNumber":true}

(la linea `annotation SummarizationSetBy = Automatic` que sigue en la 227 se queda donde esta)

Y en la 237-241:

	column paymentDate
		dataType: string
		lineageTag: 129c9fdb-59f8-4f21-ad3a-290a3c53a8db
		summarizeBy: none
		sourceColumn: paymentDate

por:

	column paymentDate
		dataType: dateTime
		formatString: General Date
		lineageTag: 129c9fdb-59f8-4f21-ad3a-290a3c53a8db
		summarizeBy: none
		sourceColumn: paymentDate

Y agregar a la verificacion, ademas del sum de totalAmountDefault, la comprobacion de tipos del lado de la base:

select table_name, column_name, data_type
from information_schema.columns
where table_schema='pbi_bnpl' and table_name in ('bnpl_par','months_closes')
  and column_name in ('totalAmountDefault','paymentDate')
order by 2, 1;   -- los dos pares deben traer el MISMO data_type

> **Nota.** Es un cambio de tipo visible en Power BI: months_closes[totalAmountDefault] pasa de entero a decimal y [paymentDate] de texto a fecha/hora. Hay que refrescar el modelo y revisar que ninguna medida ni relacion dependa del tipo viejo antes de publicar. movementDate se deja ::text en las dos porque asi ya estaba en ambas: cambiarlo seria una decision aparte, no una alineacion.

### O1.9 · Haz que ruta_inferida sea TRUE cuando no hay tramo de SCD, en vez de NULL

`sql/03_bnpl_grouped_orders.sql:110-112` · riesgo bajo · minutos

El LEFT JOIN contra dim_ruta_cliente_scd deja r en NULL para los clientes sin tramo; la comparacion da NULL, no TRUE. Aguas abajo sql/pbi/20:153-156 los pinta como 'SIN RUTA' y el coalesce(bool_or(...), false) de :64 los presenta como dato confiable. Es el unico punto donde se puede arreglar para las dos vistas de golpe.

**Hoy:**

```
-- La vigencia diaria arranca en 2025-01-01. Para ordenes anteriores se usa el primer tramo
    -- conocido del cliente, y queda marcado como inferido.
    (o.created_at::date < r.vigencia_real_desde)           AS ruta_inferida
```

**Queda:**

```
-- La vigencia diaria arranca en 2025-01-01. Para ordenes anteriores se usa el primer tramo
    -- conocido del cliente, y queda marcado como inferido.
    --
    -- El coalesce(..., true) cubre el tercer hueco, que antes salia como NULL: clientes que no
    -- tienen NINGUN tramo en dim_ruta_cliente_scd, porque la extraccion filtra `and ruta is not
    -- null` (etl_redshift_to_postgres.py:66) o porque el cliente no esta en la vigencia diaria.
    -- Con NULL, sql/pbi/20:64 hacia coalesce(bool_or(ruta_inferida), false) y esas ordenes
    -- terminaban marcadas como ruta FIRME con aliado 'SIN RUTA'. No saber la ruta es el caso
    -- mas inferido de todos, no el menos.
    coalesce(o.created_at::date < r.vigencia_real_desde, true) AS ruta_inferida
```

**Verificar:**

```
select ruta_inferida, count(*) from bnpl.grouped_orders group by 1; -- antes debe aparecer un grupo NULL; despues del rebuild solo true/false, y el conteo de true = (NULL viejo + true viejo)
```

> **Nota.** No toca etl_redshift_to_postgres.py:66. Quitar ese `and ruta is not null` generaria tramos con ruta NULL en el SCD y no arregla nada: el hueco seguiria siendo un hueco, solo que ocupando espacio. El otro hueco que menciona la auditoria (sql/11:60-61 solo extiende el primer y el ultimo tramo, no los agujeros intermedios entre tramos) NO se arregla aqui y sigue abierto: una orden que cae en un dia sin vigencia entre dos tramos tampoco cruza, y ahora al menos sale marcada como inferida en vez de firme.

---

## OLA 2 — Que no se rompa

Robustez: transacciones, deduplicación, guardas de cast, chequeos que sí vigilan la capa de negocio, y el aviso cuando algo falla de madrugada. Esfuerzo ≈ 3 jornadas.

### O2.1 · Agrega el DDL de archivos_bnpl (y el del concurso) a CAPAS para que una VM limpia pueda construir las vistas 14-17

`build_bnpl.py:30-43` · riesgo bajo · minutos

sql/pbi/14 a 17 hacen FROM archivos_bnpl.odds_combinations / atr_combinations_iv / ps_transactional_profile / bnpl_cac. Ese schema solo lo crea carga_archivos_bnpl.py:98, que es manual y no forma parte de main.py. En una VM sin ese paso previo las cuatro vistas revientan al crearse; hoy ademas se llevan el build entero por la falta de try/except (accion siguiente).

**Hoy:**

```
CAPAS = [
    (None, "02_bnpl_funciones.sql"),
    ("dim_ruta_actual", "11_bnpl_dim_ruta.sql"),
    ("dim_ruta_cliente_scd", None),  # se crea junto con dim_ruta_actual
    ("grouped_orders", "03_bnpl_grouped_orders.sql"),
    ("loss_rates", "04_bnpl_loss_rates.sql"),
    ("par_snapshot", "05_bnpl_par_snapshot.sql"),
    ("vintage_analysis", "06_bnpl_vintage_analysis.sql"),
    ("grid_bnpl", "07_bnpl_grid_bnpl.sql"),
    ("kpis_daily", "08_bnpl_kpis_daily.sql"),
    ("revenue_comision", "09_bnpl_revenue_comision.sql"),
    ("corte_venta_sku", "10_bnpl_cortes_venta.sql"),
    ("corte_venta_so", None),  # se crea junto con corte_venta_sku
]
```

**Queda:**

```
CAPAS = [
    (None, "02_bnpl_funciones.sql"),
    # DDL puro (CREATE TABLE / CREATE INDEX IF NOT EXISTS): no borra ni recarga nada, los datos
    # siguen entrando por carga_archivos_bnpl.py y carga_clientes_concurso.py a mano. Estan aqui
    # porque las vistas de consumo los leen: sql/pbi/14, 15, 16 y 17 hacen FROM archivos_bnpl.*
    # y sql/pbi/20 lee bnpl.bnpl_clientes_concurso. En una VM limpia, sin estas dos lineas, esas
    # cinco vistas fallan al crearse y pbi_bnpl queda incompleto sin que nadie se entere.
    (None, "14_archivos_bnpl.sql"),
    (None, "13_bnpl_clientes_concurso.sql"),
    ("dim_ruta_actual", "11_bnpl_dim_ruta.sql"),
    ("dim_ruta_cliente_scd", None),  # se crea junto con dim_ruta_actual
    ("grouped_orders", "03_bnpl_grouped_orders.sql"),
    ("loss_rates", "04_bnpl_loss_rates.sql"),
    ("par_snapshot", "05_bnpl_par_snapshot.sql"),
    ("vintage_analysis", "06_bnpl_vintage_analysis.sql"),
    ("grid_bnpl", "07_bnpl_grid_bnpl.sql"),
    ("kpis_daily", "08_bnpl_kpis_daily.sql"),
    ("revenue_comision", "09_bnpl_revenue_comision.sql"),
    ("corte_venta_sku", "10_bnpl_cortes_venta.sql"),
    ("corte_venta_so", None),  # se crea junto con corte_venta_sku
]
```

**Verificar:**

```
En una base limpia: .venv\Scripts\python.exe build_bnpl.py --rebuild ; luego select count(*) from pbi_bnpl.odds_combinations, pbi_bnpl.atr_combinations_iv, pbi_bnpl.ps_transactional_profile, pbi_bnpl.bnpl_cac; -- las cuatro deben existir (0 filas si no se cargaron los CSV, que es lo correcto)
```

> **Ajuste del revisor.** CAPAS queda como se propone. Ademas:

1) Verificacion correcta (una fila por tabla, y falla en seco si alguna no existe):

select 'odds_combinations' t, count(*) n from pbi_bnpl.odds_combinations
union all select 'atr_combinations_iv',      count(*) from pbi_bnpl.atr_combinations_iv
union all select 'ps_transactional_profile', count(*) from pbi_bnpl.ps_transactional_profile
union all select 'bnpl_cac',                 count(*) from pbi_bnpl.bnpl_cac
union all select 'clientes_concurso',        count(*) from bnpl.bnpl_clientes_concurso;

2) sql/13_bnpl_clientes_concurso.sql:5 — reemplazar:
--   Lo carga `carga_clientes_concurso.py`, a mano. No lo toca `build_bnpl.py`.
por:
--   Lo carga `carga_clientes_concurso.py`, a mano. `build_bnpl.py` aplica su DDL en cada
--   corrida (CREATE TABLE / CREATE INDEX IF NOT EXISTS, para que una VM limpia tenga la tabla),
--   pero NUNCA toca los datos.

3) sql/13_bnpl_clientes_concurso.sql:46 — reemplazar el literal del COMMENT:
COMMENT ON TABLE bnpl.bnpl_clientes_concurso IS 'Universo del Concurso Credito Rabbit con linea de lanzamiento. Carga manual desde Excel (carga_clientes_concurso.py); build_bnpl.py solo aplica su DDL, no sus datos.';

4) README.md:520-528, fila de la tabla:
| `bnpl.bnpl_clientes_concurso` | cliente | tabla física, carga manual. `build_bnpl.py` aplica su DDL, **no sus datos**. |

5) sql/pbi/README.md:393 — cambiar «Es la única tabla de `bnpl` que no reconstruye `build_bnpl.py`» por «`build_bnpl.py` sólo aplica su DDL; el dato lo pone negocio, no sale de Mongo ni de Redshift».

> **Nota.** Los dos .sql son idempotentes (CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS / CREATE OR REPLACE VIEW), asi que correrlos en cada build no toca los datos cargados a mano. El alias DB_BNPL_RW ya tiene DDL sobre archivos_bnpl segun README.md:478. La linea de 13_bnpl_clientes_concurso.sql solo hace falta si se aplica la accion de sql/pbi/20; incluirla igual no cuesta nada y hace verdadera la afirmacion de README.md:63.

### O2.2+O2.3 · Aisla el fallo de cada vista pbi y reconstruye pbi_bnpl tambien en las corridas --rebuild --solo

`build_bnpl.py:66-80 y 146-149` · riesgo bajo · minutos

Hoy un solo .sql roto (o un schema archivos_bnpl inexistente) deja las vistas siguientes sin crear y las ya dropeadas borradas, sin que el print final lo diga. Y `if not solo` hace que --rebuild --solo tire por CASCADE las vistas de pbi_bnpl que cuelgan de la vista reconstruida sin recrear ninguna.

**Hoy:**

```
for archivo in archivos:
        vista = archivo.stem.split("_", 1)[1]
        cuerpo = archivo.read_text(encoding="utf-8").strip().rstrip(";")
        # DROP + CREATE y no CREATE OR REPLACE: este ultimo falla si cambian los nombres, el orden
        # o el tipo de las columnas, que es justo lo que pasa al corregir una consulta.
        execute_sql(
            f'DROP VIEW IF EXISTS {PBI_SCHEMA}."{vista}" CASCADE;\n'
            f'CREATE VIEW {PBI_SCHEMA}."{vista}" AS\n{cuerpo};',
            db=DB_BNPL_RW,
        )
    print(f"{PBI_SCHEMA}: {len(archivos)} vistas creadas para Power BI")

[...]

    # Al final y siempre: son vistas simples, crearlas es solo DDL y cuesta menos de un segundo.
    # Correrlo en cada build las deja auto-reparadas si alguien tocó una a mano.
    if not solo:
        _construir_vistas_pbi()
```

**Queda:**

```
# --- reemplaza el bucle de _construir_vistas_pbi (lineas 70-80) ---
    fallidas = []
    for archivo in archivos:
        vista = archivo.stem.split("_", 1)[1]
        cuerpo = archivo.read_text(encoding="utf-8").strip().rstrip(";")
        # DROP + CREATE y no CREATE OR REPLACE: este ultimo falla si cambian los nombres, el orden
        # o el tipo de las columnas, que es justo lo que pasa al corregir una consulta.
        try:
            execute_sql(
                f'DROP VIEW IF EXISTS {PBI_SCHEMA}."{vista}" CASCADE;\n'
                f'CREATE VIEW {PBI_SCHEMA}."{vista}" AS\n{cuerpo};',
                db=DB_BNPL_RW,
            )
        except Exception as e:
            # Una consulta rota no se puede llevar a las otras 17: el DROP ya corrio, asi que
            # abortar aqui deja esa vista borrada Y las siguientes sin crear. Se registran todas
            # y se falla al final, con la lista completa.
            fallidas.append((vista, str(e).splitlines()[0][:200]))
    print(f"{PBI_SCHEMA}: {len(archivos) - len(fallidas)} de {len(archivos)} vistas creadas "
          f"para Power BI")
    for vista, error in fallidas:
        print(f"    FALLO {PBI_SCHEMA}.{vista}: {error}")
    if fallidas:
        raise SystemExit(
            f"{len(fallidas)} vistas de {PBI_SCHEMA} no se crearon: "
            f"{', '.join(v for v, _ in fallidas)}"
        )

# --- reemplaza el cierre de run() (lineas 146-149) ---
    # Al final y SIEMPRE, tambien con --solo: son vistas simples y crearlas cuesta menos de un
    # segundo. Ademas de auto-repararlas si alguien toco una a mano, esto repara el destrozo del
    # CASCADE: los .sql de capa arrancan con DROP MATERIALIZED VIEW ... CASCADE (07:16, 11:14 y
    # 11:40, 03:10, 04:15), que se lleva por delante las vistas de pbi_bnpl colgadas de la vista
    # reconstruida. Con el `if not solo` una corrida --rebuild --solo las dejaba borradas hasta
    # el siguiente build completo.
    if rebuild and solo:
        arrastradas = [v for v, _ in CAPAS if v and v not in solo]
        print(
            "AVISO: --rebuild --solo usa DROP ... CASCADE. Pudo tirar vistas de bnpl que no estan "
            f"en --solo ({', '.join(arrastradas)}); corre build_bnpl.py --rebuild completo para "
            "recrearlas."
        )
    _construir_vistas_pbi()
```

**Verificar:**

```
.venv\Scripts\python.exe build_bnpl.py --rebuild --solo grid_bnpl ; luego select count(*) from information_schema.views where table_schema = 'pbi_bnpl'; -- debe dar 18
```

> **Ajuste del revisor.** En _construir_vistas_pbi(), cambiar el cierre por una excepcion normal para que main.py la atrape:

    if fallidas:
        raise RuntimeError(
            f"{len(fallidas)} vistas de {PBI_SCHEMA} no se crearon: "
            f"{', '.join(v for v, _ in fallidas)}"
        )

(El `raise SystemExit` de la linea 68 y el de la 110 pueden quedarse: son validacion de argumentos, no fallos de datos de la corrida desatendida.)

Y en run(), decir solo lo que se sabe:

    if rebuild and solo:
        print(
            "AVISO: --rebuild --solo usa DROP ... CASCADE. Puede haberse llevado vistas de bnpl "
            "que dependen de las reconstruidas (p.ej. bnpl.kpis_daily lee bnpl.grid_bnpl). "
            "Comprueba con: select matviewname from pg_matviews where schemaname='bnpl'; "
            "si falta alguna, corre build_bnpl.py --rebuild completo."
        )
    _construir_vistas_pbi()

> **Nota.** El aviso de --rebuild --solo es informativo a proposito: bloquear la combinacion romperia el flujo de trabajo de iterar una vista sola. El problema de fondo (el CASCADE tambien tira materializadas de bnpl, no solo de pbi_bnpl) queda visible en pantalla en vez de descubrirse por un tablero vacio.

### O2.2+O2.3 · parte b · Guardar commit y hash del .sql en etl_runs, y registrar ahi las 18 vistas de pbi_bnpl

`sql/00_bnpl_ops.sql:49-59; bnpl_version.py (nuevo); build_bnpl.py:60-80 y :83-97 y :130 y :143` · riesgo bajo · ~1 h

etl_runs tiene cinco columnas y ninguna dice con que codigo se produjo la carga: si el tablero sale raro un martes no hay forma de saber que definicion de la vista corrio ese dia. Y las 18 vistas de pbi_bnpl, que son literalmente lo que Power BI consulta, no dejan absolutamente ninguna bitacora.

**Hoy:**

```
-- sql/00_bnpl_ops.sql:49-56
CREATE TABLE IF NOT EXISTS bnpl_ops.etl_runs (
    started_at timestamp NOT NULL,
    tabla      text      NOT NULL,
    modo       text,
    filas      bigint,
    segundos   numeric(10,1),
    PRIMARY KEY (started_at, tabla)
);

# build_bnpl.py:83-97
def _registrar(vista: str, modo: str, filas, segundos: float, inicio) -> None:
    execute_sql(
        "INSERT INTO bnpl_ops.etl_runs (started_at, tabla, modo, filas, segundos) "
        "VALUES (:inicio, :tabla, :modo, :filas, :segundos) "
        "ON CONFLICT (started_at, tabla) DO NOTHING",
        {
            "inicio": inicio,
            "tabla": f"bnpl.{vista}",
            "modo": modo,
            # int() porque _filas devuelve numpy.int64 y psycopg3 no adapta tipos de numpy.
            "filas": int(filas),
            "segundos": round(segundos, 1),
        },
        db=DB_OPS_RW,
    )

# build_bnpl.py:70-80 (dentro de _construir_vistas_pbi)
    for archivo in archivos:
        vista = archivo.stem.split("_", 1)[1]
        cuerpo = archivo.read_text(encoding="utf-8").strip().rstrip(";")
        # DROP + CREATE y no CREATE OR REPLACE: este ultimo falla si cambian los nombres, el orden
        # o el tipo de las columnas, que es justo lo que pasa al corregir una consulta.
        execute_sql(
            f'DROP VIEW IF EXISTS {PBI_SCHEMA}."{vista}" CASCADE;\n'
            f'CREATE VIEW {PBI_SCHEMA}."{vista}" AS\n{cuerpo};',
            db=DB_BNPL_RW,
        )
    print(f"{PBI_SCHEMA}: {len(archivos)} vistas creadas para Power BI")
```

**Queda:**

```
-- ============ sql/00_bnpl_ops.sql ============
CREATE TABLE IF NOT EXISTS bnpl_ops.etl_runs (
    started_at timestamp NOT NULL,
    tabla      text      NOT NULL,
    modo       text,
    filas      bigint,
    segundos   numeric(10,1),
    commit_sha text,
    sql_sha256 text,
    PRIMARY KEY (started_at, tabla)
);

-- La tabla ya existe en la VM, y CREATE TABLE IF NOT EXISTS no agrega columnas: estas
-- dos lineas son las que la migran. Son idempotentes, pueden quedarse en el archivo.
ALTER TABLE bnpl_ops.etl_runs ADD COLUMN IF NOT EXISTS commit_sha text;
ALTER TABLE bnpl_ops.etl_runs ADD COLUMN IF NOT EXISTS sql_sha256 text;


# ============ bnpl_version.py (archivo nuevo, en la raiz) ============
"""Identidad de la version que produjo cada carga: commit del repo y hash del .sql.

Va en la raiz y no en ops/ para que lo puedan importar tanto main.py (que agrega ops/ al
path) como build_bnpl.py y los dos ETL corridos sueltos, donde la raiz es sys.path[0].
"""
import hashlib
import subprocess
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def commit_sha() -> str:
    """Commit corto del repo, con sufijo '+sucio' si hay cambios sin commitear.

    El sufijo importa: sin el, una fila de etl_runs diria que la produjo un commit que no
    contiene el codigo que corrio. Si no hay git, devuelve 'sin-git' y no lanza.
    """
    try:
        sha = subprocess.run(
            ["git", "-C", str(BASE_DIR), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        sucio = subprocess.run(
            ["git", "-C", str(BASE_DIR), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        return f"{sha}+sucio" if sucio else sha
    except Exception:  # noqa: BLE001 - la bitacora nunca debe tumbar la carga
        return "sin-git"


def sha_sql(archivo) -> str:
    """SHA-256 corto del .sql que definio el objeto. None si no hay archivo."""
    if archivo is None:
        return None
    ruta = Path(archivo)
    if not ruta.is_absolute():
        ruta = BASE_DIR / "sql" / ruta
    try:
        return hashlib.sha256(ruta.read_bytes()).hexdigest()[:12]
    except Exception:  # noqa: BLE001
        return None


# ============ build_bnpl.py ============
# import nuevo, junto a los otros:
import bnpl_version

# _registrar pasa a recibir el nombre YA calificado y el archivo que lo definio:
def _registrar(objeto: str, modo: str, filas, segundos: float, inicio, archivo=None) -> None:
    execute_sql(
        "INSERT INTO bnpl_ops.etl_runs "
        "(started_at, tabla, modo, filas, segundos, commit_sha, sql_sha256) "
        "VALUES (:inicio, :tabla, :modo, :filas, :segundos, :commit, :sql_sha) "
        "ON CONFLICT (started_at, tabla) DO NOTHING",
        {
            "inicio": inicio,
            "tabla": objeto,
            "modo": modo,
            # int() porque _filas devuelve numpy.int64 y psycopg3 no adapta tipos de numpy.
            # None para las vistas de pbi_bnpl: son DDL, no se cuentan sus filas.
            "filas": int(filas) if filas is not None else None,
            "segundos": round(segundos, 1),
            "commit": bnpl_version.commit_sha(),
            "sql_sha": bnpl_version.sha_sql(archivo),
        },
        db=DB_OPS_RW,
    )

# los dos call sites del ciclo (lineas 130 y 143):
                _registrar(f"bnpl.{vista}", "rebuild", filas, time.time() - t0, inicio, None)
        _registrar(f"bnpl.{vista}", modo, filas, segundos, inicio, archivo)

# y dentro de _construir_vistas_pbi, el ciclo queda:
    for archivo in archivos:
        vista = archivo.stem.split("_", 1)[1]
        cuerpo = archivo.read_text(encoding="utf-8").strip().rstrip(";")
        inicio, t0 = _ahora_mx(), time.time()
        # DROP + CREATE y no CREATE OR REPLACE: este ultimo falla si cambian los nombres, el orden
        # o el tipo de las columnas, que es justo lo que pasa al corregir una consulta.
        execute_sql(
            f'DROP VIEW IF EXISTS {PBI_SCHEMA}."{vista}" CASCADE;\n'
            f'CREATE VIEW {PBI_SCHEMA}."{vista}" AS\n{cuerpo};',
            db=DB_BNPL_RW,
        )
        # Se registra cada vista: son las unicas 18 cosas que Power BI lee y hasta ahora no
        # dejaban ni una fila de bitacora. sql_sha256 dice CUAL definicion se publico.
        _registrar(f"{PBI_SCHEMA}.{vista}", "vista", None, time.time() - t0, inicio, archivo)
    print(f"{PBI_SCHEMA}: {len(archivos)} vistas creadas para Power BI")
```

**Verificar:**

```
select tabla, modo, filas, commit_sha, sql_sha256, started_at
from bnpl_ops.etl_runs
where started_at::date = current_date and tabla like 'pbi_bnpl.%'
order by tabla;
Deben salir 18 filas con commit_sha poblado y un sql_sha256 distinto por vista.
```

> **Nota.** El ALTER TABLE se aplica solo: etl_mongo_to_postgres._aplicar_ddl() (:396-400) y ops/check_freshness.aplicar_ddl() ejecutan 00_bnpl_ops.sql en cada corrida. Al aplicar esto cambia una cifra del README: :341-342 dice que deben aparecer 27 tablas en etl_runs y ya no las registran las vistas de pbi_bnpl; pasan a ser 45 (27 + 18). Falta lo mismo en los otros dos INSERT (etl_mongo_to_postgres.py:444-456 y etl_redshift_to_postgres.py:326-337): es agregar commit_sha a las columnas y :commit al VALUES, con bnpl_version.commit_sha(); el sql_sha256 ahi solo aplica al DDL del staging.

### O2.4 · Agrega funciones de cast guardado para fechas y coordenadas de texto en sql/02

`sql/02_bnpl_funciones.sql:82-88 (insertar despues)` · sin riesgo · minutos

sql/02:82-86 documenta que iso_a_mx() lleva regex justamente para no fallar con basura de origen. birthdate y las coordenadas se quedaron sin esa guarda, y son casts de columnas text del staging que el proyecto sabe que traen basura. Un valor malo tumba el CREATE MATERIALIZED VIEW de grid_bnpl y, en cadena, todo lo que cuelga de el.

**Hoy:**

```
-- Texto ISO 8601 -> timestamp en hora Mexico. Devuelve NULL en lugar de fallar si el valor no
-- es una fecha ('No Information' y similares aparecen en estas colecciones).
CREATE OR REPLACE FUNCTION bnpl.iso_a_mx(valor text) RETURNS timestamp
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE WHEN valor ~ '^\d{4}-\d{2}-\d{2}'
                THEN (valor::timestamptz AT TIME ZONE 'UTC') - interval '6 hours' END
$$;
```

**Queda:**

```
-- Texto ISO 8601 -> timestamp en hora Mexico. Devuelve NULL en lugar de fallar si el valor no
-- es una fecha ('No Information' y similares aparecen en estas colecciones).
CREATE OR REPLACE FUNCTION bnpl.iso_a_mx(valor text) RETURNS timestamp
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE WHEN valor ~ '^\d{4}-\d{2}-\d{2}'
                THEN (valor::timestamptz AT TIME ZONE 'UTC') - interval '6 hours' END
$$;

-- Texto -> date, con la MISMA guarda que iso_a_mx(). Existe porque esa guarda se puso en
-- createdAt y authorizationDate pero no en birthdate, que en el staging tambien es text
-- (sql/01:152) y viene de captura libre. Un solo '00/00/0000' en una fila de
-- fintech-credit-request tumba el rebuild entero de bnpl.grid_bnpl.
--
-- Se valida el rango ademas del patron: to_date() no falla con '2024-13-45', lo desborda al
-- año siguiente, y una edad calculada sobre eso pasa desapercibida.
CREATE OR REPLACE FUNCTION bnpl.a_fecha(valor text) RETURNS date
    LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
BEGIN
    RETURN CASE
        WHEN valor ~ '^\d{4}-\d{2}-\d{2}'
             AND left(valor, 10)::date BETWEEN '1900-01-01'::date AND '2100-01-01'::date
        THEN left(valor, 10)::date
    END;
EXCEPTION WHEN others THEN
    RETURN NULL;
END
$$;

-- Texto -> coordenada. `maximo` es 90 para latitud y 180 para longitud. Devuelve NULL si el
-- texto no es numerico o si cae fuera del rango: en el staging latitude/longitude son text
-- (sql/01:131-132, :152) y ahi han llegado cadenas vacias, comas decimales y ceros.
CREATE OR REPLACE FUNCTION bnpl.a_coord(valor text, maximo double precision)
    RETURNS double precision
    LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE v double precision;
BEGIN
    v := nullif(trim(valor), '')::double precision;
    RETURN CASE WHEN v BETWEEN -maximo AND maximo AND v <> 0 THEN v END;
EXCEPTION WHEN others THEN
    RETURN NULL;
END
$$;
```

**Verificar:**

```
select bnpl.a_fecha('No Information'), bnpl.a_fecha('0000-00-00'), bnpl.a_fecha('1988-03-14'), bnpl.a_coord('', 90), bnpl.a_coord('19.43', 90), bnpl.a_coord('999', 90); -- NULL, NULL, 1988-03-14, NULL, 19.43, NULL
```

> **Nota.** El `v <> 0` en a_coord descarta el (0,0) del Golfo de Guinea, que es el relleno tipico de una coordenada no capturada. Si alguien prefiere conservarlo, quitar esa condicion. Las funciones van en plpgsql y no en sql por el bloque EXCEPTION: eso impide el inlining, pero son 146,613 filas una vez por rebuild, no una ruta caliente.

### O2.5 · Usa a_fecha() y a_coord() en los siete casts sin guarda de grid_bnpl

`sql/07_bnpl_grid_bnpl.sql:112-123` · riesgo bajo · minutos · depende de: la accion de sql/02 (las funciones a_fecha y a_coord tienen que existir antes)

Son seis casts de texto a date y cuatro a double precision sin ninguna proteccion. Hoy no fallan por suerte, no por diseño: el mismo archivo que los rodea (sql/02) documenta que estas colecciones traen 'No Information' y similares.

**Hoy:**

```
nullif(c."address_latitude", '')::double precision      AS shop_latitude,
    nullif(c."address_longitude", '')::double precision     AS shop_longitude,
    r.name                                                  AS customer_name,
    r."lastNames"                                           AS customer_last_names,
    coalesce(nullif(r.gender, 'NOT_DEFINED'), nullif(c.gender, 'NOT_DEFINED')) AS gender,
    r.birthdate::date                                       AS customer_birthdate,
    (bnpl.hoy_mx() - r.birthdate::date) / 365               AS customer_age,
    (pa.bnpl_eligible_at::date - r.birthdate::date) / 365   AS customer_age_at_eligibility,
    (en.bnpl_enrolled_at::date - r.birthdate::date) / 365   AS customer_age_at_enrollment,
    c."phoneNumber"                                         AS customer_phone_number,
    nullif(r.latitude, '')::double precision                AS customer_latitude,
    nullif(r.longitude, '')::double precision               AS customer_longitude,
```

**Queda:**

```
bnpl.a_coord(c."address_latitude", 90)                  AS shop_latitude,
    bnpl.a_coord(c."address_longitude", 180)                AS shop_longitude,
    r.name                                                  AS customer_name,
    r."lastNames"                                           AS customer_last_names,
    coalesce(nullif(r.gender, 'NOT_DEFINED'), nullif(c.gender, 'NOT_DEFINED')) AS gender,
    -- birthdate, latitude y longitude son TEXT en el staging (sql/01:131-132, :152) y llegan de
    -- captura libre. Van por las funciones guardadas de sql/02 por la misma razon que iso_a_mx():
    -- un solo valor invalido no puede tumbar el rebuild de la vista maestra del producto.
    bnpl.a_fecha(r.birthdate)                               AS customer_birthdate,
    (bnpl.hoy_mx() - bnpl.a_fecha(r.birthdate)) / 365       AS customer_age,
    (pa.bnpl_eligible_at::date - bnpl.a_fecha(r.birthdate)) / 365
                                                            AS customer_age_at_eligibility,
    (en.bnpl_enrolled_at::date - bnpl.a_fecha(r.birthdate)) / 365
                                                            AS customer_age_at_enrollment,
    c."phoneNumber"                                         AS customer_phone_number,
    bnpl.a_coord(r.latitude, 90)                            AS customer_latitude,
    bnpl.a_coord(r.longitude, 180)                          AS customer_longitude,
```

**Verificar:**

```
Antes de aplicar, medir el impacto: select count(*) filter (where birthdate is not null and birthdate !~ '^\d{4}-\d{2}-\d{2}') as birthdate_malo, count(*) filter (where nullif(trim(latitude),'') is not null and latitude !~ '^-?\d+(\.\d+)?$') as lat_mala from mongo_bnpl.fintech_credit_request_production; -- despues: .venv\Scripts\python.exe build_bnpl.py --rebuild --solo grid_bnpl
```

> **Nota.** El cambio puede mover valores: hoy una coordenada 0,0 o fuera de rango pasa tal cual al tablero y despues del cambio sale NULL. Correr la consulta de verificacion ANTES para saber cuantas filas cambian; si son cero, el cambio es puramente defensivo.

### O2.6 · Pon DISTINCT ON en enrolados, preautorizados y lineas de grid_bnpl

`sql/07_bnpl_grid_bnpl.sql:68-94` · riesgo medio · ~1 h

Los tres entran como LEFT JOIN contra la vista base y la vista lleva CREATE UNIQUE INDEX ix_grid_bnpl_pk ON (netsuite_id). Cualquier duplicado en el lado derecho multiplica filas y el rebuild falla en el indice, dejando bnpl.grid_bnpl inexistente y con ella las cinco relaciones del modelo que cuelgan de netsuiteId.

**Hoy:**

```
enrolados AS (
    SELECT
        "netsuiteId"                                        AS netsuite_id,
        bnpl.iso_a_mx("createdAt")                          AS bnpl_enrolled_at,
        "creditLimit"                                       AS credit_limit,
        origin                                              AS enrollment_channel
    FROM mongo_bnpl.fintech_credit_approval_production
    WHERE status = 'APPROVED' AND "netsuiteId" IS NOT NULL
),
preautorizados AS (
    SELECT
        "netsuiteId"                                        AS netsuite_id,
        bnpl.iso_a_mx("authorizationDate")                  AS bnpl_eligible_at,
        "preAuthorized"                                     AS pre_authorized_by
    FROM mongo_bnpl.fintech_pre_authorization_status_production
    WHERE "netsuiteId" IS NOT NULL
),
lineas AS (
    SELECT
        "netsuiteId"                                        AS netsuite_id,
        "originalCreditLimit"                               AS original_credit_limit,
        "currentCreditLimit"                                AS current_credit_limit,
        "creditLimitAvailable"                              AS credit_limit_available,
        "customerStatus"                                    AS customer_status
    FROM mongo_bnpl.credit_limit_history_management
    WHERE "netsuiteId" IS NOT NULL
)
```

**Queda:**

```
enrolados AS (
    -- UNA aprobacion por cliente: la PRIMERA, porque de ella sale bnpl_enrolled_at y el cohort.
    -- Sin el DISTINCT ON un cliente con dos aprobaciones duplica su fila y hace fallar
    -- CREATE UNIQUE INDEX ix_grid_bnpl_pk (linea 181), o sea el rebuild entero. Es el duplicado
    -- que ya reporta ops/quality_checks.approval_netsuite_id_duplicado, que hoy es WARN y corre
    -- DESPUES del build: avisa cuando ya fallo.
    SELECT DISTINCT ON ("netsuiteId")
        "netsuiteId"                                        AS netsuite_id,
        bnpl.iso_a_mx("createdAt")                          AS bnpl_enrolled_at,
        "creditLimit"                                       AS credit_limit,
        origin                                              AS enrollment_channel
    FROM mongo_bnpl.fintech_credit_approval_production
    WHERE status = 'APPROVED' AND "netsuiteId" IS NOT NULL
    ORDER BY "netsuiteId", bnpl.iso_a_mx("createdAt") ASC NULLS LAST, "approvalId"
),
preautorizados AS (
    -- Misma regla: la PRIMERA preautorizacion, que es la que define bnpl_eligible_at.
    SELECT DISTINCT ON ("netsuiteId")
        "netsuiteId"                                        AS netsuite_id,
        bnpl.iso_a_mx("authorizationDate")                  AS bnpl_eligible_at,
        "preAuthorized"                                     AS pre_authorized_by
    FROM mongo_bnpl.fintech_pre_authorization_status_production
    WHERE "netsuiteId" IS NOT NULL
    ORDER BY "netsuiteId", bnpl.iso_a_mx("authorizationDate") ASC NULLS LAST,
             "preAuthorizationId"
),
lineas AS (
    -- Aqui al reves: credit_limit_history_management es tabla de HISTORIA (114,560 filas para
    -- ~146k clientes), y lo que el grid necesita es el estado VIGENTE, o sea el ajuste mas
    -- reciente. Es el CTE mas expuesto de los tres: no es que "a veces" tenga duplicados, es que
    -- por definicion los tiene en cuanto a un cliente le mueven la linea una segunda vez.
    SELECT DISTINCT ON ("netsuiteId")
        "netsuiteId"                                        AS netsuite_id,
        "originalCreditLimit"                               AS original_credit_limit,
        "currentCreditLimit"                                AS current_credit_limit,
        "creditLimitAvailable"                              AS credit_limit_available,
        "customerStatus"                                    AS customer_status
    FROM mongo_bnpl.credit_limit_history_management
    WHERE "netsuiteId" IS NOT NULL
    ORDER BY "netsuiteId", "creditLimitUpdateDate" DESC NULLS LAST, "customerId"
)
```

**Verificar:**

```
select 'enrolados' t, count(*) - count(distinct "netsuiteId") dup from mongo_bnpl.fintech_credit_approval_production where status='APPROVED' and "netsuiteId" is not null union all select 'preauth', count(*) - count(distinct "netsuiteId") from mongo_bnpl.fintech_pre_authorization_status_production where "netsuiteId" is not null union all select 'lineas', count(*) - count(distinct "netsuiteId") from mongo_bnpl.credit_limit_history_management where "netsuiteId" is not null; -- despues del cambio: build_bnpl.py --rebuild --solo grid_bnpl y select count(*) from bnpl.grid_bnpl (debe seguir en 146,613)
```

> **Ajuste del revisor.** Dejar los tres DISTINCT ON tal cual y reemplazar el comentario del CTE `lineas` por:

lineas AS (
    -- credit_limit_history_management es un snapshot por cliente (la historia va dentro de la
    -- columna "creditHistory", sql/01:267), no un log de movimientos: HOY no tiene netsuiteId
    -- repetidos, y no puede tenerlos sin que el rebuild falle antes — el LEFT JOIN de abajo
    -- multiplicaria filas y con eso CREATE UNIQUE INDEX ix_grid_bnpl_pk (linea 181).
    -- El DISTINCT ON es blindaje: si el dia que la fuente empiece a versionar la linea el grid
    -- se queda con el ajuste MAS RECIENTE, que es el estado vigente que pide esta vista, en vez
    -- de tumbar el pipeline entero.
    SELECT DISTINCT ON ("netsuiteId")
        "netsuiteId"                                        AS netsuite_id,
        "originalCreditLimit"                               AS original_credit_limit,
        "currentCreditLimit"                                AS current_credit_limit,
        "creditLimitAvailable"                              AS credit_limit_available,
        "customerStatus"                                    AS customer_status
    FROM mongo_bnpl.credit_limit_history_management
    WHERE "netsuiteId" IS NOT NULL
    ORDER BY "netsuiteId", "creditLimitUpdateDate" DESC NULLS LAST, "customerId"
)

Y en el comentario de `enrolados`, cambiar «Es el duplicado que ya reporta ops/quality_checks.approval_netsuite_id_duplicado» por «Se parece al que reporta ops/quality_checks.approval_netsuite_id_duplicado, que cuenta sobre TODAS las aprobaciones y no solo sobre status='APPROVED'».

> **Nota.** El criterio de desempate no es neutro y hay que decirlo: para enrolados y preautorizados se toma la PRIMERA (es la fecha de enrolamiento y el cohort), para lineas la ULTIMA (es el estado vigente). Con eso en.credit_limit sigue siendo el limite de la aprobacion original y li.current_credit_limit el de hoy, que es la distincion que el grid ya intenta hacer. bnpl_activated_line_of_credit (linea 142) usa li.original_credit_limit y por lo tanto pasa a leerse del registro mas reciente: si Riesgo lo quiere del primer registro historico, se separa en un cuarto CTE con ORDER BY ASC.

### O2.7 · Pon DISTINCT ON en el CTE enrolados de grouped_orders

`sql/03_bnpl_grouped_orders.sql:13-24` · riesgo medio · ~1 h

Mismo patron que en sql/07 pero con una consecuencia extra: aqui el CTE alimenta un agregado (cohortes.enrolled_customers y enrolled_credit_limit_cohort) que viaja hasta bnpl_par y months_closes como EnrolledCustomers y enrolledCreditLimit, o sea el denominador de las tasas de cosecha.

**Hoy:**

```
WITH enrolados AS (
    -- Clientes con credito aprobado. Es la base del cohort de enrolamiento.
    SELECT
        "netsuiteId"                                             AS netsuite_id,
        bnpl.iso_a_mx("createdAt")                               AS bnpl_enrolled_at,
        to_char(bnpl.iso_a_mx("createdAt"), 'YYYY-MM')           AS enrollment_cohort,
        "creditLimit"                                            AS enrolled_credit_limit,
        origin                                                   AS enrollment_channel
    FROM mongo_bnpl.fintech_credit_approval_production
    WHERE status = 'APPROVED'
      AND "netsuiteId" IS NOT NULL
),
```

**Queda:**

```
WITH enrolados AS (
    -- Clientes con credito aprobado. Es la base del cohort de enrolamiento.
    --
    -- DISTINCT ON por dos razones distintas, las dos reales:
    --   1. Este CTE entra como LEFT JOIN contra con_indices (linea 114). Un cliente con dos
    --      aprobaciones duplica TODAS sus ordenes y hace fallar CREATE UNIQUE INDEX
    --      ix_grouped_orders_pk (linea 123), que es de cinco columnas y no incluye la aprobacion.
    --   2. `cohortes` cuenta count(*) sobre este CTE para enrolled_customers. Sin deduplicar,
    --      un cliente con dos aprobaciones cuenta dos veces en el denominador del cohort.
    -- Se toma la PRIMERA aprobacion: el cohort de enrolamiento es la fecha en que el cliente
    -- entro al producto, no la de su ultimo ajuste.
    SELECT DISTINCT ON ("netsuiteId")
        "netsuiteId"                                             AS netsuite_id,
        bnpl.iso_a_mx("createdAt")                               AS bnpl_enrolled_at,
        to_char(bnpl.iso_a_mx("createdAt"), 'YYYY-MM')           AS enrollment_cohort,
        "creditLimit"                                            AS enrolled_credit_limit,
        origin                                                   AS enrollment_channel
    FROM mongo_bnpl.fintech_credit_approval_production
    WHERE status = 'APPROVED'
      AND "netsuiteId" IS NOT NULL
    ORDER BY "netsuiteId", bnpl.iso_a_mx("createdAt") ASC NULLS LAST, "approvalId"
),
```

**Verificar:**

```
select count(*) - count(distinct "netsuiteId") as aprobaciones_de_mas from mongo_bnpl.fintech_credit_approval_production where status='APPROVED' and "netsuiteId" is not null; -- si da > 0, comparar antes/despues: select enrollment_cohort, sum(enrolled_customers) from bnpl.grouped_orders group by 1 order by 1
```

> **Nota.** Este cambio SI mueve cifras del tablero si hoy hay aprobaciones duplicadas: enrolled_customers baja y por lo tanto las tasas por cohort del vintage suben. Correr primero la consulta de verificacion; si da 0, el cambio es solo blindaje y no mueve nada. Si da > 0, avisar a Riesgo antes de publicar, porque cambia el denominador de las cosechas.

### O2.8 · Haz que el ETL de Redshift no dependa de bnpl.grouped_orders para poder correr en una VM limpia

`etl_redshift_to_postgres.py:256-265 y 341-348` · riesgo bajo · ~1 h

main.py corre Redshift en el paso 3 y build_bnpl en el paso 4, pero _universo_bnpl() (que usan ventas_cliente y ruta_cliente_scd) y _sql_cosechas() leen bnpl.grouped_orders, que produce el paso 4. En una VM limpia el pipeline muere en el paso 3 y no llega nunca a crear la vista que necesita.

**Hoy:**

```
def _universo_bnpl() -> list:
    """Clientes con credito: con al menos una orden o con aprobacion."""
    df = pg_extract_sql("""
        select distinct netsuite_id from bnpl.grouped_orders
        where netsuite_id is not null
        union
        select distinct "netsuiteId" from mongo_bnpl.fintech_credit_approval_production
        where "netsuiteId" is not null
    """, db=DB_BNPL)
    return [v.strip() for v in df.iloc[:, 0] if v and v.strip()]
```

**Queda:**

```
def _hay_grouped_orders() -> bool:
    """En una VM limpia el paso 3 (Redshift) corre ANTES del paso 4 (capa de negocio), asi que
    bnpl.grouped_orders todavia no existe. Sin esta guarda el primer arranque revienta con un
    'relation does not exist' que no dice nada del orden del pipeline."""
    df = pg_extract_sql(
        "select to_regclass('bnpl.grouped_orders') is not null as existe", db=DB_BNPL
    )
    return bool(df["existe"].iloc[0])


def _universo_bnpl() -> list:
    """Clientes con credito: con al menos una orden o con aprobacion.

    En el primer arranque, sin grouped_orders, el universo queda solo con los aprobados. Es un
    subconjunto valido: la segunda corrida ya trae las dos mitades.
    """
    ordenes = """
        select distinct netsuite_id from bnpl.grouped_orders
        where netsuite_id is not null
        union
    """ if _hay_grouped_orders() else ""
    df = pg_extract_sql(f"""
        {ordenes}
        select distinct "netsuiteId" from mongo_bnpl.fintech_credit_approval_production
        where "netsuiteId" is not null
    """, db=DB_BNPL)
    return [v.strip() for v in df.iloc[:, 0] if v and v.strip()]


# --- y al inicio de run(), justo despues de `universo = None` (linea 347) ---
    # cosechas_agg necesita el mes de la primera orden BNPL de cada cliente y eso SOLO sale de
    # grouped_orders: no hay forma de derivarlo sin la capa de negocio. En el primer arranque se
    # omite y se avisa, en vez de tumbar el paso 3 completo.
    if "cosechas_agg" in tablas and not _hay_grouped_orders():
        print("bnpl.grouped_orders no existe todavia: se omite cosechas_agg. Corre "
              "build_bnpl.py y despues etl_redshift_to_postgres.py --solo cosechas_agg")
        tablas = [t for t in tablas if t != "cosechas_agg"]
```

**Verificar:**

```
select to_regclass('bnpl.grouped_orders'); -- simular el caso limpio en una base de prueba y correr .venv\Scripts\python.exe etl_redshift_to_postgres.py : debe cargar estructura_comercial, route_mapping, ruta_cliente_scd, ventas_cliente y estacionalidad_mes, y avisar que omite cosechas_agg
```

> **Nota.** No arregla la dependencia circular de fondo, la hace explicita y recuperable en dos corridas. La alternativa limpia — mover cosechas y ventas_cliente a un paso 3-bis despues del build — es un cambio de orquestacion en main.py y cuesta mas; esta version desbloquea el arranque en frio hoy.

### O2.9 · Haz que concurso_base lea de verdad la tabla del concurso, o quita esa fuente de la documentacion

`sql/pbi/20_concurso_base.sql:2 y 194-200` · riesgo bajo · ~1 h · depende de: la accion que agrega 13_bnpl_clientes_concurso.sql a CAPAS (si no, en una VM limpia la vista 20 pasa a fallar por una tabla que antes no necesitaba)

> **Mitad técnica.** La decisión de fondo va a `PENDIENTES_NEGOCIO.md`; lo de aquí abajo se puede hacer sin esperar respuesta.

sql/pbi/README.md:54 y README.md:63 afirman que la vista 20 lee bnpl_clientes_concurso, y grep sobre las 200 lineas del archivo da cero coincidencias. O la lee y la documentacion es cierta, o no la lee y hay una tabla de carga manual que nadie consume: hoy son las dos cosas a la vez.

**Hoy:**

```
[sql/pbi/20_concurso_base.sql:2]
-- Fuente:  bnpl.grouped_orders + bnpl.dim_ruta_actual + bnpl.grid_bnpl

[sql/pbi/20_concurso_base.sql:194-200]
    coalesce(w.ix_entregada_periodo = 1, false)         AS "esPrimeraOrdenEntregadaEnVentana"
FROM en_ventana w
-- Sin trim() en las llaves: ambos lados vienen limpios y envolver la columna anula el indice.
LEFT JOIN bnpl.dim_ruta_actual dr ON w.netsuite_id = dr.netsuite_id
LEFT JOIN bnpl.grid_bnpl g        ON w.netsuite_id = g.netsuite_id
LEFT JOIN historia_cliente h      ON w.netsuite_id = h.netsuite_id
ORDER BY w.created_at, w.netsuite_id, w.sales_order_id;

[sql/pbi/README.md:54]
| 20 | `concurso_base` | — (dataset nuevo) | `bnpl.bnpl_clientes_concurso` + `grouped_orders` | 1,098 | 44 |
```

**Queda:**

```
[sql/pbi/20_concurso_base.sql:2]
-- Fuente:  bnpl.grouped_orders + bnpl.dim_ruta_actual + bnpl.grid_bnpl + bnpl.bnpl_clientes_concurso

[sql/pbi/20_concurso_base.sql:194-200]
    coalesce(w.ix_entregada_periodo = 1, false)         AS "esPrimeraOrdenEntregadaEnVentana",

    -- ── Universo del concurso ────────────────────────────────────────────────
    -- bnpl.bnpl_clientes_concurso es la lista que negocio publico en Excel (51,294 clientes con
    -- su linea de lanzamiento). Se une SIN filtrar: la vista sigue trayendo todas las ordenes de
    -- la ventana y es DAX quien decide si el concurso se mide solo sobre el universo, con una
    -- medida sobre esEsDelUniversoConcurso. Filtrarlo aqui obligaria a reconstruir la vista cada
    -- vez que negocio cambie de opinion.
    (cc.netsuite_id IS NOT NULL)                        AS "esDelUniversoConcurso",
    cc.linea_nueva                                      AS "lineaNuevaConcurso",
    cc.clasificacion                                    AS "clasificacionConcurso"
FROM en_ventana w
-- Sin trim() en las llaves: ambos lados vienen limpios y envolver la columna anula el indice.
LEFT JOIN bnpl.dim_ruta_actual dr ON w.netsuite_id = dr.netsuite_id
LEFT JOIN bnpl.grid_bnpl g        ON w.netsuite_id = g.netsuite_id
LEFT JOIN historia_cliente h      ON w.netsuite_id = h.netsuite_id
-- bnpl_clientes_concurso tiene indice unico sobre netsuite_id (sql/13:36), asi que este LEFT
-- JOIN no puede multiplicar filas.
LEFT JOIN bnpl.bnpl_clientes_concurso cc ON w.netsuite_id = cc.netsuite_id
ORDER BY w.created_at, w.netsuite_id, w.sales_order_id;

[sql/pbi/README.md:54]
| 20 | `concurso_base` | — (dataset nuevo) | `bnpl.grouped_orders` + `dim_ruta_actual` + `grid_bnpl` + `bnpl_clientes_concurso` | 1,098 | 47 |
```

**Verificar:**

```
select count(*) filter (where "esDelUniversoConcurso") as del_universo, count(*) as total from pbi_bnpl.concurso_base; -- y cruzar contra: select count(distinct o.netsuite_id) from bnpl.grouped_orders o join bnpl.bnpl_clientes_concurso c on o.netsuite_id = c.netsuite_id where o.created_at::date between '2026-08-05' and '2026-08-30'
```

> **Nota.** Lo que NO se puede resolver sin negocio: si el concurso se mide solo sobre los 51,294 del Excel o sobre cualquier cliente que compre en la ventana. Por eso el join va sin filtro y expone una bandera. Lo que si se hace hoy sin esperar a nadie: la union, las tres columnas nuevas y las dos lineas de documentacion. Aparte, el hallazgo esta mal ubicado: la linea 2 del .sql NO menciona la tabla del concurso (dice grouped_orders + dim_ruta_actual + grid_bnpl); la afirmacion falsa esta en sql/pbi/README.md:54 y en README.md:63 ('tabla física, la lee la vista 20'). La numeracion 17 -> 20 sin 18 ni 19 es deliberada segun el propio README (los 90+ son documentacion), pero conviene dejarlo escrito ahi mismo.

### O2.10 · Mete las 15 identidades del README como checks que corren solos

`ops/quality_checks.py:104-150 (y ops/config.py:12)` · riesgo bajo · media jornada

Los 8 checks existentes usan todos {S} = STAGING_SCHEMA: ninguno mira bnpl.* ni pbi_bnpl.*. Toda la capa que alimenta el tablero esta sin vigilancia, y la unica verificacion que existe es un bloque de SQL en el README que hay que copiar y pegar a mano.

**Hoy:**

```
[ops/quality_checks.py, cierre de CHECKS en la linea 104]
]


def _ahora_mx() -> datetime:

[ops/quality_checks.py:125-141, dentro de correr_checks()]
    for check in CHECKS:
        tabla = check["tabla"]
        faltantes = [c for c in check["requiere"] if c not in existentes.get(tabla, set())]
        if faltantes:
            filas.append({
                "checked_at": checked_at,
                "check_name": check["name"],
                "tabla": tabla,
                "n_filas": None,
                "severidad": check["severidad"],
                "resultado": "NO_APLICABLE",
                "detalle": f"falta en staging: {', '.join(faltantes)}",
            })
            continue

        n = int(extract_sql(check["sql"], db=DB_STAGING)["n"].iloc[0])

[ops/config.py:12]
DB_STAGING = "mongo_bnpl"
```

**Queda:**

```
# --- ops/config.py, junto a los otros alias (linea 12) ---
DB_STAGING = "mongo_bnpl"
# Alias de lectura de la capa de negocio. Lo usan los checks de identidad entre capas, que son
# los unicos que no miran el staging.
DB_BNPL = "bnpl"


# --- ops/quality_checks.py, cambiar el import de la linea 10 ---
from config import DB_BNPL, DB_OPS_RW, DB_STAGING, STAGING_SCHEMA, TZ_OFFSET_HOURS


# --- ops/quality_checks.py, insertar justo DESPUES del `]` que cierra CHECKS (linea 104) ---

# ── Identidades entre capas ──────────────────────────────────────────────────
#
# Cada fila es un conteo que DEBE cumplirse: destino = origen * factor + delta. Si no se cumple,
# algo se quedo a medias entre dos capas y el tablero va a leer una mitad vieja.
#
# Estaban en README.md:377-408 como un bloque de SQL para copiar y pegar a mano. Un check que
# depende de que alguien se acuerde de correrlo no es un check. Aqui corren en cada pipeline y
# quedan en bnpl_ops.data_quality_checks con su historia.
#
# CRIT = si no cuadra, hay una capa incompleta y el resultado no sirve.
# WARN = el delta es real y esperado pero puede moverse (grid_bnpl) o el origen es carga manual
#        y desfasarse es normal hasta que alguien recargue (los cuatro de archivos_bnpl).
#
#              nombre                    origen                                   destino                                factor delta  sev
IDENTIDADES = [
    ("grouped_orders",           "bnpl.grouped_orders",                    "pbi_bnpl.bnpl_grouped_orders",           1,    0, "CRIT"),
    ("loss_rates",               "bnpl.loss_rates",                        "pbi_bnpl.bnpl_loss_rates",               1,    0, "CRIT"),
    ("revenue_comision",         "bnpl.loss_rates",                        "bnpl.revenue_comision",                  1,    0, "CRIT"),
    ("bnpl_par",                 "bnpl.par_snapshot",                      "pbi_bnpl.bnpl_par",                      1,    0, "CRIT"),
    ("months_closes",            "bnpl.par_snapshot",                      "pbi_bnpl.months_closes",                 1,    0, "CRIT"),
    ("vintage_analysis",         "bnpl.vintage_analysis",                  "pbi_bnpl.vintage_analysis",              1,    0, "CRIT"),
    ("grid_bnpl",                "bnpl.grid_bnpl",                         "pbi_bnpl.grid_bnpl",                     1,  -71, "WARN"),
    ("dim_ruta_actual",          "redshift_bnpl.estructura_comercial",     "bnpl.dim_ruta_actual",                   1,    0, "CRIT"),
    ("dim_ruta_cliente_scd",     "redshift_bnpl.ruta_cliente_scd",         "bnpl.dim_ruta_cliente_scd",              1,    0, "CRIT"),
    ("cosechas_agg",             "redshift_bnpl.cosechas_agg",             "pbi_bnpl.bnpl_cosechas_agg",             1,    0, "CRIT"),
    ("seasonality_delta",        "redshift_bnpl.estacionalidad_mes",       "pbi_bnpl.seasonality_delta",            11,    0, "CRIT"),
    ("odds_combinations",        "archivos_bnpl.odds_combinations",        "pbi_bnpl.odds_combinations",             1,    0, "WARN"),
    ("atr_combinations_iv",      "archivos_bnpl.atr_combinations_iv",      "pbi_bnpl.atr_combinations_iv",           1,    0, "WARN"),
    ("ps_transactional_profile", "archivos_bnpl.ps_transactional_profile", "pbi_bnpl.ps_transactional_profile",      1,    0, "WARN"),
    ("bnpl_cac",                 "archivos_bnpl.bnpl_cac",                 "pbi_bnpl.bnpl_cac",                      1,    0, "WARN"),
]

CHECKS += [
    {
        "name": f"identidad_{nombre}",
        "tabla": destino,
        "requiere": [],          # no aplica: la guarda de columnas mira solo el staging
        "db": DB_BNPL,
        "severidad": severidad,
        "detalle": f"count({destino}) debe ser count({origen}) * {factor} {delta:+d}",
        # n = filas de mas o de menos. 0 = la identidad se cumple.
        "sql": f"""select abs(
                       (select count(*) from {destino})
                       - ((select count(*) from {origen}) * {factor} + ({delta}))
                   )::bigint as n""",
    }
    for nombre, origen, destino, factor, delta, severidad in IDENTIDADES
]


# --- ops/quality_checks.py, dentro de correr_checks(): reemplazar la linea 140 ---
        # Cada check declara contra que alias corre; los del staging no declaran nada y siguen
        # cayendo en DB_STAGING, igual que antes.
        try:
            n = int(extract_sql(check["sql"], db=check.get("db", DB_STAGING))["n"].iloc[0])
        except Exception as e:
            # Misma semantica que la guarda de columnas: una relacion que no existe se registra
            # como NO_APLICABLE y queda visible, en vez de tumbar los otros checks.
            filas.append({
                "checked_at": checked_at,
                "check_name": check["name"],
                "tabla": tabla,
                "n_filas": None,
                "severidad": check["severidad"],
                "resultado": "NO_APLICABLE",
                "detalle": str(e).splitlines()[0][:200],
            })
            continue
```

**Verificar:**

```
.venv\Scripts\python.exe ops\quality_checks.py -- la tabla impresa debe traer 23 renglones, los 15 identidad_* con 0 filas y resultado OK. Confirmar con: select check_name, n_filas, resultado from bnpl_ops.data_quality_checks where checked_at = (select max(checked_at) from bnpl_ops.data_quality_checks) and check_name like 'identidad_%' order by 1
```

> **Nota.** El -71 de grid_bnpl va como WARN a proposito: README.md:425-431 explica que es correcto hoy pero que puede moverse, y un CRIT que hay que ignorar deja de leerse. El de seasonality_delta usa factor 11 (12 meses -> 132 filas), como dice README.md:422. Los 15 corren contra el alias bnpl, que segun README.md:478 ya lee bnpl, pbi_bnpl y archivos_bnpl; redshift_bnpl no esta en esa lista — si el alias no lo alcanza, esas tres filas saldran NO_APLICABLE con el error de permisos, que es informacion util, no un fallo silencioso.

### O2.11+O2.12 · Emitir las alertas de calidad con el nivel de su severidad y marcar las que son nuevas respecto a la corrida anterior

`main.py:35-36 (imports) y :153-156` · riesgo bajo · ~1 h

Las mismas 2 alertas cronicas salen todos los dias como WARNING; una tercera que aparezca se pierde en el ruido, y las dos de severidad CRIT se ven igual que las WARN. Con esto un CRIT sale como ERROR y lo nuevo queda etiquetado NUEVA, que es lo unico que hay que perseguir.

**Hoy:**

```
from config import DB_OPS_RW, FUENTES_CRITICAS, TZ_OFFSET_HOURS
from postgres_local_client import execute_sql

[... en run() ...]
        log.info("[5/6] Chequeos de calidad")
        alertas = [f for f in quality_checks.run() if f["resultado"] == "ALERTA"]
        for a in alertas:
            log.warning("calidad — %s: %s filas (%s)", a["check_name"], a["n_filas"], a["detalle"])
```

**Queda:**

```
# 1) imports (linea 35-36)
from config import DB_OPS, DB_OPS_RW, FUENTES_CRITICAS, TZ_OFFSET_HOURS
from postgres_local_client import execute_sql, extract_sql

# 2) dos funciones nuevas, junto a _revisar_frescura

def _alertas_previas() -> set:
    """Checks que ya estaban en alerta en la corrida ANTERIOR.

    quality_checks.run() ya persistio la corrida de hoy, asi que la anterior es el
    segundo checked_at mas alto. Sirve para distinguir las dos alertas cronicas
    (README.md:365-371) de una que aparecio hoy.
    """
    df = extract_sql(
        "SELECT check_name FROM bnpl_ops.data_quality_checks "
        "WHERE resultado <> 'OK' AND checked_at = ("
        "    SELECT max(checked_at) FROM bnpl_ops.data_quality_checks "
        "    WHERE checked_at < (SELECT max(checked_at) FROM bnpl_ops.data_quality_checks))",
        db=DB_OPS,
    )
    return set(df["check_name"])


def _reportar_calidad(log, filas: list) -> None:
    """Reporta las alertas con el nivel que les toca y el orden de v_quality_alerts.

    Antes todo salia como log.warning sin mirar `severidad`, y dos de los ocho checks son
    CRIT (ops/quality_checks.py:19 y :28). El criterio y el orden son los mismos de
    bnpl_ops.v_quality_alerts (sql/00_bnpl_ops.sql:97-102) para que el log y la vista que
    manda consultar README:348 digan lo mismo: CRIT primero, luego por n_filas.
    Tambien entra NO_APLICABLE, que es como la vista trata a un check sin su columna.
    """
    alertas = [f for f in filas if f["resultado"] != "OK"]
    if not alertas:
        log.info("calidad: los %d chequeos en OK", len(filas))
        return

    previas = _alertas_previas()
    orden = {"CRIT": 0, "WARN": 1}
    for a in sorted(alertas, key=lambda x: (orden.get(x["severidad"], 2), -(x["n_filas"] or 0))):
        emisor = log.error if a["severidad"] == "CRIT" else log.warning
        emisor(
            "calidad %s%s — %s: %s filas (%s)",
            a["severidad"],
            "" if a["check_name"] in previas else " NUEVA",
            a["check_name"],
            f"{a['n_filas']:,}" if a["n_filas"] is not None else "-",
            a["detalle"],
        )

    nuevas = [a["check_name"] for a in alertas if a["check_name"] not in previas]
    if nuevas:
        log.error("calidad: %d alerta(s) que no estaban ayer: %s", len(nuevas), ", ".join(nuevas))
    log.info("Detalle ordenado: select * from bnpl_ops.v_quality_alerts;")

# 3) en run(), el paso [5/6]
        log.info("[5/6] Chequeos de calidad")
        _reportar_calidad(log, quality_checks.run())
```

**Verificar:**

```
.venv\Scripts\python.exe -c "import logging, main; logging.basicConfig(level=logging.INFO); main._reportar_calidad(logging.getLogger('t'), [{'check_name':'inventado','severidad':'CRIT','resultado':'ALERTA','n_filas':3,'detalle':'prueba'}])"
Debe salir como ERROR y con la marca NUEVA. Contra la vista: select * from bnpl_ops.v_quality_alerts;
```

> **Ajuste del revisor.** Reemplaza los dos docstrings por estos, con las referencias reales:

def _alertas_previas() -> set:
    """Checks que ya estaban en alerta en la corrida ANTERIOR.

    quality_checks.run() ya persistio la corrida de hoy, asi que la anterior es el
    segundo checked_at mas alto. Sirve para distinguir las dos alertas cronicas
    (README.md:392-397) de una que aparecio hoy.
    """

def _reportar_calidad(log, filas: list) -> None:
    """Reporta las alertas con el nivel que les toca y el orden de v_quality_alerts.

    Antes todo salia como log.warning sin mirar `severidad`, y dos de los ocho checks son
    CRIT (ops/quality_checks.py:19 y :28). El criterio y el orden son los mismos de
    bnpl_ops.v_quality_alerts (sql/00_bnpl_ops.sql:97-102) para que el log y la vista que
    manda consultar README.md:375 digan lo mismo: CRIT primero, luego por n_filas.
    Tambien entra NO_APLICABLE, que es como la vista trata a un check sin su columna.
    """

El resto del cambio (imports, cuerpo de las funciones y el paso [5/6]) se queda igual.

> **Nota.** Deliberadamente NO se hace que un CRIT de calidad aborte la corrida: los dos checks CRIT (salesOrderId nulo y COMPLETED sin deliveryAt) llevan ~1,469 filas cronicas de basura de origen, asi que abortar por ellos apagaria el tablero todos los dias. Se sube el nivel del log y se marca la novedad; convertirlos en compuerta requiere primero limpiar la fuente.

### O2.11+O2.12 · parte b · Haz que una identidad rota marque la corrida como fallida en vez de esconderla en un WARNING

`main.py:153-156 y 167-170` · riesgo bajo · minutos · depende de: la accion que agrega las 15 identidades a ops/quality_checks.py

Hoy todo lo que sale de quality_checks se registra como log.warning y el pipeline devuelve 0 pase lo que pase. Sin esto, agregar las 15 identidades no cambia nada operativamente: nadie lee los WARNING del log.

**Hoy:**

```
log.info("[5/6] Chequeos de calidad")
        alertas = [f for f in quality_checks.run() if f["resultado"] == "ALERTA"]
        for a in alertas:
            log.warning("calidad — %s: %s filas (%s)", a["check_name"], a["n_filas"], a["detalle"])

[main.py:167-170]
        segundos = time.time() - t0
        log.info("Pipeline terminado en %.1f min", segundos / 60)
        _registrar_corrida(inicio, segundos, "ok")
        return 0
```

**Queda:**

```
log.info("[5/6] Chequeos de calidad")
        alertas = [f for f in quality_checks.run() if f["resultado"] == "ALERTA"]
        # Las identidades entre capas son distintas del resto: no describen basura del origen sino
        # una capa que se quedo a medias. Si una no cuadra, el tablero va a leer numeros que no
        # cruzan entre si.
        rotas = [a for a in alertas if a["check_name"].startswith("identidad_")
                 and a["severidad"] == "CRIT"]
        for a in alertas:
            registrar = log.error if a in rotas else log.warning
            registrar("calidad — %s: %s filas (%s)", a["check_name"], a["n_filas"], a["detalle"])

[main.py:167-170]
        segundos = time.time() - t0
        # Se termina la corrida completa (la frescura final ya quedo registrada) pero se sale con
        # 1 para que el Task Scheduler la marque como fallida. Un pipeline que devuelve 0 con una
        # identidad rota es un pipeline que miente.
        resultado = "ok" if not rotas else "ok_identidades_rotas"
        log.info("Pipeline terminado en %.1f min", segundos / 60)
        _registrar_corrida(inicio, segundos, resultado)
        return 0 if not rotas else 1
```

**Verificar:**

```
Provocar el caso a proposito en una base de prueba: drop view pbi_bnpl.bnpl_par; luego .venv\Scripts\python.exe main.py --sin-redshift y revisar `echo $LASTEXITCODE` (debe ser 1) y select modo from bnpl_ops.etl_runs where tabla='pipeline' order by started_at desc limit 1
```

> **Ajuste del revisor.** Verificacion que si prueba el cambio (rompe la identidad a proposito, sin tocar la base):

1. En ops/quality_checks.py, dentro de IDENTIDADES, cambiar temporalmente el delta de la primera fila:
   ("grouped_orders", "bnpl.grouped_orders", "pbi_bnpl.bnpl_grouped_orders", 1, 1, "CRIT"),
   (el delta 1 hace que n=1 -> resultado ALERTA con severidad CRIT)

2. PowerShell:
   .venv\Scripts\python.exe main.py --sin-redshift
   $LASTEXITCODE          # debe ser 1

3. En la base:
   select modo from bnpl_ops.etl_runs where tabla='pipeline' order by started_at desc limit 1;
   -- debe decir ok_identidades_rotas
   select check_name, n_filas, resultado, severidad from bnpl_ops.data_quality_checks
   where checked_at = (select max(checked_at) from bnpl_ops.data_quality_checks)
     and check_name = 'identidad_grouped_orders';
   -- 1 fila, ALERTA, CRIT

4. Revertir el delta a 0, volver a correr main.py --sin-redshift y confirmar $LASTEXITCODE = 0 y modo='ok'.

Aparte, considerar que las identidades CRIT que salgan NO_APLICABLE tambien cuenten como rotas, porque hoy se escapan:

        rotas = [a for a in quality_checks_filas
                 if a["check_name"].startswith("identidad_") and a["severidad"] == "CRIT"
                 and a["resultado"] in ("ALERTA", "NO_APLICABLE")]

> **Nota.** El filtro por prefijo identidad_ NO es cosmetico y hay que dejarlo: credit_order_sales_order_id_nulo ya esta declarado CRIT (quality_checks.py:19) y segun README.md:369 vive permanentemente en ALERTA con ~1,469 filas por basura de origen. Escalar todo lo CRIT haria fallar el pipeline todos los dias desde el primero. Aparte de esto vale la pena rebajar ese check a WARN, que es lo que el README dice que es en realidad.

### O2.13 · Haz que las dos cargas manuales dejen rastro en etl_runs y agrégales un chequeo de antigüedad

`carga_archivos_bnpl.py:19-28 y :96-115 · carga_clientes_concurso.py:114-120 · ops/quality_checks.py:10 y :103 · README.md:294-296` · riesgo bajo · media jornada · depende de: El chequeo `cargas_manuales_viejas` solo tiene sentido después de los puntos 1-3: hasta que las cargas registren, dará ALERTA por "sin registro" en las cinco tablas. Es correcto —hoy nadie sabe cuándo se cargaron— pero hay que aplicarlo en ese orden.

Son los únicos datos del tablero sin bitácora, sin semáforo de frescura y sin chequeo de calidad: nada avisa si un archivo lleva meses viejo. Dos de los cuatro CSV ya tienen 7 y 8 meses (PENDIENTES §10-11) y eso se descubrió a mano, no por una alerta.

**Hoy:**

```
carga_archivos_bnpl.py:19-28
import argparse
from pathlib import Path

import pandas as pd
from postgres_local_client import transaction

BASE_DIR = Path(__file__).resolve().parent

SCHEMA = "archivos_bnpl"
DB_RW = "bnpl_rw"

carga_archivos_bnpl.py:104-115
        df = _leer(nombre, cfg)
        print(f"{nombre}: {len(df):,} filas x {len(df.columns)} columnas  <- {cfg['ruta'].name}")

        if dry_run:
            print(f"    (dry-run) tipos: {dict(df.dtypes.astype(str))}")
            continue

        with transaction(db=DB_RW) as tx:
            tx.execute_sql(ddl)
            tx.execute_sql(f'TRUNCATE {SCHEMA}."{nombre}"')
            tx.load_dataframe(df, nombre, schema=SCHEMA)
        print(f"    -> {SCHEMA}.{nombre} cargada")

ops/quality_checks.py:10
from config import DB_OPS_RW, DB_STAGING, STAGING_SCHEMA, TZ_OFFSET_HOURS

ops/quality_checks.py:140
        n = int(extract_sql(check["sql"], db=DB_STAGING)["n"].iloc[0])

README.md:294-296
> **Limitación conocida:** `carga_archivos_bnpl.py` **no** escribe en `bnpl_ops.etl_runs`, así que no
> hay registro de cuándo se cargó cada archivo. El conteo de filas es hoy la única señal. Vale la
> pena agregarle la bitácora, como la tienen los demás scripts.
```

**Queda:**

```
1) `carga_archivos_bnpl.py` — encabezado (reemplaza las líneas 19-28):

import argparse
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from postgres_local_client import execute_sql, transaction

BASE_DIR = Path(__file__).resolve().parent

SCHEMA = "archivos_bnpl"
DB_RW = "bnpl_rw"
DB_OPS_RW = "bnpl_ops_rw"
TZ_OFFSET_HOURS = -6  # las fechas del pipeline van en hora Mexico, igual que ops/config.py:19


def _ahora_mx() -> datetime:
    return (datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)).replace(tzinfo=None)


def _registrar(tabla: str, filas: int, segundos: float, inicio) -> None:
    """Misma bitacora que el resto del pipeline. Sin esto no hay forma de saber cuando se
    cargo cada archivo: el conteo de filas es la unica senal, y no distingue recarga de
    archivo sin cambios."""
    execute_sql(
        "INSERT INTO bnpl_ops.etl_runs (started_at, tabla, modo, filas, segundos) "
        "VALUES (:inicio, :tabla, 'manual', :filas, :segundos) "
        "ON CONFLICT (started_at, tabla) DO NOTHING",
        {"inicio": inicio, "tabla": f"{SCHEMA}.{tabla}", "filas": int(filas),
         "segundos": round(segundos, 1)},
        db=DB_OPS_RW,
    )

2) `carga_archivos_bnpl.py` — cuerpo del ciclo (reemplaza las líneas 104-115):

        df = _leer(nombre, cfg)
        print(f"{nombre}: {len(df):,} filas x {len(df.columns)} columnas  <- {cfg['ruta'].name}")

        if dry_run:
            print(f"    (dry-run) tipos: {dict(df.dtypes.astype(str))}")
            continue

        inicio, t0 = _ahora_mx(), time.time()
        with transaction(db=DB_RW) as tx:
            tx.execute_sql(ddl)
            tx.execute_sql(f'TRUNCATE {SCHEMA}."{nombre}"')
            tx.load_dataframe(df, nombre, schema=SCHEMA)
        # Fuera de la transaccion a proposito: la bitacora va a otro alias y no debe poder
        # tumbar una carga que ya quedo bien.
        _registrar(nombre, len(df), time.time() - t0, inicio)
        print(f"    -> {SCHEMA}.{nombre} cargada")

3) `carga_clientes_concurso.py`: pegar los mismos `_ahora_mx` y `_registrar` (con
`tabla=f"bnpl.{TABLA}"`), tomar `inicio, t0` antes del `with transaction(...)` de la línea 116 y
llamar a `_registrar(TABLA, len(df), time.time() - t0, inicio)` después del bloque.

4) `ops/quality_checks.py` — noveno chequeo, agregar al final de `CHECKS` (después de la línea 103):

    {
        "name": "cargas_manuales_viejas",
        "tabla": "etl_runs",
        "requiere": [],   # no depende de columnas del staging
        "db": DB_OPS,
        "severidad": "WARN",
        "detalle": "Carga manual sin correr en 90 dias (o sin registro en etl_runs)",
        "sql": """select count(*) as n from (
                       select t.tabla,
                              (select max(started_at) from bnpl_ops.etl_runs r
                                where r.tabla = t.tabla) as ultima
                       from (values ('archivos_bnpl.odds_combinations'),
                                    ('archivos_bnpl.atr_combinations_iv'),
                                    ('archivos_bnpl.ps_transactional_profile'),
                                    ('archivos_bnpl.bnpl_cac'),
                                    ('bnpl.bnpl_clientes_concurso')) as t(tabla)
                   ) x
                   where ultima is null or ultima < current_date - 90""",
    },

y las dos líneas que lo habilitan:

  línea 10:  from config import DB_OPS, DB_OPS_RW, DB_STAGING, STAGING_SCHEMA, TZ_OFFSET_HOURS
  línea 140: n = int(extract_sql(check["sql"], db=check.get("db", DB_STAGING))["n"].iloc[0])

5) README.md:294-296 →

> **Cuándo se cargó cada archivo:** desde el <fecha>, las dos cargas manuales sí escriben en
> `bnpl_ops.etl_runs` con `modo = 'manual'`. Para verlo:
>
> ```sql
> select tabla, max(started_at) as ultima_carga, max(filas) as filas
> from bnpl_ops.etl_runs
> where tabla like 'archivos_bnpl.%' or tabla = 'bnpl.bnpl_clientes_concurso'
> group by tabla order by ultima_carga;
> ```
>
> Y el chequeo `cargas_manuales_viejas` de `ops/quality_checks.py` levanta un WARN si alguna lleva
> más de 90 días sin recargarse o nunca se registró.
```

**Verificar:**

```
.venv\Scripts\python.exe carga_archivos_bnpl.py --solo bnpl_cac
psql: select * from bnpl_ops.etl_runs where tabla like 'archivos_bnpl.%' order by started_at desc limit 5;   # debe traer la fila con modo='manual'
.venv\Scripts\python.exe ops\quality_checks.py    # ahora imprime 9 chequeos; cargas_manuales_viejas debe dar ALERTA hasta que las cinco tablas tengan registro fresco
```

> **Ajuste del revisor.** Punto 3, escrito como código pegable en carga_clientes_concurso.py (no como descripción):

  a) En el encabezado, reemplazar :16-20 por:

import argparse
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from postgres_local_client import execute_sql, transaction

  b) Después de `DB_RW = "bnpl_rw"` (:26), pegar `_ahora_mx` y `_registrar` TAL CUAL están en carga_archivos_bnpl.py, sin tocar `f"{SCHEMA}.{tabla}"`: ahí `SCHEMA` ya vale "bnpl" y produce `bnpl.bnpl_clientes_concurso`. Agregar también `DB_OPS_RW = "bnpl_ops_rw"` y `TZ_OFFSET_HOURS = -6`.

  c) Reemplazar :116-120 por:

    inicio, t0 = _ahora_mx(), time.time()
    with transaction(db=DB_RW) as tx:
        tx.execute_sql((BASE_DIR / "sql" / "13_bnpl_clientes_concurso.sql").read_text(
            encoding="utf-8"))
        tx.execute_sql(f'TRUNCATE {SCHEMA}."{TABLA}"')
        tx.load_dataframe(df, TABLA, schema=SCHEMA)
    # Fuera de la transaccion a proposito: la bitacora va a otro alias.
    _registrar(TABLA, len(df), time.time() - t0, inicio)

Anclaje real del punto 5: el recuadro «Limitación conocida» es README.md:300-302, no :294-296.

Y coordinar con la acción 3: si se aplican las dos, esa sección del README debe decir «nueve chequeos» e incluir la fila de `cargas_manuales_viejas`; la verificación pasa a «imprime los 9». Aplicar 13 antes que 3, o escribir 3 ya en nueve.

> **Nota.** Un detalle a verificar al aplicar: el chequeo nuevo corre con el alias `bnpl_ops` (solo lectura) contra el schema `bnpl_ops`, no con el del staging; por eso hace falta la clave `db` en el dict y el `check.get("db", DB_STAGING)`. Si ese alias no tuviera SELECT sobre `bnpl_ops.etl_runs`, el chequeo truena — probarlo antes de meterlo a main.py. El umbral de 90 días es una propuesta: para `bnpl_cac` y `odds_combinations`, que se publican por trimestre, 90 es razonable; si negocio define otra cadencia, es una constante.

### O2.14 · Mandar el detalle por tabla de los tres ETL al log en vez de a stdout

`etl_mongo_to_postgres.py:412,473,483-488,499; etl_redshift_to_postgres.py:338,350,357,364,373,389,395; build_bnpl.py:80,120,131,144` · riesgo bajo · ~1 h · depende de: accion 1 (toca las mismas lineas de etl_mongo_to_postgres.py; aplicar primero la 1 y luego esta sobre el resultado)

Los tres ETL reportan con print, que va a stdout y no al FileHandler de main.py. En las dos ultimas corridas no hay una sola linea de detalle por tabla entre [2/6] y [3/6], ni el aviso de recarga completa programada. Empeoro cuando main.py:80 subio postgres_local_client a WARNING, que era lo que dejaba rastro indirecto. Y como el .bat nunca ha corrido, hoy ese detalle se pierde al cerrar la consola.

**Hoy:**

```
# etl_mongo_to_postgres.py:499
        print(f"  -> {SCHEMA}.{defn['table']}: {filas:,} filas en {segundos:.0f}s ({modo})")

# etl_redshift_to_postgres.py:338
    print(f"  -> {SCHEMA}.{nombre}: {len(df):,} filas en {segundos:.1f}s")

# build_bnpl.py:144
        print(f"bnpl.{vista}: {filas:,} filas en {segundos:.1f}s ({modo})")
```

**Queda:**

```
# En los TRES archivos: agrega `import logging` a los imports y, debajo de BASE_DIR:
log = logging.getLogger(__name__)

# Y en el bloque __main__ de cada uno, antes de run(), para que el detalle siga saliendo
# cuando se corre el script suelto (sin main.py no hay logging configurado y no se veria nada):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

# --- etl_mongo_to_postgres.py ---
:412   log.info("  recarga completa programada (%s)", motivo)
:473   log.info("Extrayendo %s...", defn["collection"])
:483   log.info(
           "  ventana %dd + %s %s en estado no final",
           VENTANA_DIAS, f"{len(llaves):,}", defn["llave_refresco"],
       )
:488   log.info("  ventana %dd", VENTANA_DIAS)
:499   log.info(
           "  -> %s.%s: %s filas en %.0fs (%s)",
           SCHEMA, defn["table"], f"{filas:,}", segundos, modo,
       )

# --- etl_redshift_to_postgres.py ---
:338   log.info("  -> %s.%s: %s filas en %.1fs", SCHEMA, nombre, f"{len(df):,}", segundos)
:350   log.info("Extrayendo estructura comercial (ruta vigente)...")
:357   log.info("Extrayendo catalogo de rutas...")
:364   log.info("Extrayendo ruta historica de %s clientes con credito...", f"{len(universo):,}")
:373   log.info("Extrayendo venta Rabbit completa de %s clientes con credito...", f"{len(universo):,}")
:389   log.info("Agregando cosechas de la base Rabbit completa...")
:395   log.info("Calculando estacionalidad por mes calendario...")

# --- build_bnpl.py ---
:80    log.info("%s: %d vistas creadas para Power BI", PBI_SCHEMA, len(archivos))
:120   log.info("%s: aplicado (%.1fs)", archivo, time.time() - t0)
:131   log.info("bnpl.%s: %s filas (creada junto con la anterior)", vista, f"{filas:,}")
:144   log.info("bnpl.%s: %s filas en %.1fs (%s)", vista, f"{filas:,}", segundos, modo)

# --- mismo patron, opcional pero recomendado, en ops/ ---
# ops/check_freshness.py:222,224,231-238 y ops/quality_checks.py:171-176 imprimen las dos
# tablas de diagnostico (frescura por coleccion y resultado por check) y tampoco llegan al
# archivo. Es el mismo cambio: log = logging.getLogger(__name__) y print(...) -> log.info(...).
```

**Verificar:**

```
Despues de una corrida:
  Select-String -Path logs\pipeline_2026-08.log -Pattern '  -> mongo_bnpl\.' | Select-Object -Last 10
Deben salir las 10 lineas de tabla. Antes de correr nada:
  Select-String -Path etl_mongo_to_postgres.py,etl_redshift_to_postgres.py,build_bnpl.py -Pattern '^\s*print\('
debe devolver cero resultados.
```

> **Nota.** Ojo con el formato: se pasan los argumentos a log.info() en vez de interpolar con f-string, porque el separador de miles (:,) no existe en %-format; por eso los conteos van preformateados como f"{n:,}". El basicConfig del __main__ no lleva el converter de hora Mexico de main.py:48-52, asi que una corrida suelta estampa hora del SO (UTC); es aceptable para depuracion manual, pero si molesta, copia _hora_mx y asignalo al formatter.

### O2.15 · Corregir el WARNING del SessionId: moverlo al cierre, donde el reintento ya resolvio el problema

`C:/Users/Administrator/Documents/Funciones/mongo_extractor/src/mongo_extractor/tunnels/ssm.py:258-292 (fuera del repo BNPL)` · riesgo medio · minutos

Hoy el WARNING sale en el 100% de las corridas y dice que la sesion quedara Active, cuando lo mas probable es que se este cerrando bien. Es un aviso que nadie puede accionar y que entrena a ignorar los WARNING del log, justo donde ahora se van a emitir las alertas de calidad que si importan.

**Hoy:**

```
_esperar_arranque(proc, params.local_port, salida)

        session_id = _extraer_session_id(salida)
        if session_id is None:
            log.warning(
                "No se pudo parsear el SessionId de la salida del forwarder. El tunel "
                "funciona, pero al cerrar no se podra terminar la sesion en AWS: "
                "quedara Active hasta que el idle timeout la barra."
            )

[... y en el finally ...]
        if session_id is None:
            session_id = _extraer_session_id(salida)

        if session_id is not None:
            try:
                boto3.client("ssm", region_name=params.aws_region).terminate_session(
                    SessionId=session_id
                )
```

**Queda:**

```
_esperar_arranque(proc, params.local_port, salida)

        session_id = _extraer_session_id(salida)
        if session_id is None:
            # A esta altura el puerto ya escucha pero la linea "Starting session with
            # SessionId: ..." puede no estar todavia en el archivo de salida. NO es un
            # problema: el finally vuelve a parsear con el proceso ya muerto y la salida
            # completa, y ahi si cierra la sesion. Se deja en DEBUG; el WARNING solo se
            # emite si el segundo intento tampoco la encuentra, que es el unico caso en
            # que de verdad queda una sesion Active en AWS.
            log.debug(
                "SessionId aun no disponible al arrancar el tunel; se reintenta al cerrar."
            )

[... y en el finally ...]
        if session_id is None:
            session_id = _extraer_session_id(salida)
            if session_id is None:
                log.warning(
                    "No se pudo parsear el SessionId de la salida del forwarder ni al "
                    "cerrar. La sesion de SSM quedara Active hasta que el idle timeout de "
                    "AWS la barra. Auditar con: aws ssm describe-sessions --state Active "
                    "--region %s",
                    params.aws_region,
                )

        if session_id is not None:
            try:
                boto3.client("ssm", region_name=params.aws_region).terminate_session(
                    SessionId=session_id
                )
```

**Verificar:**

```
Antes de tocar nada, medir si el hallazgo es real:
  aws ssm describe-sessions --state Active --region us-east-2 --query "Sessions[].[SessionId,StartDate]" --output table
Correr el pipeline y volver a consultar: si la lista queda vacia, las sesiones SI se cerraban y el WARNING era falsa alarma. Despues del cambio, el log no debe traer la linea del SessionId y el conteo de sesiones Active debe seguir en cero.
```

> **Nota.** HALLAZGO MAL PLANTEADO. La auditoria dice que "cada corrida deja una sesion SSM Active en AWS"; leyendo ssm.py eso no se sostiene. El WARNING se emite en la linea 261 justo despues de que el puerto queda escuchando, pero el bloque finally (:278-279) vuelve a parsear el SessionId con el proceso ya muerto y la salida completa, y si lo encuentra llama a terminate_session. En las cuatro apariciones del log (lineas 7, 100, 442, 471) NUNCA aparece el segundo WARNING, el de "No se pudo terminar la sesion de SSM", asi que el cierre esta funcionando: lo que hay es ruido, no una fuga. Antes de cambiar codigo, confirmalo con el describe-sessions de la verificacion. Dos avisos: el archivo esta FUERA del repo BNPL y la libreria la usan otros proyectos (perfil tx, jump-host SSH), asi que va con PR en su propio repo (russellquiroz-spec/mongo_extractor) y despues hay que actualizar el commit anclado en requirements.txt (accion 7).

### O2.16 · Fijar el entorno: requirements.txt con el freeze real de la VM y las tres librerias internas ancladas por commit

`requirements.txt (nuevo) y README.md:634-651` · sin riesgo · minutos

No existe requirements.txt, pyproject ni lock: el README instala cuatro paquetes sin fijar version y las tres librerias por las que pasa TODA la extraccion se instalan editable desde una ruta local sin referencia fijada. Hoy la unica documentacion del entorno es el pip freeze de la VM, que no esta escrito en ningun lado; si la VM se pierde, no hay como reconstruir con que versiones se midio esto.

**Hoy:**

```
```powershell
git clone https://github.com/russellquiroz-spec/buy_now_pay_later.git
cd buy_now_pay_later
python -m venv .venv
.venv\Scripts\python.exe -m pip install pandas python-dotenv openpyxl matplotlib
```

[...]

**2. Instalar las librerías internas** (editable, desde donde estén en la VM):

```powershell
.venv\Scripts\python.exe -m pip install -e <ruta>\mongo_extractor
.venv\Scripts\python.exe -m pip install -e <ruta>\redshift_extractor
.venv\Scripts\python.exe -m pip install -e <ruta>\postgresql_extractor_uploader
```
```

**Queda:**

```
# ============ requirements.txt (archivo nuevo, en la raiz) ============
# Entorno del pipeline BNPL. Python 3.13.2 en la VM rabbit-bi-local.
# Generado con: .venv\Scripts\python.exe -m pip freeze > requirements.txt
# Reinstalar todo:  .venv\Scripts\python.exe -m pip install -r requirements.txt
#
# Las tres librerias internas van fijadas por COMMIT, no por ruta local: una VM nueva
# instala exactamente el codigo con el que se midio este pipeline. redshift_extractor va
# por SSH y necesita la llave de deploy en la maquina; sin ella, cambia el prefijo a
# https://github.com/russellquiroz-spec/redshift_extractor.git y usa un PAT.
-e git+https://github.com/russellquiroz-spec/mongo_extractor.git@03958bc93aeb88dbe8cfc368f3857e4eef7e2f58#egg=mongo_extractor
-e git+ssh://git@github.com/russellquiroz-spec/redshift_extractor.git@b34c3437f7ae7fd5f17c3a6b4e5ba6bf2d2ef876#egg=redshift_extractor
-e git+https://github.com/russellquiroz-spec/postgresql_extractor_uploader.git@fe8633c2b9286661030a17f825dee7b7e8bbb590#egg=postgres_local_client
annotated-doc==0.0.5
bcrypt==5.0.0
boto3==1.43.70
botocore==1.43.70
cffi==2.1.1
colorama==0.4.6
contourpy==1.3.3
cryptography==50.0.0
cycler==0.12.1
dnspython==2.8.0
et_xmlfile==2.0.0
fonttools==4.63.0
greenlet==3.5.5
jaraco.classes==3.4.0
jaraco.context==6.1.2
jaraco.functools==4.6.0
jmespath==1.1.0
keyring==25.7.0
kiwisolver==1.5.0
markdown-it-py==4.2.0
matplotlib==3.11.1
mdurl==0.1.2
more-itertools==11.1.0
numpy==2.5.2
openpyxl==3.1.5
packaging==26.3
pandas==3.0.5
paramiko==3.5.1
pillow==12.3.0
psycopg==3.3.4
psycopg-binary==3.3.4
psycopg2-binary==2.9.12
pyarrow==25.0.1
pycparser==3.0
Pygments==2.20.0
pymongo==4.6.3
PyNaCl==1.6.2
pyparsing==3.3.2
python-dateutil==2.9.0.post0
python-dotenv==1.0.1
pywin32-ctypes==0.2.3
rich==15.0.0
s3transfer==0.19.2
shellingham==1.5.4
six==1.17.0
SQLAlchemy==2.0.52
sqlglot==30.17.0
sshtunnel==0.4.0
typer==0.27.1
typing_extensions==4.16.0
tzdata==2026.3
urllib3==2.7.0

# ============ README.md, pasos 1 y 2 ============
```powershell
git clone https://github.com/russellquiroz-spec/buy_now_pay_later.git
cd buy_now_pay_later
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` trae **todo**, incluidas las tres librerías internas fijadas por commit,
así que el paso 2 de instalarlas a mano desde `C:\Users\Administrator\Documents\Funciones\`
ya no existe. Si vas a **modificar** una de esas librerías, clónala aparte y reinstálala
con `-e <ruta>` encima; al terminar, actualiza el commit en `requirements.txt`.
```

**Verificar:**

```
.venv\Scripts\python.exe -m pip freeze > $env:TEMP\freeze.txt
Compare-Object (Get-Content requirements.txt | Where-Object {$_ -notmatch '^#' -and $_ -ne ''}) (Get-Content $env:TEMP\freeze.txt)
No debe devolver ninguna diferencia.
```

> **Ajuste del revisor.** Antes de escribir el archivo, dejar limpios los tres repos y volver a leer los SHAs:

  git -C C:\Users\Administrator\Documents\Funciones\postgresql_extractor_uploader status --porcelain   # tiene que salir vacio
  git -C C:\Users\Administrator\Documents\Funciones\postgresql_extractor_uploader add -A; git -C ... commit -m "..."; git -C ... push
  .venv\Scripts\python.exe -m pip freeze > requirements.txt   # y encima se le pegan los comentarios de cabecera

Y en README.md, sustituir de la linea 661 a la 678 (no 634-651) por:

```powershell
git clone https://github.com/russellquiroz-spec/buy_now_pay_later.git
cd buy_now_pay_later
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` trae **todo**: las 52 dependencias con version exacta y las tres librerias
internas fijadas por commit. Ya no hay un paso 2 de instalarlas a mano desde
`C:\Users\Administrator\Documents\Funciones\`, ni hay que acordarse de que `SQLAlchemy`,
`psycopg` y `sshtunnel` entraban de arrastre. Si vas a **modificar** una de esas librerias,
clonala aparte y reinstalala con `-e <ruta>` encima; al terminar, commitea alla y actualiza
el SHA aqui — un pin que apunta a un arbol sucio no reproduce nada.

(o sea: el reemplazo abarca tambien el parrafo de :668-670 y el bloque completo del paso 2, que desaparece)

> **Nota.** Los tres commits salen del pip freeze de hoy y son reales: mongo_extractor 03958bc, redshift_extractor b34c343, postgresql_extractor_uploader fe8633c (paquete instalado: postgres_local_client). Dos avisos: (1) el remoto de las tres es la cuenta personal russellquiroz-spec — mismo bus factor de uno que el repo del pipeline, vale la pena moverlos a la organizacion; (2) si aplicas la accion 9, el commit de mongo_extractor cambia y hay que actualizar esta linea.

### O2.17 · Agregar aviso por correo cuando el pipeline no termina bien

`ops/notificar.py (nuevo) y main.py:134-175` · riesgo bajo · ~1 h

> **Mitad técnica.** La decisión de fondo va a `PENDIENTES_NEGOCIO.md`; lo de aquí abajo se puede hacer sin esperar respuesta.

Hoy no hay ninguna notificacion: el unico manejo de fallo es un echo a logs\scheduler.log, archivo que ni siquiera existe. Si el pipeline muere a las 05:30 nadie se entera hasta que alguien abre el tablero y ve datos de anteayer.

**Queda:**

```
# ============ ops/notificar.py (archivo nuevo) ============
"""Aviso por correo cuando la corrida del pipeline BNPL no termina bien.

Es lo mas simple que funciona en esta VM: SMTP autenticado sobre TLS contra el Workspace
de rabbitmx.com. No hace falta instalar un servidor de correo local (la VM no tiene uno),
ni un servicio nuevo, ni permisos extra de AWS: una libreria estandar y un secreto.

Si falta configuracion NO lanza: un fallo del aviso no puede convertirse en un segundo
fallo del pipeline, solo deja un WARNING en el log.

Configuracion, en .env.bnpl_pipeline en la raiz del repo (ya gitignoreado por `.env.*`):

    BNPL_SMTP_HOST=smtp.gmail.com
    BNPL_SMTP_PORT=587
    BNPL_SMTP_USER=<cuenta que envia>
    BNPL_SMTP_PASSWORD=<app password de 16 caracteres, NO la contrasena de la cuenta>
    BNPL_ALERTA_PARA=russell.quiroz@rabbitmx.com,<quien mas deba enterarse>
"""
import os
import smtplib
import socket
from email.message import EmailMessage
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ARCHIVO_ENV = BASE_DIR / ".env.bnpl_pipeline"
COLA_LINEAS = 60


def _cargar_env() -> None:
    """Lee el .env propio del pipeline. Se lee aqui y no en los .env de las librerias
    internas, que son compartidos con los otros proyectos de la VM."""
    if not ARCHIVO_ENV.exists():
        return
    for linea in ARCHIVO_ENV.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip())


def _cola_del_log(archivo: Path) -> str:
    try:
        return "\n".join(archivo.read_text(encoding="utf-8").splitlines()[-COLA_LINEAS:])
    except Exception:
        return "(no se pudo leer el log)"


def avisar_fallo(resultado: str, archivo_log: Path, log) -> None:
    _cargar_env()
    destinos = [d.strip() for d in os.environ.get("BNPL_ALERTA_PARA", "").split(",") if d.strip()]
    host = os.environ.get("BNPL_SMTP_HOST")
    usuario = os.environ.get("BNPL_SMTP_USER")
    clave = os.environ.get("BNPL_SMTP_PASSWORD")

    if not (destinos and host and usuario and clave):
        log.warning(
            "Aviso por correo sin configurar (falta %s): este fallo no se le avisa a nadie.",
            ARCHIVO_ENV.name,
        )
        return

    msg = EmailMessage()
    msg["Subject"] = f"[BNPL] pipeline {resultado} en {socket.gethostname()}"
    msg["From"] = usuario
    msg["To"] = ", ".join(destinos)
    msg.set_content(
        f"El pipeline BNPL termino con resultado '{resultado}'.\n\n"
        f"Log completo en la VM: {archivo_log}\n\n"
        f"Ultimas {COLA_LINEAS} lineas:\n\n{_cola_del_log(archivo_log)}\n"
    )

    try:
        with smtplib.SMTP(host, int(os.environ.get("BNPL_SMTP_PORT", 587)), timeout=30) as smtp:
            smtp.starttls()
            smtp.login(usuario, clave)
            smtp.send_message(msg)
        log.info("Aviso de fallo enviado a %s", ", ".join(destinos))
    except Exception as exc:  # noqa: BLE001 - avisar nunca debe tumbar la corrida
        log.warning("No se pudo enviar el aviso de fallo: %s", exc)


# ============ main.py ============
# junto a los otros imports de ops (despues de `import check_freshness`):
import notificar

# en run(), los tres caminos de fallo:
        if not _revisar_frescura(log):
            log.error("Pipeline detenido: hay fuentes criticas sin actualizarse.")
            _registrar_corrida(inicio, time.time() - t0, "abortado_frescura")
            notificar.avisar_fallo("abortado_frescura", archivo, log)
            return 1

    except Exception:
        log.exception("Pipeline abortado por un error")
        _registrar_corrida(inicio, time.time() - t0, "error")
        notificar.avisar_fallo("error", archivo, log)
        return 1
```

**Verificar:**

```
.venv\Scripts\python.exe -c "import sys, logging; sys.path.insert(0,'ops'); import notificar; from pathlib import Path; logging.basicConfig(level=logging.INFO); notificar.avisar_fallo('prueba', Path('logs/pipeline_2026-08.log'), logging.getLogger('t'))"
Sin el .env debe salir el WARNING y NO reventar. Con el .env puesto, debe llegar el correo con las ultimas 60 lineas del log.
```

> **Nota.** Lo que SI se puede hacer hoy sin esperar a nadie: crear ops/notificar.py y enganchar main.py. El codigo degrada solo (WARNING en el log) hasta que exista el .env. Lo que hay que pedir: (a) un app password de Google Workspace para la cuenta que envia — requiere 2FA activo y que la politica del dominio no bloquee app passwords; idealmente una cuenta de servicio, no la personal de Russell; (b) la lista de a quien avisar. Si Workspace bloquea app passwords, la alternativa igual de simple es un webhook entrante de Slack: se cambia el cuerpo de avisar_fallo por un requests.post al webhook y el unico secreto es la URL. Hueco que queda abierto: si run_pipeline.bat falla ANTES de que arranque Python (.venv borrado, disco lleno), este aviso no corre; eso solo lo cubre revisar el LastTaskResult de la tarea (accion 5).

---

## OLA 3 — Modelo de Power BI y nombres

Regresiones de la migración que no cambian ninguna definición de negocio, más los nombres que hoy no distinguen dos cosas distintas. Esfuerzo ≈ 1.5 jornadas, más 1 jornada aparte para O3.14.

### O3.1 · Borrar las 3 consultas huerfanas 'Errores en...' que quedan en expressions.tmdl y sus 4 queryGroups

`pbi_new/Buy Now Pay Later.SemanticModel/definition/expressions.tmdl:1-69 y .../model.tmdl:9-27 (tras la accion 2: pbi/...)` · riesgo bajo · minutos · depende de: Accion 2 (para trabajar sobre la carpeta ya renombrada)

Son restos de tres inspecciones de errores de 2024 (los queryGroups estan fechados 28/06/2024, 07/08/2024 y 12/09/2024). No cargan ninguna tabla y leen del modelo, no de disco: no bloquean el refresh ni mueven una cifra. Se limpian por una sola razon — quien abra Power Query ve 3 consultas mas de las que hay tablas y no puede saber si son parte del modelo. Es opcional y va al final de la lista a proposito.

**Hoy:**

```
expressions.tmdl (69 lineas, 9,057 bytes) — 3 expresiones, ninguna cargada como tabla:
  1: expression 'Errores en bnpl_grouped_orders' =
  3:         Origen = bnpl_grouped_orders,
 13:   #"Conservar errores" = Table.SelectRowsWithErrors(#"Índice agregado", {"netsuiteId", ...})
 24: expression 'Errores en grid_bnpl' =
 47: expression 'Errores en grid_bnpl (2)' =

model.tmdl:9-27
/// Errores en las consultas cargadas en 28/06/2024 01:21:01 a. m..
queryGroup 'Errores en las consultas: 28/06/2024 01:21:01 a  m'

	annotation PBI_QueryGroupOrder = 0
... (3 bloques mas, hasta PBI_QueryGroupOrder = 3)
```

**Queda:**

```
# Ruta recomendada, desde Power BI Desktop (deja el TMDL consistente solo):
#   1. Abrir pbi\Buy Now Pay Later.pbip
#   2. Inicio > Transformar datos
#   3. En el panel izquierdo, borrar las 3 consultas:
#        'Errores en bnpl_grouped_orders', 'Errores en grid_bnpl', 'Errores en grid_bnpl (2)'
#      y los 4 grupos vacios 'Errores en las consultas: ...'
#   4. Cerrar y aplicar > Guardar

# Ruta a mano sobre el TMDL, si no hay Desktop disponible. Son tres cortes:
cd "C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later\pbi\Buy Now Pay Later.SemanticModel\definition"

# a) el archivo completo sobra: sus 3 expresiones son las unicas que quedan
Remove-Item "expressions.tmdl"

# b) en model.tmdl, borrar las lineas 9-27 completas (los 4 bloques queryGroup + sus annotation)
# c) en model.tmdl:29, quitar las 3 entradas del PBI_QueryOrder, que queda asi:
annotation PBI_QueryOrder = ["bnpl_grouped_orders","grid_bnpl","bnpl_loss_rates","bnpl_par","vintage_analysis","loans_matured_default_profile","vars_and_iv","odds_combinations","odds_table","atr_combinations_iv","months_closes","ps_transactional_profile","seasonality_delta","overall_prev_post_bnpl_sales","bnpl_audiencia_agg","bnpl_cac","bnpl_cosechas_agg"]
```

**Verificar:**

```
cd C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later; Test-Path "pbi\Buy Now Pay Later.SemanticModel\definition\expressions.tmdl"   # False
Select-String -Path "pbi\Buy Now Pay Later.SemanticModel\definition\model.tmdl" -Pattern "queryGroup|Errores en"   # vacio
# y despues abrir el .pbip: tiene que cargar sin error de TMDL
```

> **Nota.** HALLAZGO MAL PLANTEADO / YA RESUELTO. AUDITORIA.md:290 afirma que expressions.tmdl de pbi_new es byte a byte identico al de pbi/, con 19 expresiones, 8 Csv.Document (lineas 78, 104, 124, 150, 188, 200, 237, 249) y 4 SharePoint.Files (89, 135, 164, 214). Hoy en disco eso es FALSO: los SHA-256 difieren (pbi DA2F59E2..., pbi_new 927452A5...), pbi/ pesa 18,823 bytes y pbi_new/ 9,057, y el conteo en pbi_new/expressions.tmdl es Csv.Document=0, SharePoint.Files=0, File.Contents=0. El barrido sobre TODO el .SemanticModel de pbi_new devuelve una sola coincidencia, 'Consulta1' dentro de diagramLayout.json (posicion de un nodo, inocuo). La limpieza de las 16 consultas auxiliares sí se hizo: el archivo se guardo a las 06:58 del 2026-08-14, despues de la corrida de la auditoria (que vio model.tmdl a las 06:17). Consecuencia: README.md:581 y sql/pbi/README.md:123-124 NO mienten — son ciertos hoy. Lo unico que sobrevive son estas 3 consultas 'Errores en...', que no son origenes de archivo. Lo que sí sigue en pie del hallazgo es el hueco del comando de verificacion (accion 11).

### O3.2 · Borrar las cuatro tablas calculadas muertas: Clientes_Mensual, TablaParaGrafica, cohort_type y x_axis_type

`pbi_new/Buy Now Pay Later.SemanticModel/definition/model.tmdl:107,117,118,122 + definition/tables/{Clientes_Mensual,TablaParaGrafica,cohort_type,x_axis_type}.tmdl + relationships.tmdl:286-289 + tables/LocalDateTable_1f5c33d1-6555-4404-93a9-89efe3080eaa.tmdl` · riesgo bajo · ~1 h

Verificado con grep sobre los 196 visual.json: 'Entity": "Clientes_Mensual'=0, 'TablaParaGrafica'=0, 'cohort_type'=0, 'x_axis_type'=0. Contra eso, 'Cohort Type'=16 y 'X Axis Type'=16, que son las tablas buenas. Clientes_Mensual (tabla calculada, partición con GENERATE(VALUES(bnpl_grouped_orders[netsuiteId]), CALENDAR(...)) y un ADDCOLUMNS con CALCULATE+FILTER sobre bnpl_grouped_orders encima) recalcula un panel cliente x mes contra 99,019 filas en cada refresh para datos que nadie ve. cohort_type y x_axis_type son DATATABLE de 2 filas, copias en minúsculas de 'Cohort Type' y 'X Axis Type': quien vaya a cambiar el orden de un slicer tiene 50% de probabilidad de editar la muerta.

**Hoy:**

```
model.tmdl:107  ref table Clientes_Mensual
model.tmdl:108  ref table LocalDateTable_1f5c33d1-6555-4404-93a9-89efe3080eaa
model.tmdl:117  ref table cohort_type
model.tmdl:118  ref table x_axis_type
model.tmdl:122  ref table TablaParaGrafica

relationships.tmdl:286-289
relationship 40d7ec80-ddeb-4ef6-8506-83cf0b0d44ed
	joinOnDateBehavior: datePartOnly
	fromColumn: Clientes_Mensual.InicioMes
	toColumn: LocalDateTable_1f5c33d1-6555-4404-93a9-89efe3080eaa.Date
```

**Queda:**

```
Hacerlo en Power BI Desktop (Vista Modelo > clic derecho > Eliminar) sobre las cuatro tablas, en este orden: TablaParaGrafica, cohort_type, x_axis_type, Clientes_Mensual. Desktop se lleva solo la relación 40d7ec80, la LocalDateTable_1f5c33d1 y los ref de model.tmdl.

Si se hace a mano en texto, hay que tocar CINCO lugares por Clientes_Mensual, no uno:
1. borrar definition/tables/Clientes_Mensual.tmdl, TablaParaGrafica.tmdl, cohort_type.tmdl, x_axis_type.tmdl
2. borrar definition/tables/LocalDateTable_1f5c33d1-6555-4404-93a9-89efe3080eaa.tmdl (su partición hace Calendar(... MIN('Clientes_Mensual'[InicioMes]) ...), queda rota)
3. borrar las 4 líneas de model.tmdl: `ref table Clientes_Mensual`, `ref table LocalDateTable_1f5c33d1-6555-4404-93a9-89efe3080eaa`, `ref table cohort_type`, `ref table x_axis_type`, `ref table TablaParaGrafica`
4. borrar el bloque relationship 40d7ec80-ddeb-4ef6-8506-83cf0b0d44ed de relationships.tmdl:286-289
5. borrar de definition/cultures/es-MX.tmdl los bloques del modelo lingüístico que las nombran (líneas ~52913-53171, ~55345-57196, ~58782-59112, ~80655-80967, ~82464-82563)
```

**Verificar:**

```
Antes: medir el tiempo del refresh completo en Desktop. Después: repetirlo y anotar la diferencia (la que debe bajar es Clientes_Mensual). Y grep -c 'ref table' model.tmdl debe bajar en 5. En el reporte, ninguna página debe mostrar el aspa de campo faltante.
```

> **Ajuste del revisor.** Reescribir el cambio_propuesto así:

Hacerlo en Power BI Desktop (Vista Modelo > clic derecho > Eliminar) sobre las cuatro tablas, en este orden: TablaParaGrafica, cohort_type, x_axis_type, Clientes_Mensual. Desktop se lleva solo la relación 40d7ec80, la LocalDateTable_1f5c33d1, los ref de model.tmdl Y regenera el modelo lingüístico de es-MX.tmdl sin dejar el JSON roto. Esta es la vía recomendada.

Si se hace a mano en texto, son CUATRO pasos, no cinco:
1. borrar definition/tables/Clientes_Mensual.tmdl, TablaParaGrafica.tmdl, cohort_type.tmdl, x_axis_type.tmdl
2. borrar definition/tables/LocalDateTable_1f5c33d1-6555-4404-93a9-89efe3080eaa.tmdl (su partición, línea 108, hace Calendar(... MIN('Clientes_Mensual'[InicioMes]) ...) y queda rota)
3. borrar las CINCO líneas de model.tmdl: 96 no (esa es Top100InactiveCustomers, va aparte) — son 107 'ref table Clientes_Mensual', 108 'ref table LocalDateTable_1f5c33d1-6555-4404-93a9-89efe3080eaa', 117 'ref table cohort_type', 118 'ref table x_axis_type', 122 'ref table TablaParaGrafica'
4. borrar el bloque relationship 40d7ec80-ddeb-4ef6-8506-83cf0b0d44ed de relationships.tmdl:286-289

NO tocar definition/cultures/es-MX.tmdl por rangos de líneas. Si el modelo lingüístico hay que limpiarlo, o se abre y guarda en Desktop (lo regenera), o se borra la anotación linguisticMetadata completa (líneas 3 al final del archivo) y se deja que Desktop la reconstruya. Los rangos propuestos (~55345-57196 en particular) cortan a mitad del bloque 'cohort_type.cohort_type_orden', que además pertenece a la tabla VIVA 'Cohort Type'.

Verificación corregida:
- grep -c 'ref table' 'pbi_new/Buy Now Pay Later.SemanticModel/definition/model.tmdl' debe pasar de 102 a 97.
- python -c "import io,json; s=io.open(r'pbi_new/Buy Now Pay Later.SemanticModel/definition/cultures/es-MX.tmdl',encoding='utf-8').read(); i=s.index('{'); json.loads(s[i:].replace('\t',''))" no debe lanzar excepción (el JSON de linguisticMetadata sigue bien formado).
- En el reporte, ninguna página debe mostrar el aspa de campo faltante.
- Antes/después: medir el refresh completo en Desktop y anotar la diferencia (la que debe bajar es Clientes_Mensual).

> **Nota.** Este es el único de la lista que NO conviene hacer en texto: son cinco archivos más el modelo lingüístico de es-MX.tmdl (que tiene ~57 mil líneas y referencia las cuatro tablas en cinco bloques distintos). Desktop lo hace consistente en un clic. TablaParaGrafica además referencia las medidas [2activeCustomerRate] y [2EnrolledCustomersMetric] y las columnas grid_bnpl[isEnrolled] y grid_bnpl[enrollment_cohort]: borrarla no rompe nada porque la dependencia va en ese sentido, no al revés. Actualizar después sql/pbi/README.md:340-342, que hoy lista 6 tablas calculadas cuando en pbi_new hay 24 particiones `= calculated` sin contar LocalDateTables.

### O3.3 · Restaurar la jerarquía Año/Mes en el visual "Ever Activated Customers"

`pbi_new/Buy Now Pay Later.Report/definition/pages/880e9dc625f4a5eabc4b/visuals/3fae7adac63213c97e39/visual.json:16-34` · riesgo bajo · minutos

El JSON propuesto es copia literal de pbi/.../pages/880e9dc625f4a5eabc4b/visuals/3fae7adac63213c97e39/visual.json:16-70. En pbi_new el field quedó como Column plano pero conservando el queryRef y el nativeQueryRef de la jerarquía: el eje pasa de 3 barras (Año) a un punto por fecha, con la leyenda diciendo "Año", y el RUNNINGSUM([Count of customerId]) de la Y se recalcula sobre ese eje. El modelo sí conserva la variation (grid_bnpl.tmdl:460-463, relationship cb87e5a6 contra LocalDateTable_e20cbdde), así que no hay que tocar el .tmdl.

**Hoy:**

```
"Category": {
          "projections": [
            {
              "field": {
                "Column": {
                  "Expression": {
                    "SourceRef": {
                      "Entity": "grid_bnpl"
                    }
                  },
                  "Property": "bnplActivatedAt"
                }
              },
              "queryRef": "grid_bnpl.bnplActivatedAt.Variación.Jerarquía de fechas.Año",
              "nativeQueryRef": "bnplActivatedAt Año",
              "active": true
            }
          ]
        },
```

**Queda:**

```
"Category": {
          "projections": [
            {
              "field": {
                "HierarchyLevel": {
                  "Expression": {
                    "Hierarchy": {
                      "Expression": {
                        "PropertyVariationSource": {
                          "Expression": {
                            "SourceRef": {
                              "Entity": "grid_bnpl"
                            }
                          },
                          "Name": "Variación",
                          "Property": "bnplActivatedAt"
                        }
                      },
                      "Hierarchy": "Jerarquía de fechas"
                    }
                  },
                  "Level": "Año"
                }
              },
              "queryRef": "grid_bnpl.bnplActivatedAt.Variación.Jerarquía de fechas.Año",
              "nativeQueryRef": "bnplActivatedAt Año",
              "active": true
            },
            {
              "field": {
                "HierarchyLevel": {
                  "Expression": {
                    "Hierarchy": {
                      "Expression": {
                        "PropertyVariationSource": {
                          "Expression": {
                            "SourceRef": {
                              "Entity": "grid_bnpl"
                            }
                          },
                          "Name": "Variación",
                          "Property": "bnplActivatedAt"
                        }
                      },
                      "Hierarchy": "Jerarquía de fechas"
                    }
                  },
                  "Level": "Mes"
                }
              },
              "queryRef": "grid_bnpl.bnplActivatedAt.Variación.Jerarquía de fechas.Mes",
              "nativeQueryRef": "bnplActivatedAt Mes",
              "active": true
            }
          ]
        },
```

**Verificar:**

```
grep -c '"HierarchyLevel"' sobre ese visual.json debe dar 2. En Desktop: el eje del visual debe mostrar Año con drill-down a Mes, y el eje categórico deja de tener cientos de puntos.
```

> **Nota.** Este SÍ se puede editar en el JSON, pero Power BI Desktop reescribe visual.json completo al guardar: aplicar el cambio con Desktop cerrado, abrir, verificar y guardar. Si se prefiere hacerlo en Desktop: quitar el campo del pozo Eje X y volver a arrastrar grid_bnpl[bnplActivatedAt] eligiendo "Jerarquía de fechas" en vez de la columna, luego borrar los niveles Trimestre y Día.

### O3.4 · Quitar la selección persistida del slicer "Cosecha Enrolamiento" de Survival Matrix

`pbi_new/Buy Now Pay Later.Report/definition/pages/d43c45235570af5f6675/visuals/6cc439884a884b8c5208/visual.json (bloque visual.objects.general, último de objects)` · riesgo bajo · minutos

Extraje los 20 valores literales: 2024-06..2025-05 y 2026-01..2026-08. Faltan 2025-06 a 2025-12 — siete cohortes, justo las más maduras después del arranque. El slicer se ve con casillas marcadas (mode Basic, selectAllCheckboxEnabled true, no invertido), no vacío, y filtra los 35 visuales de Survival Matrix. Sin selección persistida el slicer arranca mostrando todas las cohortes.

**Hoy:**

```
"general": [
    {
     "properties": {
      "filter": {
       "filter": {
        "Version": 2,
        "From": [
         {
          "Name": "b",
          "Entity": "bnpl_grouped_orders",
          "Type": 0
         }
        ],
        "Where": [
         {
          "Condition": {
           "In": {
            "Expressions": [ ... enrollment_cohort ... ],
            "Values": [ ['2024-06'], ['2024-07'], ['2024-08'], ['2024-09'], ['2024-10'], ['2024-11'], ['2024-12'], ['2025-01'], ['2025-02'], ['2025-03'], ['2025-04'], ['2025-05'], ['2026-01'], ['2026-02'], ['2026-03'], ['2026-04'], ['2026-05'], ['2026-06'], ['2026-07'], ['2026-08'] ]
           }
          }
         }
        ]
       }
      }
     }
    }
   ]
```

**Queda:**

```
Borrar el par clave/valor "general" completo de visual.objects (es el último de los cinco: data, header, selection, items, general). El bloque objects debe terminar así:

   "items": [
    {
     "properties": {
      "fontColor": {
       "solid": {
        "color": {
         "expr": {
          "Literal": {
           "Value": "'#00AEEF'"
          }
         }
        }
       }
      },
      "bold": {
       "expr": {
        "Literal": {
         "Value": "true"
        }
       }
      }
     }
    }
   ]
  },
```

**Verificar:**

```
python -c "import json,io; d=json.load(io.open(r'...\\visual.json',encoding='utf-8')); print(list(d['visual']['objects'].keys()))" debe imprimir ['data','header','selection','items']. En Desktop: el slicer aparece sin casillas marcadas y Survival Matrix muestra 2025-06 a 2025-12.
```

> **Ajuste del revisor.** Anclaje literal real (visual.json de 566 líneas):
- línea 107: '      ],'   <- cierra "items"
- líneas 108-287: el bloque '      "general": [' … '      ]'  <- la selección persistida
- línea 288: '    },'      <- cierra "objects"

Edición exacta:
1. Borrar las líneas 108 a 287 inclusive.
2. Cambiar la línea 107 de '      ],' a '      ]' (quitar la coma; "items" pasa a ser la última clave de objects).

El resultado, con la indentación real del archivo (6 espacios en la clave):

      "items": [
        {
          "properties": {
            "fontColor": {
              "solid": {
                "color": {
                  "expr": {
                    "Literal": {
                      "Value": "'#00AEEF'"
                    }
                  }
                }
              }
            },
            "bold": {
              "expr": {
                "Literal": {
                  "Value": "true"
                }
              }
            }
          }
        }
      ]
    },

La verificación se queda igual, ya funciona.

> **Nota.** CORRECCIÓN AL HALLAZGO: dice que "en pbi/ también está viciado (13 valores, le falta 2024-10), así que no lo introdujo la migración". Es falso. Extraje los valores de pbi/: son 14, no 13, y son 2024-06, 07, 08, 09, 10, 11, 12, 2025-01, 02, 03, 04, 05, 06, 07 — contiguos (aparecen desordenados en el JSON, 2024-11 y 2024-12 al final, y por eso se leyó como hueco). O sea que en pbi/ el slicer traía TODAS las cohortes existentes al guardar, y el hueco de 2025-06..2025-12 SÍ es de pbi_new. Es estado de UI: se corrige con un clic en Desktop (Seleccionar todo) y ese es el camino recomendado, porque Desktop reescribe este JSON al guardar. Mejor todavía: dejarlo sin selección persistida para que no vuelva a envejecer sin que nadie se dé cuenta.

### O3.5 · Hacer que inventario.py recolecte TODAS las referencias, resolviendo los alias por el bloque From

`ayuda_tablero/inventario.py:126, 149-151, 249-251, 258, 266` · riesgo bajo · ~1 h

Hoy `fields` sólo se llena con el `queryState` (:217), el `filters` que se recolectaba en :249-251 no lo lee nadie, y nunca se recorren `visual.objects` ni el `filterConfig` de `page.json` ni el de `report.json`. Encima el revisor resuelve la entidad por longitud del nombre en vez de por el bloque `From`, así que una referencia con alias queda invisible. Un filtro sobre una columna inexistente no vacía el visual: lo deja SIN FILTRAR — es la clase que rompe callada y es justo la que no se revisa.

**Hoy:**

```
:126
def lit(node):

:149-151
    pages[pid] = {"name": p.get("displayName"), "id": pid,
                  "order": order.index(pid) if pid in order else 999,
                  "dir": os.path.dirname(pdir)}

:249-251
        filters = []
        walk_fields(v.get("filterConfig", {}), filters)
        walk_fields(objs.get("general", [{}])[0].get("properties", {}).get("filter", {}) if "general" in objs else {}, filters)

:258
            "filters": [f for f in filters if f.get("property")],

:266
out = {"model": model, "pages": pages, "visuals": visuals}
```

**Queda:**

```
1) Insertar ANTES de `def lit(node):` (:126):

# ---------------- referencias resueltas (queryState + filtros + objects) ----------------
REF_KINDS = ("Column", "Measure", "HierarchyLevel", "NativeVisualCalculation", "SparklineData")


def _alias_map(nodo, heredado=None):
    """Alias de consulta -> entidad real, leyendo el bloque From de este nivel."""
    m = dict(heredado or {})
    frm = nodo.get("From")
    if isinstance(frm, list):
        for f in frm:
            if isinstance(f, dict) and f.get("Name"):
                m[f["Name"]] = f.get("Entity")
    return m


def _entidad(nodo, alias):
    """(entidad, alias_sin_resolver). Resuelve SourceRef.Source contra el From."""
    e = nodo.get("Expression")
    if not isinstance(e, dict):
        return None, None
    sr = e.get("SourceRef")
    if isinstance(sr, dict):
        if sr.get("Entity"):
            return sr["Entity"], None
        src = sr.get("Source")
        if src in alias:
            return alias[src], None
        return None, src
    h = e.get("Hierarchy")
    if isinstance(h, dict):
        pv = (h.get("Expression") or {}).get("PropertyVariationSource")
        if isinstance(pv, dict):
            return _entidad(pv, alias)
        return _entidad(h, alias)
    return None, None


def walk_refs(o, out, origen, alias=None, ruta=""):
    """Recolecta toda referencia a tabla.columna/medida, venga de donde venga."""
    alias = alias or {}
    if isinstance(o, dict):
        alias = _alias_map(o, alias)
        for k in REF_KINDS:
            nodo = o.get(k)
            if not isinstance(nodo, dict):
                continue
            ent, sin_resolver = _entidad(nodo, alias)
            prop, jer, nivel = nodo.get("Property"), None, None
            if k == "HierarchyLevel":
                h = (nodo.get("Expression") or {}).get("Hierarchy") or {}
                pv = (h.get("Expression") or {}).get("PropertyVariationSource") or {}
                jer, nivel = h.get("Hierarchy"), nodo.get("Level")
                prop = pv.get("Property") or prop
            out.append({"kind": k, "entity": ent, "property": prop, "role": ruta,
                        "origen": origen, "alias": sin_resolver,
                        "hierarchy": jer, "level": nivel})
        for kk, vv in o.items():
            walk_refs(vv, out, origen, alias, ruta or kk)
    elif isinstance(o, list):
        for v in o:
            walk_refs(v, out, origen, alias, ruta)


def dedup_refs(refs):
    seen, out = set(), []
    for f in refs:
        if not f.get("property"):
            continue
        key = (f["kind"], f["entity"], f["property"], f["role"], f["origen"], f["level"])
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


2) Reemplazar :149-151 por:

    pref = []
    walk_refs(p.get("filterConfig", {}), pref, "filtro-pagina")
    pages[pid] = {"name": p.get("displayName"), "id": pid,
                  "order": order.index(pid) if pid in order else 999,
                  "dir": os.path.dirname(pdir),
                  "refs": dedup_refs(pref)}

3) Reemplazar :249-251 por:

        # --- TODAS las referencias del visual: consulta, filtros y objetos ---
        refs = []
        walk_refs(vis.get("query", {}), refs, "query")
        walk_refs(v.get("filterConfig", {}), refs, "filtro-visual")
        walk_refs(objs, refs, "objects")

4) Reemplazar :258 por:

            "refs": dedup_refs(refs),

5) Reemplazar :266 por:

rrefs = []
walk_refs(json.load(open(os.path.join(RPT, "report.json"), encoding="utf-8")).get("filterConfig", {}),
          rrefs, "filtro-reporte")

out = {"model": model, "pages": pages, "visuals": visuals, "report_refs": dedup_refs(rrefs)}
```

**Verificar:**

```
Correr con Desktop cerrado:
.venv\Scripts\python.exe ayuda_tablero\inventario.py
Debe seguir imprimiendo "visuales: 196 / paginas: 15". Y comprobar que el nuevo campo existe y trae las referencias con alias resuelto:
.venv\Scripts\python.exe -c "import json;d=json.load(open(r'ayuda_tablero/_datos/inventario.json',encoding='utf-8'));print(sum(len(v['refs']) for v in d['visuals']), 'refs'); print([r for v in d['visuals'] if v['id']=='32f24f3b89c6ffcf18f5' for r in v['refs']])"
Debe imprimir del orden de 1,300+ refs y, para el textbox de Audiencias, una entrada con entity 'TARGET' y property 'Area'.
```

> **Ajuste del revisor.** En el punto 3, agregar una línea más (vco ya está definido en :157):

        # --- TODAS las referencias del visual: consulta, filtros y objetos ---
        refs = []
        walk_refs(vis.get("query", {}), refs, "query")
        walk_refs(v.get("filterConfig", {}), refs, "filtro-visual")
        walk_refs(objs, refs, "objects")
        walk_refs(vco, refs, "objects")   # titulo/subtitulo con valor dinamico

Verificación corregida (medida en esta VM, con Desktop cerrado):
.venv\Scripts\python.exe ayuda_tablero\inventario.py
  -> "visuales: 196 / paginas: 15"
.venv\Scripts\python.exe -c "import json;d=json.load(open(r'ayuda_tablero/_datos/inventario.json',encoding='utf-8'));print(sum(len(v['refs']) for v in d['visuals']),'refs');print([r for v in d['visuals'] if v['id']=='32f24f3b89c6ffcf18f5' for r in v['refs']])"
  -> 973 refs (971 sin la línea de vco), y para el textbox de Audiencias DOS entradas: una con entity None / property 'TARGET.Area' (el Column de afuera, que cuelga de un Subquery) y otra con entity 'TARGET' y property 'Area'.
.venv\Scripts\python.exe -c "import json;d=json.load(open(r'ayuda_tablero/_datos/inventario.json',encoding='utf-8'));print([r for v in d['visuals'] if v['id']=='467d1a5f6fe8fee01a7e' for r in v['refs'] if r['role']=='title'])"
  -> una entrada revenue_view_selector[totalRevenueTitle] (comprueba que el título dinámico ya se ve).

Y en el punto 5, dejar escrito que report_refs va a salir en 0 mientras report.json no tenga clave filterConfig — el recolector queda puesto para cuando alguien agregue un filtro de reporte.

> **Nota.** Probado en frío sobre una copia del script apuntando a un _datos aparte: corre, no cambia los conteos y produce 1,387 referencias. Verificado además que `fields` y `filters` no los consume NADIE fuera de revisar_referencias.py (grep sobre componer.py, volcado.py, textos_a_mano.py, medir_en_base.py = 0), así que sustituir `filters` por `refs` no rompe la generación de tooltips. `fields` se conserva porque lo usa la sección "visuales sin campos de datos".

### O3.6 · Reescribir revisar_referencias.py para que lea las referencias completas y liste las jerarquías automáticas

`ayuda_tablero/revisar_referencias.py:1-65 (archivo completo)` · riesgo bajo · ~1 h · depende de: la acción de inventario.py (necesita el campo `refs` y `report_refs`)

El script es la red de seguridad declarada en ayuda_tablero/README.md:121 y :148-157, y hoy da luz verde ("ninguna") con una referencia muerta dentro del tablero. Además la sección nueva de jerarquías automáticas convierte al mismo script en la herramienta de medición para apagar la fecha automática: sin ella ese apagado se hace a ciegas.

**Hoy:**

```
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
```

**Queda:**

```
Archivo completo:

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
```

**Verificar:**

```
.venv\Scripts\python.exe ayuda_tablero\inventario.py
.venv\Scripts\python.exe ayuda_tablero\revisar_referencias.py
Antes del arreglo del textbox debe reportar exactamente:
  [tabla-inexistente] TARGET.Area  (Column, origen objects, rol values)
        pagina "Audiencias" · visual 32f24f3b89c6ffcf18f5 (textbox)
  por origen: {'objects': 1}
y la sección de jerarquías debe cerrar con: TOTAL: 18 visuales sobre 7 columnas base.
```

> **Nota.** Probado de punta a punta contra el PBIP real desde una copia en scratchpad: con el código actual el script imprime "ninguna"; con este imprime la referencia TARGET.Area y nada más — o sea que no genera falsos positivos sobre los 196 visuales. La sección de jerarquías da 18 visuales sobre 7 columnas base, no 19: ver la nota de la acción de fecha automática.

### O3.7 · Borrar la referencia rota TARGET.Area del textbox "Audiencias BNPL"

`pbi_new/Buy Now Pay Later.Report/definition/pages/49e8cfe327f3ff31d85e/visuals/32f24f3b89c6ffcf18f5/visual.json (bloque visual.objects.values)` · sin riesgo · minutos

No existe ninguna tabla TARGET en el modelo: grep de 'Entity": "TARGET' sobre todo pbi_new da 0 fuera de este archivo, y no hay TARGET.tmdl en definition/tables. Es un valor dinámico huérfano dentro de un textbox, con anotación de lenguaje natural ("utterance": "target area"), arrastrado de otro reporte. ayuda_tablero/revisar_referencias.py:21-22 no lo detecta porque solo itera v["fields"] (el queryState) y nunca mira visual.objects.

**Hoy:**

```
"values": [
    {
     "properties": {
      "expr": {
       "expr": {
        "Min": {
         "Expression": {
          "Column": {
           "Expression": {
            "Subquery": {
             "Query": {
              "Version": 2,
              "From": [
               {
                "Name": "t",
                "Entity": "TARGET",
                "Type": 0
               }
              ],
              "Select": [
               {
                "Column": {
                 "Expression": { "SourceRef": { "Source": "t" } },
                 "Property": "Area"
                },
                "Name": "TARGET.Area"
               }
              ],
              ... OrderBy sobre t.Area ...
             }
            }
           },
           "Property": "TARGET.Area"
          }
         },
         "IncludeAllTypes": 1
        },
        "Annotations": { "NaturalLanguage": { ... "utterance": "target area" } }
       }
      }
     },
     "selector": { "id": "Valor" }
    }
   ]
```

**Queda:**

```
Borrar el par clave/valor "values" completo de visual.objects. El bloque queda solo con "general" (los paragraphs del texto "Audiencias BNPL "), o sea:

  "objects": {
   "general": [
    {
     "properties": {
      "paragraphs": [
       {
        "textRuns": [
         {
          "value": "Audiencias BNPL ",
          "textStyle": {
           "fontSize": "24pt",
           "color": "#00aeef"
          }
         }
        ],
        "horizontalTextAlignment": "center"
       }
      ]
     }
    }
   ]
  },
```

**Verificar:**

```
grep -rn 'TARGET' sobre pbi_new/Buy Now Pay Later.Report debe dar 0 resultados. El textbox debe seguir mostrando "Audiencias BNPL" en azul, centrado, 24pt.
```

> **Ajuste del revisor.** Anclaje literal real (visual.json de 110 líneas):
- línea 34: '      ],'      <- cierra "general"
- líneas 35-107: el bloque '      "values": [' … '      ]'  <- la referencia rota a TARGET
- línea 108: '    },'        <- cierra "objects"

Edición exacta:
1. Borrar las líneas 35 a 107 inclusive.
2. Cambiar la línea 34 de '      ],' a '      ]'.

El bloque objects queda así, con la indentación real del archivo:

    "objects": {
      "general": [
        {
          "properties": {
            "paragraphs": [
              {
                "textRuns": [
                  {
                    "value": "Audiencias BNPL ",
                    "textStyle": {
                      "fontSize": "24pt",
                      "color": "#00aeef"
                    }
                  }
                ],
                "horizontalTextAlignment": "center"
              }
            ]
          }
        }
      ]
    },

La verificación se queda igual. Sugerencia: correrla también sobre pbi/ para dejar constancia de que la basura ya venía de ahí.

> **Nota.** El textbox se ve bien hoy: el valor dinámico no llega a renderizarse. Es limpieza, no una falla visible. Vale la pena hacerlo junto con la acción 37 del plan (extender revisar_referencias.py a filters, filterConfig de página y visual.objects), porque si no el script sigue dando luz verde con basura adentro. Desktop reescribe visual.json al guardar: editar con Desktop cerrado.

### O3.7 · parte b · Borrar el valor dinámico TARGET.Area del cuadro de texto de Audiencias

`pbi_new/Buy Now Pay Later.Report/definition/pages/49e8cfe327f3ff31d85e/visuals/32f24f3b89c6ffcf18f5/visual.json:34-105` · riesgo bajo · minutos · depende de: conviene hacerlo DESPUÉS de la extensión del revisor, para ver el contador pasar de 1 a 0 y comprobar que la compuerta sirve

No existe ninguna tabla `TARGET` en el modelo (40 tablas reales, verificado contra el inventario). Es una referencia muerta que arrastró una edición vieja de "valor dinámico" de cuadro de texto. Los `textRuns` no la usan —el texto es 100% estático—, así que borrarla no cambia nada en pantalla y deja el revisor de referencias en cero, que es lo que permite confiar en él como compuerta.

**Hoy:**

```
El archivo tiene 110 líneas. `visual.objects` trae dos claves: `general` (:15-33, el texto estático "Audiencias BNPL " a 24pt en #00aeef) y `values` (:34-105), que es esto:

      "values": [
        {
          "properties": {
            "expr": {
              "expr": {
                "Min": {
                  "Expression": {
                    "Column": {
                      "Expression": {
                        "Subquery": {
                          "Query": {
                            "Version": 2,
                            "From": [
                              {
                                "Name": "t",
                                "Entity": "TARGET",
                                "Type": 0
                              }
                            ],
                            "Select": [
                              {
                                "Column": {
                                  "Expression": {
                                    "SourceRef": {
                                      "Source": "t"
                                    }
                                  },
                                  "Property": "Area"
                                },
                                "Name": "TARGET.Area"
                              }
                            ],
... (OrderBy sobre la misma columna, y una anotación NaturalLanguage con utterance "target area")
          "selector": {
            "id": "Valor"
          }
        }
      ]
```

**Queda:**

```
Borrar la clave `"values"` completa (:34-105) y la coma que la separa de `general`, de modo que `objects` quede sólo con el texto estático:

  "visual": {
    "visualType": "textbox",
    "objects": {
      "general": [
        {
          "properties": {
            "paragraphs": [
              {
                "textRuns": [
                  {
                    "value": "Audiencias BNPL ",
                    "textStyle": {
                      "fontSize": "24pt",
                      "color": "#00aeef"
                    }
                  }
                ],
                "horizontalTextAlignment": "center"
              }
            ]
          }
        }
      ]
    },
    "drillFilterOtherVisuals": true
  }
}
```

**Verificar:**

```
.venv\Scripts\python.exe ayuda_tablero\inventario.py
.venv\Scripts\python.exe ayuda_tablero\revisar_referencias.py
La primera sección debe decir "ninguna". Y abrir la página Audiencias en Desktop: el encabezado debe seguir diciendo "Audiencias BNPL" centrado y en azul.
```

> **Ajuste del revisor.** Misma operación, con las líneas reales:

Borrar de la línea 35 ('      "values": [') a la línea 107 ('      ]') inclusive, y quitar la coma final de la línea 34, que pasa de
      ],
a
      ]

El bloque resultante es el que ya trae la acción y es correcto:

  "visual": {
    "visualType": "textbox",
    "objects": {
      "general": [
        {
          "properties": {
            "paragraphs": [
              {
                "textRuns": [
                  {
                    "value": "Audiencias BNPL ",
                    "textStyle": {
                      "fontSize": "24pt",
                      "color": "#00aeef"
                    }
                  }
                ],
                "horizontalTextAlignment": "center"
              }
            ]
          }
        }
      ]
    },
    "drillFilterOtherVisuals": true
  }
}

El archivo debe quedar en 37 líneas. Agregar a la verificación:
(Get-Content "pbi_new\Buy Now Pay Later.Report\definition\pages\49e8cfe327f3ff31d85e\visuals\32f24f3b89c6ffcf18f5\visual.json" | Measure-Object -Line).Lines   -> 37
Select-String -Path "...\32f24f3b89c6ffcf18f5\visual.json" -Pattern "TARGET"   -> cero lineas

> **Nota.** Leído el archivo completo (110 líneas): el `values` es la única referencia a TARGET en todo el reporte y el textbox no muestra ningún valor calculado. La anotación `NaturalLanguage` con `utterance: "target area"` confirma que salió de una pregunta de Q&A, no de un diseño.

### O3.8 · Desambiguar los cuatro títulos del Funnel y darle subtítulo al primero

`pbi_new/Buy Now Pay Later.Report/definition/pages/f384ed5188290d63776a/visuals/{f92593db85fb5f1534ce:1087 y 1104, 0b018a1b4ac75783e506:910 y 941, 7d5e7258b21f913fd163:1034, 3f57b402a0115b201aa2:1064}/visual.json` · riesgo bajo · ~1 h · depende de: nada para editar. Pero los dos títulos que dicen "4+ months tenure" sólo son ciertos cuando esté aplicada la acción 16 de la auditoría (B5, guardia de blanco en grid_bnpl.tmdl:124): hoy ese filtro no excluye a los ~137 mil no enrolados y las dos tablas arrancan en ~146K en vez de ~9K.

Hoy tres de las cuatro tablas se titulan igual, están una encima de otra en la misma página y una de ellas no tiene ni subtítulo. Dos universos distintos (con y sin el filtro de antigüedad) y dos granos distintos (por cohorte vs una fila total) se leen como si fueran la misma tabla repetida. Quien cite "la tabla de funnel" en una junta no puede decir cuál miró.

**Hoy:**

```
f92593db85fb5f1534ce:1087
                  "Value": "'Funnel Distribution per Number Of Orders'"
(no tiene bloque "subTitle"; el arreglo "title" cierra en :1104 y sigue "visualHeader": [ en :1105)

0b018a1b4ac75783e506:910
                  "Value": "'Funnel Distribution per Number Of Orders'"
0b018a1b4ac75783e506:941
                  "Value": "'Percentage of the enrolled customers'"

7d5e7258b21f913fd163:1034
                  "Value": "'Funnel Distribution per Number Of Orders'"

3f57b402a0115b201aa2:1064
                  "Value": "'Funnel Distribution per Number Of Orders (Percentage)'"
```

**Queda:**

```
Los cuatro son tableEx sobre grid_bnpl, columnas 0..30, apilados y visibles a la vez (y=1117, 1518, 1923, 2051). Diferencias reales medidas: los dos de arriba traen la columna Enrollment Cohort (15 proyecciones) y los dos de abajo NO (14 proyecciones: son una sola fila de totales); los de arriba no tienen filtro y los de abajo filtran grid_bnpl[bnplMinimumTenure] In {1L}; f92593db y 7d5e7258 agregan con Function 0 (Sum = clientes) y 0b018a1b y 3f57b402 con Function 1 (Avg, formato 0.00% = porcentaje).

1) f92593db85fb5f1534ce:1087
                  "Value": "'Funnel Distribution per Number Of Orders (Customers by Cohort)'"

   y ADEMAS insertar entre :1104 (el `],` que cierra "title") y :1105 (`"visualHeader": [`):

      "subTitle": [
        {
          "properties": {
            "show": {
              "expr": {
                "Literal": {
                  "Value": "true"
                }
              }
            },
            "text": {
              "expr": {
                "Literal": {
                  "Value": "'Enrolled customers by number of BNPL orders. All cohorts, no tenure filter.'"
                }
              }
            },
            "fontColor": {
              "solid": {
                "color": {
                  "expr": {
                    "Literal": {
                      "Value": "'#00AEEF'"
                    }
                  }
                }
              }
            }
          }
        }
      ],

2) 0b018a1b4ac75783e506:910
                  "Value": "'Funnel Distribution per Number Of Orders (% of Customers by Cohort)'"
   0b018a1b4ac75783e506:941
                  "Value": "'Percentage of the enrolled customers of each cohort. No tenure filter.'"

3) 7d5e7258b21f913fd163:1034
                  "Value": "'Funnel Distribution per Number Of Orders (Customers, 4+ months tenure)'"

4) 3f57b402a0115b201aa2:1064
                  "Value": "'Funnel Distribution per Number Of Orders (% of Customers, 4+ months tenure)'"
```

**Verificar:**

```
Cerrar Power BI Desktop primero. Luego:
.venv\Scripts\python.exe ayuda_tablero\inventario.py
.venv\Scripts\python.exe ayuda_tablero\volcado.py "Funnel"
En la salida los cuatro tableEx deben mostrar cuatro cadenas distintas después de `::` y todos con ` // ` (subtítulo). Validar además que el JSON siga siendo parseable:
Get-ChildItem "pbi_new\Buy Now Pay Later.Report\definition" -Recurse -Filter *.json | ForEach-Object { $f=$_.FullName; try { $null = ConvertFrom-Json (Get-Content $f -Raw -Encoding UTF8) } catch { Write-Output ("ROTO: " + $f) } }
```

> **Nota.** Verificado en los archivos: la diferencia entre los pares no es sólo el filtro, también el grano (15 vs 14 proyecciones). Eso no estaba en el hallazgo y es lo que más confunde: los dos de abajo son una sola fila de totales, no una tabla por cohorte. Los títulos propuestos van en ASCII a propósito para no depender de cómo Desktop re-serialice caracteres al guardar.

### O3.9 · Corregir los tres nativeQueryRef corruptos del Funnel, sin tocar queryRef

`pbi_new/Buy Now Pay Later.Report/definition/pages/f384ed5188290d63776a/visuals/0b018a1b4ac75783e506/visual.json:155, 281, 302` · riesgo bajo · minutos

El alias que se exporta a Excel y que sale en "Ver como tabla" dice "Promedio de 51", "Promedio de 151" y "Promedio de 201" para las columnas 5, 15 y 20. Quien exporte la tabla se lleva encabezados que nombran cohortes de pedidos que no existen.

**Hoy:**

```
:154-155
              "queryRef": "Sum(grid_bnpl.5)",
              "nativeQueryRef": "Promedio de 51",
:280-281
              "queryRef": "Sum(grid_bnpl.15)",
              "nativeQueryRef": "Promedio de 151",
:301-302
              "queryRef": "Sum(grid_bnpl.20)",
              "nativeQueryRef": "Promedio de 201",
```

**Queda:**

```
Cambiar SOLO las tres líneas de nativeQueryRef:

:155
              "nativeQueryRef": "Promedio de 5",
:281
              "nativeQueryRef": "Promedio de 15",
:302
              "nativeQueryRef": "Promedio de 20",

NO tocar queryRef. Verificado: `"Sum(grid_bnpl.5)"` aparece 3 veces en el archivo — una como queryRef (:154) y dos como `"metadata"` de selectores (:522 y :772, ancho de columna y formato condicional). Cambiar queryRef desengancha esos dos selectores y la tabla pierde el ancho y el formato de esa columna.
```

**Verificar:**

```
Select-String -Path "pbi_new\Buy Now Pay Later.Report\definition\pages\f384ed5188290d63776a\visuals\0b018a1b4ac75783e506\visual.json" -Pattern "Promedio de (51|151|201)"
Debe devolver cero líneas. Y que sigan estando las tres de metadata:
Select-String -Path "...\0b018a1b4ac75783e506\visual.json" -Pattern 'metadata": "Sum\(grid_bnpl\.5\)' → 2 líneas.
```

> **Nota.** En pantalla el encabezado de la tabla NO está mal: sale de `displayName`, que sí dice "5", "15" y "20" (:156, :282, :303). El daño es en exportación y tooltips. Aparte: los 14 queryRef de este visual dicen `Sum(...)` cuando la agregación real es `Function: 1` (Avg). Es el artefacto "queryRef miente" ya documentado en ayuda_tablero/README.md:178-181; volcado.py lo marca como ALIAS DESACTUALIZADO y va a seguir marcándolo después de este arreglo. Es correcto que siga así.

### O3.10 · Renombrar las seis gráficas de tasa PAR del Vintage: título y nombre de serie

`pbi_new/Buy Now Pay Later.Report/definition/pages/2f83323bac49134fe42d/visuals/{0ff2052f3312e68375b0:102-103 y 420, e9aa4c10e1eb56d608b4:102-103 y 408, 18f1d6ffead214e615a8:102-103 y 364, 5a0d21450822b2cc87ac:102-103 y 364, 8a726824316a777192ae:102-103 y 363, 75ae87cd796169d70244:102-103 y 364}/visual.json` · riesgo bajo · ~1 h

En Vintage Analysis conviven seis gráficas de tasa. Las de cada par sólo se distinguen por un `+` en el título ("PAR 60+ Rate" vs "PAR 60 Rate") y nombran la serie EXACTAMENTE igual, así que ni el eje ni el tooltip las separan. Son denominadores distintos: capital desplegado vs clientes activados, que en PAR 30 dan 6.02% y 31.30% — 5.2x de diferencia. Es el mismo riesgo que PENDIENTES §12 ya describe, y la recomendación 1 de esa sección sólo cubre dos de las seis.

**Hoy:**

```
Títulos (visualContainerObjects.title[0].properties.text):
0ff2052f3312e68375b0:420   "Value": "'PAR 30 Rate per Enrollment Cohort'"      (medida par30RateAmount)
e9aa4c10e1eb56d608b4:408   "Value": "'PAR 30 Rate per Enrollment Cohort'"      (medida par30RateCustomers)
18f1d6ffead214e615a8:364   "Value": "'PAR 60+ Rate per Enrollment Cohort'"     (medida par60RateAmount)
5a0d21450822b2cc87ac:364   "Value": "'PAR 60 Rate per Enrollment Cohort'"      (medida par60RateCustomers)
8a726824316a777192ae:363   "Value": "'PAR 90+ Rate per Enrollment Cohort'"     (medida par90RateAmount)
75ae87cd796169d70244:364   "Value": "'PAR 90 Rate per Enrollment Cohort'"      (medida par90RateCustomers)

Nombre de serie (los seis, en :102-103):
              "nativeQueryRef": "PAR 30+ Rate",
              "displayName": "PAR 30+ Rate",
              (idéntico en el par de 60 y en el par de 90)
```

**Queda:**

```
Títulos:
0ff2052f3312e68375b0:420   "Value": "'PAR 30+ Rate per Enrollment Cohort (over Deployed Capital)'"
e9aa4c10e1eb56d608b4:408   "Value": "'PAR 30+ Rate per Enrollment Cohort (over Activated Customers)'"
18f1d6ffead214e615a8:364   "Value": "'PAR 60+ Rate per Enrollment Cohort (over Deployed Capital)'"
5a0d21450822b2cc87ac:364   "Value": "'PAR 60+ Rate per Enrollment Cohort (over Activated Customers)'"
8a726824316a777192ae:363   "Value": "'PAR 90+ Rate per Enrollment Cohort (over Deployed Capital)'"
75ae87cd796169d70244:364   "Value": "'PAR 90+ Rate per Enrollment Cohort (over Activated Customers)'"

Nombre de serie (cambiar las DOS líneas, :102 y :103, en cada archivo):
0ff2052f3312e68375b0   "PAR 30+ Rate over Deployed Capital"
e9aa4c10e1eb56d608b4   "PAR 30+ Rate over Activated Customers"
18f1d6ffead214e615a8   "PAR 60+ Rate over Deployed Capital"
5a0d21450822b2cc87ac   "PAR 60+ Rate over Activated Customers"
8a726824316a777192ae   "PAR 90+ Rate over Deployed Capital"
75ae87cd796169d70244   "PAR 90+ Rate over Activated Customers"

Queda, por ejemplo, en 18f1d6ffead214e615a8:
              "queryRef": "vintage_analysis.par60RateAmount",
              "nativeQueryRef": "PAR 60+ Rate over Deployed Capital",
              "displayName": "PAR 60+ Rate over Deployed Capital",
```

**Verificar:**

```
Cerrar Desktop. Luego:
.venv\Scripts\python.exe ayuda_tablero\inventario.py
.venv\Scripts\python.exe ayuda_tablero\volcado.py "Vintage Analysis"
Los seis lineChart de tasa deben tener título distinto entre sí y `<Y>` con nombre distinto entre sí. Y:
Select-String -Path "pbi_new\Buy Now Pay Later.Report\definition\pages\2f83323bac49134fe42d\visuals\*\visual.json" -Pattern "Rate per Enrollment Cohort" | Group-Object Line | Where-Object Count -gt 1
Debe salir vacío (ningún título repetido).
```

> **Ajuste del revisor.** Mismos títulos y nombres propuestos, pero explicitar la excepción de puntuación en el sexto archivo:

8a726824316a777192ae/visual.json:102-103 (SIN coma en la 103, porque no hay clave "format" después):
              "nativeQueryRef": "PAR 90+ Rate over Deployed Capital",
              "displayName": "PAR 90+ Rate over Deployed Capital"

En los otros cinco (0ff2052f, e9aa4c10, 18f1d6ff, 5a0d2145, 75ae87cd) sí lleva coma en :103, porque les sigue "format": "0.00 %;-0.00 %;0.00 %".

Agregar al cierre de la acción: junto con esto hay que actualizar PENDIENTES_NEGOCIO.md:606, :686, :994 y :1071, que citan el título viejo 'PAR 30 Rate per Enrollment Cohort'.

Agregar a la verificación el chequeo de JSON, que es lo que atrapa la coma colgante:
Get-ChildItem "pbi_new\Buy Now Pay Later.Report\definition\pages\2f83323bac49134fe42d" -Recurse -Filter *.json | ForEach-Object { $f=$_.FullName; try { $null = ConvertFrom-Json (Get-Content $f -Raw -Encoding UTF8) } catch { Write-Output ("ROTO: " + $f) } }

> **Nota.** Verificado que en estos seis archivos `queryRef` NO se usa como `metadata` de ningún selector (a diferencia del caso del Funnel), así que cambiar nativeQueryRef y displayName es seguro. Los subtítulos de las seis ya están correctos y desambiguan; el problema era sólo título y serie. Aparte: el subtítulo de e9aa4c10 dice "PAR 30+ Customers Over Ever Activated Customers" pero la línea de referencia de ese visual NO se llama BEP sino "Healthy Value" con valor 0.04D (:193) — ver la acción de PENDIENTES.

### O3.11 · Corregir los seis subtítulos del Vintage que están copiados de la gráfica equivocada

`pbi_new/Buy Now Pay Later.Report/definition/pages/2f83323bac49134fe42d/visuals/{0c0d2b3ec11dcc5709e0:415, 4aee864e1ccec3a458de:415, 1304ed5cb5304007760c:415, 68813540220b0c0eda33:415, 8ac9249e3078acd8a263:415, a66966556a8e05273701:414}/visual.json` · riesgo bajo · minutos · depende de: nada (independiente de la acción de renombrar las seis tasas, aunque conviene hacerlas en la misma pasada)

Las seis gráficas no-tasa de la página traen pegado el subtítulo de la gráfica de tasa de PAR 30. Cinco anuncian el número de PAR equivocado y las seis anuncian un cociente ("Over Ever Activated Customers") cuando el eje Y es una suma absoluta: Sum(PAR30N) son clientes, Sum(PAR30) son pesos. El subtítulo es justamente el mecanismo con el que PENDIENTES §12 dice que se desambiguan estas gráficas; en estas seis desinforma.

**Hoy:**

```
Los SEIS traen literalmente el mismo subtítulo, y en cinco de ellos ni siquiera coincide el número de PAR:

0c0d2b3ec11dcc5709e0:369 título 'PAR 30+ Customers per Enrollment Cohort'  · Y = Sum(vintage_analysis.PAR30N)
0c0d2b3ec11dcc5709e0:415   "Value": "'PAR 30+ Customers Over Ever Activated Customers'"
4aee864e1ccec3a458de:369 título 'PAR 60+ Customers per Enrollment Cohort'  · Y = Sum(PAR60N)
4aee864e1ccec3a458de:415   "Value": "'PAR 30+ Customers Over Ever Activated Customers'"
1304ed5cb5304007760c:369 título 'PAR 90+ Customers per Enrollment Cohort'  · Y = Sum(PAR90N)
1304ed5cb5304007760c:415   "Value": "'PAR 30+ Customers Over Ever Activated Customers'"
68813540220b0c0eda33:369 título 'PAR 30+ Balance per Enrollment Cohort'    · Y = Sum(PAR30)
68813540220b0c0eda33:415   "Value": "'PAR 30+ Customers Over Ever Activated Customers'"
8ac9249e3078acd8a263:369 título 'PAR 60+ Balance per Enrollment Cohort'    · Y = Sum(PAR60)
8ac9249e3078acd8a263:415   "Value": "'PAR 30+ Customers Over Ever Activated Customers'"
a66966556a8e05273701:368 título 'PAR 90+ Balance per Enrollment Cohort'    · Y = Sum(PAR90)
a66966556a8e05273701:414   "Value": "'PAR 30+ Customers Over Ever Activated Customers'"
```

**Queda:**

```
0c0d2b3ec11dcc5709e0:415
                  "Value": "'Number of customers in PAR 30+ (count, not a rate)'"
4aee864e1ccec3a458de:415
                  "Value": "'Number of customers in PAR 60+ (count, not a rate)'"
1304ed5cb5304007760c:415
                  "Value": "'Number of customers in PAR 90+ (count, not a rate)'"
68813540220b0c0eda33:415
                  "Value": "'PAR 30+ outstanding balance per cohort (amount, not a rate)'"
8ac9249e3078acd8a263:415
                  "Value": "'PAR 60+ outstanding balance per cohort (amount, not a rate)'"
a66966556a8e05273701:414
                  "Value": "'PAR 90+ outstanding balance per cohort (amount, not a rate)'"
```

**Verificar:**

```
.venv\Scripts\python.exe ayuda_tablero\inventario.py
.venv\Scripts\python.exe ayuda_tablero\volcado.py "Vintage Analysis"
Ningún par título // subtítulo debe repetirse. Y:
Select-String -Path "pbi_new\Buy Now Pay Later.Report\definition\pages\2f83323bac49134fe42d\visuals\*\visual.json" -Pattern "PAR 30\+ Customers Over Ever Activated Customers"
Debe devolver UNA sola línea (la de e9aa4c10e1eb56d608b4, que sí es la gráfica de tasa sobre clientes).
```

> **Nota.** Hallazgo nuevo, no venía en el paquete: al abrir los archivos para verificar los títulos de PAR 60 y PAR 90 salió que hay SEIS subtítulos copiados de la gráfica de al lado, no sólo los títulos. Es el mismo copiar-pegar que produjo el BEP de 4% en la gráfica de clientes.

### O3.12 · Borra las cuatro vistas v_pbi_* de archivos_bnpl, que duplican sql/pbi/14 a 17 y no las consume nadie

`sql/14_archivos_bnpl.sql:89-121` · riesgo bajo · minutos

Cuatro vistas con la misma logica que sql/pbi/14 a 17, sin consumidor (grep de v_pbi_ en .py, .sql y .md solo encuentra este archivo y AUDITORIA.md). Ademas el comentario dice 'aqui viven materializadas' de cuatro CREATE OR REPLACE VIEW, que no materializan nada: quien lo lea creera que hay una copia fisica que no existe.

**Hoy:**

```
-- ── Vistas para Power BI ────────────────────────────────────────────────────────────────
--
-- Las tablas de arriba guardan en snake_case, que es la convencion del staging. Estas vistas
-- hacen la traduccion a los nombres EXACTOS que espera el modelo — incluidos '%good', '%bad' y
-- 'Id cliente' con su espacio — para que el paso M en Power Query sea:
--
--     Value.NativeQuery(Origen, "select * from archivos_bnpl.v_pbi_odds_combinations")
--
-- y no haya que escapar una sola comilla. Es la misma consulta que hay en sql/pbi/14 a 17; ahi
-- estan documentadas y aqui viven materializadas para que el tablero no tenga que cargarlas.

CREATE OR REPLACE VIEW archivos_bnpl.v_pbi_odds_combinations AS
SELECT loan_disbursement_index_range AS "loanDisbursementIndexRange",
       flag AS "flag", atr1 AS "atr1", atr2 AS "atr2",
       atr1_rank AS "atr1Rank", atr2_rank AS "atr2Rank",
       events AS "events", good AS "good", bad AS "bad",
       br AS "br", bad_rate AS "bad_rate",
       pct_good AS "%good", pct_bad AS "%bad", woe AS "woe", iv AS "iv"
FROM archivos_bnpl.odds_combinations;

CREATE OR REPLACE VIEW archivos_bnpl.v_pbi_atr_combinations_iv AS
SELECT loan_disbursement_index_range AS "loanDisbursementIndexRange",
       flag AS "flag", combination AS "combination",
       number_of_combinations AS "number_of_combinations", iv AS "iv"
FROM archivos_bnpl.atr_combinations_iv;

CREATE OR REPLACE VIEW archivos_bnpl.v_pbi_ps_transactional_profile AS
SELECT id_cliente AS "Id cliente", transactional_profile AS "transactionalProfile"
FROM archivos_bnpl.ps_transactional_profile;

CREATE OR REPLACE VIEW archivos_bnpl.v_pbi_bnpl_cac AS
SELECT enrollment_cohort AS "enrollmentCohort", cac AS "cac"
FROM archivos_bnpl.bnpl_cac;
```

**Queda:**

```
-- ── Vistas para Power BI: NO van aqui ───────────────────────────────────────────────────
--
-- La traduccion de snake_case a los nombres exactos del modelo ('%good', '%bad', 'Id cliente'
-- con su espacio) vive en sql/pbi/14 a 17 y la publica build_bnpl.py como pbi_bnpl.*, igual que
-- las otras 14 tablas del tablero. Este archivo tuvo cuatro vistas v_pbi_* con esa misma
-- traduccion; se borraron porque el mismo SQL en dos lugares es exactamente lo que sql/15 dice
-- que el proyecto no hace, y ademas nadie las consumia: PASOS_M.md apunta a pbi_bnpl.
--
-- Para tirarlas de una base que ya las tiene:
--
--     DROP VIEW IF EXISTS archivos_bnpl.v_pbi_odds_combinations;
--     DROP VIEW IF EXISTS archivos_bnpl.v_pbi_atr_combinations_iv;
--     DROP VIEW IF EXISTS archivos_bnpl.v_pbi_ps_transactional_profile;
--     DROP VIEW IF EXISTS archivos_bnpl.v_pbi_bnpl_cac;
```

**Verificar:**

```
Antes de borrar, confirmar que no las lee nadie: grep -rn "v_pbi_" --include=*.py --include=*.sql --include=*.md . (solo debe salir este archivo y AUDITORIA.md). Despues: select count(*) from information_schema.views where table_schema='archivos_bnpl'; -- debe dar 0
```

> **Nota.** El DROP no va dentro del archivo porque carga_archivos_bnpl.py:112 lo ejecuta en cada carga manual y un DROP repetido ahi no aporta nada; se corre una vez a mano sobre la VM. Verificar antes en Power BI que ningun paso M viejo apunte a archivos_bnpl.v_pbi_*: PASOS_M.md dice pbi_bnpl, pero el .pbix es el que manda.

### O3.13 · Devolver activePageName a la portada y anotar por qué se pierde

`pbi_new/Buy Now Pay Later.Report/definition/pages/pages.json:20 · ayuda_tablero/README.md (sección "Cómo se regenera")` · riesgo bajo · minutos

Se construyó una portada para que alguien nuevo sepa leer el tablero, `pageOrder` la pone primera, y aun así el tablero abre en Resumen Ejecutivo: la página que más definiciones ambiguas tiene (dos bases de comisión, el eje de locPenetration, un visual de Python que puede estar roto). El que llega nuevo aterriza justo donde más ayuda necesita, sin la ayuda.

**Hoy:**

```
pages.json:3-4 y :20
  "pageOrder": [
    "00portada0bnpl0lectu",
    ...
  "activePageName": "a4eca66684d1a46d5446"

ayuda_tablero/portada.py:153-155
    meta["pageOrder"] = [PID] + [p for p in meta["pageOrder"] if p != PID]
    meta["activePageName"] = PID
    json.dump(meta, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
```

**Queda:**

```
1) pages.json:20
  "activePageName": "00portada0bnpl0lectu"

   Equivalente reproducible (hace lo mismo y además reordena):
   .venv\Scripts\python.exe ayuda_tablero\portada.py

2) Agregar en ayuda_tablero/README.md, justo debajo del aviso "**Cierra Power BI Desktop antes de
   aplicar**":

**Y al guardar desde Desktop, vuelve a abrir la portada antes de guardar.** `pages.json` guarda
`activePageName`, que es la página que se abre primero. `portada.py` la deja en la portada
(`portada.py:154`), pero Desktop la reescribe con **la página que estuviera seleccionada al
guardar**. Por eso hoy vuelve a decir `a4eca66684d1a46d5446` (Resumen Ejecutivo) aunque el
`pageOrder` sí empieza por la portada. Si al guardar estás parado en otra página, se pierde otra
vez — y no hay nada que lo detecte.
```

**Verificar:**

```
Select-String -Path "pbi_new\Buy Now Pay Later.Report\definition\pages\pages.json" -Pattern "activePageName"
→ debe decir 00portada0bnpl0lectu.
Y la prueba de verdad: abrir el .pbip en Desktop y confirmar que la pestaña que carga es "Cómo leer este tablero". Después de cerrar Desktop, volver a correr el Select-String: si cambió, es que se guardó desde otra pestaña.
```

> **Nota.** El hallazgo está bien planteado pero le falta la causa, que sí se puede leer en el código: `portada.py:154` YA hace `meta["activePageName"] = PID`. O sea que no es que nadie lo haya configurado — se configuró y Desktop lo revirtió al guardar. Por eso el arreglo de una línea solo no basta: sin la nota en el README se va a volver a perder en la siguiente sesión de Desktop. Ese mismo aviso cierra el conteo viejo de PENDIENTES:493-494, que se corrige en su propia acción.

### O3.14 · Plan por pasos para apagar la fecha y hora automáticas sin dejar 18 visuales sin campo

`pbi_new/Buy Now Pay Later.SemanticModel/definition/model.tmdl:31 (el interruptor, al FINAL del plan) + los .tmdl de las 7 tablas base` · riesgo alto · una jornada o más · depende de: la extensión de revisar_referencias.py: es la que produce y verifica el inventario de los 18 visuales. Sin ella el paso 0 y el paso 4 se hacen a ojo.

Hoy 61 de las 81 relaciones del modelo apuntan a una LocalDateTable: sólo 20 son de negocio, y nadie puede leer el diagrama de relaciones para entender el tablero. Apagar la opción de golpe deja sin campo a 18 visuales repartidos en 5 páginas, dos de ellas el Resumen Ejecutivo y Salud del Portafolio. El orden importa: primero la sustituta, luego re-apuntar, y sólo al final el interruptor.

**Hoy:**

```
pbi_new/.../definition/model.tmdl:31
annotation __PBI_TimeIntelligenceEnabled = 1

Y en cada tabla base, un bloque como éste (ejemplo real, bnpl_par.tmdl:36-39):
		variation Variación
			isDefault
			relationship: b75ba78e-123c-4239-8a6d-7d988a0158ca
			defaultHierarchy: LocalDateTable_28f68b36-bdbf-4c8d-a027-5d82e8a54c99.'Jerarquía de fechas'
```

**Queda:**

```
PASO 0 · Medir (10 min, sin tocar nada)
  .venv\Scripts\python.exe ayuda_tablero\inventario.py
  .venv\Scripts\python.exe ayuda_tablero\revisar_referencias.py
  La sección "VISUALES ATADOS A UNA JERARQUIA DE FECHAS AUTOMATICA" es el inventario de trabajo.

  > **CORREGIDO EL 2026-08-14, DESPUÉS DE APLICAR O3.3.** Este inventario decía 18 visuales sobre 7
  > columnas base, y la nota del final explicaba que eran 18 y no 19 porque el visual
  > `3fae7adac63213c97e39` ("Ever Activated Customers") **ya había perdido** su jerarquía y usaba un
  > `Column` plano. **O3.3 se la devuelve**, que es justo lo que esa acción existe para hacer. Así que
  > al aplicar O3.3 el inventario de O3.14 sube a **19 visuales sobre 8 columnas base**, con
  > `grid_bnpl[bnplActivatedAt] → 1 visual` como fila nueva. Medido con `revisar_referencias.py`
  > después de O3.3: `TOTAL: 19 visuales sobre 8 columnas base`.
  >
  > Consecuencia para el PASO 2: son **8 columnas sustitutas en 7 tablas**, no 7 en 6. La que falta es
  > `grid_bnpl: bnplActivatedMes = FORMAT('grid_bnpl'[bnplActivatedAt], "yyyy-mm")`.
  >
  > Este choque **no está** en «Acciones que se pisan». Si algún día se decide NO hacer O3.14, O3.3 se
  > queda como está y no pasa nada; si se hace, hay que re-apuntar 19 visuales, no 18.

  Antes de O3.3 daba 18 visuales sobre 7 columnas base:

    bnpl_grouped_orders[createdAtClean]              5  KPI's Tracking
        12381723ef8668b870ba  Frecuencia de compra por cliente activo
        7a8e293149e0cda1cd63  Drop Size Promedio
        9cf0322db8639388edb0  Active Customers Over Cumulative Enrolled Customers
        c1518826799edccf72a8  Cumulative Sales Volume
        ce161a4b4447d007bdc3  Gasto mensual por cliente activo
    overall_prev_post_bnpl_sales[createdAt]          4  Cambio en Comportamiento de Compra
        33ecb14540906d90211c  Frequency
        94682a41e886765ba81a  Active Customers
        a422793fb8aae6ca0b14  Average Drop Size
        a4229bc9357c17155ecd  Compra Mensual
    bnpl_loss_rates[expectedPaymentDate]             2  Salud del Portafolio
        a06d7f67dd080a08ed06 · d0ab979d830d90d87cc0
    bnpl_par[corte]                                  2  Salud del Portafolio
        a419f4a6b3e841c3c405 · db7672f18e68429c61c1
    bnpl_loss_rates[paidDate]                        2  Resumen Ejecutivo
        467d1a5f6fe8fee01a7e · ceb3c416848990d01b8e
    loans_matured_default_profile[expectedPaymentDate] 2  Default Customer Profile (OCULTA)
        b4fee5609a080ee9d3b4 · f1403f99d70bd1a7c5cd
    bnpl_cosechas_agg[mes_ft_tx]                     1  Cambio en Comportamiento de Compra
        4737ecbaf603b948dc0b  slicer "Cosecha" (usa Año / Trimestre / Mes)

PASO 1 · Confirmar que ninguna medida depende de la jerarquía (5 min)
  Select-String -Path "pbi_new\Buy Now Pay Later.SemanticModel\definition\tables\*.tmdl" `
    -Pattern "DATEADD|TOTALYTD|TOTALQTD|TOTALMTD|SAMEPERIODLASTYEAR|DATESYTD|DATESMTD|DATESINPERIOD|PARALLELPERIOD|PREVIOUSMONTH|PREVIOUSYEAR|NEXTMONTH|ENDOFMONTH|STARTOFMONTH"
  Hoy devuelve CERO. Si algún día devuelve algo, este plan cambia: hará falta una tabla de fechas
  de verdad con relación, no columnas calculadas. Mientras dé cero, las 61 LocalDateTable existen
  sólo para poner Año/Mes en un eje.

PASO 2 · Crear la columna sustituta en cada una de las 7 tablas (Desktop → Nueva columna, para que
  asigne el lineageTag; media jornada con las verificaciones)

    bnpl_grouped_orders:          createdAtMes         = FORMAT('bnpl_grouped_orders'[createdAtClean], "yyyy-mm")
    overall_prev_post_bnpl_sales: createdAtMes         = FORMAT('overall_prev_post_bnpl_sales'[createdAt], "yyyy-mm")
    bnpl_loss_rates:              expectedPaymentMes   = FORMAT('bnpl_loss_rates'[expectedPaymentDate], "yyyy-mm")
    bnpl_loss_rates:              paidMes              = FORMAT('bnpl_loss_rates'[paidDate], "yyyy-mm")
    bnpl_par:                     corteMes             = FORMAT('bnpl_par'[corte], "yyyy-mm")
    loans_matured_default_profile:expectedPaymentMes   = FORMAT('loans_matured_default_profile'[expectedPaymentDate], "yyyy-mm")
    bnpl_cosechas_agg:            cosechaMes           = FORMAT('bnpl_cosechas_agg'[mes_ft_tx], "yyyy-mm")

  En TMDL cada una queda así (ejemplo; el GUID lo pone Desktop):

	column corteMes = FORMAT('bnpl_par'[corte], "yyyy-mm")
		dataType: string
		lineageTag: <guid nuevo>
		summarizeBy: none

		annotation SummarizationSetBy = Automatic

  El formato "yyyy-mm" ordena cronológicamente como texto: no hace falta sortByColumn ni una
  columna de orden. Es la razón de elegir ese formato y no "mmm yyyy".

PASO 3 · Re-apuntar los 18 visuales, UNO POR UNO, comparando contra una captura previa
  En cada visual: quitar los dos niveles (Año y Mes) del eje y poner la columna nueva. En el
  slicer 4737ecbaf603b948dc0b se pierde el desglose Año/Trimestre/Mes y queda una lista plana de
  cosechas yyyy-mm: la selección persistida se pierde y hay que volver a marcarla.

PASO 4 · Compuerta antes de tocar el interruptor
  .venv\Scripts\python.exe ayuda_tablero\inventario.py
  .venv\Scripts\python.exe ayuda_tablero\revisar_referencias.py
  "TOTAL: 0 visuales sobre 0 columnas base". Si no da cero, NO seguir.

PASO 5 · Apagar (en Desktop, no editando el archivo)
  Archivo → Opciones y configuración → Opciones → Configuración del archivo actual → Carga de
  datos → desmarcar "Fecha y hora automáticas". Desktop borra de un golpe las 61 LocalDateTable,
  las 61 declaraciones `variation` y las 61 relaciones. Guardar.
  Editar model.tmdl:31 a mano NO sirve: mientras la opción del archivo esté encendida, Desktop
  regenera las tablas al abrir.

PASO 6 · Verificar el resultado
  (Get-ChildItem "pbi_new\Buy Now Pay Later.SemanticModel\definition\tables" -Filter "LocalDateTable*").Count   → 0
  (Select-String -Path "pbi_new\...\relationships.tmdl" -Pattern "^relationship").Count                          → 20
  Select-String -Path "pbi_new\...\model.tmdl" -Pattern "__PBI_TimeIntelligenceEnabled"                          → 0 o "= 0"
  Abrir las 5 páginas afectadas y comparar contra las capturas del paso 3.

PASO 7 · Dejarlo escrito en sql/pbi/README.md, junto a la lista de tablas calculadas: que la
  fecha automática está apagada a propósito, que el eje mensual sale de columnas `...Mes` y que
  volver a encenderla recrea las 61 tablas.
```

**Verificar:**

```
La compuerta es el paso 4: `revisar_referencias.py` tiene que cerrar con "TOTAL: 0 visuales sobre 0 columnas base" ANTES de tocar la opción. Después del paso 5, los tres conteos del paso 6 (0 LocalDateTable, 20 relaciones, anotación fuera).
```

> **Ajuste del revisor.** PASO 2 · encabezado corregido:
  PASO 2 · Crear la columna sustituta: 7 columnas en 6 tablas (bnpl_loss_rates lleva DOS, una por
  cada fecha que hoy tiene jerarquía). Desktop -> Nueva columna, para que asigne el lineageTag.

PASO 6 · comandos completos:
  (Get-ChildItem "pbi_new\Buy Now Pay Later.SemanticModel\definition\tables" -Filter "LocalDateTable*").Count          -> 0   (hoy 61)
  (Get-ChildItem "pbi_new\Buy Now Pay Later.SemanticModel\definition\tables" -Filter "DateTableTemplate*").Count       -> 0   (hoy 1)
  (Select-String -Path "pbi_new\Buy Now Pay Later.SemanticModel\definition\relationships.tmdl" -Pattern "^relationship").Count  -> 20  (hoy 81)
  (Select-String -Path "pbi_new\Buy Now Pay Later.SemanticModel\definition\tables\*.tmdl" -Pattern "^\s+variation ").Count      -> 0   (hoy 61)
  Select-String -Path "pbi_new\Buy Now Pay Later.SemanticModel\definition\model.tmdl" -Pattern "__PBI_TimeIntelligenceEnabled"  -> 0 lineas, o "= 0"
  Select-String -Path "pbi_new\Buy Now Pay Later.SemanticModel\definition\model.tmdl" -Pattern "ref table LocalDateTable"       -> 0 lineas

PASO 1 · comando completo (el `-Pattern` en una sola línea, sin el backtick de continuación, que en Git Bash no aplica):
  Select-String -Path "pbi_new\Buy Now Pay Later.SemanticModel\definition\tables\*.tmdl" -Pattern "DATEADD|TOTALYTD|TOTALQTD|TOTALMTD|SAMEPERIODLASTYEAR|DATESYTD|DATESMTD|DATESINPERIOD|PARALLELPERIOD|PREVIOUSMONTH|PREVIOUSYEAR|NEXTMONTH|ENDOFMONTH|STARTOFMONTH"
  (corrido hoy: cero líneas)

> **Nota.** Dos correcciones al hallazgo, verificadas archivo por archivo. (1) En pbi_new la anotación está en model.tmdl:31, no en :63 — el :63 es el de la carpeta pbi/ vieja. (2) Son 18 visuales, no 19: el visual 19 (3fae7adac63213c97e39, "Ever Activated Customers" en KPI's Tracking) YA perdió la jerarquía y hoy usa un Column plano; sólo conserva la cadena vieja en `queryRef` ("grid_bnpl.bnplActivatedAt.Variación.Jerarquía de fechas.Año"). Ése no se rompe al apagar la fecha automática — es el hallazgo B12 y se arregla aparte (acción 30 de la auditoría). Dato que abarata todo el plan: no hay UNA sola función de inteligencia de tiempo en las 40 tablas del modelo, así que no hace falta construir una tabla de fechas ni relaciones nuevas; con columnas calculadas alcanza, y se evita repetir el accidente de las relaciones perdidas en la migración (B7/B8). Si en el futuro alguien quiere DATEADD o YTD, entonces sí habrá que construir la tabla de fechas.

---

## OLA 4 — Documentación, gobierno y continuidad

Esfuerzo total: **dos jornadas**. Todas las ediciones del README, **de abajo hacia arriba** y localizando el texto, no la línea (regla 1a).

### O4.1 · Corregir el grano documentado de `grouped_orders` [S13]
`sql/03_bnpl_grouped_orders.sql:1` + `README.md:520` · riesgo ninguno · **minutos**

La cabecera dice un grano y el índice único dice otro: quien sume `order_gross_sales` directo infla las ventas por el número de SKUs.

```sql
-- bnpl.grouped_orders — 1 fila por (cliente, sales order, order_id, order_status, sales_channel).
--
-- OJO: NO es una fila por sales order. El GROUP BY de `ordenes` va por esas cinco columnas y el
-- indice unico de abajo tambien (linea 123). Una sales order con tres SKUs distintos o con dos
-- cambios de estatus son varias filas. Cualquier conteo de ordenes o suma de monto directo sobre
-- esta vista sale inflado: hay que colapsar antes por (netsuite_id, sales_order_id), como hace el
-- CTE `ordenes` de sql/pbi/20_concurso_base.sql:43-84.
```
`README.md:520` (entre `bnpl.dim_ruta_cliente_scd` y `bnpl.loss_rates`):
```markdown
| `bnpl.grouped_orders` | cliente + sales order + order_id + estatus + canal | base: cohort, índice de pedido, entrega. **No** es 1 fila por sales order |
```
**Verifica:** `select count(*) as filas, count(distinct (netsuite_id, sales_order_id)) as ordenes from bnpl.grouped_orders;` — si `filas > ordenes`, el grano documentado hoy es falso.

### O4.2 · Las tres afirmaciones desactualizadas de `PENDIENTES_NEGOCIO.md` [N5]
`:493-494`, `:609-612`, `:631-633` · riesgo ninguno · **minutos**

**a) `:493-494`** — el conteo describe `pbi/` (14/11) y hoy son 15/12:
```markdown
para quien edita. De 15 páginas del tablero, 12 son visibles; las ocultas son *Default Customer
Profile*, *Return On Investment* y *Search*. (La 15ª es la portada *Cómo leer este tablero*.)
```
**b) `:609-612`** — la tabla llama "BEP" a las dos líneas de referencia, y la de la derecha se llama distinto y vale distinto:
```markdown
| Posición | Medida | Subtítulo | Línea de referencia | Valor hoy |
|---|---|---|---|---|
| Izquierda | `par30RateAmount` | *PAR 30+ Balance Over Cumulative Deployed & Matured Capital* | **"BEP" 3.5%** | 6.02% |
| Derecha | `par30RateCustomers` | *PAR 30+ Customers Over Ever Activated Customers* | **"Healthy Value" 4.0%** | 31.30% |

Las dos líneas **no se llaman igual**: la de la izquierda es `'BEP'`
(`0ff2052f3312e68375b0:193`, valor `0.035D`) y la de la derecha es `'Healthy Value'`
(`e9aa4c10e1eb56d608b4:193`, valor `0.04D`). Son las **únicas dos gráficas de tasa PAR** de la
página con línea de referencia: las de PAR 60 y PAR 90 no tienen ninguna. (En la misma página hay
una tercera línea de referencia, también llamada `'BEP'` y de valor `19D`, pero es de otra gráfica:
`f4fa8eab332531023583`, *Propaga Net Income Estimation*, y no mide mora.)
```
**c) `:631-633`** — la recomendación 1 cubría 2 de 6 gráficas:
```markdown
1. **Renombrar las seis gráficas de tasa**, no dos: el problema se repite idéntico en PAR 60
   (`18f1d6ffead214e615a8` sobre capital vs `5a0d21450822b2cc87ac` sobre clientes) y en PAR 90
   (`8a726824316a777192ae` vs `75ae87cd796169d70244`). En los tres pares las dos gráficas
   nombran la serie exactamente igual (`nativeQueryRef` y `displayName` en :102-103), así que ni
   el eje ni el tooltip las distinguen; el subtítulo sí. Nombres propuestos:
   `PAR NN+ Rate per Enrollment Cohort (over Deployed Capital)` y
   `(over Activated Customers)`. No cambia ninguna cifra.
```
**Verifica:**
```powershell
(Get-ChildItem "pbi\Buy Now Pay Later.Report\definition\pages" -Directory).Count   # 15
Select-String -Path "pbi\...\pages\*\page.json" -Pattern "HiddenInViewMode"        # 3 lineas
Select-String -Path "pbi\...\pages\2f83323bac49134fe42d\visuals\*\visual.json" -Pattern "'BEP'|'Healthy Value'"   # 3 lineas, no 2
```
> La recomendación 2 (revisar el 4% con quien lo definió) **sí requiere negocio** y se queda como está.

### O4.3 · `ayuda_tablero/README.md`: declarar el alcance real del revisor [N11]
`:121`, `:148-157` · riesgo ninguno · **minutos** · *después de O3.5 y O3.6*

Mientras diga "resuelve cada campo", quien lo corra va a creer que un "ninguna" cubre los filtros.

`:121`:
```markdown
| `revisar_referencias.py` | resuelve **toda** referencia al modelo —campos, filtros de visual, de página y de reporte, y valores dinámicos dentro de `visual.objects`— y reporta las que no existen. Lista además los visuales atados a una jerarquía de fechas automática |
```
`:153` — cambiar «Para ver qué quedó sin significado:» por «Para ver qué referencias dejaron de resolver contra el modelo:».

Y después del bloque powershell existente:
```markdown
El revisor cubre **cinco** orígenes de referencia y los distingue en la salida:

| `origen` | De dónde sale | Cómo rompe si la columna no existe |
|---|---|---|
| `query` | el campo está puesto en la gráfica | el visual da error visible |
| `filtro-visual` | `filterConfig` del `visual.json` | **el visual se queda SIN FILTRAR, sin avisar** |
| `filtro-pagina` | `filterConfig` del `page.json` | toda la página queda sin filtrar |
| `filtro-reporte` | `filterConfig` del `report.json` | todo el reporte queda sin filtrar |
| `objects` | valor dinámico dentro de un objeto (título, cuadro de texto) | el objeto se pinta vacío |

La columna que importa es la segunda: un filtro roto **no** vacía el visual, lo deja sin filtrar, y
eso no se ve en pantalla. Por eso el revisor no puede quedarse en el `queryState`.

Para resolver a qué tabla apunta un alias (`"SourceRef": {"Source": "g"}`) lee el bloque `From` del
mismo ámbito, incluidas las `Subquery`. Lo que no resuelve se reporta como `alias-sin-resolver`, no
se descarta en silencio.

`filtro-reporte` hoy siempre sale en cero: el `report.json` de este PBIP no tiene clave
`filterConfig`. El recolector queda puesto para el día que alguien agregue un filtro de reporte.

La sección **VISUALES ATADOS A UNA JERARQUIA DE FECHAS AUTOMATICA** existe para el apagado de
`__PBI_TimeIntelligenceEnabled`: dice exactamente qué visuales hay que re-apuntar antes de tocar
esa opción, y tiene que quedar en cero antes de apagarla.
```
**Verifica** (hay que mirar las etiquetas que el recolector emite, no las de lo roto — eso sale en cero después de O3.7):
```powershell
.venv\Scripts\python.exe ayuda_tablero\inventario.py
.venv\Scripts\python.exe -c "import json,collections;d=json.load(open(r'ayuda_tablero/_datos/inventario.json',encoding='utf-8'));c=collections.Counter(r['origen'] for v in d['visuals'] for r in v['refs']);c.update(r['origen'] for p in d['pages'].values() for r in p['refs']);c.update(r['origen'] for r in d['report_refs']);print(c)"
# query, filtro-visual, objects y filtro-pagina (filtro-reporte en 0)
```

### O4.4 · Documentar el requisito de Python + seaborn para los 9 `pythonVisual` [N12]
`README.md:495` (Requisitos), `:665`, `:668-670` · riesgo ninguno · **una hora**

`seaborn` no aparece en ningún `.py`, `.md` ni comando del repo, y sin él nueve gráficas —una en la primera página que se abre— se ven como recuadros de error. **Es la única falla del proyecto que no deja rastro en ningún log**: falla el render, no el refresh, así que una corrida con esos 9 rotos se reporta igual de verde que una sana.

Agregar después de `README.md:495`:
```markdown
- **Power BI Desktop con intérprete de Python configurado.** 9 de los 196 visuales del tablero son
  `pythonVisual` y en los 9 la primera línea ejecutable es `import seaborn as sns`. Sin un intérprete
  registrado en *Archivo → Opciones → Opciones globales → Scripts de Python*, esos 9 visuales pintan
  un recuadro de error. **No sale en ningún log.** Dónde están:

  | Página | Visuales |
  |---|---|
  | Resumen Ejecutivo (`a4eca66684d1a46d5446`) — es la primera que se abre | `f9c2e0e39c8a6d2e5603` |
  | Cambio en Comportamiento de Compra (`f2df469501207dcc7b25`) | `244b55881eac31d2270e`, `96ef08940b40c3457d10`, `c8bf341930b0123a7e45`, `cf3a8e4f07bbee408a67` |
  | Return On Investment (`2e0ca9895d50e2380127`, oculta en lectura) | `073fdf579c77450e4321`, `346bffe961ebe71c7aa5`, `3ded30fe4e178cc60974`, `89cfea3537b6a97e47d8` |

  Paquetes que usan los scripts: `seaborn`, `matplotlib`, `numpy` y `pandas`. Si Desktop apunta al
  `.venv` del proyecto, quedan cubiertos con el `pip install` de la sección de despliegue.
```
`README.md:665`:
```powershell
.venv\Scripts\python.exe -m pip install pandas python-dotenv openpyxl matplotlib seaborn
```
`README.md:668-670`:
```markdown
`pandas` y `matplotlib` son para los scripts de análisis; `openpyxl` lo necesita
`carga_clientes_concurso.py` para leer el Excel; `seaborn` **no lo usa el pipeline** sino los 9
visuales de Python del tablero (ver *Requisitos*), y se instala aquí para que el venv que apunte
Power BI Desktop ya lo traiga. El resto de las dependencias (SQLAlchemy, psycopg, sshtunnel) las
arrastran las librerías internas del paso 2.
```
> ⚠️ **Choca con O2.16**, que elimina el paso 2 y sustituye el `pip install` por `-r requirements.txt`. Si haces las dos: aplica O2.16 y en este párrafo deja solo la frase de `seaborn`, sin la referencia al paso 2.

**Verifica:**
```powershell
.venv\Scripts\python.exe -c "import seaborn, matplotlib, numpy, pandas; print(seaborn.__version__)"
Select-String -Path "pbi\Buy Now Pay Later.Report\definition\pages\*\visuals\*\visual.json" -Pattern "pythonVisual" | Measure-Object   # 9
```
En Desktop: `f9c2e0e39c8a6d2e5603` (Resumen Ejecutivo) debe pintar el histograma, no un recuadro.

> Para la Fase 7: en el Service los visuales de Python corren sobre la lista fija de paquetes de Microsoft, con tope de 150k filas y sin "Publicar en la web".

### O4.5 · Runbook de falla: en qué estado queda la base según el paso que reventó [G2-gob]
`README.md:351-357` (insertar después de la tabla de modos, antes de `### 2. ¿Cargó todo?`) · riesgo ninguno · **una hora**

Hoy el README solo dice "reventó a media corrida, el traceback está en `logs/`". No dice las tres formas de empeorar el incidente que el código sí tiene.

````markdown
#### Si el modo es `error`

El traceback dice **dónde** reventó; esta tabla dice **en qué estado quedó la base**, que no es lo
mismo y es lo que decide qué hay que correr:

| Falló en | Qué quedó en la base | Volver a correr | Qué correr |
|---|---|---|---|
| 1/6 frescura | nada, salvo lo que se escribió en `bnpl_ops` | sí | `main.py` |
| 2/6 staging Mongo | **la tabla que se estaba cargando quedó vacía, o sin su ventana**: el `TRUNCATE`/`DELETE` va en su propia transacción y se confirma *antes* de extraer (`etl_mongo_to_postgres.py:416` y `:424-434`). Las tablas anteriores quedaron completas | sí, es idempotente | ver el recuadro de abajo |
| 3/6 Redshift | nada a medias: DDL + `TRUNCATE` + carga van en **una transacción por tabla** (`etl_redshift_to_postgres.py:320-323`). La que falló conserva el dato anterior | sí | `etl_redshift_to_postgres.py --solo <tabla>` |
| 4/6 capa de negocio, **sin** `--rebuild` | nada: `REFRESH MATERIALIZED VIEW` es una sola sentencia; si falla, la matview conserva su contenido anterior | sí | `build_bnpl.py --solo <vista>` |
| 4/6 capa de negocio, **con** `--rebuild` | **la vista que falló ya no existe, y las que dependían de ella tampoco**: cada `.sql` abre con `DROP MATERIALIZED VIEW … CASCADE` | sí, pero **nunca con `--solo`** | `build_bnpl.py --rebuild` completo |
| 4/6 vistas de `pbi_bnpl` | las que alcanzó están nuevas, la que falló **no existe** y el refresh de Power BI va a fallar ahí | sí | `build_bnpl.py` sin flags: rehace las 18 al final |
| 5/6 calidad · 6/6 frescura | solo `bnpl_ops`. El tablero ya quedó cargado | sí | `ops\quality_checks.py` · `ops\check_freshness.py` |

> **El caso que hay que mirar dos veces: `credit_order_production`.** Es la única colección en modo
> ventana (`etl_mongo_to_postgres.py:56`). Si el pipeline murió durante su recarga completa mensual,
> la tabla quedó **vacía** y en `etl_runs` no hay fila `modo='full'` de ese intento. Eso juega a
> favor: `_preparar_destino` (`:408-413`) vuelve a ver `dias >= FULL_CADA_DIAS` y **rehace la recarga
> completa sola**, tanto desde `main.py` como desde `etl_mongo_to_postgres.py --solo
> credit_order_production` — los dos caminos ejecutan el mismo código, `main.py:142` no hace nada
> más que pasar el flag.
>
> El único caso en que se pierde el histórico es si el full que murió lo habías forzado tú con
> `--full` mientras existía un full exitoso de hace menos de 30 días: ahí el reintento a secas sí
> cargaría solo la ventana de 60 días sobre la tabla vacía. Después de un error en esa tabla, cuesta
> lo mismo y no falla nunca:
>
> ```powershell
> .venv\Scripts\python.exe etl_mongo_to_postgres.py --solo credit_order_production --full
> ```

**Antes de re-correr, mira qué falta**; no repitas 20 minutos a ciegas:

```sql
-- deben salir 27 tablas con started_at de hoy
select distinct on (tabla) tabla, started_at, modo, filas
from bnpl_ops.etl_runs where tabla <> 'pipeline'
order by tabla, started_at desc;

-- deben ser 18
select count(*) from information_schema.views where table_schema = 'pbi_bnpl';
```

**Casi siempre sale más barato re-correr el paso que el pipeline**: `main.py` completo vuelve a bajar
Mongo (~14 min); si lo que falló fue el paso 4, `build_bnpl.py` son 85 segundos. `--sin-redshift`
reprocesa sin volver a pagar los 3.5 min de Redshift.

**Si el refresh ya corrió sobre una base a medias**, el tablero muestra números incompletos y no lo
dice. Arregla la base y dispara un refresh a mano desde el Service.
````
> Si aplicaste **O1.1**, la fila de `2/6 staging Mongo` cambia de sentido: pasa a ser "la tabla conserva la carga anterior". Actualízala en la misma pasada. Y si aplicaste **O2.2/O2.3**, las 27 tablas pasan a 45.

### O4.6 · Documentar los nueve chequeos de calidad, no solo los dos que están en alerta [G3-gob]
`README.md:392-397` · riesgo ninguno · **una hora**

De los 8 (9 con O2.13) el README documenta 2, encabezados con "no las persigas": entrena a ignorar la sección entera. El más caro de ignorar es `credit_order_delivery_at_nulo`, que es CRIT, tira pedidos del PAR y no está escrito en ningún `.md`.

````markdown
**Los nueve chequeos de calidad.** `ops/quality_checks.py` corre nueve; hoy solo dos están en alerta.
El canal de revisión es **la vista, no el log**: `bnpl_ops.v_quality_alerts` pone los CRIT hasta arriba.

| Check | Sev | Qué significa si sale en alerta | Qué hacer |
|---|---|---|---|
| `credit_order_sales_order_id_nulo` | CRIT | Órdenes que Mongo trae sin `salesOrderId`: no se agrupan ni se unen con delivery | **Ruido conocido: ~1,469 filas.** Basura de origen, y el staging es espejo fiel. Actuar solo si salta de golpe |
| `credit_order_delivery_at_nulo` | CRIT | Órdenes `COMPLETED` sin `deliveryAt`: sin eso no hay `expectedPaymentDate` y el pedido se cae del PAR | Hoy en 0. Si deja de estar en 0, **cambió la fuente**: escalar a Ingeniería antes de dar la mora por buena |
| `credit_order_sales_order_id_multi_cliente` | WARN | Un `salesOrderId` de más de un `netsuiteId` | Rompe el grano de `grouped_orders`. Revisar con `analisis/unicidad_llaves.py` |
| `approval_netsuite_id_duplicado` | WARN | Cliente con más de una aprobación | Esperado: `grid_bnpl` se queda con una. Vigilar solo si crece |
| `aprobados_sin_customer` | WARN | Aprobados sin ficha en `fintech-customers` | Sube mientras esa fuente esté en CRIT. Son clientes sin `shopName` ni teléfono en el tablero |
| `payment_report_transaction_id_duplicado` | WARN | Transacción repetida en `payment-report`: **duplica revenue** | Eran 3 filas en la comparación del 2026-08-12. Si crece, el revenue está inflado |
| `ordenes_sin_delivery` | WARN | Órdenes `COMPLETED` sin registro en `state-of-delivery` | Suele ser desfase de la fuente de entregas; se cierra en la corrida siguiente |
| `pagos_sin_orden` | WARN | Pagos cuya transacción no existe en `credit-order` | **Ruido conocido: ~276 filas.** Analizado en `analisis/pagos_sin_orden.py` |
| `cargas_manuales_viejas` | WARN | Una de las cinco cargas manuales lleva más de 90 días sin recargarse, o nunca se registró en `etl_runs` | Recargar el archivo o el Excel que corresponda (README → *Los archivos del Drive*) |

Un chequeo cuya tabla o columna no exista sale como `NO_APLICABLE`, no como OK: eso significa que a
la extracción le falta un campo.

**Los dos marcados como ruido conocido son los únicos que hoy están abiertos. Cualquier otro que
aparezca es nuevo y hay que revisarlo**, empezando por su historia:

```sql
select * from bnpl_ops.v_quality_alerts;
select checked_at, n_filas from bnpl_ops.data_quality_checks
where check_name = '<el que salió>' order by checked_at desc limit 30;
```
````
**Verifica:** `.venv\Scripts\python.exe ops\quality_checks.py` → imprime los 9, nombres y severidades uno a uno.

> ⚠️ **Choca con O2.13.** Aplica O2.13 antes, o escribe esta sección ya en nueve (que es como está arriba). Si decides no hacer O2.13, quita la última fila y cambia "nueve" por "ocho".
> Aparte: vale la pena bajar `credit_order_sales_order_id_nulo` a WARN, que es lo que el README dice que es en realidad.

### O4.7 · `DICCIONARIO.md` generado desde `conocimiento.py` [G6-gob]
`ayuda_tablero/diccionario.py` (nuevo) + `README.md:20-21` y árbol · riesgo ninguno · **una hora** · *requiere que `ayuda_tablero/` ya esté en git (O0.6)*

El único catálogo a nivel columna y medida vive escondido en un script de tooltips. Generarlo evita el modo de falla clásico: un diccionario a mano que en tres meses contradice a los tooltips.

```python
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
```
`README.md`, después de la línea 21:
```markdown
| ¿Qué significa esta columna, este campo o esta medida? | [`DICCIONARIO.md`](DICCIONARIO.md) — generado, se edita en `ayuda_tablero/conocimiento.py` |
```
Y en el árbol de *Estructura*, después de la línea de `migrar_a_vm.py` (:772):
```
DICCIONARIO.md              GENERADO: 21 tablas, 59 campos, 66 medidas. Sale de ayuda_tablero/conocimiento.py
```
**Verifica:**
```powershell
.venv\Scripts\python.exe ayuda_tablero\diccionario.py            # 21 tablas, 59 campos, 66 medidas
.venv\Scripts\python.exe ayuda_tablero\diccionario.py --escribir
Select-String -Path .\DICCIONARIO.md -Pattern '^\| `' | Measure-Object   # 146 filas (21+59+66)
```
> `M` se completa con un `M.update({...})` en `conocimiento.py:235`: quien mantenga el archivo debe agregar medidas nuevas **ahí**, no arriba.
> Aparte, matar el catálogo obsoleto: `.kiro/specs/migracion-pipeline-bnpl/design.md:478-488` describe un schema `bnpl_analytics` y módulos `transform_*.py` que nunca existieron — agregarle una línea `> Catálogo obsoleto. El vigente es DICCIONARIO.md.`

### O4.8 · Respaldo de lo que NO se reconstruye, y el RTO real [G8-gob]
`ops/respaldo.bat` (nuevo) + `README.md` antes de `## Estructura` (:762) · riesgo bajo · **media jornada**

No hay respaldo de nada (`grep pg_dump` sobre el repo da cero) y tampoco está escrito qué sí y qué no se reconstruye. Las tres piezas irreproducibles caben en unos MB.

```bat
@echo off
REM Respalda lo unico que NO se rehace corriendo el pipeline:
REM   archivos_bnpl.*             los 4 CSV del Drive (uno es del 2026-01-08: puede que ya no este)
REM   bnpl.bnpl_clientes_concurso el Excel de negocio
REM   bnpl_ops.*                  el historico de frescura, calidad y corridas — irrecuperable
REM Todo lo demas (mongo_bnpl, redshift_bnpl, las 11 matviews, las 18 vistas) lo rehace main.py.
setlocal
set PGBIN=C:\Program Files\PostgreSQL\17\bin
set DESTINO=D:\Respaldos\bnpl
set PGHOST=localhost
set PGPORT=9553
set PGDATABASE=rabbit-bi-local
set PGUSER=RELLENAR_USUARIO
REM Sin PGPASSWORD: la contrasena va en %APPDATA%\postgresql\pgpass.conf
REM   localhost:9553:rabbit-bi-local:RELLENAR_USUARIO:<contrasena>

for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set HOY=%%d
if not exist "%DESTINO%" mkdir "%DESTINO%"

REM Dos invocaciones: pg_dump ignora -n cuando se pasa -t, y un dump con los dos juntos
REM saldria con la tabla del concurso y los DOS schemas VACIOS, imprimiendo "Respaldo OK".
"%PGBIN%\pg_dump.exe" -Fc -n archivos_bnpl -n bnpl_ops -f "%DESTINO%\bnpl_ops_archivos_%HOY%.dump"
if errorlevel 1 (echo RESPALDO FALLIDO ^(schemas^) & exit /b 1)

"%PGBIN%\pg_dump.exe" -Fc -t bnpl.bnpl_clientes_concurso -f "%DESTINO%\bnpl_concurso_%HOY%.dump"
if errorlevel 1 (echo RESPALDO FALLIDO ^(concurso^) & exit /b 1)

REM Retencion: 30 dias.
forfiles /p "%DESTINO%" /m bnpl_*_*.dump /d -30 /c "cmd /c del @path" 2>nul
echo Respaldo OK: %DESTINO%
endlocal
```
Y a `.gitignore`, para que el `.bat` nunca lleve credenciales:
```gitignore
ops/respaldo.local.bat
```

Sección nueva en `README.md`, antes de `## Estructura`:
````markdown
## Respaldo y reconstrucción

Esto es un data mart derivado: casi todo se rehace corriendo el pipeline. El riesgo no es perder el
dato, es **cuánto tarda volver a tenerlo**. Hoy no hay respaldo de ningún tipo.

| Schema | ¿Se rehace solo? | Con qué | Cuánto tarda |
|---|---|---|---|
| `mongo_bnpl` | sí | `etl_mongo_to_postgres.py --full` | 20–40 min (la variación es del túnel SSM) |
| `redshift_bnpl` | sí | `etl_redshift_to_postgres.py` | 3.5 min · 1.29M filas |
| `bnpl` (11 matviews) | sí | `build_bnpl.py --rebuild` | 1.4 min |
| `pbi_bnpl` (18 vistas) | sí | `build_bnpl.py` | < 1 s |
| `archivos_bnpl` | **no** | volver a bajar los 4 CSV del Drive | depende de que sigan ahí: `ps_transactional_profile` es del 2026-01-08 |
| `bnpl.bnpl_clientes_concurso` | **no** | volver a pedir el Excel a Comercial | depende de una persona |
| `bnpl_ops` | **no** | nada: el histórico de frescura, calidad y corridas se pierde | irrecuperable |

**RTO de máquina: ~45 min**, y eso suponiendo que el túnel SSM, Redshift y las tres librerías
internas estén en pie. Lo que puede alargarlo a días son las tres últimas filas.

**Por eso el respaldo es solo de esas tres.** Son pocos MB y no se reconstruyen:

```powershell
ops\respaldo.bat
schtasks /Create /TN "BNPL Respaldo" /SC WEEKLY /D SUN /ST 04:00 ^
  /TR "C:\ruta\buy_now_pay_later\ops\respaldo.bat" /RU <usuario> /RP *
```

Restaurar: `pg_restore -h localhost -p 9553 -d rabbit-bi-local -c <archivo>.dump`.

**Pendiente de confirmar con quien administra la VM**: si hay snapshot de EBS del disco donde vive
`postgresql-x64-17`. Si lo hay, esto es un complemento; si no, es el único respaldo que existe.
````
**Verifica** (todo en PowerShell; no mezclar sintaxis de cmd):
```powershell
$pgbin = 'C:\Program Files\PostgreSQL\17\bin'
& .\ops\respaldo.bat
Get-ChildItem 'D:\Respaldos\bnpl' | Select-Object Name, Length, LastWriteTime
& "$pgbin\pg_restore.exe" -l 'D:\Respaldos\bnpl\bnpl_ops_archivos_<fecha>.dump' | Select-String 'archivos_bnpl|bnpl_ops'
& "$pgbin\pg_restore.exe" -l 'D:\Respaldos\bnpl\bnpl_concurso_<fecha>.dump'    | Select-String 'bnpl_clientes_concurso'
```
El primero debe listar las 4 tablas + 4 vistas de `archivos_bnpl` y las 4 tablas + 2 vistas de `bnpl_ops`. **Si sale vacío, el dump se hizo con `-t` y `-n` juntos.**

### O4.9 · Dueño, escalamiento y SLA — la mitad que no espera a nadie (de [G1-gob])
`README.md:22-24` (inserción), `:385`, `:597-599` · riesgo ninguno · **una hora**

`grep` de dueño/responsable/contacto/SLA sobre los 9 `.md` no devuelve un solo nombre ni correo. Hoy un CRIT se escala a un sustantivo abstracto y `fintech-customers-production` lleva 513 h caída sin que nadie sepa si alguien la sigue.

Lo que **sí** se puede pegar hoy son los seis compromisos con su línea de código y la fila de la incidencia. Los nombres van como `{{TOKEN}}` para poder verificar que se llenaron:

```markdown
## Dueño, escalamiento y SLA

| Papel | Quién | Cómo se le pide |
|---|---|---|
| Dueño del pipeline (código, corrida diaria, tablero) | {{NOMBRE}} · {{CORREO}} | {{CANAL}} |
| Suplente — hoy no hay: el bus factor es 1 | {{NOMBRE}} · {{CORREO}} | {{CANAL}} |
| Dato de Mongo (colecciones `*-production`) | Ingeniería · {{EQUIPO}} | {{TICKET}} |
| Dato de Redshift (`analytics.mv_pedidos_enriquecidos_*`) | {{EQUIPO}} · {{NOMBRE}} | {{TICKET}} |
| Los 3 CSV de riesgo (`odds_combinations`, `atr_combinations_iv`, `bnpl_cac`) | Rabbit Risk Analytics · {{NOMBRE}} | {{CORREO}} |
| `ps_transactional_profile.csv` | Pago de Servicios · {{NOMBRE}} | {{CORREO}} |
| Excel del concurso y universo de lanzamiento | Comercial · {{NOMBRE}} | {{CORREO}} |
| Gateway `Gateway_BI` y workspace de Power BI | {{NOMBRE}} · {{CORREO}} | {{CORREO}} |
| VM `rabbit-bi-local` y perfil AWS del túnel SSM | {{EQUIPO}} · {{NOMBRE}} | {{TICKET}} |

**Los compromisos, escritos.** Hasta hoy el único SLA del proyecto eran dos constantes en código:

| Compromiso | Valor | De dónde sale | Qué pasa si no se cumple |
|---|---|---|---|
| Arranque de la corrida diaria | **08:00 hora CDMX** (disparador `14:00` UTC) | tarea `BNPL Pipeline` del Task Scheduler, ver *Despliegue a la VM* | el tablero se queda con el dato de ayer |
| Dato listo para el refresh | **08:20 CDMX** (08:00 + ~20 min) | medido, ver *Flujo completo* | — |
| Refresh del Service | **07:00 CDMX, y está mal: debe moverse a 09:00** | actualización programada del Service | hoy el refresh **se adelanta a la carga del día** y publica lo de ayer sin avisar |
| Duración de la corrida | ~20 min · ~40 el día del `--full` mensual | medido, ver *Flujo completo* | se come la ventana hasta las 09:00 |
| Frescura de una fuente — WARN | 24 h sin escrituras en Mongo | `ops/config.py:22` `LAG_WARN_HORAS` | se vigila, no se actúa |
| Frescura de una fuente — CRIT | 48 h sin escrituras en Mongo | `ops/config.py:23` `LAG_CRIT_HORAS` | si está en `FUENTES_CRITICAS`, la corrida **aborta** |
| Desfase del staging | 1% de los documentos | `ops/config.py:38` `FALTANTES_WARN_PCT` | correr el ETL; si persiste, `--full` |

**No hay SLA de reparación de fuente y no puede haberlo desde aquí**: un CRIT en Mongo lo arregla
Ingeniería. Lo que sí se compromete este proyecto es a abrir el ticket el mismo día y a dejarlo
anotado abajo, con fecha. Un CRIT sin renglón en esta tabla es un CRIT que nadie está siguiendo.

### Incidencias abiertas con las fuentes

| Fuente | En CRIT desde | Horas al {{FECHA}} | Ticket | Quién lo lleva | Última revisión |
|---|---|---:|---|---|---|
| `fintech-customers-production` | 2026-07-22 | 513 | {{TICKET}} | {{NOMBRE}}, Ingeniería | {{FECHA}} |
```
`README.md:385` (fila del CRIT en la tabla de escalamiento):
```markdown
| `CRIT` en fuente | más de 48 h sin escrituras en Mongo | **es de ingeniería, no del pipeline**: la fuente dejó de alimentarse. Abre ticket a {{EQUIPO_ING}} y agrégala a *Incidencias abiertas con las fuentes* |
```
`README.md:597-599`:
```markdown
> Al 2026-08-14, `fintech-customers-production` lleva **513 h** en CRIT: dejó de recibir escrituras
> el 2026-07-22. Reportado a {{EQUIPO_ING}} el {{FECHA}}, ticket {{TICKET}}, lo lleva {{NOMBRE}}.
> Impacto: los clientes enrolados desde entonces no tienen `shopName` ni teléfono. El seguimiento va
> en *Dueño, escalamiento y SLA → Incidencias abiertas con las fuentes*; si esa fila no se actualiza,
> nadie lo está siguiendo.
```
**Verifica:** `Select-String -Path .\README.md -Pattern '\{\{[A-Z_]+\}\}' | Select-Object LineNumber, Line` → cero cuando el dueño llenó todos.

> **Nota de exactitud**: la primera versión de esta tabla decía "05:30 CDMX" y "ventana de 90 min hasta las 07:00". Eso es el horario **viejo**; el README de hoy dice 08:00 en cuatro lugares y documenta que el refresh de las 07:00 se adelanta a los datos. La tabla de arriba ya está corregida — y deja visible el único incidente vivo del despliegue.

### O4.10 · Quién administra cada acceso — la mitad que no espera a nadie (de [G7-gob])
`README.md` entre :495 y :497 · riesgo ninguno · **una hora**

La columna "dónde vive hoy" sale del código y del log; solo faltan los nombres.

```markdown
### Quién administra cada acceso

Arriba está **qué** hace falta. Esto es **a quién pedírselo** el día que otra persona tenga que
levantar el pipeline. Hoy todo cuelga de una sola cuenta de Windows (`Administrator` en la VM): ése
es el bus factor, y no se arregla documentándolo, pero sí se acota.

| Acceso | Dónde vive hoy | Quién lo administra | Cómo se pide |
|---|---|---|---|
| Perfil AWS del túnel SSM | `~/.aws/credentials` de `Administrator` + `.env.mongo_extractor` (perfil `bnpl`) | {{EQUIPO}} · {{NOMBRE}} | {{TICKET}} |
| Permiso de Session Manager sobre el bastión | rol de AWS {{ROL}} | {{EQUIPO}} | {{TICKET}} |
| Redshift `data-rabbit-prod` | `.env.redshift_extractor` | {{EQUIPO}} · {{NOMBRE}} | {{TICKET}} |
| PostgreSQL `rabbit-bi-local`, alias `*_rw` | `.env.postgres_local_client` en la VM | {{NOMBRE}} | {{CORREO}} |
| Rol `pbi_gateway` (solo lectura sobre `pbi_bnpl`) | gestor de contraseñas {{CUAL}} | {{NOMBRE}} | {{CORREO}} |
| VM: RDP, servicio `postgresql-x64-17`, Task Scheduler | instancia {{ID}} | {{EQUIPO}} | {{TICKET}} |
| Gateway `Gateway_BI` y workspace de Power BI | Power BI Service | {{NOMBRE}} | {{CORREO}} |
| Drive compartido `D:\Shared drives\Data Room - BI & Data Analytics` | Google Drive | {{NOMBRE}} | {{CORREO}} |
| `mongo_extractor`, `redshift_extractor`, `postgresql_extractor_uploader` | `C:\Users\Administrator\Documents\Funciones\` — **fuera del repo y sin versionar** | {{NOMBRE}} | {{CORREO}} |
| Repositorio git | `github.com/russellquiroz-spec/buy_now_pay_later` — **cuenta personal, no de la organización** | {{NOMBRE}} | mover a la org: {{TICKET}} |

Tres cosas de esa tabla que no dependen de nadie más y hay que cerrar:

1. **Las tres librerías internas no tienen copia en ningún repo ni versión fijada.** Sin ellas el
   pipeline no arranca, y si esa carpeta se pierde no hay de dónde reinstalarlas. (Lo cierra
   `requirements.txt`.)
2. **El remoto es una cuenta personal.** Si esa cuenta se va, se va el historial.
3. **La tarea programada corre como el usuario con credenciales AWS**: con `SYSTEM` el túnel SSM no
   levanta, así que rotar o dar de baja esa cuenta rompe la corrida diaria del día siguiente.

Ninguna prueba única cubre las diez filas. Cada una prueba lo suyo, todas de lectura:

```powershell
.venv\Scripts\python.exe ops\check_freshness.py                              # tunel SSM + PostgreSQL local
.venv\Scripts\python.exe etl_redshift_to_postgres.py --solo route_mapping    # Redshift
Get-ChildItem "D:\Shared drives\Data Room - BI & Data Analytics" | Select-Object -First 3   # Drive
Get-Service postgresql-x64-17 | Select-Object Status                         # acceso a la VM
```

El gateway, el workspace y el rol `pbi_gateway` no se prueban desde aquí: se comprueban disparando
un refresh a mano desde el Service.
```

### O4.11 · Reparar la tabla partida de `PENDIENTES_NEGOCIO.md` [G11-gob]
`:1067-1079` · riesgo ninguno · **minutos**

El blockquote parte la tabla en dos: las filas que van después **no renderizan**, así que dos acciones ejecutables desaparecen de la lista que la gente lee.

```markdown
| Acción | Efecto en los números | Dónde |
|---|---|---|
| Corregir `"60-89"` → `"DQ 60-89"` en `lossAmount` | `lossAmount` **+$308,974 (+3.4%)** | `bnpl_loss_rates.tmdl:643` |
| Corregir las etiquetas del `SWITCH` de `dynamicTotalRevenue` | quita un salto de 16% al mover el slicer | `bnpl_loss_rates.tmdl:29` |
| Renombrar las dos gráficas `PAR 30 Rate…` | ninguno | página *Vintage Analysis* |
| Limpiar el `queryRef` muerto `par30Cumulative` | ninguno | visual `0ff2052f3312e68375b0` |
| Chequeo de frescura por contenido para `bnpl_cac` y `ps_transactional_profile` | ninguno | `ops/quality_checks.py` |
| Borrar la carpeta `pbi/` (modelo viejo): ahí siguen las 8 `Csv.Document` y las 4 `SharePoint.Files` | ninguno; publicar ese `.pbix` por error sobrescribe el productivo | `pbi/…/expressions.tmdl` |
| ~~Agregar `{"PaidPrev", 0}` al `DATATABLE` de `dq_order`~~ | **hecho el 2026-08-14**, ninguno | `dq_order.tmdl` |
| ~~Borrar `Consulta1` y las expresiones de SharePoint~~ | **hecho el 2026-08-14**, ninguno (§15) | `expressions.tmdl` |

> **Ya no está en esta lista**: activar el `WHERE p.par <> 'PaidPrev'` de las consultas 03 y 04.
> Sobre `bnpl_par` **sí mueve cifras** —$1,684M de venta bruta en dos gráficas— y necesita decisión
> de negocio. Ver §13b.1.
```
**Verifica:**
```powershell
Select-String -Path '.\pbi\Buy Now Pay Later.SemanticModel\definition\expressions.tmdl' -Pattern 'Csv.Document|SharePoint.Files|Consulta1'   # cero
Select-String -Path '..\_deprecado_pbi_origenes_csv_2026-08-14\Buy Now Pay Later.SemanticModel\definition\expressions.tmdl' -Pattern 'Csv.Document|SharePoint.Files|Consulta1'   # 16 hits: es el modelo viejo
```
> La fila tachada **estaba bien tachada**: el `expressions.tmdl` del modelo bueno no tiene ni un `Csv.Document`. Lo que sigue sucio es la copia vieja, que ya salió del repo en O0.2.

### O4.12 · Fechar `plan_implementacion.md` como histórico — la mitad que no espera a nadie (de [G12-gob])
`.kiro/specs/migracion-pipeline-bnpl/plan_implementacion.md:3`, `:13`, `:660-663`, `:680-681` · riesgo ninguno · **minutos**

`README.md:38` manda a este plan para el detalle de las decisiones, y quien lo abra lee "en revisión", "No hay repo git" y una entrega prometida que no existe.

`:3`:
```markdown
Estado: **histórico — foto del 2026-08-12.** El diagnóstico y las mediciones siguen siendo válidos;
el estado del proyecto **no**. Las fases 0 a 6 están completas: el estado vigente se lee en
[`README.md` → Estado](../../../README.md#estado).
```
Debajo de `:13`:
```markdown
> Tabla histórica: así estaba el 2026-08-11. Todo lo de aquí se resolvió — incluido el control de
> versiones, que hoy es `github.com/russellquiroz-spec/buy_now_pay_later`.
```
`:660-663`:
```markdown
## Fase 6 — Power BI — **COMPLETADA 2026-08-14**

Modelo repuntado de los 18 orígenes CSV a `pbi_bnpl` (publicado), gateway `Gateway_BI` en la misma VM
con el rol de solo lectura `pbi_gateway`, y actualización programada a las 07:00 hora CDMX. Detalle
en `README.md` → *Power BI*.

**No se construyó** la "Página de estado del pipeline alimentada por `bnpl_ops.v_freshness_status`"
que prometía este plan: `sql/pbi/` salta de la 17 a la 20 y no existe esa consulta. La vista sí
existe y se consulta a mano (`README.md` → *Verificar una corrida*). Si se decide construirla, entra
como la consulta 19 y como una tabla más del modelo.
```
`:680-681` (punto 8):
```markdown
8. ~~**VM**~~ **Cerrado el 2026-08-12**: la VM es `rabbit-bi-local`, el PostgreSQL destino es
   `localhost:9553/rabbit-bi-local` en esa misma máquina, los datos ya se migraron y la tarea diaria
   `BNPL Pipeline` ya está registrada (08:00 CDMX / disparador 14:00 UTC). `migrar_a_vm.py` quedó
   deprecado. Lo único abierto del despliegue es **mover el refresh de Power BI de las 07:00 a las
   09:00**, que hoy se adelanta a la corrida (`README.md` → *Despliegue a la VM*).
```
> El punto 1 (14.2% con o sin IVA) **NO se cierra aquí**: `PENDIENTES_NEGOCIO.md` §16.1 sigue esperando a Finanzas. Se reencuadra: "medido, no decidido", y se manda a §16.1. Esa parte va a PENDIENTES.

**Verifica:**
```powershell
Get-ChildItem .\sql\pbi\*.sql | Select-Object Name   # confirma que no hay consulta 19 de estado
```

### O4.13 · Registrar las cinco relaciones que cambió la migración, y el PII de `Top100InactiveCustomers` (mitad técnica de [M11])
documento nuevo o sección de `PENDIENTES_NEGOCIO.md` · riesgo ninguno · **minutos**

Hoy **no existe ningún documento** que liste las relaciones que cambiaron. Escribir estas cinco líneas cuesta cinco minutos y es lo que evita que la próxima migración las vuelva a perder sin que nadie lo note:

| # | Relación | Qué pasó |
|---|---|---|
| a | `grid_bnpl[bnplEnrolledAt] → enrollment_dates[Date]` (`ec74a7f6-…`) | **perdida** — restaurada en O1.4 |
| b | `bnpl_loss_rates_with_lead[netsuiteId] → grid_bnpl[netsuiteId]` (`eef16e8f-…`) | **perdida** — restaurada en O1.5 |
| c | `grid_bnpl[netsuiteId] → Top100InactiveCustomers[netsuiteId]`, bidireccional (`43b9c13a-…`) | **perdida** — no se restaura: la tabla está en decisión |
| d | `loans_matured_default_profile[netsuiteId] → grid_bnpl[netsuiteId]` (`AutoDetected_3645b986`) | **nueva**, la inventó Power BI |
| e | `months_closes[netsuiteId] → grid_bnpl[netsuiteId]` (`AutoDetected_c6522e8d`) | **desactivada**, como consecuencia de (d) |

Y el inventario de PII que `Top100InactiveCustomers` publica al modelo, que es lo que hace urgente la pregunta a negocio: `customerName` (:488), `customerLastNames` (:496), `customerPhoneNumber` (:553), `customerBirthdate` (:512), `customerLatitude` (:561), `customerLongitude`, `shopName` (:420), `shopZipCode` (:444) — de 100 tenderos identificados, dentro de un modelo que se manda por correo. Es tabla calculada sobre `grid_bnpl`: no trae origen nuevo, duplica en memoria un subconjunto con PII y **ningún visual lo consume** (0 referencias, ni en el modelo migrado ni en el viejo).

**Verifica:**
```powershell
grep -rn 'Top100InactiveCustomers' 'pbi/Buy Now Pay Later.Report/definition/'   # sin resultados
```
> Lo que espera respuesta: si esa lista sigue haciendo falta, y si necesita nombre y teléfono o le basta `netsuiteId`. Si la respuesta es "ya no", se borra con el procedimiento de Desktop de O3.2 (arrastra sus 7 `LocalDateTable`).

### O4.14 · Medir los dos escenarios de `months_closes → grid_bnpl` (mitad técnica de [M3])
en Desktop + `PENDIENTES_NEGOCIO.md §13.4` · riesgo ninguno · **una hora**

`PENDIENTES_NEGOCIO.md:786-789` ya archiva exactamente este cambio como pregunta abierta. Lo que se hace hoy sin esperar a nadie es **convertirla en una pregunta con evidencia**: medir en Desktop, con las dos configuraciones, el valor de la tarjeta de saldo de `months_closes` sin filtro y con un filtro cualquiera del grid, y anotar los dos pares de números debajo de la tabla de `:772-777`.

El cambio en sí (borrar `AutoDetected_3645b986` para que `months_closes → grid_bnpl` vuelva a activarse) **espera a Riesgo/Finanzas**: mueve $3.88M en *Salud del Portafolio*.

Cuando se autorice, el bloque que queda en `relationships.tmdl:379-386` es:
```tmdl
relationship AutoDetected_c6522e8d-8cd2-4269-9c77-392587d5770d
	fromColumn: months_closes.netsuiteId
	toColumn: grid_bnpl.netsuiteId
```
y hay que corregir en la misma pasada `ayuda_tablero/textos_a_mano.py:99` y `:133` (quitar «por la vía de `loans_matured_default_profile`, que cubre el 99.84% de las filas» y la frase «Al elegir una oficina se caen…»; dejar «Los slicers del grid la filtran directo por netsuiteId») y regenerar el tooltip del visual `8b340c00cf26999459f3`.

> **Alternativa**, si se prefiere conservar el filtrado de `loans_matured`: dejar `3645b986` y ponerle `isActive: false` a `AutoDetected_f537417c` (`months_closes.salesOrderId → loans_matured.salesOrderId`, líneas 215-217), que es una relación hecho-a-hecho más sospechosa que las otras dos. **Una de las dos, no las dos.**

### O4.15 · `analisis_one_shot/README.md` (mitad técnica de [G13-gob]) y el `.env` de la raíz [G9-gob]
riesgo ninguno · **minutos**

**a) `analisis_one_shot/README.md:63`** — nombra una base que ya no existe, así que quien lo siga se atora en el primer paso:
```markdown
| Clientes aprobados BNPL | PostgreSQL `rabbit-bi-local` (alias `mongo_bnpl` de `postgres_local_client`) | `mongo_bnpl.fintech_credit_approval_production` |
```
**b) `analisis_one_shot/README.md:90-101`** — lista 8 de 10 scripts:
````markdown
```
analisis_one_shot/
├── run.py                    ← Orquestador — ejecutar este
├── run_v1.py                 ← Variante V1: la línea de crédito sale del Excel de Propaga, no de Mongo
├── config.py                 ← Alias de BD, ruta de salida y el Excel de línea de crédito de la V1
├── extract_redshift.py       ← Query + fetch de órdenes Redshift
├── extract_bnpl_postgres.py  ← Enrolled clients + órdenes BNPL desde PostgreSQL
├── analisis_1.py             ← Lógica Análisis 1 (activos Rabbit vs BNPL)
├── analisis_2.py             ← Lógica Análisis 2 (línea de crédito vs drop size)
├── base_minima.py            ← Construcción de la base SO-nivel
├── exportar.py               ← Excel writer + histograma PNG
└── README.md                 ← Este archivo
```

> **De dónde sale la línea de crédito, y por qué hay dos versiones.** `run.py` la toma de
> `fintech_credit_approval_production` (lo que hay en Mongo). `run_v1.py` la toma del Excel que
> publica Propaga (`config.py:9`), porque **Propaga actualiza las líneas mensualmente en ese archivo
> antes de cargarlas a MongoDB**: entre publicación y carga, Mongo tiene la línea del mes anterior.
> No está confirmado cuánto dura ese desfase — ver `PENDIENTES_NEGOCIO.md` §16.11.
````
> El árbol **ya no lleva** `analisis_bnpl_one_shot.py`, porque lo borra el punto (c). Si decides no borrarlo, agrégalo con la nota `← DEPRECADO: muere en su línea 10, lo reemplazó run.py`.

**c) El `.env` de la raíz y su único consumidor** — el README dice «No hay `.env` que crear en la raíz» y sí existe, con tres URIs `postgresql+psycopg2://` con contraseña. Agregar después de `README.md:500`:
```markdown
> **Hay un `.env` en la raíz y no es de este proyecto.** Trae tres URIs `postgresql+psycopg2://` con
> usuario y contraseña: `BD_ENGINE_RABBIT_LOCAL`, `BD_ENGINE_RABBIT_LOCAL_SOPORTE` y
> `BD_ENGINE_RABBIT_LOCAL_PBI` — las tres apuntan a la misma base, `localhost:9553/rabbit-bi-local`.
> **Ningún script del pipeline lo lee.** Lo genera `postgresql_extractor_uploader` desde el alias
> `local_rw` de su propio `.env.postgres_local_client`, así que se regenera solo si lo borras — de
> hecho se regeneró durante la auditoría del 2026-08-14 y le apareció la tercera variable. Está en
> `.gitignore:2-3` y nunca se commiteó (verificado con `git log --all --diff-filter=A -- .env`).
> Resumen: no hay que crearlo, no hay que mantenerlo y no hay que commitearlo; si esa contraseña se
> rota, este archivo queda viejo y da igual.
```
Y cerrar la contradicción en `README.md:680`:
```markdown
**3. No hay `.env` que crear en la raíz.** Cada librería lee el suyo (`.env.mongo_extractor`,
`.env.redshift_extractor`, `.env.postgres_local_client`), que debe existir en la VM con el perfil
correspondiente. Si ves un `.env` en la raíz, no lo creaste tú y no lo mantienes tú: lo genera
`postgresql_extractor_uploader` y ningún script del pipeline lo lee — ver *Requisitos*.
```
Y borrar el único consumidor, que muere en su línea 10 y sostiene 10 KB de código muerto:
```powershell
git rm analisis_one_shot/analisis_bnpl_one_shot.py
```
**Verifica:**
```powershell
Select-String -Path .\analisis_one_shot\README.md -Pattern 'rabbit_fintech_bi'   # cero
(Get-ChildItem .\analisis_one_shot -Filter *.py).Count                           # 9, los 9 en el arbol
Select-String -Path .\*.py,.\ops\*.py,.\analisis\*.py,.\analisis_one_shot\*.py -Pattern 'BD_ENGINE_RABBIT_LOCAL'   # cero
.venv\Scripts\python.exe -m compileall analisis_one_shot
```
> `rabbit_fintech_bi` también sigue en `design.md:474` y `:700`: conviene barrerlo de una vez.

### O4.16 · Estructura y diagrama del README: falta `ayuda_tablero/` y hay un tercer paso manual [G10-gob]
`README.md:65` (diagrama), `:135-141`, árbol :764-795 · riesgo ninguno · **minutos**

`ayuda_tablero/` son 10 `.py`, un README de 9.5 KB y los 168 textos del tablero, y no aparece ni en el árbol ni en el diagrama.

`:135-141`:
````markdown
**Tres pasos son manuales a propósito.** Los dos primeros porque el dato lo publica una persona, no
una fuente, así que no tiene sentido intentarlos todos los días; el tercero porque escribe el PBIP,
no la base.

```powershell
.venv\Scripts\python.exe carga_archivos_bnpl.py                          # 4 CSV del Drive -> archivos_bnpl.*
.venv\Scripts\python.exe carga_clientes_concurso.py                      # Excel de negocio -> bnpl.bnpl_clientes_concurso
.venv\Scripts\python.exe ayuda_tablero\documentar_tablero.py --aplicar   # los 168 tooltips del PBIP
```
````
y al final del párrafo que sigue:
```markdown
El tercero sí es idempotente y sin `--aplicar` solo dice qué cambiaría; su detalle está en
[`ayuda_tablero/README.md`](ayuda_tablero/README.md).
```

En el diagrama, **después** de la línea 65 sin tocarla (esa línea trae el `(mover a 09:00)`, que es el pendiente abierto):
```
  El modelo (PBIP)              ayuda_tablero/                  los 168 tooltips del tablero
  pbi/…Report                ─▶ documentar_tablero.py --aplicar  A MANO, cuando cambia el modelo
```
En el árbol, después de `migrar_a_vm.py` (:772) y antes de `ops/`:
```
ayuda_tablero/              MANUAL: los 168 tooltips del PBIP (ver su README)
  conocimiento.py           El catálogo: 21 tablas, 59 campos, 66 medidas. Fuente de DICCIONARIO.md
  documentar_tablero.py     La entrada: sin flags dice qué cambiaría, --aplicar lo escribe
  _datos/                   inventario.json y textos.json: derivados, no se versionan
```
**Verifica:**
```powershell
(Select-String -Path .\README.md -Pattern 'ayuda_tablero').Count   # de 2 a >= 6
Select-String -Path .\README.md -Pattern 'Dos cargas son manuales' # cero
```

---

---

## 2. Acciones que se pisan — resumen

| Se pisan | Qué pasa si no lo cuidas | Orden |
|---|---|---|
| **O3.7** y la acción [M10] del paquete modelo | Son **la misma edición** del textbox `32f24f3b89c6ffcf18f5` descrita dos veces | Hacerla una vez |
| **O2.11** y **O2.12** (`main.py` `[5/6]`) | Cada una reescribe el mismo bloque; aplicar la segunda sobre la primera borra `_reportar_calidad` o borra `rotas` | Fusionadas en O2.11+O2.12, tal como está escrito |
| **O2.2** y **O2.3** (bucle de `_construir_vistas_pbi`) | El `try/except` y el `_registrar` viven en el mismo bucle | Bucle fusionado en O2.2+O2.3 |
| **O2.10** y **O2.13** (`quality_checks.py:140`) | Las dos introducen `check.get("db", DB_STAGING)` y el `try/except` | O2.10 primero; O2.13 solo agrega el noveno check |
| **O2.13** y **O4.6** | Una hace nueve chequeos, la otra documenta ocho | O2.13 antes, o escribir O4.6 ya en nueve |
| **O1.1** y **O2.14** | Las dos tocan `etl_mongo_to_postgres.py:412-499` | O1.1 primero; O2.14 sobre el resultado |
| **O2.15** y **O2.16** | O2.16 ancla el commit de `mongo_extractor`; O2.15 lo cambia | O2.15 → commit/push → O2.16 con el SHA nuevo |
| **O2.16** y **O4.4** | O2.16 elimina el paso 2 del README; O4.4 lo referencia | O2.16 primero, y en O4.4 dejar solo la frase de `seaborn` |
| **O4.15** y el árbol de `analisis_one_shot` | Si se borra `analisis_bnpl_one_shot.py`, no se escribe su renglón | Ya resuelto en el texto de O4.15 |
| **O1.8** y **O3.14** | O1.8 crea una `LocalDateTable` nueva al retipar `paymentDate` | O1.8 antes; O3.14 la barre |
| **O0.4** + **O4.x** (todas las del README) | Los anclajes se corren entre sí | De abajo hacia arriba, localizando el texto |
| **O3.3** y **O3.14** *(no estaba listado)* | O3.3 devuelve la jerarquía a `3fae7adac63213c97e39`, así que el inventario de O3.14 sube de **18 visuales sobre 7 columnas** a **19 sobre 8**. La nota de O3.14 dice que son 18 «porque ese visual ya la perdió» — deja de ser cierto en cuanto se aplica O3.3 | Si se hacen las dos: O3.3 primero y re-medir con `revisar_referencias.py` antes del PASO 2 |
| **O3.10** y **O4.2c** *(no estaba listado)* | O4.2c está redactada como recomendación futura («Renombrar las seis gráficas… Nombres propuestos…») y O3.10 ya las renombró, serie incluida | O3.10 primero; escribir O4.2c en pasado y tachada |
| **O2.8** y **O2.14** *(no estaba listado)* | O2.8 agrega un `print` nuevo en `run()` que O2.14 tiene que convertir, o su verificación falla con un resultado | O2.8 primero; O2.14 sobre el resultado |
| **O2.2** y `16_pbi_grants.sql` *(no estaba listado)* | Con el `raise` justo tras el bucle, una vista rota deja a `pbi_gateway` sin permisos sobre las sanas: el archivo de grants nunca corre | El `raise` va DESPUÉS de aplicar los grants |

---

## 3. Checklist

### Ola 0 — Git
- [x] O0.1 `.gitignore`: `.pbi/` y `*.abf` ignorados (`git check-ignore` imprime la regla)
- [x] O0.2 `pbi/` (deprecado) fuera del repo y sin su `.pbi/`; `pbi_new/` conserva su nombre; cache y `.pbix` borrados
- [x] ~~O0.3~~ CANCELADA - inventario.py:7 y portada.py:8 ya apuntan a `pbi_new`, que es el productivo
- [x] O0.4a `README.md:769-770` — qué se versiona del PBIP y qué no
- [x] O0.4b `README.md:576-589` — sección Power BI reescrita
- [x] O0.4c `README.md:760-761` — una sola carpeta en el árbol
- [x] O0.4d `sql/pbi/README.md:121-126` y `:135` — estado de la migración
- [x] O0.4e `sql/pbi/README.md:294-301` — el barrido cubre todo el SemanticModel
- [x] O0.4f `README.md:815-816` y `sql/pbi/README.md:472-473` — markup XML borrado
- [x] O0.5 Cuatro commits temáticos de los 25 modificados
- [x] O0.6 Cuatro commits de lo nuevo (sql, cargas, ayuda_tablero, auditoría) — **+ `sql/16_pbi_grants.sql` y `PLAN_TECNICO.md`, que el plan no listaba**
- [x] O0.7 Commit del PBIP — **falta el `git push`**, bloqueado por el clasificador de permisos de la sesión

### Ola 1 — El tablero deja de mentir
- [x] O1.1 ETL Mongo: extraer antes de borrar, una transacción, `RuntimeError` en 0 documentos
- [x] O1.2 `docs_mongo == 0` → CRIT en `check_freshness`
- [x] O1.3 `bnplMinimumTenure` con guardia de blanco (146K → 9K) — *falta comprobar la tarjeta en Desktop*
- [x] O1.4 Relación `grid_bnpl[bnplEnrolledAt] → enrollment_dates[Date]` restaurada
- [x] O1.5 Relación `with_lead → grid_bnpl` restaurada + 3 lugares de texto corregidos — **eran 6 ocurrencias en `textos_a_mano.py`, no 5** (la 6ª con otra redacción y partida entre líneas), **y faltaba `conocimiento.py:75`**, que metía `SIN_GRID` en la tabla cuya relación restaura esta acción
- [x] O1.6 `Y0` de `tendenciaNoEnroladosDropProyectada` filtra `"N"`
- [x] O1.7 SWITCH de `bnpl_audiencia_agg[valor]` + `formatString: #,0`
- [x] O1.8 Tipos de `months_closes` alineados en el `.sql` **y** en el `.tmdl`
- [x] O1.9 `ruta_inferida` = TRUE cuando no hay tramo — *medir después del rebuild, no se tocó la base*

### Ola 2 — Que no se rompa
- [x] O2.1 `CAPAS` con `14_archivos_bnpl.sql` y `13_bnpl_clientes_concurso.sql` + 4 doc fixes
- [x] O2.2 `build_bnpl`: try/except por vista, `commit_sha`/`sql_sha256`, `bnpl_version.py`. **El `raise` se movió DESPUÉS de `16_pbi_grants.sql`**: abortar antes dejaba a `pbi_gateway` sin permisos sobre las vistas sanas
- [ ] **O2.3 NO APLICADA — el código no coincide con el plan.** El cierre de `run()` ya trae `if not solo or rebuild:` (no `if not solo:`) y seis líneas de comentario propias. Falta el caso `--solo` sin `--rebuild` y el aviso del revisor. Parche listo, pendiente de decidir si esa guarda es deliberada
- [x] O2.4 `bnpl.a_fecha()` y `bnpl.a_coord()` en `sql/02`
- [x] O2.5 Los siete casts de `grid_bnpl` por las funciones guardadas — *medir después del rebuild*
- [x] O2.6 `DISTINCT ON` en `enrolados`, `preautorizados` y `lineas` de `grid_bnpl`
- [x] O2.7 `DISTINCT ON` en `enrolados` de `grouped_orders` — **hoy no puede mover cifras**: los cuatro CTE entran contra un `CREATE UNIQUE INDEX`, así que si hubiera duplicados el build ya estaría roto
- [x] O2.8 Redshift arranca en frío sin `bnpl.grouped_orders`
- [ ] **O2.9 DIFERIDA** — `sql/pbi/20_concurso_base.sql` y `sql/pbi/README.md` se estaban editando a mano en paralelo
- [x] O2.10 Las 15 identidades entre capas como chequeos
- [x] O2.11+O2.12 `main.py [5/6]`: nivel por severidad, marca NUEVA, salida 1 si una identidad se rompe (incluye `NO_APLICABLE`)
- [x] O2.13 Cargas manuales en `etl_runs` + `cargas_manuales_viejas`
- [x] O2.14 Los 16 `print` de los tres ETL → `log.info` — **son 17: O2.8 agrega uno que esta acción tiene que convertir** (choque no listado en «Acciones que se pisan»)
- [ ] **O2.15 DIFERIDA** — vive fuera del repo (`mongo_extractor`), requiere PR aparte y medir antes con `aws ssm describe-sessions`
- [ ] **O2.16 DIFERIDA** — depende de O2.15 y de que los tres repos internos estén limpios para leer sus SHA
- [x] O2.17 `ops/notificar.py` + enganche en `main.py` — *falta el `.env.bnpl_pipeline` (credencial SMTP y destinatarios)*

### Ola 3 — Modelo y nombres
- [x] O3.1 3 consultas "Errores en…" y 4 queryGroups borrados — *falta abrir el `.pbip` y confirmar que carga*
- [ ] **O3.2 REQUIERE DESKTOP** — 4 tablas calculadas muertas. El plan mismo dice que es el único que no conviene hacer en texto
- [x] O3.3 Jerarquía Año/Mes en "Ever Activated Customers" — **sube el inventario de O3.14 a 19/8**
- [x] O3.4 Slicer "Cosecha Enrolamiento" sin selección persistida
- [x] O3.5 `inventario.py` recolecta las cinco fuentes de referencias — **971 refs**, no 973 (O3.3 suma 1, O3.7 resta 1... y sigue moviéndose)
- [x] O3.6 `revisar_referencias.py` reescrito — reportó `TARGET.Area` y, tras O3.7, **ninguna**
- [x] O3.7 `TARGET.Area` borrado del textbox de Audiencias — **el archivo queda en 38 líneas, no 37**: el revisor midió terminadores CRLF, no líneas
- [x] O3.8 Cuatro títulos del Funnel + subtítulo del primero
- [x] O3.9 Tres `nativeQueryRef` del Funnel (sin tocar `queryRef`)
- [x] O3.10 Seis gráficas de tasa PAR: título y serie
- [x] O3.11 Seis subtítulos del Vintage corregidos
- [x] O3.12 Cuatro vistas `v_pbi_*` fuera del `.sql` + 4 `DROP` a mano (pendientes de correr sobre la VM)
- [x] O3.13 `activePageName` a la portada + nota en `ayuda_tablero/README.md`
- [ ] **O3.14 REQUIERE DESKTOP** — fecha automática. Jornada larga, riesgo alto. **Inventario corregido: 19 visuales sobre 8 columnas base**, no 18/7

### Ola 4 — Documentación, gobierno y continuidad
- [x] O4.1 Grano de `grouped_orders` en `sql/03:1` y en el README
- [x] O4.2 Tres afirmaciones de `PENDIENTES` — **eran 3 citas del título viejo, no 4**: la cuarta usaba la forma abreviada `PAR 30 Rate…` que ningún grep del título completo atrapa
- [x] O4.3 `ayuda_tablero/README.md`: los cinco orígenes del revisor
- [x] O4.4 Requisito de Python + `seaborn` para los 9 `pythonVisual`
- [x] O4.5 Runbook de falla — **reescrito**: con O1.1, el staging ya NO queda vacío; 27→46 tablas; 18→19 vistas
- [x] O4.6 Los chequeos de calidad documentados — **son 24, no 9**, y **10 CRIT / 5 WARN** entre las identidades
- [x] O4.7 `ayuda_tablero/diccionario.py` creado + las dos líneas del README — *falta correr `--escribir` para generar `DICCIONARIO.md`*
- [x] O4.8 `ops/respaldo.bat` + `.gitignore` + sección de RTO — *falta rellenar `PGUSER` y el `pgpass.conf`*
- [x] O4.9 Dueño, escalamiento y SLA — **23 líneas con `{{TOKEN}}` por llenar**
- [x] O4.10 Quién administra cada acceso (10 filas)
- [x] O4.11 Tabla partida de `PENDIENTES` reparada
- [x] O4.12 `plan_implementacion.md` fechado como histórico + Fase 6 cerrada
- [x] O4.13 Las cinco relaciones que cambió la migración + inventario de PII
- [ ] **O4.14 REQUIERE DESKTOP** — medición de los dos escenarios de `months_closes`; mueve $3.88M y espera a Riesgo/Finanzas
- [x] O4.15 `analisis_one_shot/README.md` + `.env` de la raíz + `analisis_bnpl_one_shot.py` borrado
- [x] O4.16 `ayuda_tablero/` en el diagrama y en el árbol; "tres pasos manuales"

### Ola 5 — Validación post-corrida
- [ ] **O5.1 `validar_bnpl.py` no está enganchado a nada.** Existe desde `96230b1` y se corre a mano
  (`python validar_bnpl.py`); ni `main.py` ni `run_pipeline.bat` lo invocan. Las dos cosas que
  **solo** él comprueba no se verifican en ninguna corrida programada: los permisos reales de
  `pbi_gateway` —conectándose como ese rol y planeando cada vista, que es lo único que caza el
  `42501` del 2026-08-14— y el inventario de objetos vivos sin archivo que los produzca, que es lo
  que sacó a `concurso_base_liquidado` antes de que el CASCADE se la llevara. El enganche va en
  `main.py:237`, después de `[6/6]`, donde hoy se decide el código de salida.
- [ ] **O5.2 Decidir qué hace el pipeline con el hallazgo conocido — ANTES de aplicar O5.1.**
  El validador sale con código 1 ante *cualquier* hallazgo y `run_pipeline.bat` propaga ese código al
  Task Scheduler. Hoy el único hallazgo es `credit_order_sales_order_id_nulo` (1,507 filas, CRIT),
  defecto de la fuente que no se arregla desde aquí: enganchado tal cual, la tarea se reportaría
  FALLO todas las noches por algo ya aceptado — el mismo patrón que `cargas_manuales_viejas`. Tres
  salidas: bajar ese check a WARN, correr el validador informativo sin tocar el código de salida, o
  darle línea base (~1,507) para que alerte solo cuando crezca.

**Medido (2026-08-26)** sobre la corrida **de prueba, lanzada a mano**, del 2026-08-25 22:00 (20.0
min, terminada bien) — no sobre una programada: el validador pasa completo salvo ese CRIT. 10/10
colecciones extraídas; 20 vistas en la base contra 20 archivos en `sql/pbi/` y 11 materializadas
contra 11 en `build_bnpl.CAPAS`, **cero huérfanas**; 21 de 24 chequeos en OK con las 14
identidades entre capas en 0; y los permisos en verde, incluidos los tres schemas vedados
(`archivos_bnpl`, `mongo_bnpl`, `redshift_bnpl`) y el SELECT real como `pbi_gateway` sobre las
cinco tablas del concurso. Es decir: O5.1 no está bloqueada por otra cosa que O5.2.

### Va a PENDIENTES, no a este plan
- [ ] Credencial SMTP / webhook y lista de destinatarios (activa O2.17)
- [ ] ¿El concurso se mide solo sobre el universo del Excel? (activa el filtro de O2.9)
- [ ] ¿Se activa `months_closes → grid_bnpl`? Mueve $3.88M (O4.14 le pone evidencia)
- [ ] ¿Sigue haciendo falta `Top100InactiveCustomers` con PII? (O4.13 le pone el inventario)
- [ ] Nombres, correos y colas de tickets de O4.9 y O4.10
- [ ] 14.2% del interés: ¿con o sin IVA? (§16.1)
- [ ] Desfase entre el Excel de líneas de Propaga y su carga a Mongo (§16.11)
- [ ] Mover el remoto de la cuenta personal a la organización

---

## 4. Estado de la aplicación — 2026-08-14

**Aplicadas: 55 de las 67.** Ola 0 completa salvo el `push`, Ola 1 completa, Ola 2 con 13 de 17,
Ola 3 con 12 de 14, Ola 4 con 15 de 16.

**Las 12 que faltan, y por qué:**

| Acción | Motivo |
|---|---|
| O0.7 (`git push`) | bloqueado por el clasificador de permisos de la sesión; los commits existen en local |
| O2.3 | el código ya no coincide con el plan: trae `if not solo or rebuild:` con comentario propio |
| O2.9 | `sql/pbi/20` y `sql/pbi/README.md` se estaban editando a mano en paralelo |
| O2.15 | vive fuera del repo (`mongo_extractor`); PR aparte y medir antes con `describe-sessions` |
| O2.16 | depende de O2.15 y de que los tres repos internos estén limpios |
| O3.2 · O3.14 · O4.14 | requieren Power BI Desktop |

Y estas quedaron **aplicadas pero sin verificar**, porque su comprobación necesita Desktop o la base:
O1.3-O1.7 (tarjetas y visuales), O1.8, O1.9, O2.5-O2.7, O2.10 (consultas SQL). Las consultas están
escritas y listas para pegar en el reporte de cada lote.

**Lo que cambió respecto de lo que el plan predecía**, y que hay que tener presente al leer el resto:

| # | Lo que decía el plan | Lo que había en realidad |
|---|---|---|
| 1 | `master` está `ahead 2` | `ahead 3` — falta `57b1c87` en la lista de O0.7 |
| 2 | O0.6 versiona `sql/13-15` | falta `sql/16_pbi_grants.sql`, y `PLAN_TECNICO.md` no está en ningún commit |
| 3 | `pbi_bnpl` tiene **18** vistas | **19** desde `21_concurso_clientes.sql`. El plan lo dice mal en cinco sitios |
| 4 | O1.5 toca 5 ocurrencias de `textos_a_mano.py` | son **6**; la 6ª con otra redacción y partida entre líneas, invisible a una búsqueda literal — y la verificación del plan daba luz verde igual |
| 5 | O1.5 no menciona `conocimiento.py` | `conocimiento.py:75` metía `SIN_GRID` en `bnpl_loss_rates_with_lead`, justo la tabla cuya relación restaura la acción |
| 6 | O2.3 parte de `if not solo:` | el código ya trae `if not solo or rebuild:` — alguien lo arregló a medias |
| 7 | O2.2 pone el `raise` tras el bucle | ahí deja a `pbi_gateway` sin permisos sobre las vistas sanas: `16_pbi_grants.sql` nunca corre |
| 8 | O2.8 y O2.14 no se pisan | sí: O2.8 agrega un `print` que O2.14 tiene que convertir |
| 9 | Verificación de O2.10: «23 renglones»; de O2.13: «9 chequeos» | **24**, aplicadas en el orden que manda el plan |
| 10 | O2.6/O2.7 «pueden mover cifras» | hoy no: los `CREATE UNIQUE INDEX` garantizan que ya no hay duplicados |
| 11 | O0.4d/O0.4e verifican sobre `pbi\` | residuo del renombre cancelado; se aplicó sobre `pbi_new\` |
| 12 | Verificación de O1.1 «sin tocar Mongo» | `run()` aplica DDL contra Postgres en su línea 480 antes de fallar |

**Cambio de operación no previsto por el plan:** la tarea `\BNPL Pipeline` se movió de `13:30` UTC
(07:30 CDMX) a **`06:00` UTC (00:00 CDMX)**. El margen contra el refresh de las 08:30 pasa de 40 min
a 8 h 30 min. `README.md` y `plan_implementacion.md` ya lo reflejan.

**Pendiente y con dueño:**

- `git push` de los commits (bloqueado por el clasificador de permisos de la sesión).
- Las verificaciones que necesitan Power BI Desktop (O1.3 a O1.7) y las que necesitan la base
  (O1.8, O1.9, O2.5, O2.6, O2.7, O2.10): ninguna se corrió, por el riel de no tocar la base.
- Decidir sobre O2.3.
- Enganchar `validar_bnpl.py` al pipeline (O5.1), que depende de decidir O5.2: hoy su
  código 1 por el CRIT conocido marcaría la tarea como FALLO cada noche.

---

**Esfuerzo total honesto:** Ola 0 ≈ 1 jornada · Ola 1 ≈ 1.5 jornadas · Ola 2 ≈ 3 jornadas · Ola 3 ≈ 1.5 jornadas + 1 jornada larga aparte para O3.14 · Ola 4 ≈ 2 jornadas. **Nueve a diez jornadas**, y las Olas 0 y 1 valen por sí solas: sin la 0 nada de esto es entregable, y sin la 1 el tablero seguirá dando números que nadie puede defender en una junta.
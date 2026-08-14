# Auditoría del pipeline BNPL — informe final

> ## Convención de nombres del PBIP
>
> | Carpeta | Estado | Qué es |
> |---|---|---|
> | **`pbi_new/`** | **PRODUCTIVO** | El modelo publicado. Sus 17 tablas leen de `pbi_bnpl` y refresca desde el Service por `Gateway_BI`. |
> | **`pbi/`** | **DEPRECADO** | El modelo viejo, con 18 orígenes de archivo. No se refresca por gateway. No se abre ni se publica. |
>
> A lo largo de este informe se compara el contenido de las dos carpetas para reconstruir qué cambió en
> la migración. **Toda mención de `pbi/` es al modelo deprecado**, y sirve como referencia histórica —
> por ejemplo, es la única copia de las dos relaciones que la migración perdió (§B7 y §B8). El modelo
> que hay que corregir es siempre `pbi_new/`.
>
> Las dos comparten `reportId` y `datasetId`, y por eso §C9 es un riesgo activo: publicar el deprecado
> sobrescribe el artefacto productivo.

**Fecha:** 2026-08-14 · **Alcance:** repo completo en modo lectura (no se ejecutó el pipeline ni se consultó Postgres) · **Hallazgos consolidados:** 71 verificados → 52 después de deduplicar.

---

## 0. Lo que está bien (y hay que decirlo)

Este proyecto tiene documentación mejor que la mayoría de los pipelines que se auditan. Buena parte de lo que un auditor normalmente reporta como hallazgo aquí ya está escrito, y escrito con precisión:

| Lo que cubre bien | Dónde |
|---|---|
| Semáforo de frescura, qué significa cada estado y qué hacer | README.md:334-371 |
| Que las dos alertas de calidad crónicas son normales y por qué | README.md:366-371, :122-125 |
| Que la Fase 5 está lista salvo programar la tarea, con el `schtasks` completo y la advertencia de que SYSTEM no levanta el túnel SSM | README.md:33, :636-643 |
| Que los tiempos de 17 min son anteriores a los tres pasos nuevos de Redshift, y que "si da 17, es que el paso 3 no corrió" | README.md:108-111, :330 |
| 15 identidades de verificación entre capas, con sus valores medidos | README.md:377-423 |
| Runbook completo de fallas del refresh de Power BI | sql/pbi/README.md:220-327 |
| Por qué el refresh no puede ser incremental (pagos con 519 días de retraso) | README.md:504-506, :712 |
| El grano ancho real de `grouped_orders` y por qué hay que colapsarlo | sql/pbi/20_concurso_base.sql:44-46 |
| Reglas de negocio abiertas, cerradas con datos y con quién hay que hablar | PENDIENTES_NEGOCIO.md, 1078 líneas |

Varios "hallazgos" iniciales se cayeron precisamente porque el README ya los decía mejor. El valor de este informe está en lo que queda: lo que existe en el código y no está escrito en ninguna parte, y lo que está escrito de forma que ya no corresponde al código.

---

## 1. Bloqueante transversal

### T1 · Nada de la capa de consumo está en git — CRÍTICO — no documentado (el README afirma lo contrario)

Consolida los hallazgos de git de cuatro lentes distintos.

- `git ls-files --others --exclude-standard` = **704 archivos sin rastrear**: `sql/pbi/` (21 archivos, las 18 consultas que *son* el tablero), `pbi_new/` (334), `pbi/` (333), `ayuda_tablero/` (11, incluidos los 168 tooltips), `carga_archivos_bnpl.py`, `carga_clientes_concurso.py`, `sql/13-15`.
- `git diff --stat` = 25 archivos modificados, 2,147 inserciones, 470 borrados sin commitear, incluidos README.md y PENDIENTES_NEGOCIO.md.
- `git branch -vv` = `master b4979cc [origin/master: ahead 2]`: ni los dos commits que existen están empujados.
- `git check-ignore` sobre `sql/pbi/01_*.sql` sale vacío: **no están ignorados, simplemente nunca se agregaron**. `.gitignore` solo excluye `*.pbix`.
- Se buscó copia fuera de la VM: la carpeta de OneDrive que apunta el registro **no existe**. No hay respaldo del proyecto fuera de este disco.
- Contradicción documental: README.md:702-703 dice "sí se versionan el `.pbip` y las carpetas `.Report/` / `.SemanticModel/`". Hoy ninguna está trackeada.
- El propio despliegue del README (`git clone …`, README.md:600) reconstruiría un pipeline **sin capa de consumo**, y solo se notaría cuando `build_bnpl.py:68` reviente con `No encontré consultas en sql/pbi`.

**Consecuencia directa:** si se pierde la VM se pierde el tablero completo. Y sin repo, ninguno de los arreglos de abajo queda registrado ni es revisable.

---

## 2. Lo que hace que el tablero muestre datos viejos, incompletos o se rompa

| # | Hallazgo | Sev | Doc |
|---|---|---|---|
| A1 | Colección Mongo con 0 filas trunca el staging y la corrida se marca `ok` | Alto | Parcial |
| A2 | Si el pipeline falla de madrugada nadie se entera: cero notificaciones | Alto | No |
| A3 | La tarea programada no existe y `run_pipeline.bat` nunca se ha ejecutado — **cerrado 2026-08-14** | Alto | Sí |
| A4 | `build_bnpl.py` crea vistas sobre `archivos_bnpl`, que solo se carga a mano | Alto | Parcial |
| A5 | `grid_bnpl` y `grouped_orders` unen contra Mongo sin deduplicar | Alto | Parcial |
| A6 | Casts de texto sin guarda dentro de las materializadas | Medio | No |
| A7 | `--rebuild --solo X` borra vistas de `pbi_bnpl` por CASCADE y no las recrea | Medio | Parcial |
| A8 | El staging de Mongo borra antes de extraer y sin transacción | Medio | No |
| A9 | El paso 3 depende del paso 4 (`bnpl.grouped_orders`) | Medio | No |
| A10 | Nada valida automáticamente `bnpl.*` ni `pbi_bnpl.*` | Medio | Parcial |
| A11 | Las cargas manuales no dejan rastro ni tienen semáforo | Medio | Parcial |
| A12 | Un solo ambiente: DROP de vistas contra la base que lee Power BI, y una colección `-dev` | Medio | No |
| A13 | No hay respaldo del PostgreSQL local | Medio | No |
| A14 | El paso 3 nunca ha corrido con sus seis tablas dentro de `main.py` | Bajo | Sí |

### A1 · Una colección con 0 filas deja el tablero en ceros y la corrida sale "ok"
`etl_mongo_to_postgres.py:416` hace `TRUNCATE` con `execute_sql` (autocommit) 75 líneas **antes** del `extract_aggregate` de la 491. En :493 el `if filas:` solo salta el load — no lanza excepción. Se registra `filas=0` en `etl_runs`, el paso 4 refresca las matviews sobre la tabla vacía y `main.py:167-170` escribe `modo='ok'` y `return 0`.
La compuerta de frescura no lo atrapa: `ops/check_freshness.py:157-158` devuelve `SIN_DATOS` (no `CRIT`) cuando `docs_mongo == 0`, y `main.py:99` solo bloquea con `semaforo_fuente == 'CRIT'`. Si la colección fue **renombrada**, `sondear_mongo` da `docs_mongo=0` y ni siquiera sale el WARNING del paso 6.
El diseño pedía lo contrario: `.kiro/specs/…/design.md:643` — *"Abortar la etapa con mensaje explícito indicando colección"*. No se implementó y no está en ningún README.
*Pendiente de verificar contra la base:* que las matviews de `bnpl` efectivamente den ceros con el staging vacío.

### A2 · Cero notificaciones
El único manejo de fallo es `run_pipeline.bat:13-17`: un `echo` a `logs\scheduler.log`, **archivo que no existe**. Búsqueda de notific/correo/email/Slack/Teams/webhook en todos los `.py` y `.md`: las únicas coincidencias hablan de destinos de publicación del legacy. README.md:119-120 dice "para que el Task Scheduler lo reporte" — el Task Scheduler solo guarda el código en su historial, no avisa a nadie. Combinado con A1, hay modos de falla que ni siquiera levantan el código 1.

### A3 · La tarea no existe y la ruta desatendida nunca se probó
`Get-ScheduledTask` en la VM: 154 tareas, ninguna con BNPL ni pipeline. `logs/` solo tiene `pipeline_2026-08.log`; `scheduler.log` no existe, o sea que el `.bat` **nunca se ejecutó**. Las tres corridas del histórico son 2026-08-12 23:38, 2026-08-13 00:17 y 2026-08-13 12:53 — horas de gente. Hoy 2026-08-14, sin corrida.
Lo que ya está escrito (README.md:33, :636-643) es que falta programarla. Lo que **no** está escrito es que el `.bat` nunca corrió ni una vez: usuario sin sesión, credenciales AWS del perfil y el túnel SSM sin sesión interactiva están sin probar. Y README.md:650 afirma en presente que `logs\scheduler.log` "tiene lo que el `.bat` capturó".

**Cerrado el 2026-08-14.** Existe la tarea `\BNPL Pipeline`, diaria, disparador `13:30` = **07:30 CDMX** (el reloj de la VM está en UTC; el `05:30` que pedía el plan pasó primero a las 8 por decisión de negocio y de ahí a las 7:30, para no quedar pegado al refresh). Corre como `Administrator` con `LogonType S4U` y `RunLevel Highest`: sin contraseña guardada y sin depender de una sesión abierta, que era justo el supuesto sin probar. Se lanzó una vez con `Start-ScheduledTask` —no desde consola, para ejercitar la ruta desatendida— y **el túnel SSM sí levanta sin sesión interactiva**; `logs\scheduler.log` ya existe, así que README.md:650 dejó de ser una afirmación a futuro. Queda vivo lo que esta auditoría señala aparte: A2 (nadie se entera si falla) no lo arregla tener la tarea. Y el refresh de Power BI se movió de las 07:00 a las **08:30** el mismo día: contra la corrida de las 07:30 eso deja **40 min** de margen en un día normal y **20 min** el de la recarga completa. Con la corrida a las 08:00 —que fue el primer arreglo— el margen era de 10 min y no alcanzaba; de ahí el adelanto. Lo que hay que recordar si alguien vuelve a mover cualquiera de las dos horas: el paso 4 tiene las 18 vistas de `pbi_bnpl` en `DROP`+`CREATE`, así que un refresh que caiga dentro de la corrida puede **fallar**, no sólo llegar tarde. Ver el README en *Despliegue a la VM*.

### A4 · `archivos_bnpl` es una dependencia oculta del paso 4
`build_bnpl.py:66-79` crea las 18 vistas con `DROP + CREATE` y **sin try/except por archivo**. Cuatro leen tablas que ningún paso de `main.py` escribe: `sql/pbi/14:30`, `15:14`, `16:20`, `17:15` → `FROM archivos_bnpl.*`. El DDL de ese schema solo se aplica en `carga_archivos_bnpl.py:98`, que es manual, y `14_archivos_bnpl.sql` **no está** en `CAPAS` (build_bnpl.py:30-43). La sección de despliegue (README.md:595-651) nunca menciona correr las cargas manuales antes de la primera corrida; README.md:267-268 incluso dice lo contrario.
Alcance real (corregido): las vistas 01 a 13 sí se crean; se pierden **14, 15, 16, 17 y 20**. No es "no se publica nada", pero es media capa de consumo caída en un primer despliegue.

### A5 · Duplicados sin dedup tumban el REFRESH
`ops/quality_checks.py:46-55` tiene el check `approval_netsuite_id_duplicado` con el detalle *"grid_bnpl debe quedarse con una"*. Pero `sql/07:68-93` define `enrolados`, `preautorizados` y `lineas` como SELECT planos sin `DISTINCT ON`, y entran como LEFT JOIN contra el `UNIQUE INDEX` de :181. Igual `sql/03:13-24` contra el índice de :123-124. La más expuesta es `lineas`, que sale de `credit_limit_history_management` (114,560 filas, tabla de historia).
Hoy no ocurre (`grid_bnpl` 146,613 vs `fintech_customers` 146,614, relación 1:1). El día que ocurra, falla el `CREATE UNIQUE INDEX`, o sea el `REFRESH MATERIALIZED VIEW`, y el paso 4 aborta. El check que lo detectaría corre en el paso 5 — **después** — y es severidad WARN.

### A6 · Casts de texto sin guarda
`sql/07:112-113` (`nullif(address_latitude,'')::double precision`), `:117-120` (`r.birthdate::date`, cuatro veces) y `:122-123` (`r.latitude/r.longitude`). En staging esas columnas son `text` (`sql/01_staging.sql:131-132`, `:152`) y el proyecto **sabe** que traen basura: `sql/02_bnpl_funciones.sql:82-86` explica que `iso_a_mx()` lleva un regex "para devolver NULL en lugar de fallar si el valor no es una fecha (No Information y similares aparecen en estas colecciones)". Esa guarda se aplicó a `createdAt` y `authorizationDate`, no a `birthdate` ni a las coordenadas. `nullif(…,'')` solo cubre cadena vacía, no `'19.43 N'`. Un solo valor basura tumba el `REFRESH` de `grid_bnpl` y con él el paso 4.

### A7 · `--rebuild --solo` borra vistas y no las recrea
Los `.sql` de capa empiezan con `DROP MATERIALIZED VIEW … CASCADE` (`sql/07:16`, `sql/11:14` y `:40`, `sql/03:10`, `sql/04:15`), y `build_bnpl.py:148` es literalmente `if not solo: _construir_vistas_pbi()`. `--rebuild --solo grid_bnpl` tira por CASCADE **7 vistas** de `pbi_bnpl` (verificadas una por una: `02:19`, `06:44`, `08:83` y `:160`, `10:71`, `12:53`, `13:37`, `20:198`) y ninguna se recrea. La documentación (README.md:157-159, sql/pbi/README.md:145-146) solo dice que `--solo` "no reconstruye" las vistas, nunca que **las borra**. El síntoma y el arreglo sí están en sql/pbi/README.md:323; el mecanismo no.

### A8 · Borrar antes de extraer, sin transacción
`etl_mongo_to_postgres.py:416` y `:437` hacen `TRUNCATE`/`DELETE` con `execute_sql` (autocommit) y `extract_aggregate` está hasta la 491. El mismo defecto **ya se corrigió en el otro ETL**: `etl_redshift_to_postgres.py:318-323` — *"DDL, TRUNCATE y carga en una sola transacción: antes el TRUNCATE se confirmaba aparte del append, así que un fallo del COPY dejaba la tabla vacía"* — y en `carga_archivos_bnpl.py:104-114`. El de Mongo, que pasa por el eslabón más frágil (README.md:181-182: "166 s y 356 s en corridas consecutivas"), se quedó sin el arreglo. Se auto-repara en 24 h; el riesgo real es que alguien corra `build_bnpl.py` a mano en ese estado.

### A9 · El paso 3 lee lo que construye el paso 4
`etl_redshift_to_postgres.py:258-264` (`_universo_bnpl`) y `:292-299` (`_sql_cosechas`) leen `bnpl.grouped_orders`, que construye `build_bnpl.py:34` en el paso 4. Corregido respecto de la versión inicial: `_universo_bnpl` hace UNION con `fintech_credit_approval_production`, que el paso 2 ya cargó, así que un cliente aprobado hoy **sí** entra. El rezago de 24 h real es solo el CASE de cohortes de `_sql_cosechas`. Lo que queda intacto: **en una VM limpia el paso 3 revienta** con `relation bnpl.grouped_orders does not exist`, y README.md:595-643 no dice en qué orden sembrar.

### A10 · Las identidades del README no las corre nadie
`ops/quality_checks.py:12-104`: los ocho checks usan `{S} = STAGING_SCHEMA`. **Ninguno toca `bnpl.*` ni `pbi_bnpl.*`.** La consulta de 15 identidades de README.md:377-408 (el delta de −71 de `grid_bnpl`, el ×11 de estacionalidad, los pares que deben ser iguales) es un bloque para copiar y pegar; `main.py:153-156` nunca la ejecuta y `bnpl_ops.data_quality_checks` nunca la registra. El propio README:431 la trata como señal viva ("Si algún día el delta deja de ser 71…") y la deja sin vigilancia. Una corrida que deje `par_snapshot` desfasado de `loss_rates` termina en `ok` y el tablero se refresca con números incoherentes. **El mecanismo ya existe; solo faltan las filas de `CHECKS`.**

### A11 · Las cargas manuales no dejan rastro ni tienen semáforo
`carga_archivos_bnpl.py` y `carga_clientes_concurso.py`: `grep etl_runs` = **0** en ambos. `carga_clientes_concurso.py:119-120` es `TRUNCATE` + `load_dataframe`, destructivo, sobre un Excel de `D:\Shared drives\…\BBDD tablero BNPL LANZAMIENTO.xlsx` cuyo mapeo va **posicional** porque dos columnas solo se distinguen por una mayúscula (:34-38). `.gitignore:16-17` excluye `*.csv` y `*.xlsx`, así que ni el archivo ni una huella quedan.
Y lo decisivo: `grep archivos_bnpl|concurso` sobre `ops/config.py`, `ops/check_freshness.py` y `ops/quality_checks.py` = **cero**. Son los únicos datos del tablero **sin semáforo de frescura ni chequeo de calidad**. PENDIENTES_NEGOCIO.md:866-900 ya probó que dos de los cuatro archivos están 7 y 8 meses viejos. README.md:294-296 admite la limitación solo para `carga_archivos_bnpl.py`.

### A12 · Un solo ambiente, y una colección `-dev` en producción
`build_bnpl.py:75-76` hace `DROP VIEW … CASCADE; CREATE VIEW` sobre las 18 consultas, y `:146-149` lo ejecuta "al final y siempre" en cada corrida, contra la misma base que lee el modelo (`localhost:9553/rabbit-bi-local`). No hay base de pruebas: los cuatro alias de README.md:475-482 apuntan a la misma instancia.
Aparte: `ops/config.py:75-77` y `etl_mongo_to_postgres.py:261-262` extraen la colección **`propaga-transaction-dev`** → `mongo_bnpl.propaga_transaction`, la tabla más cara del staging (119.3 s). El sufijo `-dev` aparece en `plan_implementacion.md:183` y `:528` sin que nadie toque la pregunta. **No se puede resolver desde el repo: hay que preguntarle a ingeniería si esa es la colección productiva de Propaga.**

### A13 · Sin respaldo del Postgres local
`grep pg_dump|pg_restore|basebackup|backup|respaldo` sobre `.py`, `.sql`, `.bat` y `.md`: **cero scripts**. Los 18 `.tmdl` apuntan a `PostgreSQL.Database("localhost:9553","rabbit-bi-local")`. Reconstruir implica túnel SSM, recarga completa del staging (20-40 min), 1,294,006 filas desde Redshift y toda la capa de negocio, con `migrar_a_vm.py` ya deprecado. Es un data mart derivado, así que el riesgo es **RTO, no RPO** — pero ese RTO lo agrava T1, porque las consultas para rehacerlo no están commiteadas.
*Pendiente de verificar contra la VM:* si hay snapshot de EBS (el Task Scheduler muestra "Amazon Ec2 Launch") o respaldo del servicio `postgresql-x64-17`.

### A14 · El paso 3 nunca corrió completo
En la última corrida, el paso 3 va de las 13:07:38 a las 13:09:06 (88 s) con exactamente **tres** conexiones a Redshift. Faltan las tres nuevas (`ventas_cliente` 1.29M filas / 78.6 s, `cosechas_agg`, `estacionalidad_mes`), que hoy sí están en `etl_redshift_to_postgres.py:342-345` (mtime del archivo posterior a esa corrida). Esto **ya está documentado con más precisión que el hallazgo** en README.md:108-111 y :330. Lo único no escrito es que el encabezado de README:161 rotula el desglose como "corrida del 2026-08-13" cuando tres renglones se midieron aparte.

---

## 3. Cifras equivocadas o ambiguas en pantalla

| # | Hallazgo | Sev | Doc |
|---|---|---|---|
| B1 | `grid_bnpl` arranca de `fintech_customers`: el aprobado sin ficha **no existe** en la tabla ancla | Alto | Parcial (mal descrito) |
| B2 | `deployedCapital` / `everActivated` son sumas repetidas del panel: ~9.3× lo colocado | Alto | Parcial |
| B3 | Roll rates cuenta como castigado lo que la columna PAR llama `Paid` | Alto | No |
| B4 | El universo de "maduros" está anclado a `TODAY()-115`, constante sin dueño | Alto | No |
| B5 | `bnplMinimumTenure` sin guardia de blanco: el embudo arranca en ~146K en vez de ~9K | Alto | No |
| B6 | "Propaga Net Income Estimation": un P&L con 4 constantes inventadas dentro del visual | Alto | No |
| B7 | Funnel: las dos gráficas de enrolamiento perdieron su relación con el calendario | Alto | No |
| B8 | Roll rates dejaron de responder a los slicers del grid, y la portada lo canoniza | Alto | Parcial |
| B9 | `locPenetration` divide entre el límite **por pedido** | Medio | No |
| B10 | La tendencia de los NO enrolados arranca de un punto que mezcla los dos grupos | Medio | No |
| B11 | El slicer de Survival Matrix esconde 7 cohortes (2025-06 a 2025-12) | Medio | No |
| B12 | "Ever Activated Customers" perdió la jerarquía de fecha y la etiqueta sigue diciendo "Año" | Medio | No |
| B13 | Cuatro tablas del Funnel con el mismo título y dos universos distintos | Medio | No |
| B14 | PAR 60 y PAR 90: los títulos solo se distinguen por un `+` y la serie se llama igual | Medio | Parcial |
| B15 | `loanDisbursementIndex` tiene tres definiciones (1/2/3/4+ en DAX, 1/2/3+ en SQL, rank crudo) | Medio | Parcial |
| B16 | Huecos del SCD de ruta: órdenes sin ruta que **no** quedan marcadas como inferidas | Medio | No |
| B17 | El grano de `grouped_orders` está declarado de tres formas distintas | Medio | Parcial |
| B18 | `concurso_base` **no** lee `bnpl_clientes_concurso`, contra lo que dicen los dos README | Medio | Parcial |
| B19 | `03_bnpl_par` y `04_months_closes` divergen en dos tipos y la cabecera jura que no | Bajo | No |
| B20 | `revenueShare`: una cuarta definición del revenue de Rabbit, latente | Bajo | No |
| B21 | La medida `valor` de Audiencias mapea los índices corridos y funciona por accidente | Bajo | No |

### B1 · El aprobado sin ficha de cliente desaparece de la tabla ancla
`sql/07:168` es `FROM mongo_bnpl.fintech_customers_production c`, con todo el crédito en LEFT JOIN (:170-178) y `WHERE c."netsuiteId" IS NOT NULL` (:179). **Sin fila en `fintech_customers` no hay fila en `grid_bnpl`.** README.md:571-572 dice "no tienen `shopName` ni teléfono" y `ops/quality_checks.py:61` dice "`grid_bnpl` queda sin `shopName`": las dos describen **columnas** faltantes, no **filas** faltantes. En ningún documento se dice que el cliente desaparece.
No es solo el apagón del 22-jul: es estructural. `pbi_bnpl.grid_bnpl` es el lado "uno" de cinco relaciones; las órdenes de ese cliente sí viven en `bnpl_par`, `loss_rates` y `months_closes` (salen de `credit_order_production`, independiente) y caen al miembro en blanco: desaparecen de cualquier visual segmentado por ruta, oficina o cohorte. *Pendiente contra la base:* el volumen, que es justo lo que mide el check `aprobados_sin_customer` y nadie ha reportado.

### B2 · `deployedCapital` no es capital
`sql/05:69` cruza cada orden contra **cada corte posterior a su vencimiento** y `:50` conserva `l.total_amount` en todas las copias. `sql/06:22` hace `sum(original_amount) AS deployed_capital` y `:19` `count(DISTINCT netsuite_id) AS ever_activated`. El factor: 1,061,120 filas de `bnpl_par` contra 92,009 órdenes de `loss_rates` = **11.5 cortes por orden**. Las medidas suman a través de ese eje (`vintage_analysis.tmdl:4` y `:9`).
Cada punto de la gráfica (cohorte × mes de maduración) está bien. Cualquier **total o agregado** suma la misma orden hasta 11 veces en numerador y denominador con pesos distintos. PENDIENTES_NEGOCIO.md:626 toma los $1,760,170,361 como "capital desplegado" legítimo cuando :299 dice que lo financiado real es $188,694,899 → **9.3×**. El 6.02% que §16.5 propone llevar a comité como "la tasa PAR30 oficial" es un cociente de dos sumas infladas.

### B3 · Un pedido pagado con 100 días de atraso sale en DQ 90+ *y* en Paid
`sql/04:120-125`: un pedido pagado **conserva** sus días de atraso (`paid_date - expected_payment_date`). `sql/04:192-196`: `par = 'Paid'` en cuanto `paid_date` no es nulo. Del otro lado, `bnpl_loss_rates.tmdl:432-529` (stage2..stage7) miran **solo** `daysPastDue`, nunca `paidDate`. Resultado: con dpd=100 los siete stages salen sin un solo "Paid", el pedido cae en el numerador de castigo (`with_lead.tmdl:21`, `:49`) y a la vez `paidAmount` lo suma y `lossAmount` lo excluye. Dos tarjetas de la misma página dan lecturas contradictorias del mismo pedido.
Corrige además a PENDIENTES_NEGOCIO.md:763, que dice que el denominador son "los pedidos que aún no vencen (`stage = Ongoing`)": `stage='Ongoing'` es `stage1`, o sea **todo lo entregado hace más de 115 días** — justo el capital maduro que §13b.3 pide como denominador. La palabra "Ongoing" significa cosas opuestas en las dos tablas del modelo. *Pendiente contra la base:* `select count(*), sum(total_amount) from bnpl.loss_rates where paid_date is not null and days_past_due >= 90`.

### B4 · `TODAY()-115` y `>4 meses`: dos constantes sin dueño
Las siete columnas `stage1..stage7` (`bnpl_loss_rates.tmdl:427,436,453,470,487,504,521`) arrancan con `IF(deliveryAt <= TODAY() - 115, …)`. `grep 115` sobre `sql/` = **cero**; sobre README, PENDIENTES, sql/pbi/README y PASOS_M = **cero**. La única definición de plazo del proyecto es `sql/02:13-14`, `dias_credito() = 15`; 15 + 90 = 105, sobran 10 días que nadie puede justificar. Igual `grid_bnpl.tmdl:124`, `>4 meses`, otro corte de madurez sin explicación y distinto del anterior. El universo no queda congelado con la corrida y **no es reproducible contra `bnpl.loss_rates`**, que no tiene ese concepto.

### B5 · El embudo de "≥4 meses" incluye a los ~137 mil que nunca se enrolaron
`grid_bnpl.tmdl:124`: `IF(DATEDIFF([bnplEnrolledAt], TODAY(), MONTH) > 4, 1, 0)`, **sin guardia de blanco**. `sql/pbi/06_grid_bnpl.sql:3` declara el grano: "cliente (146,613 filas — TODOS los clientes, no solo los enrolados)", y `:83` mapea `bnpl_enrolled_at::date`, así que el NULL viaja al modelo como blanco. En DAX un blanco se coacciona a 1899-12-30 → `DATEDIFF` ≈ 1,500 meses → la bandera queda en 1. Los dos visuales filtrados (`7d5e7258b21f913fd163` y `3f57b402a0115b201aa2`, ambos con `In {1L}`) dirían "For customers who have at least 4 months of tenure" arrancando en ~146,542 en vez de ~9,283. Es **idéntico en `pbi/`**, o sea que si eso es lo publicado, la cifra mala ya está a la vista.
*Pendiente de verificar en Desktop:* tarjeta con `SUM(grid_bnpl[bnplMinimumTenure])` → ¿146K o 9K?

### B6 · Un P&L completo armado con constantes dentro del visual
`pages/2f83323bac49134fe42d/visuals/0022e35f90d69de5ed50/visual.json` (Vintage Analysis, **visible**), 11 `NativeVisualCalculation` — DAX escrito en el visual, no en el modelo: `Interest Rate`=0.04 (:79), `Proportion of Default Interest`=.4 (:102), `VAT Rate`=.16 (:138), `Rabbit Fee`=.142 (:162), y de ahí `Gross Income`, `VAT`, `Rabbit Revenue Share`, `Net Income`, `Profit & Loss` y `P&L Running Sum`. El mismo bloque se repite en el lineChart `f4fa8eab332531023583` (misma página) y en `4626e50a605a1215e871` (ROI, oculta). `grep` de "Gross Income", "Net Income", "Profit & Loss" y del 40% en los cuatro documentos: **cero**.

Tres problemas encimados:
1. El **4%** y el **40%** no existen en el pipeline ni en la documentación. Ojo con cómo se plantea: PENDIENTES:64-65 y :151 hablan de `commission = totalAmount × 0.04` (la columna `bnpl.comision_sobre_monto`, `sql/09:47-49`), y el visual aplica 0.04 sobre `[Paid Amount]`, otra base. La columna SQL sigue sin alimentar nada; lo engañoso es la premisa de §16.2 ("no alimenta ningún reporte") cuando hay una tasa de 4% pintada en pantalla.
2. `[Gross]−[Gross]×0.16` no es lo mismo que `[Gross]/1.16`. Nadie puede decir cuál se quería porque el visual no declara si `Gross Income` trae IVA.
3. La columna se titula `Amount in DQ 15 +` pero es `lossAmount`, que por el typo de `bnpl_loss_rates.tmdl:633` (`"60-89"` sin prefijo DQ) excluye DQ 60-89 ($308,974): el `Profit & Loss` resta menos mora de la que hay.

### B7 · Funnel: relación perdida en la migración
`pbi/…/relationships.tmdl:31-33` tiene `grid_bnpl.bnplEnrolledAt -> enrollment_dates.Date`. En `pbi_new` **no existe**: `enrollment_dates` solo aparece contra un LocalDateTable (línea 8) y contra `dynamic_enrollment_dates` (230-231). Queda como isla. Las dos gráficas afectadas — "Clientes Enrolados Vs Clientes Activados" (`5507f6d55f9cc3ab1075`) y "Línea de Crédito Enrolada Vs Línea de Crédito Activada" (`07b82a305c395408c175`) — usan eje X `dynamic_enrollment_dates[visual_date]` con Y sobre `grid_bnpl`. **No dan error: pintan el total repetido en cada período.** Mecanismo: `variation Variación` sobre `bnplEnrolledAt` existe **solo en `pbi_new`** (`grid_bnpl.tmdl:429`) — la jerarquía automática se comió la relación manual al re-apuntar el origen. "Funnel" tiene 0 apariciones en toda la documentación.

### B8 · Roll rates dejaron de filtrarse por el grid, y la portada lo canoniza
`pbi/…/relationships.tmdl:169-171` tiene `bnpl_loss_rates_with_lead.netsuiteId -> grid_bnpl.netsuiteId`. En `pbi_new` no existe. Los 6 visuales que la consumen están en Salud del Portafolio (los 4 pivotes "Roll rates between Delinquency Buckets" y 2 multiRowCard), y en la misma página hay slicers sobre `grid_bnpl` de oficina, `inferredGender`, `customerAgeRangeAtEligibility` y `enrollment_cohort`. En `pbi/` sí se filtraban; en `pbi_new` ya no.
Peor: **la portada nueva lo describe como característica del modelo** (`00portada0bnpl0lectu/visuals/p0trampas00000000003`: "Alcanzan las gráficas de mora, pero no las de cosechas, audiencias ni roll rates, que no tienen relación con el grid"). A partir de ahora nadie lo va a cuestionar.
Mismo mecanismo detrás de §13b.4: todas las relaciones `netsuiteId` de `pbi_new` son `AutoDetected_*` (375-391), o sea que Power BI las reinventó; `months_closes -> grid_bnpl` quedó `isActive: false` (385-387) cuando en `pbi/` estaba activa — y eso son los $3.88M que PENDIENTES:770-789 explica como "cómo quedó la cadena de relaciones", sin decir que es un **cambio**. **Cinco relaciones cambiaron en la migración (3 perdidas, 1 nueva, 1 desactivada) y no hay ningún documento que las liste.**

### B9 · `locPenetration`
`bnpl_grouped_orders.tmdl:8`: `sum(orderGrossSales)/SUM(creditLimit)` sobre una tabla cuyo grano es "cliente × sales order × order_id × status × canal" (99,019 filas). `creditLimit` es el límite **vigente al momento de esa orden** (`sql/03:33-35`, tomado de `payment_report_production`) — no es un atributo repetido del cliente, dígase bien o negocio lo desarma en dos minutos. Aun así, el denominador suma la misma línea tantas veces como pedidos haya: un cliente con $10,000 y 5 pedidos de $2,000 aparece con 20% cuando usó el 100%. Se usa en el eje secundario de "Volumen de Venta" del **Resumen Ejecutivo**. `ayuda_tablero/conocimiento.py:194` la define como "venta sobre línea autorizada", justo la lectura a nivel cliente que la fórmula no entrega.

### B10 · Tendencia de no enrolados con origen contaminado
`bnpl_cosechas_agg.tmdl`: en `tendenciaEnroladosDropProyectada` el Y0 (:251) y el Yref (:261) filtran ambos `flg_cte_bnpl = "Y"`. En `tendenciaNoEnroladosDropProyectada` el Yref (:331) filtra `= "N"` pero el **Y0 (:321) no filtra nada**. Como el `ALLSELECTED` barre el filtro del visual, ese origen promedia los dos grupos. Las dos rectas se dibujan juntas en `b063e42593e592cc0a31` ("Comparativo del Drop Size…", página visible), que es exactamente la página que existe para argumentar cuánto más compra un cliente por tener BNPL.

### B11 · Slicer que esconde 7 cohortes
`pages/d43c45235570af5f6675/visuals/6cc439884a884b8c5208`: slicer "Cosecha Enrolamiento", modo `Basic`, con la selección persistida como lista literal `In` (no invertida) de 20 valores: 2024-06…2025-05 y 2026-01…2026-08. **Faltan 2025-06 a 2025-12** — las cohortes más maduras después del arranque. Survival Matrix es visible y el slicer filtra sus 35 visuales; se ve con casillas marcadas, no vacío.
Nota: en `pbi/` el mismo slicer trae 13 valores y tampoco son contiguos (le falta 2024-10). **La selección parcial no la introdujo la migración: ya venía viciada.** Es estado de UI, se corrige con un clic.

### B12 · "Ever Activated Customers"
En `pbi/` el Category son dos `HierarchyLevel` (Año y Mes) sobre `grid_bnpl[bnplActivatedAt]`. En `pbi_new` es un `Column` plano, conservando `"nativeQueryRef": "bnplActivatedAt Año"`. Pasa de 3 barras a cientos de puntos, con la leyenda diciendo "Año". El modelo sí conserva la `variation` (`grid_bnpl.tmdl:460`), así que se arregla sin tocar el modelo.

### B13 · Cuatro tablas del Funnel, un solo título
En `pages/f384ed5188290d63776a`, apiladas y **todas visibles al mismo tiempo** (y=1117, 1518, 1923, 2051, sin traslape, ninguna `isHidden`):

| Visual | Título | Subtítulo | Agregación | Filtro |
|---|---|---|---|---|
| f92593db85fb5f1534ce | Funnel Distribution per Number Of Orders | **ninguno** | Sum | ninguno |
| 0b018a1b4ac75783e506 | *mismo* | Percentage of the enrolled customers | Avg | ninguno |
| 7d5e7258b21f913fd163 | *mismo* | For customers who have at least 4 months of tenure. | Sum | `bnplMinimumTenure = 1` |
| 3f57b402a0115b201aa2 | … (Percentage) | *mismo* | Avg | `bnplMinimumTenure = 1` |

Tres con el mismo título, dos universos distintos, y la primera **sin subtítulo** no tiene forma de distinguirse. Además los alias de la segunda están corruptos: `Promedio de 51`, `Promedio de 151`, `Promedio de 201` para las columnas 5, 15 y 20. Es el mismo riesgo que PENDIENTES:593-620 documenta para el PAR de Vintage; el Funnel no aparece en ningún `.md`.

### B14 · PAR 60 y PAR 90
Cuatro gráficas en Vintage Analysis: `18f1d6ff…` "PAR 60+ Rate" (`par60RateAmount`, sobre capital) contra `5a0d2145…` "PAR 60 Rate" (`par60RateCustomers`, sobre clientes), y el par equivalente de PAR 90. **Las dos de cada par nombran la serie igual** (`nativeQueryRef: "PAR 60+ Rate"` en ambas), así que ni el eje ni el tooltip las distinguen. En descargo: cada una **sí trae subtítulo** que las desambigua ("…Over Cumulative Deployed & Matured Capital" vs "…Over Ever Activated Customers"), el mismo mecanismo que §12 ya describe para PAR 30. Lo que vale del hallazgo es que la recomendación 1 de §12 (PENDIENTES:630-632) cubre **dos de seis** gráficas.
Corrección de paso a PENDIENTES:611-612: las dos líneas de referencia no se llaman ambas "BEP"; la de la derecha se llama **"Healthy Value"** (`e9aa4c10e1eb56d608b4:193`).

### B15 · `loanDisbursementIndex`, tres definiciones
`bnpl_loss_rates.tmdl:535-541`: `SWITCH(TRUE(), rank <= 3, FORMAT(rank,"0"), rank >= 4, "4+")` — con el comentario huérfano del corte anterior: `-- Devolver "3+" como texto`. Contra `sql/pbi/08:104-106` (y `12:42`, `13:61`, `14`, `15`), que binan `1/2/'3+'` como `loanDisbursementIndexRange`; y contra `sql/pbi/08:103`, donde `loanDisbursementIndex` es el rank crudo, un entero. **El slicer visible de Salud del Portafolio (`c96f0d4d9688626702d3`) usa la versión DAX.** Quien filtre "3" ahí ve solo el tercer pedido; quien lea "3+" en el modelo de riesgo ve del tercero en adelante. Y el mismo identificador significa rango en una tabla y entero en otra.

### B16 · Huecos del SCD de ruta
`etl_redshift_to_postgres.py:66` filtra con `and ruta is not null`, así que un cliente sin ruta unas semanas parte su historia en dos tramos. `sql/11:60-61` solo extiende el **primer** tramo hacia atrás y el **último** hacia adelante: los huecos intermedios no se cierran. `sql/03:119-121` une con `BETWEEN valido_desde AND valido_hasta` y `:112` calcula `ruta_inferida = (created_at::date < r.vigencia_real_desde)`, que con `r` en NULL da **NULL, no TRUE**. Esas órdenes llegan con ruta/supervisor/oficina en NULL y `ruta_inferida` en NULL; `sql/pbi/20:153-156` las convierte en "SIN RUTA" y `:64` hace `coalesce(bool_or(ruta_inferida), false)` → **aparecen como dato firme sin ruta, no como inferido**. La mora y la colocación de esas órdenes no se atribuyen a nadie.
Matiz que acota el volumen: el agrupamiento de `etl_redshift:68-96` es por `(netsuite_id, ruta, tramo)`, así que un hueco solo parte la historia si la ruta **cambió** a los lados. Con 13,893 tramos para ~10,700 clientes con crédito, el volumen esperado es chico. *Pendiente contra la base:* `count(*) from bnpl.grouped_orders where ruta is null and ruta_inferida is null`.

### B17 · Grano de `grouped_orders`
`sql/03:1` dice "1 fila por (cliente, sales order)" y README.md:493 dice "cliente + sales order". El índice único real es de **cinco** columnas (`sql/03:123-124`, coherente con el `GROUP BY 1,2,3,4,5` de :56). El grano correcto **sí está escrito** — `sql/pbi/01:4` y sobre todo `sql/pbi/20:44-46` ("un order_id por SKU, y una fila más por cada cambio de status. Sin este colapso, cualquier conteo de órdenes o suma de monto sale inflado"). Es **contradicción entre archivos**, no ausencia. El riesgo latente: `sql/04:199` declara `UNIQUE (netsuite_id, sales_order_id)` sobre `grouped_orders` filtrado a COMPLETED; hoy funciona por el dato, y el día que un sales order tenga dos `order_id` en COMPLETED revienta el REFRESH de `loss_rates` y con él `par_snapshot`, vintage y `revenue_comision`.

### B18 · `concurso_base` no lee la tabla del concurso
`sql/pbi/20_concurso_base.sql:2` declara "Fuente: `bnpl.grouped_orders` + `dim_ruta_actual` + `grid_bnpl`" y en las 200 líneas **`clientes_concurso` no aparece ni una vez** (`grep` sobre todo `sql/`). Contra eso: `sql/pbi/README.md:54` dice "`bnpl.bnpl_clientes_concurso` + grouped_orders" y README.md:63 dice de la tabla "(tabla física, la lee la vista 20)". No hay `18_*.sql` (el directorio salta de 17 a 20) ni paso M para ella. Los 51,294 clientes del universo del concurso **no llegan al tablero por ningún camino**, y sin ellos no hay denominador para "clientes colocados sobre universo objetivo".
Se salva `sql/13:14`: "netsuite_id va DOS veces a propósito, **igual que** en `sql/pbi/20`" es comparación de patrón, y `:17` aclara que es "para relacionar en Power BI contra `netsuiteIdNum` de `concurso_base`". Ese archivo está bien escrito; son **dos** frases equivocadas, no tres.

### B19 · `bnpl_par` vs `months_closes`
`sql/pbi/04:5-8` dice: "son la misma tabla con otra ropa. Diferencias, **todas cosméticas**" y lista tres. Hay dos más y no lo son: `totalAmountDefault` sale `double` en `03:39` y **`::bigint`** en `04:57` (redondea centavos); `paymentDate` sale `timestamp` en `03:41` y **`::text`** en `04:59`. Las dos tablas cuelgan del mismo modelo con relaciones propias. `sql/pbi/README.md:294-308`, la tabla de referencia de tipos, no cubre ninguna de las dos.

### B20 · `revenueShare`
`bnpl_loss_rates.tmdl:365-367`: `interests * .142`, sobre la columna `interests` que `sql/04:157-162` ya devuelve **con** la exención del primer pedido (cero para 9,031 órdenes) y **sin** la condición "solo si se cobró" que sí tienen `rabbit_revenue` (`sql/04:189-191`) y `rabbit_revenue_sin_iva` (`sql/09:44-46`). Es una cuarta base, distinta de las tres de PENDIENTES:57-65. Hoy **ningún visual la usa** (grep = 0). Es una columna sumable, con nombre plausible, colgando de la tabla más usada.

### B21 · La medida `valor` de Audiencias
`'Medidas Audiencia'.tmdl:43-44` define órdenes **0** (Clientes) y **1** (Gross Sales). `bnpl_audiencia_agg.tmdl:4-12` hace `SWITCH(med, 1, SUM([Gross Sales]), 2, SUM([Clientes]), SUM([Clientes]))`: la rama 2 es código muerto y Clientes acierta **solo porque cae en el default**. Es la misma clase de bug que PENDIENTES:127-145 documenta para `dynamicTotalRevenue`. El día que se agregue una tercera medida, esa devolverá Clientes en silencio. Además la medida no tiene `formatString` (:15) y los dos visuales de la página Audiencias (`b83e4baf…` "Activos" y `85b6027d…` "Inactivos") pintan millones de pesos como número pelón.

---

## 4. Existe en el código y no está en ningún README

| # | Hallazgo | Sev |
|---|---|---|
| C1 | No hay dueño de datos, contacto de escalamiento ni SLA escrito | Alto |
| C2 | No hay runbook de falla del pipeline; 6 de 8 chequeos sin documentar | Alto |
| C3 | Datos personales de tenderos llegan al modelo sin clasificación ni RLS | Alto |
| C4 | 9 visuales del tablero son scripts de Python con `seaborn`; uno en la página de entrada | Medio |
| C5 | La fecha automática está encendida: 61 tablas ocultas, 61 de 81 relaciones, 19 visuales atados | Medio |
| C6 | Cinco tablas calculadas vivas sin que nada las use, una recalcula un panel cliente × mes | Medio |
| C7 | `revisar_referencias.py` no revisa filtros ni `objects`, y ahí hay una referencia rota real | Medio |
| C8 | No hay diccionario de datos; el catálogo real vive en un script de tooltips sin commitear | Medio |
| C9 | Consolidación `pbi/` vs `pbi_new/`: mismo `reportId` y `datasetId`, y `.pbix` rezagados | Medio |
| C10 | `expressions.tmdl` sigue apuntando a un OneDrive personal, y el chequeo del README es ciego | Medio |
| C11 | `.env` huérfano en la raíz con tres cadenas de conexión, que el README niega | Medio |
| C12 | Bus factor de uno: no hay inventario de accesos | Medio |
| C13 | La sección "Estructura" del README no corresponde al árbol | Medio |
| C14 | Sesiones SSM que quedan `Active` en cada corrida, sin documentar | Bajo |
| C15 | No hay `requirements.txt` ni lock; tres librerías críticas viven fuera del repo | Bajo |
| C16 | Los ETL imprimen con `print()`: el log del pipeline no trae detalle por tabla | Bajo |
| C17 | No queda registro de qué versión del código produjo los datos | Bajo |

### C1 · Sin dueño, sin escalamiento, sin SLA
`grep dueño|responsable|contacto|SLA|owner|steward` sobre los 9 `.md` del repo: **no aparece un solo nombre de persona ni correo**. Los aciertos son preguntas (PENDIENTES:285, :418, :635, :1036) o áreas sin persona ("a Finanzas", "a Riesgo", "a Ingeniería de Datos"). README.md:358 dice que un CRIT de fuente "es de ingeniería, no del pipeline" sin decir a quién; README.md:571 dice "está reportado a ingeniería" sin ticket, persona ni fecha. El único SLA que existe son dos constantes en código: `ops/config.py:22-23`, `LAG_WARN_HORAS = 24` / `LAG_CRIT_HORAS = 48`. Mientras tanto `fintech-customers-production` lleva **513 h** caída (log:469) y no hay forma de saber si alguien le da seguimiento. El compromiso de la hora del refresh (07:00 cuando se escribió esto, 08:30 desde el 2026-08-14) no está escrito como SLA.

### C2 · Sin runbook de falla
Para `modo = 'error'` el README.md:328 dice únicamente: "reventó a media corrida. El traceback está en `logs/pipeline_YYYY-MM.log`". No dice si el staging quedó a medias, si es seguro re-correr, ni si basta `--solo`. Atenuante real: README.md:140-159 sí da la mecánica de `--solo` y `--rebuild`; falta decir si es seguro usarla tras un `error` y si cada paso es idempotente.
Del lado de calidad: `ops/quality_checks.py` define **8** chequeos (:16, 25, 34, 46, 57, 69, 81, 93), **dos** con severidad CRIT (:19 y :28). README.md:366-371 documenta solo los 2 que hoy están en alerta y los encabeza con "no las persigas". `main.py:153-156` los registra todos como `log.warning` sin leer `severidad`, así que un CRIT nuevo (p.ej. `credit_order_delivery_at_nulo`) produce una línea de log idéntica al ruido de siempre — en un README que ya enseñó a ignorar las alertas de calidad. El único runbook que existe (`sql/pbi/README.md:220-327`) es del lado de Power BI.

### C3 · PII sin clasificar
`sql/pbi/06_grid_bnpl.sql` expone `shopName` (:56), `customerName` (:68), `customerLastNames` (:69), `customerPhoneNumber` (:75). `sql/pbi/08_loans_matured_default_profile.sql:116-129` agrega `shopZipCode`, `shopLatitude/Longitude`, `customerBirthdate`, `inferredGender` y `customerLatitude/Longitude` — el comentario de :130 dice explícitamente "el domicilio del onboarding". El modelo lo importa completo (`grid_bnpl.tmdl:674` `mode: import`, `:680` `select * from pbi_bnpl.grid_bnpl`). **Cuatro visuales lo pintan** (`pages/2610102b…/visuals/{868471…, df054c…}` y `pages/e7cfbf6b…/visuals/{01c431…, df64ac…}`), los cuatro con `customerPhoneNumber`. Y `Top100InactiveCustomers.tmdl` arrastra nombre (:488), apellidos (:496), fecha de nacimiento (:512), teléfono (:553) y coordenadas (:561, :571): **una lista nominal de 100 tenderos con teléfono y domicilio dentro del modelo.** El `.pbix` pesa 144,586,465 bytes con todo eso embebido — un archivo que se manda por correo sin pensarlo.
`grep 'dato personal|PII|privacidad|enmascar|anonimiz|RLS|confidencial'` sobre README, PENDIENTES y sql/pbi/README: **un solo hit**, README.md:572, y es sobre un hueco de datos, no sobre privacidad. Es exposición por omisión, no por decisión. (Defendible subirlo a crítico por LFPDPPP; se deja en alto porque desde el repo no se puede verificar quién tiene hoy el `.pbix`.)

### C4 · Visuales de Python con `seaborn`
9 de los 196 visuales de `pbi_new` son `pythonVisual`: 4 en Return On Investment (oculta), 4 en Cambio en Comportamiento de Compra (visible) y **1 en Resumen Ejecutivo**, que además es el `activePageName` de `pages.json` — la primera página que carga el tablero. El script de `a4eca…/visuals/f9c2e0e39c8a6d2e5603` arranca con `import seaborn as sns / matplotlib / numpy / matplotlib.ticker` y usa `sns.histplot`. README.md:602-606 instala `pandas python-dotenv openpyxl matplotlib` y aclara que son "para los scripts de análisis"; **`seaborn` no aparece en ningún lado del repo ni de la documentación**. Sin un intérprete registrado en Opciones → Scripting de Python con esos paquetes, se ven 9 recuadros de error — falla el render, no el refresh, así que no sale en ningún log. Además condiciona la Fase 7: los visuales de Python en el Service corren sobre la lista fija de paquetes de Microsoft, con tope de 150k filas y sin "Publicar en la web".

### C5 · Fecha automática encendida
`model.tmdl:63`: `annotation __PBI_TimeIntelligenceEnabled = 1`. Hay **61 `LocalDateTable_*.tmdl`** en `pbi_new` (64 en `pbi/`) y 61 declaraciones `variation` que cuadran una a una. De las **81** relaciones, **61 apuntan a un LocalDateTable**: solo 20 son de negocio. Y 19 visuales enlazan la Jerarquía de fechas, repartidos en Salud del Portafolio (4), KPI's Tracking (6), Cambio en Comportamiento de Compra (5), Default Customer Profile (2) y Resumen Ejecutivo (2). `grep LocalDateTable|TimeIntelligence|"fecha automática"` en README, PENDIENTES, sql/pbi/README y PASOS_M: **cero**.
Lo que vale no es el peso (atribuirle los 144 MB es especulación: `bnpl_par` y `months_closes` traen 1,061,120 filas cada una y `overall_prev_post` 1,293,358), sino **la trampa**: apagarla de golpe deja 19 visuales sin campo, en 5 páginas.

### C6 · Cinco tablas calculadas muertas
Cruzando los 196 `visual.json` contra los `.tmdl`, no aparecen en ningún visual ni en el DAX de ninguna otra tabla: `Clientes_Mensual` (:44), `TablaParaGrafica` (:47), `Top100InactiveCustomers` (:693), `cohort_type` (:30) y `x_axis_type` (:30). `Clientes_Mensual` hace `GENERATE(VALUES(bnpl_grouped_orders[netsuiteId]), CALENDAR(…, EOMONTH(TODAY(),0)))` con un `CALCULATE(SUM(...), FILTER(...))` encima: **clientes × meses × barrido de 99,019 filas, en cada refresh, para datos que nadie ve.**
`cohort_type` / `x_axis_type` son copias minúsculas de `Cohort Type` / `X Axis Type`, que sí se usan (13 y 37 referencias contra 0 y 0): quien vaya a cambiar el orden de un slicer tiene 50% de probabilidad de editar la muerta. `sql/pbi/README.md:340-342` lista 6 tablas calculadas cuando en `pbi_new` hay **24** particiones `= calculated` sin contar LocalDateTable; PENDIENTES:908 titula "Muerta (1)" y solo declara `Consulta1`.
`Top100InactiveCustomers` además perdió su relación con `grid_bnpl` en la migración (`pbi/…:333-337`) y conserva 7 relaciones contra LocalDateTables. Ya estaba sin consumir antes de migrar.

### C7 · El chequeo de referencias tiene un punto ciego
`ayuda_tablero/revisar_referencias.py:21-22` itera solo `v["fields"]`, que `inventario.py:217` llena únicamente con el `queryState`. `inventario.py:249-251` sí recolecta un `filters` aparte — que el revisor **nunca mira** —, y nadie recorre `visual.objects` ni el `filterConfig` de `page.json`. Además `:29` descarta como "alias" toda entidad de ≤3 caracteres en vez de resolver el bloque `From`.
Hay una referencia rota real que el script no reporta: **`TARGET.Area`** en `pages/49e8cfe327f3ff31d85e/visuals/32f24f3b89c6ffcf18f5` (textbox "Audiencias BNPL", `objects.values[0].properties.expr`, `Subquery` con `From: [{"Entity":"TARGET"}]`). No existe ninguna tabla `TARGET` en el modelo. El script es la red de seguridad declarada en `ayuda_tablero/README.md:121, 148-156` y hoy da luz verde con una referencia muerta dentro. La clase que no revisa — filtros de visual y de página — es justo la que rompe en silencio: un filtro sobre una columna inexistente no vacía el visual, lo deja **sin filtrar**.

### C8 · No hay diccionario de datos
Lo que hay: README.md:487-501 (11 vistas con grano, sin columnas) y sql/pbi/README.md:35-54 (18 vistas con filas y número de columnas, sin significado). El único catálogo a nivel columna y medida es **`ayuda_tablero/conocimiento.py`**: `T` (:26, 21 tablas con grano, fuente y advertencias), `C` (:115, 59 campos) y `M` (:178, **66 medidas DAX**). Ese archivo está sin commitear y ningún README lo presenta como diccionario — README.md:20-21 solo lo menciona como generador de tooltips. Existe además un catálogo obsoleto en `design.md:478-488` (sigue diciendo "Falta `enrollmentChannel`", nombra un schema `bnpl_analytics` y módulos `transform_*.py` que nunca se construyeron). El activo de gobierno más valioso del proyecto está escondido en un script de tooltips, sin respaldo.

### C9 · Consolidar `pbi/` y `pbi_new/`
Los dos `Report/.pbi/localSettings.json` traen el **mismo** `"reportId": "d36d2832-baa9-4d61-a031-b303715a6480"` y los dos `SemanticModel/.pbi/localSettings.json` el **mismo** `"datasetId": "a9b8b79d-6049-4e42-b331-ec69ac184a40"`. Abrir el `.pbix` equivocado y darle Publicar sobrescribe el artefacto productivo con el modelo viejo de orígenes CSV — y `pbi/` tiene **18 orígenes de archivo** (15 `.tmdl` con `Csv.Document(File.Contents("C:\Users\RodolfoGonzalezOrta\…"))`, p.ej. `grid_bnpl.tmdl:688` y `bnpl_grouped_orders.tmdl:709`, más 3 contra SharePoint). Con refresh "correcto" y datos congelados: el modo de falla más difícil de detectar.
Además, **dentro de cada carpeta el `.pbix` está rezagado respecto de su TMDL**: `pbi_new/…pbix` es de las 01:49 y su `model.tmdl` de las 06:17 (4h28m). Eso no lo menciona ninguna doc y git lo ignora.
Consolidar está verificado como seguro: el único DAX que existe en `pbi/` y no en `pbi_new/` es la medida `bnpl_cosechas_agg[bnplGrossReal]` (`:446`), que **ningún visual usa**; `pbi_new` tiene además el arreglo de `dq_order` con `PaidPrev` y la portada. README.md:583 sí dice cuál carpeta es la buena.

### C10 · El OneDrive personal sigue declarado como origen
`expressions.tmdl` de `pbi_new` es **byte a byte idéntico** al de `pbi/` (`diff -q` = 0): 19 expresiones, **8 `Csv.Document`** (líneas 78, 104, 124, 150, 188, 200, 237, 249) y **4 `SharePoint.Files("https://rabbitmx-my.sharepoint.com/personal/rodolfo_gonzalez_rabbitmx_com")`** (89, 135, 164, 214). Contra eso: README.md:581 dice que `pbi_new` va "sin un solo `Csv.Document`" y sql/pbi/README.md:122-124 lo repite.
**El chequeo que lo respalda tiene un agujero:** el comando de sql/pbi/README.md:287-291 solo barre `…SemanticModel\definition\tables`, nunca `expressions.tmdl`, y por eso concluye "Hoy no devuelve nada, y así debe quedarse".
Atenuantes: PENDIENTES:910-913 y :1073 ya lo describen **por nombre** como tarea pendiente (se hizo la mitad: `Consulta1` sí se borró), y ninguna tabla de `pbi_new` referencia esas expresiones — son huérfanas, no mueven una cifra. El costo real es el trámite de credenciales de la Fase 7 y que el README miente.

### C11 · `.env` huérfano
Existe `.env` en la raíz (466 bytes, **mtime 2026-08-14 06:31 — de hoy**) con tres variables: `BD_ENGINE_RABBIT_LOCAL`, `BD_ENGINE_RABBIT_LOCAL_SOPORTE` y `BD_ENGINE_RABBIT_LOCAL_PBI` (esta última sin una sola referencia en el repo), las tres URIs `postgresql+psycopg2://usuario:contraseña@host/base`. Su único consumidor es `analisis_one_shot/analisis_bnpl_one_shot.py:28-32`, que es **código muerto**: la línea 10 hace `raise SystemExit("Usar run.py en su lugar.")` al importar.
README.md:618 dice "**No hay `.env` que crear en la raíz**" y :470 "No lee `BD_ENGINE_RABBIT_LOCAL`". Lo bueno, verificado: está gitignoreado (`.gitignore:2-3`) y **nunca se commiteó** (`git log --all --diff-filter=A -- .env` vacío). No es un `.env` peor que los tres `.env.*` que el propio README avala; el hallazgo es la **contradicción documental más la dependencia huérfana**: nadie lo administra, y quien limpie siguiendo el README rompe `analisis_one_shot`. Que se haya editado hoy hace más urgente aclarar si es fuente de configuración o residuo.

### C12 · Bus factor de uno
`logs/pipeline_2026-08.log:468`: "Found credentials in shared credentials file: `~/.aws/credentials`" — el túnel SSM depende del perfil AWS de `Administrator`. Las tres librerías internas se instalan editable desde `C:\Users\Administrator\Documents\Funciones\`, y en `Documents\` hay además una carpeta `Credenciales`. README.md:618-622 dice que los tres `.env.*` "deben existir en la VM" y que "ninguno se versiona". README.md:641 admite que con SYSTEM el túnel no levanta, así que la tarea tiene que correr como esa persona. El remoto es una cuenta personal.
El README **sí** documenta qué credenciales hacen falta (tabla de Requisitos, :460-467). Lo que falta es **quién las administra y cómo se recuperan**: una tabla de accesos.

### C13 · La "Estructura" del README no corresponde al árbol
README.md:670-700 lista el árbol y **no incluye `ayuda_tablero/`** (10 `.py` + README + los 168 tooltips); el diagrama de arquitectura (:42-68) tampoco. `grep ayuda_tablero` sobre README.md solo pega en las líneas 20 y 21.
Se desinflan dos partes del hallazgo original: `legacy/` **no** es inventado — está en `.gitignore:22` y README.md:697 lo describe como "no se versionan: traen credenciales en claro", así que su ausencia del disco es consistente. Y el tercer paso manual (`documentar_tablero.py --aplicar`) **sí** está documentado en README.md:21 y `ayuda_tablero/README.md:28-35`. El hueco real es que no aparece en "Lo que NO cuelga de main.py" (README.md:127-138), que dice "**Dos** cargas son manuales".

### C14 · Sesiones SSM que quedan `Active`
`logs/pipeline_2026-08.log` líneas 7, 100, 442 y 471 — en el 100% de las corridas: *"No se pudo parsear el SessionId de la salida del forwarder. El túnel funciona, pero al cerrar no se podrá terminar la sesión en AWS: quedará Active hasta que el idle timeout la barra."* `grep SessionId|forwarder|idle timeout` sobre los 9 `.md`: **cero**. El README menciona el túnel SSM en 7 líneas y nunca esto. Es acumulación de sesiones y ruido de auditoría, probablemente barrido por el idle timeout; lo que no puede quedar es un WARNING recurrente que nadie sabe si es grave.
*Pendiente contra AWS:* cuántas sesiones Active hay acumuladas hoy en Session Manager.

### C15 · Entorno no reproducible
No existe `requirements.txt`, `pyproject.toml`, `Pipfile` ni `poetry.lock`. README.md:603 es `pip install pandas python-dotenv openpyxl matplotlib` **sin una sola versión fijada**, y README.md:613-615 instala `mongo_extractor`, `redshift_extractor` y `postgresql_extractor_uploader` como editables desde una ruta que el README deja como `<ruta>`. "Toda extracción va por ellas" (README.md:466) y no están versionadas ni fijadas en ningún lado. El `pip freeze` de la VM es hoy la única documentación, y no está escrito.

### C16 · El detalle por tabla no llega al log del pipeline
`etl_mongo_to_postgres.py:499`, `etl_redshift_to_postgres.py:338` y `build_bnpl.py:144` reportan con `print`, no con `logging`. Resultado: en las dos últimas corridas no hay **una sola línea** de detalle por tabla entre `[2/6]` y `[3/6]`, ni el aviso de "recarga completa programada" que anuncia el full mensual. Dato que refuerza: en la primera corrida el log **sí** traía el conteo por tabla vía los `write_start` de `postgres_local_client`; desapareció cuando `main.py:80` subió esa librería a WARNING.
Matiz importante: README.md:650 **no** miente — describe bien el reparto (`pipeline.log` = detalle por paso, `scheduler.log` = lo que el `.bat` capturó). El problema es que el `.bat` no corre (A3), así que hoy ese detalle se pierde al cerrar la consola.

### C17 · Sin trazabilidad de versión
`bnpl_ops.etl_runs` (`sql/00:49-56`) tiene cinco columnas: `started_at, tabla, modo, filas, segundos`. No se guarda commit SHA ni hash de los `.sql`. Y **las 18 vistas de `pbi_bnpl` — las únicas que Power BI lee — no se registran en absoluto**: `_construir_vistas_pbi()` (build_bnpl.py:59-79) no llama a `_registrar`. Es un hallazgo derivado de T1: una vez commiteado `sql/pbi/`, el historial de git responde solo la pregunta de qué definición tenía la vista tal día.

---

## 5. Deuda menor y limpieza

| # | Hallazgo | Evidencia |
|---|---|---|
| D1 | Cuatro vistas `v_pbi_*` duplican `sql/pbi/14` a `17`, contra la regla central del proyecto | `sql/14_archivos_bnpl.sql:97-98` lo admite en su propio comentario ("es la misma consulta… aquí viven **materializadas**" — y son `CREATE OR REPLACE VIEW`, se contradice en la misma frase). Contradice sql/pbi/README.md:12-13 y README.md:73-76. `PASOS_M.md` apunta a `pbi_bnpl`: las cuatro no las consume nadie. |
| D2 | README.md y sql/pbi/README.md terminan con markup de herramienta pegado | README.md:721-722 y sql/pbi/README.md:436-437 terminan con `</content>` y `</invoke>`. |
| D3 | Tabla rota en PENDIENTES: dos acciones ejecutables quedaron fuera de la lista | El blockquote de PENDIENTES:1070-1072 parte la tabla; las filas 1073 ("Borrar `Consulta1` y las expresiones de SharePoint") y 1074 ("Chequeo de frescura por contenido…") ya no renderizan. |
| D4 | `plan_implementacion.md` desfasado y un entregable desaparecido | README.md:38 remite ahí. Sigue listando abierto el punto 1 (IVA, ya cerrado con datos en PENDIENTES:20 y §1) y el 8 (la VM, resuelta). Fase 6 es la única sin "COMPLETADA". Promete una "Página de estado del pipeline alimentada por `bnpl_ops.v_freshness_status`" que **no existe** (sql/pbi/ salta de 17 a 20). Atenuante: `:3` dice "Estado: en revisión" y `:22` todavía afirma "No hay repo git", o sea que es una foto vieja. |
| D5 | `analisis_one_shot/README.md` desfasado, y un supuesto de negocio sin registrar | `:63` nombra la base `rabbit_fintech_bi`, que ya no existe (también en design.md:474 y :700); la estructura lista 8 scripts y hay 10 (faltan `run_v1.py` y `analisis_bnpl_one_shot.py`). Lo relevante: `config.py:7-11` documenta que **Propaga actualiza las líneas de crédito mensualmente en un Excel antes de cargarlas a MongoDB** — dato de gobierno que no está en PENDIENTES. |
| D6 | El conteo de páginas de PENDIENTES quedó viejo y la portada no abre el tablero | PENDIENTES:493-494 dice "de 14 páginas, 11 visibles" (describe `pbi/`); `pbi_new` tiene **15 y 12**. Y `pages.json` mantiene `activePageName = a4eca66684d1a46d5446` (Resumen Ejecutivo), no la portada que se construyó para que alguien nuevo sepa leer el tablero. |

---

## 6. Dudoso — lo que falta comprobar

### DU1 · La severidad de los `quality_checks` y el ruido crónico
**Lo cierto:** `main.py:153-156` emite todas las alertas con `log.warning` sin ramificar por severidad, y las tres corridas producen siempre los mismos tres WARNING (`credit_order_sales_order_id_nulo` 1,469 filas, `pagos_sin_orden` 276, y `fintech-customers-production sin escrituras (513 h)`).
**Lo que tumba el titular:** la severidad **sí hace algo**. `sql/00_bnpl_ops.sql:97-102` define `bnpl_ops.v_quality_alerts` con `ORDER BY CASE severidad WHEN 'CRIT' THEN 1 …`, o sea que un CRIT nuevo aparece hasta arriba, y README:348 instruye consultar esa vista al verificar una corrida.
**Comprobación que falta:** decidir cuál es el canal real de revisión. Si es la vista, el problema no existe; si es el log, un CRIT nuevo se ve igual que el ruido de siempre.

### DU2 · `total_revenue` negativo
`sql/04:186-191`: `CASE WHEN paid_date IS NULL THEN 0 ELSE coalesce(total_amount_to_pay,0) - coalesce(total_amount,0) END`. `paid_date` sale de `coalesce(p.paid_date, pr.paid_date)` (:98) y `total_amount_to_pay` de `coalesce(p.total_amount_to_pay, pr.total_amount_to_pay)` (:91), con `p` y `pr` unidos por separado (:102-103): **no vienen forzosamente de la misma fila**. Si la fuente que aporta la fecha no aporta el monto, el revenue queda en `-total_amount`, y eso se propaga a `kpis_daily` (`sql/08:61-62`), `revenue_comision` (`sql/09:40-41`) y a la línea de revenue del Resumen Ejecutivo, compensándose en silencio dentro de cualquier SUM.
**Comprobación que falta:** `select count(*), sum(total_revenue) from bnpl.loss_rates where total_revenue < 0`. Si da 0, es solo endurecimiento defensivo. PENDIENTES:116-125 documenta el caso simétrico (39 órdenes con `total_amount = 0`), no este.

### DU3 · Duración del refresh de Power BI
**Lo cierto:** no hay `refreshPolicy` ni `RangeStart/RangeEnd` en ninguna de las dos `SemanticModel`, las particiones son todas `mode: import`, y el refresh no deja rastro en `bnpl_ops` porque corre a mano en Desktop.
**Lo que no se sostiene:** la mitad "no hay incremental" está documentada y es **deliberada** (README.md:504-506 y :712: un pago puede llegar 519 días tarde), y el incremental solo aplica después del gateway. "Nadie sabe si terminó" tampoco: README.md:588 dice que lo lanza una persona desde Desktop.
**Lo que sí queda:** README.md:645-648 dimensiona la ventana de 90 minutos con los 32 s del servidor "más la carga del modelo", **sin ese número**. Falta medir el refresh completo una vez y escribirlo.

### Pendientes de verificar contra la base, Desktop o AWS

| Qué | Cómo se cierra |
|---|---|
| A1 · ¿Las matviews de `bnpl` dan ceros con el staging vacío? | Prueba en un ambiente aparte, no en productivo |
| B1 · Volumen de aprobados sin ficha en `fintech_customers` | El check `aprobados_sin_customer` ya lo mide; nadie lo ha reportado |
| B3 · Pedidos pagados con 90+ días de atraso | `select count(*), sum(total_amount) from bnpl.loss_rates where paid_date is not null and days_past_due >= 90` |
| B5 · Magnitud del embudo | Tarjeta `SUM(grid_bnpl[bnplMinimumTenure])` en Desktop → ¿146K o 9K? |
| B16 · Volumen de huecos del SCD | `count(*) from bnpl.grouped_orders where ruta is null and ruta_inferida is null` |
| A12 · ¿`propaga-transaction-dev` es la colección productiva? | Preguntar a ingeniería. No se puede resolver desde el repo |
| A13 · ¿Hay snapshot de EBS o respaldo de `postgresql-x64-17`? | Consola de AWS / servicios de la VM |
| C14 · Sesiones SSM acumuladas | Session Manager |

---

## 7. Plan de acción

### Hoy (bloquea todo lo demás)

| # | Acción | Archivo |
|---|---|---|
| 1 | `git add` de `sql/pbi/`, `ayuda_tablero/`, `carga_archivos_bnpl.py`, `carga_clientes_concurso.py`, `sql/13-15` y `pbi_new/`. Commits temáticos. **Y `git push`** (hoy va `ahead 2`) | raíz del repo |
| 2 | Consolidar antes de commitear los 667 archivos de dos modelos: borrar `pbi/`, renombrar `pbi_new/` → `pbi/`, borrar el `.pbix` de adentro (está 4h28m rezagado del TMDL). Si se conserva `pbi/` como referencia, quitarle `.pbi/localSettings.json` para que no quede atado al `reportId` productivo | `pbi/`, `pbi_new/`, `ayuda_tablero/inventario.py:7`, `portada.py:8` |
| 3 | Corregir README.md:702-703, que afirma que esas carpetas ya se versionan | README.md |
| 4 | Escribir el bloque de dueño: quién opera el pipeline, backup, a quién se escala un CRIT de fuente en ingeniería, ventana comprometida con negocio, dónde vive el seguimiento de fuentes caídas | README.md |
| 5 | ~~Crear la tarea programada, correrla una vez y verificar que aparezca `logs\scheduler.log`~~ **Hecho 2026-08-14**: `\BNPL Pipeline`, diaria 13:30 UTC = 07:30 CDMX, `S4U`, verificada con una corrida real. El refresh se movió a las **08:30** el mismo día, con 40 min de margen | README.md → *Despliegue a la VM* |

### Esta semana

| # | Acción | Archivo |
|---|---|---|
| 6 | Abortar con excepción si `extract_aggregate` devuelve 0 filas en una colección que no es legítimamente vacía; y convertir el bloque de "desincronizadas" del paso 6 en `return 1` cuando una fuente crítica quede en CRIT/FALTA | `etl_mongo_to_postgres.py:491-499`, `main.py:158-170` |
| 7 | Agregar notificación de fallo (SMTP o webhook) con código de salida, `modo` de `etl_runs` y últimas 20 líneas del log. Definir destinatario y escribirlo | `main.py` o `run_pipeline.bat` |
| 8 | Aplicar `sql/14_archivos_bnpl.sql` desde `build_bnpl.py` (es `CREATE TABLE IF NOT EXISTS`) **y** envolver el loop de vistas en un try por archivo que registre cuál falló y siga | `build_bnpl.py:30-43`, `:66-79` |
| 9 | Que `_construir_vistas_pbi()` corra siempre que `rebuild` sea True, aunque haya `--solo` | `build_bnpl.py:148` |
| 10 | `DISTINCT ON (netsuiteId) ORDER BY createdAt DESC` en `enrolados`, `preautorizados` y `lineas`; subir `approval_netsuite_id_duplicado` a CRIT o moverlo a pre-check | `sql/07:68-93`, `sql/03:13-24`, `ops/quality_checks.py:46-55` |
| 11 | Guardas para los casts de texto: `bnpl.texto_a_date()` y `bnpl.texto_a_float()` con el mismo patrón de `iso_a_mx` | `sql/02_bnpl_funciones.sql`, `sql/07:112-123` |
| 12 | Portar las 15 identidades de README.md:377-408 a `CHECKS`, con CRIT en los pares que deben ser exactamente iguales | `ops/quality_checks.py` |
| 13 | Registrar las dos cargas manuales en `bnpl_ops.etl_runs` (nombre de archivo, mtime, hash) y agregarles chequeo de frescura | `carga_archivos_bnpl.py`, `carga_clientes_concurso.py`, `ops/config.py`, `ops/check_freshness.py` |
| 14 | Mover TRUNCATE/DELETE + `load_dataframe` a una sola transacción por colección, como `_cargar()` en el ETL de Redshift | `etl_mongo_to_postgres.py:414-499` |
| 15 | Antes de publicar `pbi_new`: recrear `grid_bnpl[bnplEnrolledAt] -> enrollment_dates[Date]` y `bnpl_loss_rates_with_lead[netsuiteId] -> grid_bnpl[netsuiteId]`; revisar las 5 relaciones que cambiaron en la migración y dejarlas escritas | `pbi_new/…/relationships.tmdl`, portada `p0trampas00000000003` |
| 16 | Arreglar `bnplMinimumTenure` con guardia de blanco **después** de verificarlo en Desktop | `grid_bnpl.tmdl:124` |
| 17 | Decidir qué columnas de PII necesita el tablero. Sacar `customerPhoneNumber` y el domicilio a una vista aparte con acceso restringido; revisar quién tiene el `.pbix` hoy | `sql/pbi/06`, `sql/pbi/08`, `Top100InactiveCustomers.tmdl` |
| 18 | Escribir "Cuando falla el pipeline": los 3 modos de `etl_runs`, si cada paso es idempotente, cómo se re-corre solo el caído, y tabla con los 8 chequeos (qué mide, severidad, si está abierto, qué hacer) | README.md |
| 19 | Antes de la reunión §16.2 con Finanzas: llevar el P&L de `0022e35f90d69de5ed50` en la mano y preguntar por el 4% y el 40%; corregir la premisa de §16.2 | PENDIENTES_NEGOCIO.md:64-65, :151, :954 |
| 20 | Nombrar el problema de `deployedCapital` en §12 antes de que el 6.02% llegue a comité | PENDIENTES_NEGOCIO.md §12, §16.5 |
| 21 | Documentar el requisito de Python + `seaborn` para los 9 `pythonVisual`, y verificar Resumen Ejecutivo abriéndolo | README.md, junto al requisito de Power BI Desktop |
| 22 | Borrar las dos últimas líneas de README.md y sql/pbi/README.md; mover el blockquote de PENDIENTES:1070-1072 después de la tabla | README.md, sql/pbi/README.md, PENDIENTES_NEGOCIO.md |
| 23 | Definir el respaldo: `pg_dump` diario fuera de la VM, o confirmar por escrito que la estrategia es snapshot de EBS con su RPO/RTO. Probar una restauración | README.md, script nuevo |

### Puede esperar

| # | Acción | Archivo |
|---|---|---|
| 24 | Renombrar las 6 gráficas de PAR y las 4 tablas del Funnel para que digan qué miden y sobre quién; corregir el `nativeQueryRef` duplicado | `pages/2f83323b…`, `pages/f384ed51…`, PENDIENTES §12 |
| 25 | Corregir `locPenetration` (`SUMX` sobre clientes o apoyarse en `grid_bnpl`) tras confirmar con negocio contra qué línea se mide | `bnpl_grouped_orders.tmdl:8` |
| 26 | Reescribir `stage2..stage7` para que respeten `paidDate`, o renombrar las tarjetas a "peor mora alcanzada"; renombrar el valor `Ongoing` de la escalera a `Matured` | `bnpl_loss_rates.tmdl:432-529`, PENDIENTES §13b.3 |
| 27 | Bajar el corte de madurez a SQL (`bnpl.dias_madurez()`), unificar 115 días y >4 meses, y escribir quién los fijó | `sql/02_bnpl_funciones.sql`, `bnpl_loss_rates.tmdl`, `grid_bnpl.tmdl:124` |
| 28 | Agregar `&& flg_cte_bnpl = "N"` al Y0 de la tendencia de no enrolados | `bnpl_cosechas_agg.tmdl:321` |
| 29 | Marcar las 7 cohortes faltantes del slicer de Survival Matrix y decidir si debe llevar selección persistida | `pages/d43c4523…/visuals/6cc43988…` |
| 30 | Restaurar la jerarquía Año/Mes en "Ever Activated Customers" y limpiar el `nativeQueryRef` | `pages/880e9dc6…/visuals/3fae7ada…` |
| 31 | Unificar el corte de `loanDisbursementIndex` en DAX y SQL; separar `Index` (entero) de `IndexRange` (rango). Preguntar a riesgo antes de tocar el de SQL: de ahí cuelgan los bins de §10.1 | `bnpl_loss_rates.tmdl:535-541`, `sql/pbi/08`, `12`, `13`, `14`, `15` |
| 32 | Cerrar los huecos del SCD (extender `valido_hasta` al `valido_desde` siguiente −1 día) o marcar `ruta_inferida = true` sin match, según el volumen medido | `sql/11:60-61`, `sql/03:112` |
| 33 | Corregir el grano en README.md:493 y la cabecera de `sql/03`; agregar el check `count(*) vs count(distinct)` sobre COMPLETED | README.md, `sql/03:1`, `ops/quality_checks.py` |
| 34 | Decidir si el universo del concurso debe llegar al tablero: o `sql/pbi/18_bnpl_clientes_concurso.sql` + paso M, o corregir sql/pbi/README.md:54 y README.md:63 | según la decisión |
| 35 | Igualar los tipos de `totalAmountDefault` y `paymentDate` entre `03` y `04`, y agregarlos a la tabla de tipos | `sql/pbi/03:39,41`, `sql/pbi/04:57,59`, sql/pbi/README.md:294-308 |
| 36 | Borrar `Clientes_Mensual`, `TablaParaGrafica`, `cohort_type`, `x_axis_type` y (previa confirmación) `Top100InactiveCustomers`; actualizar la lista de tablas calculadas | `pbi/…/tables/`, `model.tmdl`, sql/pbi/README.md:340 |
| 37 | Extender `revisar_referencias.py` a `filters`, `filterConfig` de página y `visual.objects`, resolviendo alias por el bloque `From`. Borrar `TARGET.Area` | `ayuda_tablero/revisar_referencias.py:21-29`, `pages/49e8cfe3…/visuals/32f24f3b…` |
| 38 | Borrar las expresiones de SharePoint/CSV de `expressions.tmdl`, corregir README.md:581 y sql/pbi/README.md:123-124, y arreglar el grep de verificación para que barra `definition\*.tmdl` | `pbi/…/expressions.tmdl`, `model.tmdl:61` |
| 39 | Promover `conocimiento.py` a fuente del diccionario: referenciarlo desde el README y generar un `DICCIONARIO.md` con dueño por métrica | `ayuda_tablero/conocimiento.py`, README.md |
| 40 | Plan para apagar la fecha automática: medir, crear tabla de fechas propia, reapuntar los 19 visuales, y solo entonces `__PBI_TimeIntelligenceEnabled = 0`. Dejarlo escrito | sql/pbi/README.md, `model.tmdl:63` |
| 41 | Migrar `analisis_bnpl_one_shot.py` a `postgres_local_client` y borrar el `.env` de la raíz (o corregir README.md:470 y :618) | `analisis_one_shot/analisis_bnpl_one_shot.py:10,28,32`, `.env` |
| 42 | Generar `requirements.txt` con `pip freeze` y anotar el commit/tag de las tres librerías internas | raíz, README.md:603-615 |
| 43 | Cambiar los `print` por `logging.getLogger(__name__).info(...)` en los tres scripts | `etl_mongo_to_postgres.py:499`, `etl_redshift_to_postgres.py:338`, `build_bnpl.py:144` |
| 44 | Documentar el WARNING del SessionId junto al túnel SSM (o reportarlo al dueño de `mongo_extractor`) | README.md:624-642 |
| 45 | Borrar las cuatro `v_pbi_*` de `sql/14:100-121` o cambiar el comentario para decir que son alias sin uso | `sql/14_archivos_bnpl.sql` |
| 46 | Actualizar la Estructura del README (agregar `ayuda_tablero/`, meterlo al diagrama, cambiar "dos cargas manuales" por tres pasos con `documentar_tablero.py --aplicar`) | README.md:42-68, :127-138, :670-700 |
| 47 | Cerrar los puntos 1 y 8 de `plan_implementacion.md`, marcar Fase 6 y decidir por escrito si la página de estado del pipeline se construye o se cancela | `.kiro/specs/migracion-pipeline-bnpl/plan_implementacion.md` |
| 48 | Actualizar el conteo de páginas a 15/12 y decidir si `activePageName` debe ser la portada | PENDIENTES_NEGOCIO.md:493-494, `pages.json` |
| 49 | Actualizar `analisis_one_shot/README.md` y llevar el supuesto del Excel de Propaga a PENDIENTES como pregunta para Riesgo | `analisis_one_shot/README.md:63,90-100`, PENDIENTES_NEGOCIO.md |
| 50 | Registrar commit SHA y hash de los `.sql` en `etl_runs`, e incluir las 18 vistas de `pbi_bnpl` en la bitácora (depende de la acción 1) | `sql/00_bnpl_ops.sql`, `build_bnpl.py:59-79` |
| 51 | Tabla de accesos: cada credencial, quién la administra, cómo se solicita (sin valores). Dársela a una segunda persona y que corra `ops/check_freshness.py` | README.md |
| 52 | Mover el repositorio de la cuenta personal a la organización | GitHub |
---

## 8. Anexo · Verificaciones hechas fuera de los agentes

Estas se comprobaron a mano contra la máquina y el repo, no por lectura de archivos:

| Qué | Comando | Resultado |
|---|---|---|
| No existe la tarea programada (A3) | `Get-ScheduledTask \| ? TaskPath -notlike '\Microsoft\*'` | 12 tareas, ninguna de BNPL. Sí hay `Indicadores_logisticos` y `AB Ejecusión Indicadores Operatrivos` de otros proyectos: el Task Scheduler se usa en esta VM, sólo que no para este pipeline. |
| `run_pipeline.bat` nunca corrió (A3) | `ls logs/` | Sólo `pipeline_2026-08.log`. `scheduler.log` no existe. |
| 704 archivos fuera de git (T1) | `git ls-files --others --exclude-standard \| wc -l` | 704 |
| `sql/pbi/` no está ignorado, nunca se agregó (T1) | `git check-ignore -v sql/pbi/01_*.sql` | vacío |
| Los 2 commits no están empujados (T1) | `git status -sb` | `## master...origin/master [ahead 2]` |
| `concurso_base` no lee la tabla del concurso (B18) | `grep -c clientes_concurso sql/pbi/20_concurso_base.sql` | 0 |
| 4 vistas dependen de `archivos_bnpl` (A4) | `grep -ln archivos_bnpl sql/pbi/*.sql` | 14, 15, 16, 17 |
| `TODAY()-115` existe sólo en DAX (B4) | `grep 115 sql/ --include=*.sql` | 0 en SQL, 7 en `bnpl_loss_rates.tmdl` |
| `bnplMinimumTenure` sin guardia de blanco (B5) | `grep -n bnplMinimumTenure grid_bnpl.tmdl` | `IF(DATEDIFF([bnplEnrolledAt], TODAY(), MONTH) > 4, 1, 0)` |
| Relaciones perdidas en la migración (B7, B8) | `grep -n enrollment_dates\|with_lead relationships.tmdl` en ambos | `pbi/` tiene `enrollment_dates.Date` dos veces y `with_lead.netsuiteId`; `pbi_new/` no tiene ninguna de las dos |

### Anomalía sin explicar: `.env` se regeneró durante la auditoría

Al abrir la auditoría, `.env` medía **346 bytes** con dos variables (`BD_ENGINE_RABBIT_LOCAL`,
`BD_ENGINE_RABBIT_LOCAL_SOPORTE`) y su mtime era **2026-08-13 15:00**. Media hora después medía
**466 bytes**, con una tercera variable `BD_ENGINE_RABBIT_LOCAL_PBI`, y mtime **2026-08-14 06:31**.

Se descartó que lo hicieran los agentes de la auditoría: sus únicas escrituras fueron al directorio
temporal de trabajo (`grep` de `Write`/`Edit` y de redirecciones de shell sobre los transcripts = 0
sobre `.env`). Y `BD_ENGINE_RABBIT_LOCAL_PBI` **no aparece en ningún `.py`, `.sql` ni `.md`** del
repositorio, así que ningún código versionado lo lee ni lo escribe.

Conclusión: algo fuera del flujo documentado regenera ese archivo — la cabecera del propio `.env`
dice "Generado desde el alias `local_rw` de `.env.postgres_local_client`", así que existe un
generador que no está en el repo. Refuerza **C11**: mientras el README.md:618 sostiene que "no hay
`.env` que crear en la raíz", hay un archivo con tres cadenas de conexión que alguien o algo
mantiene, sin dueño declarado.

**Qué falta:** identificar el generador antes de borrar el archivo (acción 41), o el borrado se
deshará solo y quien limpie no va a entender por qué.

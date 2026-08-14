# Pipeline BNPL — Rabbit

BNPL (*Buy Now Pay Later*) es el producto de crédito que Rabbit ofrece a los tenderos: compran a
crédito y pagan **15 días después de recibir el pedido**. El crédito lo otorga **Propaga**, nuestro
partner, y Rabbit se lleva una **comisión sobre el interés**.

La información que Propaga nos devuelve vive en MongoDB. Este pipeline la baja a PostgreSQL, la
convierte en las tablas de riesgo y venta, y alimenta Power BI.

## Si es tu primer día

| Pregunta | Dónde está |
|---|---|
| ¿Qué corre, en qué orden y cuánto tarda? | [Flujo completo](#flujo-completo) |
| ¿Cómo cambio una consulta del tablero? | [Cambiar una consulta](#cambiar-una-consulta-del-tablero) |
| ¿Cómo agrego una tabla nueva al tablero? | [`sql/pbi/README.md` → Agregar una tabla nueva](sql/pbi/README.md#agregar-una-tabla-nueva-al-tablero) |
| ¿Cómo recargo los CSV del Drive? ¿Están viejos? | [Los archivos del Drive](#los-archivos-del-drive) |
| ¿Cómo sé si la corrida de hoy quedó bien? | [Verificar una corrida](#verificar-una-corrida) |
| Falló el refresh de Power BI, ¿ahora qué? | [`sql/pbi/README.md` → Cuando falla el refresh](sql/pbi/README.md#cuando-falla-el-refresh) |
| ¿Qué mide esta gráfica del tablero? | el ícono ⓘ de su encabezado, o [`ayuda_tablero/README.md`](ayuda_tablero/README.md) |
| Cambié el modelo, ¿cómo actualizo los textos de ayuda? | [`ayuda_tablero/README.md` → Cuando cambia el modelo](ayuda_tablero/README.md#cuando-cambia-el-modelo) |
| ¿Qué significa esta columna, este campo o esta medida? | [`DICCIONARIO.md`](DICCIONARIO.md) — generado, se edita en `ayuda_tablero/conocimiento.py` |
| ¿Qué falta confirmar con negocio? | `PENDIENTES_NEGOCIO.md` (se mantiene aparte) |

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
| Arranque de la corrida diaria | **00:00 hora CDMX** (disparador `06:00` UTC) | tarea `BNPL Pipeline` del Task Scheduler, ver *Despliegue a la VM* | el tablero se queda con el dato de ayer |
| Dato listo para el refresh | **00:20 CDMX** (00:00 + ~20 min) | medido, ver *Flujo completo* | — |
| Refresh del Service | **08:30 CDMX** | actualización programada del Service | el tablero no toma la carga de la madrugada y sigue publicando lo de ayer sin avisar |
| Duración de la corrida | ~20 min · ~40 el día del `--full` mensual | medido, ver *Flujo completo* | se come la ventana hasta las 08:30 |
| Frescura de una fuente — WARN | 24 h sin escrituras en Mongo | `ops/config.py:25` `LAG_WARN_HORAS` | se vigila, no se actúa |
| Frescura de una fuente — CRIT | 48 h sin escrituras en Mongo | `ops/config.py:26` `LAG_CRIT_HORAS` | si está en `FUENTES_CRITICAS`, la corrida **aborta** |
| Desfase del staging | 1% de los documentos | `ops/config.py:41` `FALTANTES_WARN_PCT` | correr el ETL; si persiste, `--full` |

**No hay SLA de reparación de fuente y no puede haberlo desde aquí**: un CRIT en Mongo lo arregla
Ingeniería. Lo que sí se compromete este proyecto es a abrir el ticket el mismo día y a dejarlo
anotado abajo, con fecha. Un CRIT sin renglón en esta tabla es un CRIT que nadie está siguiendo.

### Incidencias abiertas con las fuentes

| Fuente | En CRIT desde | Horas al {{FECHA}} | Ticket | Quién lo lleva | Última revisión |
|---|---|---:|---|---|---|
| `fintech-customers-production` | 2026-07-22 | 513 | {{TICKET}} | {{NOMBRE}}, Ingeniería | {{FECHA}} |

## Estado

| Fase | Qué hace | Estado |
|---|---|---|
| 0 | Tablero de frescura y calidad de las fuentes | **listo** |
| 1 | ETL Mongo → staging PostgreSQL | **listo** |
| 2 | DDL tipado e índices | **listo** |
| 3 | Tablas finales (PAR, vintage, grid, KPIs, revenue, cortes) | **listo** |
| 4 | Dimensiones de ruta y cierre de huecos | **listo** |
| 5 | Orquestación y despliegue a la VM | **listo** — tarea `BNPL Pipeline`, diaria 00:00 CDMX |
| 6 | Capa de consumo `pbi_bnpl` + archivos del Drive en `archivos_bnpl` | **listo** — 19 vistas, 4 tablas |
| 7 | Power BI Service + Gateway | **listo** — refresh desde el Service por `Gateway_BI` |

Plan detallado con las decisiones y sus mediciones:
[`.kiro/specs/migracion-pipeline-bnpl/plan_implementacion.md`](.kiro/specs/migracion-pipeline-bnpl/plan_implementacion.md).

## Arquitectura

```
  FUENTE                        SCRIPT                          SCHEMA EN rabbit-bi-local (localhost:9553)

  MongoDB (Propaga)             etl_mongo_to_postgres.py        mongo_bnpl.*        10 tablas, espejo fiel
  52 colecciones, túnel SSM  ─▶ 13.9 min                     ─▶
                                                                      │
  Redshift                      etl_redshift_to_postgres.py     redshift_bnpl.*     6 tablas: rutas, ventas,
  data-rabbit-prod           ─▶ 3.5 min                      ─▶       │             cosechas, estacionalidad
                                                                      │
                                                                      ▼
                                build_bnpl.py                   bnpl.*              11 vistas materializadas
                                1.4 min                      ─▶       │             (la capa de negocio)
                                                                      │
                                                                      ▼
                                build_bnpl.py                   pbi_bnpl.*          19 vistas, una por tabla
                                (mismo paso, al final)       ─▶       ▲             del modelo de Power BI
                                                                      │
  Drive compartido              carga_archivos_bnpl.py          archivos_bnpl.*   ──┤  4 tablas: los CSV que
  4 CSV                      ─▶ A MANO, ~20 s               ─▶                       ninguna consulta reemplaza
                                                                      │
  Excel de negocio              carga_clientes_concurso.py      bnpl.bnpl_clientes_concurso
  BBDD tablero LANZAMIENTO   ─▶ A MANO                       ─▶       │  (tabla física, la lee la vista 20)
                                                                      ▼
                                                                Power BI Service  ──Gateway_BI──▶  refresh 08:30

  El modelo (PBIP)              ayuda_tablero/                  los 168 tooltips del tablero
  pbi_new/…Report            ─▶ documentar_tablero.py --aplicar  A MANO, cuando cambia el modelo

  bnpl_ops.*   frescura de fuentes, calidad de datos, bitácora de cargas — lo escribe cada paso
```

**El staging es un espejo fiel de Mongo**: no deduplica ni corrige. Si Mongo trae basura, la trae
igual y lo reporta `bnpl_ops.data_quality_checks`. La limpieza vive en la capa `bnpl`.

**`pbi_bnpl` no tiene lógica propia.** Cada una de sus 19 vistas es, literalmente, un archivo de
`sql/pbi/*.sql` envuelto en un `CREATE VIEW` por `build_bnpl.py`. El `.sql` es la única fuente y no
puede quedar desfasado de la vista.

### Los seis schemas

| Schema | Qué es | Quién lo escribe | ¿Se puede tirar? |
|---|---|---|---|
| `mongo_bnpl` | 10 tablas espejo de Mongo | `etl_mongo_to_postgres.py` | sí, se rehace |
| `redshift_bnpl` | 6 tablas de Redshift: rutas, ventas, cosechas, estacionalidad | `etl_redshift_to_postgres.py` | sí, se rehace |
| `bnpl` | 11 vistas materializadas: la capa de negocio + 1 tabla física del concurso | `build_bnpl.py` (la del concurso, `carga_clientes_concurso.py`) | las 11 sí; la tabla del concurso **no** |
| `pbi_bnpl` | 19 vistas, una por tabla del modelo de Power BI | `build_bnpl.py` desde `sql/pbi/*.sql` | sí, se rehace en cada corrida |
| `archivos_bnpl` | 4 tablas + 4 vistas: los CSV que ninguna consulta reemplaza | `carga_archivos_bnpl.py`, **a mano** | **NO** — hay que volver a conseguir los archivos |
| `bnpl_ops` | 4 tablas + 2 vistas: frescura, calidad, bitácora | todos los pasos | sí, pero se pierde el histórico |

---

## Flujo completo

**Un solo comando** hace los seis pasos automáticos, en orden y con log:

```powershell
.venv\Scripts\python.exe main.py
```

| Paso | Script | Qué produce | Tiempo medido |
|---|---|---|---|
| 1/6 frescura | `ops/check_freshness.py` | `bnpl_ops.source_freshness`, `freshness_history` | ~15 s |
| 2/6 staging Mongo | `etl_mongo_to_postgres.py` | `mongo_bnpl.*` (10 tablas) | **13.9 min** |
| 3/6 estructura comercial | `etl_redshift_to_postgres.py` | `redshift_bnpl.*` (6 tablas) | **3.5 min** |
| 4/6 capa de negocio | `build_bnpl.py` | `bnpl.*` (11 matviews) + `pbi_bnpl.*` (19 vistas) | **1.4 min** |
| 5/6 calidad | `ops/quality_checks.py` | `bnpl_ops.data_quality_checks` | ~15 s |
| 6/6 frescura final | `ops/check_freshness.py` | deja registrado que el staging quedó sincronizado | ~15 s |
| | | **total** | **~20 min** |

> Las corridas registradas en `bnpl_ops.etl_runs` como `tabla='pipeline'` dan 17.0 y 17.5 min, pero
> **son anteriores a los tres pasos nuevos de Redshift** (`ventas_cliente`, `cosechas_agg`,
> `estacionalidad_mes`), que se midieron aparte y suman 2.3 min. La próxima corrida completa debe
> dar ~20 min. Si da 17, es que el paso 3 no corrió.

| Flag de `main.py` | Para qué |
|---|---|
| `--full` | fuerza recarga completa del staging (se dispara solo cada 30 días) |
| `--sin-redshift` | omite el paso 3 — útil para reprocesar sin volver a bajar 3.5 min de Redshift |
| `--rebuild` | reconstruye las vistas de `bnpl` desde los `.sql` en vez de refrescarlas |

Deja todo en `logs/pipeline_YYYY-MM.log` y en las tablas de `bnpl_ops`, y devuelve código 1 si algo
falló, para que el Task Scheduler lo reporte.

En la VM ese comando **no** se corre a mano: lo dispara la tarea `\BNPL Pipeline` todos los días a las
**00:00 de CDMX** vía `run_pipeline.bat` — cómo quedó registrada y por qué el disparador dice `06:00`
está en [Despliegue a la VM](#despliegue-a-la-vm). Ojo con qué significa "lo reporte": el código 1
queda en el `LastTaskResult` de la tarea y en `bnpl_ops.etl_runs`, y desde el 2026-08-14 `ops/notificar.py`
manda además un correo con las últimas 60 líneas del log — **pero sólo si existe `.env.bnpl_pipeline`**
con la credencial SMTP y la lista de destinatarios. Mientras ese archivo no exista, el aviso degrada a
un WARNING en el log y hay que ir a verlo a mano.

**Se detiene si una fuente crítica está en CRIT** (`credit-order`, `payment-report`,
`state-of-delivery`): cargar datos viejos encima del tablero es peor que no cargar. Las demás
fuentes en CRIT solo generan una advertencia — `fintech-customers` lleva semanas caída y eso no
invalida la mora ni el revenue. La lista está en `ops/config.py` → `FUENTES_CRITICAS`.

### Lo que NO cuelga de `main.py`

**Tres pasos son manuales a propósito.** Los dos primeros porque el dato lo publica una persona, no
una fuente, así que no tiene sentido intentarlos todos los días; el tercero porque escribe el PBIP,
no la base.

```powershell
.venv\Scripts\python.exe carga_archivos_bnpl.py                          # 4 CSV del Drive -> archivos_bnpl.*
.venv\Scripts\python.exe carga_clientes_concurso.py                      # Excel de negocio -> bnpl.bnpl_clientes_concurso
.venv\Scripts\python.exe ayuda_tablero\documentar_tablero.py --aplicar   # los 168 tooltips del PBIP
```

Ninguna de las dos cargas se rehace sola. Si borras `archivos_bnpl`, hay que volver a conseguir los
archivos: por eso vive en un schema aparte de `bnpl`, que sí se puede tirar y reconstruir.
El tercero sí es idempotente y sin `--aplicar` solo dice qué cambiaría; su detalle está en
[`ayuda_tablero/README.md`](ayuda_tablero/README.md).

### Cada paso por separado

```powershell
.venv\Scripts\python.exe ops\check_freshness.py        # frescura
.venv\Scripts\python.exe ops\quality_checks.py         # calidad
.venv\Scripts\python.exe etl_mongo_to_postgres.py      # staging Mongo
.venv\Scripts\python.exe etl_redshift_to_postgres.py   # Redshift, 6 tablas, 3.5 min
.venv\Scripts\python.exe build_bnpl.py                 # capa de negocio + vistas PBI, 85 s
```

Los dos ETL y `build_bnpl.py` aceptan `--solo` para no rehacer todo:

```powershell
.venv\Scripts\python.exe etl_redshift_to_postgres.py --solo estacionalidad_mes
.venv\Scripts\python.exe build_bnpl.py --solo grid_bnpl,kpis_daily
```

> **`--solo` en `build_bnpl.py` NO reconstruye las vistas de `pbi_bnpl`.** Es deliberado: `--solo`
> es para recargas puntuales de la capa de negocio. Si lo que cambiaste es un `.sql` de `sql/pbi/`,
> corre `build_bnpl.py` sin flags.

### Desglose de tiempos (corrida del 2026-08-13)

| Staging Mongo | s | | Redshift | s | | Capa de negocio | s |
|---|---:|---|---|---:|---|---|---:|
| `fintech_customers` | 149.4 | | `ventas_cliente` | 78.6 | | `par_snapshot` | 25.2 |
| `credit_order` (ventana) | 121.2 | | `estructura_comercial` | 46.2 | | `vintage_analysis` | 13.2 |
| `propaga_transaction` | 119.3 | | `cosechas_agg` | 32.1 | | `loss_rates` | 12.0 |
| `payment_report` | 107.2 | | `ruta_cliente_scd` | 27.4 | | `grouped_orders` | 11.0 |
| `credit_limit_history` | 101.6 | | `estacionalidad_mes` | 27.2 | | `dim_ruta_actual` | 10.1 |
| `revenue_orders` | 76.8 | | `route_mapping` | 1.3 | | `grid_bnpl` | 7.2 |
| `fintech_pre_authorization` | 65.5 | | | | | `revenue_comision` | 2.2 |
| `state_of_delivery` | 52.9 | | | | | `corte_venta_sku` | 1.2 |
| `fintech_credit_request` | 20.6 | | | | | `kpis_daily` | 0.7 |
| `fintech_credit_approval` | 18.1 | | | | | `dim_ruta_cliente_scd` + `corte_venta_so` | 0.4 |
| **total** | **832.6** | | **total** | **212.8** | | **total** | **83.2** |

Las 19 vistas de `pbi_bnpl` no aparecen porque son sólo DDL: crearlas cuesta menos de un segundo.
Lo que sí cuesta es **leerlas**, y eso lo paga Power BI en cada refresh — ver
[Verificar una corrida](#verificar-una-corrida).

El cuello es la extracción desde Mongo por el túnel SSM, no la escritura. La variación es del túnel:
la misma extracción tardó 166 s y 356 s en corridas consecutivas.

---

## Cambiar una consulta del tablero

Las 17 tablas del modelo de Power BI se alimentan de `pbi_bnpl.*`, y cada vista es un archivo de
`sql/pbi/`. **El `.sql` es la única fuente.** Corregir una consulta es esto y nada más:

```powershell
# 1. Editar el .sql. El nombre de la vista es el del archivo SIN su número:
#    sql/pbi/06_grid_bnpl.sql  ->  pbi_bnpl.grid_bnpl
code sql\pbi\06_grid_bnpl.sql

# 2. Reconstruir las vistas (DROP + CREATE de las 19; tarda menos de un segundo)
.venv\Scripts\python.exe build_bnpl.py

# 3. Comprobar contra la base ANTES de tocar Power BI
```

```sql
select count(*) from pbi_bnpl.grid_bnpl;
select * from pbi_bnpl.grid_bnpl limit 5;
-- los tipos, que es lo que rompe el refresh:
select column_name, data_type from information_schema.columns
where table_schema = 'pbi_bnpl' and table_name = 'grid_bnpl'
order by ordinal_position;
```

```
# 4. Refrescar en Power BI Desktop. El paso M no cambia: sigue siendo
#    "select * from pbi_bnpl.grid_bnpl".
```

`build_bnpl.py` usa **DROP + CREATE**, no `CREATE OR REPLACE`: este último falla si cambian los
nombres, el orden o el tipo de las columnas, que es justo lo que pasa al corregir una consulta.

### Lo que NO hay que hacer

| No hagas esto | Por qué |
|---|---|
| Editar la consulta dentro del `.pbix` | Entierra la lógica en un binario de 122 MB. El siguiente `build_bnpl.py` no la ve, y el `.sql` y el tablero se separan sin que nadie se entere. |
| Pegar SQL en el paso M | Hay que escapar cada comilla y queda una segunda copia de la consulta. El M correcto es de una línea: `select * from pbi_bnpl.<vista>`. |
| Crear la vista a mano con `CREATE VIEW` | La próxima corrida la sobrescribe desde el `.sql` y tu cambio desaparece. Edita el `.sql`. |
| Elegir la tabla con el navegador de Power BI | `grid_bnpl` y `vintage_analysis` existen en **dos** schemas y ahí aparecen con el mismo nombre. Siempre `Value.NativeQuery` con el schema calificado. |
| Dejar `Table.TransformColumnTypes` o `Table.RemoveColumns` después del `Origen` | Las vistas ya devuelven el tipo correcto y no traen la columna sin nombre del CSV. Esos dos pasos fallan. |
| Cambiar el nombre de una columna "para que se vea mejor" | De los alias en camelCase cuelgan 66 medidas DAX, 22 relaciones y ~50 columnas calculadas. Un rename no falla el refresh: falla la medida, tres páginas más allá. |

El detalle de cada consulta, sus columnas y lo que se verificó contra los CSV originales está en
[`sql/pbi/README.md`](sql/pbi/README.md). El paso M de cada tabla, listo para copiar, en
[`sql/pbi/PASOS_M.md`](sql/pbi/PASOS_M.md).

---

## Los archivos del Drive

Cuatro CSV que **ninguna consulta puede reemplazar**: dos son la salida de un modelo de riesgo
(WOE/IV por atributo), uno es la clasificación que hace el equipo de Pago de Servicios y el último
es captura manual de negocio. Ver `PENDIENTES_NEGOCIO.md`, secciones 10 y 11.

| Tabla | Archivo en el Drive | Filas | Última versión publicada |
|---|---|---:|---|
| `archivos_bnpl.odds_combinations` | `Rabbit Risk Analytics\Buy Now Pay Later\Default Profile\odds_combinations.csv` | 84,986 | 2026-06-10 |
| `archivos_bnpl.atr_combinations_iv` | `…\Default Profile\atr_combinations_iv.csv` | 468 | 2026-06-10 |
| `archivos_bnpl.ps_transactional_profile` | `Rabbit Analytics\Pago de Servicios Automation\ps_transactional_profile.csv` | 100,793 | 2026-01-08 |
| `archivos_bnpl.bnpl_cac` | `Rabbit Risk Analytics\Buy Now Pay Later\bnpl_cac.csv` | 25 | 2026-06-10 |

Raíz del Drive: `D:\Shared drives\Data Room - BI & Data Analytics\`.

### Recargarlos

```powershell
# Siempre primero: valida columnas y tipos sin escribir nada
.venv\Scripts\python.exe carga_archivos_bnpl.py --dry-run

# Los cuatro
.venv\Scripts\python.exe carga_archivos_bnpl.py

# Uno solo
.venv\Scripts\python.exe carga_archivos_bnpl.py --solo bnpl_cac
```

El DDL, el `TRUNCATE` y la carga van **en una sola transacción**: una corrida fallida no deja tablas
a medias. Si al archivo le falta una columna, el script se detiene y te dice cuáles trae.

No hace falta correr `build_bnpl.py` después: las cuatro vistas de `pbi_bnpl` leen la tabla, así que
el dato nuevo aparece en el siguiente refresh de Power BI.

### Cómo sé si están viejos

Dos preguntas distintas:

**¿Riesgo/negocio publicó una versión nueva?** Compara la fecha del archivo en el Drive contra la
tabla de arriba:

```powershell
Get-ChildItem "D:\Shared drives\Data Room - BI & Data Analytics\Rabbit Risk Analytics\Buy Now Pay Later" `
  -Recurse -Filter *.csv | Select-Object LastWriteTime, Length, FullName
```

**¿Lo que está cargado coincide con el archivo?** `--dry-run` imprime las filas del CSV sin escribir;
compáralas contra la base:

```sql
select 'odds_combinations' t, count(*) from archivos_bnpl.odds_combinations
union all select 'atr_combinations_iv',      count(*) from archivos_bnpl.atr_combinations_iv
union all select 'ps_transactional_profile', count(*) from archivos_bnpl.ps_transactional_profile
union all select 'bnpl_cac',                 count(*) from archivos_bnpl.bnpl_cac;
```

Si los conteos difieren, el archivo cambió y no se ha recargado.

> **Cuándo se cargó cada archivo:** desde el 2026-08-14, las dos cargas manuales sí escriben en
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

### El Excel del concurso

`bnpl.bnpl_clientes_concurso` (51,294 filas) es la única tabla de `bnpl` cuyos **datos** no salen del
pipeline: el universo de lanzamiento y la línea de crédito los pone negocio en
`BBDD tablero BNPL LANZAMIENTO.xlsx`. `build_bnpl.py` sí aplica su DDL en cada corrida —`CREATE TABLE`
/ `CREATE INDEX IF NOT EXISTS`, para que una VM limpia tenga la tabla— pero **nunca toca sus datos**.
Mismo patrón que los CSV: `--dry-run` primero, transacción única.

```powershell
.venv\Scripts\python.exe carga_clientes_concurso.py --dry-run
.venv\Scripts\python.exe carga_clientes_concurso.py
```

**Ojo:** si alguien corre `build_bnpl.py --rebuild` con un `DROP SCHEMA bnpl CASCADE` de por medio,
esta tabla se va con él y hay que recargarla. Las 11 matviews se rehacen solas; ésta no.

---

## Verificar una corrida

### 0. ¿La tarea disparó?

Primero desde el lado del Task Scheduler, que es lo único que sabe si el `.bat` arrancó:

```powershell
Get-ScheduledTaskInfo -TaskName "BNPL Pipeline" | Select-Object LastRunTime, LastTaskResult, NextRunTime
Get-Content logs\scheduler.log -Tail 20
```

| `LastTaskResult` | Significa |
|---|---|
| `0` | el `.bat` terminó con código 0: los seis pasos corrieron |
| `1` | `main.py` devolvió 1 — revisa `modo` en `etl_runs` y el traceback del log |
| `267009` | sigue corriendo (`0x00041301`) |
| `267011` | la tarea nunca se ha ejecutado (`0x00041303`) |

> **Las dos horas no coinciden y las dos están bien.** `LastRunTime` y `NextRunTime` salen del reloj
> del SO, que en esta VM es **UTC**; el log y `bnpl_ops.etl_runs` van en **hora México**, porque
> `main.py` los ancla con `TZ_OFFSET_HOURS`. La misma corrida se lee `07:28` en el Task Scheduler y
> `01:28` en `pipeline_2026-08.log`: son seis horas de diferencia, no dos corridas.

### 1. ¿Terminó?

```sql
select started_at, modo, round(segundos/60.0, 1) as minutos
from bnpl_ops.etl_runs where tabla = 'pipeline'
order by started_at desc limit 5;
```

| `modo` | Significa |
|---|---|
| `ok` | los seis pasos terminaron |
| `abortado_frescura` | una fuente crítica estaba en CRIT; **no se cargó nada** |
| `error` | reventó a media corrida. El traceback está en `logs/pipeline_YYYY-MM.log` |

Si `minutos` da ~17 en vez de ~20, revisa que el paso 3 haya corrido las **seis** tablas.

#### Si el modo es `error`

El traceback dice **dónde** reventó; esta tabla dice **en qué estado quedó la base**, que no es lo
mismo y es lo que decide qué hay que correr:

| Falló en | Qué quedó en la base | Volver a correr | Qué correr |
|---|---|---|---|
| 1/6 frescura | nada, salvo lo que se escribió en `bnpl_ops` | sí | `main.py` |
| 2/6 staging Mongo | **la tabla conserva la carga anterior**: el `TRUNCATE`/`DELETE` va en la misma transacción que el COPY y corre *después* de que la extracción trajo datos (`etl_mongo_to_postgres.py:429-452`). Si Mongo devuelve cero, la etapa aborta sin tocar el staging. Las tablas anteriores quedaron completas | sí, es idempotente | ver el recuadro de abajo |
| 3/6 Redshift | nada a medias: DDL + `TRUNCATE` + carga van en **una transacción por tabla** (`etl_redshift_to_postgres.py:320-323`). La que falló conserva el dato anterior | sí | `etl_redshift_to_postgres.py --solo <tabla>` |
| 4/6 capa de negocio, **sin** `--rebuild` | nada: `REFRESH MATERIALIZED VIEW` es una sola sentencia; si falla, la matview conserva su contenido anterior | sí | `build_bnpl.py --solo <vista>` |
| 4/6 capa de negocio, **con** `--rebuild` | **la vista que falló ya no existe, y las que dependían de ella tampoco**: cada `.sql` abre con `DROP MATERIALIZED VIEW … CASCADE` | sí, pero **nunca con `--solo`** | `build_bnpl.py --rebuild` completo |
| 4/6 vistas de `pbi_bnpl` | **sólo la que falló queda fuera**: hay un `try/except` por vista, así que las demás sí se crean y `sql/16_pbi_grants.sql` se reaplica al final. La corrida **falla igual**, con el `raise` después de los grants; el refresh de Power BI va a fallar en esa tabla | sí | `build_bnpl.py` sin flags: rehace las 19 al final |
| 5/6 calidad · 6/6 frescura | solo `bnpl_ops`. El tablero ya quedó cargado | sí | `ops\quality_checks.py` · `ops\check_freshness.py` |

> **El caso que hay que mirar dos veces: `credit_order_production`.** Es la única colección en modo
> ventana (`etl_mongo_to_postgres.py:58`). Si el pipeline murió durante su recarga completa mensual,
> la transacción se revirtió y la tabla **conserva la carga anterior**; en `etl_runs` no queda fila
> `modo='full'` de ese intento. Eso juega a favor: `_decidir_modo` vuelve a ver
> `dias >= FULL_CADA_DIAS` y **rehace la recarga completa sola**, tanto desde `main.py` como desde
> `etl_mongo_to_postgres.py --solo credit_order_production` — los dos caminos ejecutan el mismo
> código, `main.py` no hace nada más que pasar el flag.
>
> Si lo que quieres es garantizar que el reintento sea completo y no la ventana de 60 días —por
> ejemplo, porque el full que murió lo habías forzado tú con `--full` teniendo uno exitoso de hace
> menos de 30 días— cuesta lo mismo y no falla nunca:
>
> ```powershell
> .venv\Scripts\python.exe etl_mongo_to_postgres.py --solo credit_order_production --full
> ```

**Antes de re-correr, mira qué falta**; no repitas 20 minutos a ciegas:

```sql
-- deben salir 46 tablas con started_at de hoy
select distinct on (tabla) tabla, started_at, modo, filas
from bnpl_ops.etl_runs where tabla <> 'pipeline'
order by tabla, started_at desc;

-- deben ser 19
select count(*) from information_schema.views where table_schema = 'pbi_bnpl';
```

**Casi siempre sale más barato re-correr el paso que el pipeline**: `main.py` completo vuelve a bajar
Mongo (~14 min); si lo que falló fue el paso 4, `build_bnpl.py` son 85 segundos. `--sin-redshift`
reprocesa sin volver a pagar los 3.5 min de Redshift.

**Si el refresh ya corrió sobre una base a medias**, el tablero muestra números incompletos y no lo
dice. Arregla la base y dispara un refresh a mano desde el Service.

### 2. ¿Cargó todo?

```sql
select distinct on (tabla) tabla, started_at, modo, filas, segundos
from bnpl_ops.etl_runs
where tabla <> 'pipeline'
order by tabla, started_at desc;
```

Deben aparecer **46 tablas** con `started_at` de hoy: 10 de `mongo_bnpl`, 6 de `redshift_bnpl`, 11 de
`bnpl` y las 19 vistas de `pbi_bnpl`, que desde el 2026-08-14 también dejan bitácora (entran con
`modo = 'vista'` y `filas` en nulo: son DDL, no carga). Cada fila trae además `commit_sha` —el commit
del repo que produjo esa carga, con sufijo `+sucio` si había cambios sin commitear— y `sql_sha256`,
el hash del `.sql` que definió el objeto: eso es lo que permite saber *qué* definición corrió el día
que el tablero salga raro.

### 3. ¿Las fuentes están al día?

```sql
select * from bnpl_ops.v_freshness_status;   -- estado actual, lo crítico primero
select * from bnpl_ops.v_quality_alerts;     -- solo lo que está en alerta
```

`semaforo_fuente` mide si **Mongo** sigue recibiendo datos; `semaforo_staging`, si **el staging** está
al día con Mongo.

| Semáforo | Significa | Qué hacer |
|---|---|---|
| `OK` | menos de 24 h sin escrituras | nada |
| `WARN` | entre 24 y 48 h | vigilar; puede ser normal en colecciones de baja frecuencia |
| `CRIT` en fuente | más de 48 h sin escrituras en Mongo | **es de ingeniería, no del pipeline**: la fuente dejó de alimentarse. Abre ticket a {{EQUIPO_ING}} y agrégala a *Incidencias abiertas con las fuentes* |
| `CRIT` en staging | falta más del 1% de los documentos | correr el ETL; si persiste, `--full` |
| `FALTA` | la tabla no existe en el staging | correr el ETL |

Para saber **desde cuándo** una fuente dejó de actualizarse, `bnpl_ops.freshness_history` guarda una
fila por colección por corrida.

**Los 24 chequeos de calidad.** `ops/quality_checks.py` corre 24: **9 sobre el staging** y **15
identidades entre capas**. Hoy solo dos están en alerta. El canal de revisión es **la vista, no el
log**: `bnpl_ops.v_quality_alerts` pone los CRIT hasta arriba.

Los nueve del staging:

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

Las quince identidades entre capas — las mismas de [¿Cuadran los conteos?](#4-cuadran-los-conteos),
que desde el 2026-08-14 ya no se copian y pegan a mano. Cada una mide `filas de más o de menos`
contra su regla, así que **0 es lo único que cuenta como OK**:

| Check | Sev | Regla |
|---|---|---|
| `identidad_grouped_orders` | CRIT | `pbi_bnpl.bnpl_grouped_orders` = `bnpl.grouped_orders` |
| `identidad_loss_rates` | CRIT | `pbi_bnpl.bnpl_loss_rates` = `bnpl.loss_rates` |
| `identidad_revenue_comision` | CRIT | `bnpl.revenue_comision` = `bnpl.loss_rates` |
| `identidad_bnpl_par` | CRIT | `pbi_bnpl.bnpl_par` = `bnpl.par_snapshot` |
| `identidad_months_closes` | CRIT | `pbi_bnpl.months_closes` = `bnpl.par_snapshot` |
| `identidad_vintage_analysis` | CRIT | `pbi_bnpl.vintage_analysis` = `bnpl.vintage_analysis` |
| `identidad_dim_ruta_actual` | CRIT | `bnpl.dim_ruta_actual` = `redshift_bnpl.estructura_comercial` |
| `identidad_dim_ruta_cliente_scd` | CRIT | `bnpl.dim_ruta_cliente_scd` = `redshift_bnpl.ruta_cliente_scd` |
| `identidad_cosechas_agg` | CRIT | `pbi_bnpl.bnpl_cosechas_agg` = `redshift_bnpl.cosechas_agg` |
| `identidad_seasonality_delta` | CRIT | `pbi_bnpl.seasonality_delta` = `redshift_bnpl.estacionalidad_mes` × 11 |
| `identidad_grid_bnpl` | WARN | `pbi_bnpl.grid_bnpl` = `bnpl.grid_bnpl` − 71 — el delta está explicado abajo, pero **puede moverse** |
| `identidad_odds_combinations` · `_atr_combinations_iv` · `_ps_transactional_profile` · `_bnpl_cac` | WARN | cada vista de `pbi_bnpl` = su tabla de `archivos_bnpl`. Son carga manual: desfasarse es normal hasta que alguien recargue |

**Una identidad CRIT que no cuadra cuesta la corrida.** `main.py` las mira aparte del resto: si
alguna sale `ALERTA` —o `NO_APLICABLE`, que es lo mismo, porque una identidad que no se pudo medir
tampoco está comprobada— el pipeline **termina los seis pasos**, registra
`modo = 'ok_identidades_rotas'` en `bnpl_ops.etl_runs` y **sale con código 1** para que el Task
Scheduler lo marque como fallido. Un pipeline que devuelve 0 con una capa a medias es un pipeline
que miente.

Un chequeo cuya tabla o columna no exista sale como `NO_APLICABLE`, no como OK: eso significa que a
la extracción le falta un campo.

**Los dos marcados como ruido conocido son los únicos que hoy están abiertos. Cualquier otro que
aparezca es nuevo y hay que revisarlo**, empezando por su historia:

```sql
select * from bnpl_ops.v_quality_alerts;
select checked_at, n_filas from bnpl_ops.data_quality_checks
where check_name = '<el que salió>' order by checked_at desc limit 30;
```

### 4. ¿Cuadran los conteos?

Esto es lo que de verdad dice si la corrida quedó bien. Cada fila es una identidad que **debe**
cumplirse; si no se cumple, algo se quedó a medias entre dos capas.

Desde el 2026-08-14 **ya no hay que copiar y pegar nada**: las 15 identidades corren solas en el paso
[5/6] como los chequeos `identidad_*` de `ops/quality_checks.py` y quedan con su historia en
`bnpl_ops.data_quality_checks`. El SQL de abajo se queda como referencia para revisarlas a mano. Si
una identidad **CRIT** no cuadra —o no se puede medir— el pipeline sale con código 1 y registra
`modo = 'ok_identidades_rotas'` en `bnpl_ops.etl_runs`.

```sql
select 'grouped_orders'  as par, (select count(*) from bnpl.grouped_orders) as origen,
       (select count(*) from pbi_bnpl.bnpl_grouped_orders)                  as destino
union all select 'loss_rates',   (select count(*) from bnpl.loss_rates),
       (select count(*) from pbi_bnpl.bnpl_loss_rates)
union all select 'revenue_comision', (select count(*) from bnpl.loss_rates),
       (select count(*) from bnpl.revenue_comision)
union all select 'par_snapshot -> bnpl_par', (select count(*) from bnpl.par_snapshot),
       (select count(*) from pbi_bnpl.bnpl_par)
union all select 'par_snapshot -> months_closes', (select count(*) from bnpl.par_snapshot),
       (select count(*) from pbi_bnpl.months_closes)
union all select 'vintage_analysis', (select count(*) from bnpl.vintage_analysis),
       (select count(*) from pbi_bnpl.vintage_analysis)
union all select 'grid_bnpl (-71)', (select count(*) from bnpl.grid_bnpl),
       (select count(*) from pbi_bnpl.grid_bnpl)
union all select 'estructura -> dim_ruta_actual', (select count(*) from redshift_bnpl.estructura_comercial),
       (select count(*) from bnpl.dim_ruta_actual)
union all select 'scd -> dim_ruta_cliente_scd', (select count(*) from redshift_bnpl.ruta_cliente_scd),
       (select count(*) from bnpl.dim_ruta_cliente_scd)
union all select 'cosechas_agg', (select count(*) from redshift_bnpl.cosechas_agg),
       (select count(*) from pbi_bnpl.bnpl_cosechas_agg)
union all select 'estacionalidad (x11)', (select count(*) from redshift_bnpl.estacionalidad_mes),
       (select count(*) from pbi_bnpl.seasonality_delta)
union all select 'odds_combinations', (select count(*) from archivos_bnpl.odds_combinations),
       (select count(*) from pbi_bnpl.odds_combinations)
union all select 'atr_combinations_iv', (select count(*) from archivos_bnpl.atr_combinations_iv),
       (select count(*) from pbi_bnpl.atr_combinations_iv)
union all select 'ps_transactional_profile', (select count(*) from archivos_bnpl.ps_transactional_profile),
       (select count(*) from pbi_bnpl.ps_transactional_profile)
union all select 'bnpl_cac', (select count(*) from archivos_bnpl.bnpl_cac),
       (select count(*) from pbi_bnpl.bnpl_cac);
```

Medido el 2026-08-14:

| Par | Regla | Origen | Destino |
|---|---|---:|---:|
| `grouped_orders` | iguales | 99,019 | 99,019 |
| `loss_rates` · `revenue_comision` | iguales | 92,009 | 92,009 |
| `par_snapshot` → `bnpl_par` · `months_closes` | iguales | 1,061,120 | 1,061,120 |
| `vintage_analysis` | iguales | 530 | 530 |
| **`grid_bnpl`** | **destino = origen − 71** | 146,613 | 146,542 |
| `estructura_comercial` → `dim_ruta_actual` | iguales | 611,212 | 611,212 |
| `ruta_cliente_scd` → `dim_ruta_cliente_scd` | iguales | 13,893 | 13,893 |
| `cosechas_agg` | iguales | 51,721 | 51,721 |
| `estacionalidad_mes` → `seasonality_delta` | destino = origen × 11 | 12 | 132 |
| las 4 de `archivos_bnpl` | iguales | 84,986 / 468 / 100,793 / 25 | idem |

**El −71 de `grid_bnpl` es correcto y tiene que estar.** Son 70 registros fantasma cuyo
`netsuite_id` sólo difiere por espacios (`' 351229'` vs `'351229'`) más 1 con el id vacío. En
PostgreSQL el índice único los deja convivir porque la columna es `text`; al pasar a `bigint` para
Power BI colapsan, y Power BI **no admite blancos ni duplicados** en el lado "uno" de una relación —
y de esa columna cuelgan cinco. Por eso la consulta 06 lleva un `DISTINCT ON`. Las 70 filas están
vacías (0 órdenes, 0 enroladas, sin ruta, sin `shopName`) y cada una tiene su gemela buena. Si algún
día el delta deja de ser 71, revisa `analisis/unicidad_llaves.py` antes de dar el número por bueno.

Dos deltas más que **no** son constantes y por eso no sirven como check:

| Par | Delta hoy | Qué lo explica |
|---|---:|---|
| `bnpl.loss_rates` → `pbi_bnpl.loans_matured_default_profile` | −1,747 | los créditos que aún no vencen. Cambia todos los días. |
| `redshift_bnpl.ventas_cliente` → `pbi_bnpl.overall_prev_post_bnpl_sales` | −648 | ventas de clientes del universo BNPL sin `bnpl_enrolled_at` (aprobados que nunca compraron a crédito). |

### 5. ¿Cuánto le va a costar a Power BI leer esto?

El refresh lee las 19 vistas completas. Costo del lado del servidor, medido con `EXPLAIN ANALYZE`
(no incluye transferencia ni compresión del modelo):

| Vista | s | | Vista | s |
|---|---:|---|---|---:|
| `overall_prev_post_bnpl_sales` | 8.7 | | `odds_table` | 1.0 |
| `months_closes` | 5.5 | | `vars_and_iv` | 0.8 |
| `bnpl_par` | 5.2 | | `grid_bnpl` | 0.7 |
| `loans_matured_default_profile` | 4.0 | | `bnpl_grouped_orders` | 0.3 |
| `bnpl_audiencia_agg` | 3.5 | | `bnpl_loss_rates` | 0.2 |
| `concurso_base` | 2.1 | | las otras 7 | < 0.1 |
| | | | **total** | **32.0 s** |

Si algún día eso se aprieta contra la ventana de refresh, las tres pesadas se materializan cambiando
`CREATE VIEW` por `CREATE MATERIALIZED VIEW` en `sql/15_pbi_vistas.sql` y agregándolas al refresh.
Hoy no hace falta.

---

## Requisitos

- Python 3.11+ con el venv del proyecto (`.venv/`).
- Librerías internas instaladas como editable desde `Documents/Funciones/`:
  `mongo_extractor`, `redshift_extractor` y `postgresql_extractor_uploader` (que instala el
  paquete `postgres_local_client`). **Toda extracción va por ellas**, no con clientes propios.
- Credenciales AWS para el túnel SSM de Mongo (perfil `bnpl` en `.env.mongo_extractor`).
- Acceso al Drive compartido montado en `D:\Shared drives\` (sólo para las dos cargas manuales).
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

**El proyecto ya no arma la conexión a PostgreSQL.** No lee `BD_ENGINE_RABBIT_LOCAL` ni llama a
`create_engine`: todo el acceso pasa por `postgres_local_client`, que resuelve host, credenciales
y schema desde su propio `.env.postgres_local_client`. Cada llamada declara su alias con `db=`, sin
depender de `DEFAULT_DB`. Los alias que usa el pipeline:

| Alias | Para qué |
|---|---|
| `mongo_bnpl` / `mongo_bnpl_rw` | leer y escribir el staging |
| `bnpl` / `bnpl_rw` | leer y construir la capa de negocio, `pbi_bnpl` y `archivos_bnpl` |
| `bnpl_ops` / `bnpl_ops_rw` | frescura, calidad y bitácora |
| `redshift_bnpl_rw` | escribir la estructura comercial |

Los `_rw` son los únicos con escritura y `ALLOW_DDL`; los demás rechazan cualquier DML/DDL.

> `bnpl_rw` es el alias que crea los tres schemas (`bnpl`, `pbi_bnpl`, `archivos_bnpl`). No hay un
> alias por schema: los tres los escribe el mismo rol.

> **Hay un `.env` en la raíz y no es de este proyecto.** Trae tres URIs `postgresql+psycopg2://` con
> usuario y contraseña: `BD_ENGINE_RABBIT_LOCAL`, `BD_ENGINE_RABBIT_LOCAL_SOPORTE` y
> `BD_ENGINE_RABBIT_LOCAL_PBI` — las tres apuntan a la misma base, `localhost:9553/rabbit-bi-local`.
> **Ningún script del pipeline lo lee.** Lo genera `postgresql_extractor_uploader` desde el alias
> `local_rw` de su propio `.env.postgres_local_client`, así que se regenera solo si lo borras — de
> hecho se regeneró durante la auditoría del 2026-08-14 y le apareció la tercera variable. Está en
> `.gitignore:2-3` y nunca se commiteó (verificado con `git log --all --diff-filter=A -- .env`).
> Resumen: no hay que crearlo, no hay que mantenerlo y no hay que commitearlo; si esa contraseña se
> rota, este archivo queda viejo y da igual.

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

## Las tablas de la capa de negocio

| Vista | Grano | Para qué |
|---|---|---|
| `bnpl.dim_ruta_actual` | cliente | ruta, supervisor y oficina **vigentes** |
| `bnpl.dim_ruta_cliente_scd` | cliente × tramo | ruta **histórica**, como intervalos de vigencia |
| `bnpl.grouped_orders` | cliente + sales order + order_id + estatus + canal | base: cohort, índice de pedido, entrega. **No** es 1 fila por sales order |
| `bnpl.loss_rates` | orden entregada | morosidad (PAR), días de atraso, revenue |
| `bnpl.par_snapshot` | orden × corte mensual | auditar de dónde sale cada tasa del vintage |
| `bnpl.vintage_analysis` | cohort × mes de maduración | evolución del PAR por cohort |
| `bnpl.grid_bnpl` | cliente | maestro: embudo, conteos, revenue por cliente |
| `bnpl.kpis_daily` | día | serie diaria sin huecos, con acumulados y tasas |
| `bnpl.revenue_comision` | orden | el ingreso del producto, orden por orden |
| `bnpl.corte_venta_sku` / `_so` | SKU / sales order | corte semanal, ventana de 8 días desde jueves |
| `bnpl.bnpl_clientes_concurso` | cliente | tabla física, carga manual. `build_bnpl.py` aplica su DDL, **no sus datos**. |

`build_bnpl.py --rebuild` reconstruye las vistas desde los `.sql` (usar al cambiar la lógica);
sin flags solo las refresca. El refresh es completo, no incremental, **y tiene que serlo**: un pago
puede llegar 519 días tarde, así que el PAR de un mes cerrado cambia retroactivamente.

Las reglas de negocio (plazo del crédito, 14.2% de comisión, interés moratorio, exención del primer
pedido, buckets PAR) viven como funciones en `sql/02_bnpl_funciones.sql`, no incrustadas en cada
vista. Cambiar una regla es cambiar una función y refrescar.

El orden de `CAPAS` en `build_bnpl.py` es el de **dependencia**, no el del número de archivo: las
dims de ruta están en el `11_` pero se construyen primero porque `grouped_orders` las lee.

## Las tablas que vienen de Redshift

| Tabla | Grano | Filas | Alimenta |
|---|---|---:|---|
| `redshift_bnpl.estructura_comercial` | cliente (toda la base) | 611,212 | `bnpl.dim_ruta_actual` — el grid necesita ruta para todos, no sólo los que tienen crédito |
| `redshift_bnpl.route_mapping` | ruta | 340 | catálogo ruta → equipo, oficina, región |
| `redshift_bnpl.ruta_cliente_scd` | cliente × tramo | 13,893 | `bnpl.dim_ruta_cliente_scd` — la ruta histórica |
| `redshift_bnpl.ventas_cliente` | cliente × sales order | 1,294,006 | `overall_prev_post_bnpl_sales`, `loans_matured_default_profile` |
| `redshift_bnpl.cosechas_agg` | mes × cohorte × flag BNPL | 51,721 | `bnpl_cosechas_agg` |
| `redshift_bnpl.estacionalidad_mes` | mes calendario | 12 | `seasonality_delta` (12 × 11 = 132 pares) |

Las tres últimas son los **pasos nuevos**. Lo que hay que saber de ellas:

- **`ventas_cliente` es venta Rabbit COMPLETA, no sólo BNPL.** Es lo que la capa BNPL no puede saber
  por sí sola: qué compró el tendero fuera del crédito. De ahí sale `fraudFlag` en el tablero y la
  comparación antes/después de enrolarse. Alcance: el universo BNPL (clientes con orden o con
  aprobación), **desde 2021-04-01** — no seis meses antes del primer crédito, porque el CSV original
  llega a 57 meses antes del enrolamiento y con una ventana corta esa comparación se queda sin lado
  izquierdo.
- **`cosechas_agg` y `estacionalidad_mes` se agregan EN Redshift**, no aquí. Al grano de cliente × mes
  son decenas de millones de filas; lo que baja son 51,721 y 12.
- **`estacionalidad_mes` se calcula sobre TODA la base Rabbit**, no sobre el universo BNPL. Medido:
  la estacionalidad de los clientes con crédito no representa a la del negocio — 6.8% de error en
  ticket, 9.5% en volumen, correlación de apenas 0.66.
- **Hay un escalón en enero-2025 y es deliberado.** Las tablas `mv_pedidos_enriquecidos_*` no son
  homogéneas: 2021–2024 sólo tienen `monto_venta`; las `_v2` de 2025–2026 traen el desglose
  `amount_completed` / `amount_in_progress`. Se usa el desglose donde existe y `monto_venta` antes.
- **Diciembre-2023 va dividido entre 20.** `mv_pedidos_enriquecidos_2023` lo trae inflado ~25x en
  monto y en piezas. Es un parche sobre datos corruptos, no un cálculo: cuando se corrija la fuente
  hay que quitar el `/ 20.0` de `_bloques_pedidos()`. Ver `PENDIENTES_NEGOCIO.md`.
- **El SCD se comprime en Redshift.** La vigencia diaria son 301M filas y para el universo BNPL 5.3M;
  comprimida por cambio de ruta baja a ~13.9K. Traer 5.3M filas por el túnel para comprimirlas
  después sería absurdo.

## Modos del ETL de Mongo

| Comando | Qué hace | Cuándo |
|---|---|---|
| (sin flags) | Ventana de 60 días en `credit-order` + recarga completa del resto | corrida diaria |
| `--full` | Recarga completa de todo por TRUNCATE (preserva DDL e índices) | se dispara solo cada 30 días |
| `--recrear` | DROP y recrea desde `sql/01_staging.sql` | al cambiar la proyección, **actualizando ese `.sql` primero** |
| `--solo col1,col2` | Solo esas colecciones o tablas | recargas puntuales; evita los ~20 min de `credit-order` |

**Tiempos esperados**: la corrida diaria del staging tarda ~14 min y la recarga completa entre 20 y
40. La variación es del túnel SSM, no del pipeline.

### Por qué una ventana y no un incremental

Un incremental por `_id` solo vería inserciones y perdería los cambios de estado — una orden pasa de
`CREATED` a `COMPLETED` y se le llena `deliveryAt` al entregarse. Medido sobre el histórico: una orden
se entrega **a más tardar 17 días** después de creada, así que reprocesar 60 días da 3.5x de margen y
baja el 8% de las filas en vez del 100%.

Lo que la ventana no cubre son las órdenes que quedaron en estado no final hace más tiempo (~225
sales orders atascados). Esas se re-extraen dirigidas por `salesOrderId` en la misma llamada.

> Al 2026-08-14, `fintech-customers-production` lleva **513 h** en CRIT: dejó de recibir escrituras
> el 2026-07-22. Reportado a {{EQUIPO_ING}} el {{FECHA}}, ticket {{TICKET}}, lo lleva {{NOMBRE}}.
> Impacto: los clientes enrolados desde entonces no tienen `shopName` ni teléfono. El seguimiento va
> en *Dueño, escalamiento y SLA → Incidencias abiertas con las fuentes*; si esa fila no se actualiza,
> nadie lo está siguiendo.

## Power BI

El modelo productivo es **`pbi_new/`**, y es el que está publicado: sus 17 tablas leen de `pbi_bnpl`,
sin un solo `Csv.Document`, sin `SharePoint.Files`, sin `Table.TransformColumnTypes`, sin
`excludeFromModelRefresh` y sin `Consulta1`. Refresca desde el Service por `Gateway_BI`.
(`concurso_base` no está en el modelo: es un tablero aparte, con su propio modelo ya publicado.)

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

### El gateway — configurado el 2026-08-14

El origen de Power Query apunta a `localhost:9553` y el gateway corre **en la misma VM**, así que el
refresh sale desde el Service sin exponer PostgreSQL a la red.

| Pieza | Valor |
|---|---|
| Gateway | `Gateway_BI` — ya existía y sirve otros tableros; no hubo que instalar ni registrar nada |
| Conexión | `rabbit-bi-local` → tipo PostgreSQL, servidor `localhost:9553`, base `rabbit-bi-local` |
| Credencial | Básica, rol `pbi_gateway`: solo lectura y solo sobre `pbi_bnpl` |
| Conexión cifrada | **desmarcada** — el servidor tiene `ssl = off` |
| Actualización programada | **08:30 CDMX** (movida de las 07:00 el 2026-08-14), 8 h después del cierre normal de la corrida de medianoche — ver [Despliegue a la VM](#despliegue-a-la-vm) |

El driver (Npgsql 4.0.10) viene empaquetado con el gateway; no se instala aparte. Y como gateway y
PostgreSQL comparten máquina, la conexión es loopback: no hay tráfico que un TLS pudiera proteger.

Lo único manual del rol es crearlo, porque lleva contraseña:

```sql
CREATE ROLE pbi_gateway LOGIN PASSWORD '<en el gestor de contraseñas>';
```

**Sus permisos no son manuales.** Viven en [`sql/16_pbi_grants.sql`](sql/16_pbi_grants.sql) y
`build_bnpl.py` los aplica al final de cada corrida, después del `DROP` + `CREATE` de las vistas.
Antes eran cuatro líneas que se corrían una vez al configurar, y ése era el problema: este rol pierde
sus permisos solo, de tres maneras distintas, y las tres ya rompieron el refresh.

**1. El `DROP VIEW` se lleva el `GRANT`.** `build_bnpl.py` recrea las 19 vistas en cada corrida y un
`GRANT` vive pegado al objeto. El archivo pone las default privileges — para que las vistas nuevas
nazcan legibles — y además un `GRANT SELECT` explícito, que repara el caso de una vista recreada a
mano fuera del pipeline. El `FOR ROLE` tiene que nombrar al dueño de las vistas, no al usuario que
ejecuta el pipeline; se lee del catálogo en vez de escribirse, para que no deje de aplicar en
silencio si algún día cambia.

**2. Las funciones se cobran al que consulta.** Ésta es la que falló el 2026-08-14, con
`42501: permission denied for schema bnpl` — un schema que el modelo no menciona en ninguna de sus 17
consultas. Que una vista lea sus **tablas** con los privilegios del dueño es cierto, y por eso
`pbi_gateway` no necesita `SELECT` sobre `bnpl`. Con las **funciones** no aplica: PostgreSQL las cobra
al que consulta ([`CREATE VIEW`](https://www.postgresql.org/docs/current/sql-createview.html) →
*Notes*). Y seis vistas llaman funciones de `bnpl`:

| Vista | Funciones que invoca |
|---|---|
| `bnpl_audiencia_agg` | `bnpl.estados_activacion()`, `bnpl.hoy_mx()` |
| `loans_matured_default_profile` | `bnpl.ahora_mx()`, `bnpl.dias_credito()` |
| `odds_table` | `bnpl.ahora_mx()` |
| `overall_prev_post_bnpl_sales` | `bnpl.estados_activacion()` |
| `vars_and_iv` | `bnpl.ahora_mx()` |
| `concurso_base` | `bnpl.estados_activacion()` (la consume el tablero del concurso, no el de `pbi_new/`) |

Cinco de ésas son tablas del modelo, y basta una para tumbar el refresh completo.

Los schemas a los que se da `USAGE` **no van escritos** en el archivo: se leen de `pg_depend`, que
registra qué función usa cada vista. Si mañana una consulta de `sql/pbi/` empieza a llamar una función
de otro schema, el `USAGE` sale en la siguiente corrida sin que nadie toque nada. Eso es lo que evita
que el error vuelva — lo que hay que mantener no es una lista, es nada.

`USAGE` **no da lectura**: sólo permite resolver nombres dentro del schema. El `EXECUTE` de las 16
funciones no se otorga porque en PostgreSQL nace en `PUBLIC`; si algún día se le revoca a `PUBLIC`,
hay que agregar un `GRANT EXECUTE ON ALL FUNCTIONS`.

**3. Un modelo que lee `bnpl` directo.** El tablero del concurso —otro modelo, no el de `pbi_new/`—
apunta a `bnpl.bnpl_clientes_concurso` y `bnpl.dim_ruta_actual` sin pasar por `pbi_bnpl`, así que
necesita `SELECT` explícito sobre las dos. Falló así el 2026-08-14 a las 14:28, con
`42501: permission denied for table bnpl_clientes_concurso`: nueve segundos, antes de leer una fila.

Ese par va en el arreglo `directos` del archivo y **no en un `GRANT` corrido a mano**, porque
`sql/11_bnpl_dim_ruta.sql` hace `DROP MATERIALIZED VIEW … CASCADE`: un permiso suelto aguanta los
refreshes diarios y desaparece en el próximo `--rebuild`. Es la única lista escrita a mano del
archivo, y tiene que serlo: la dependencia vive en un modelo de Power BI, no en `pg_depend`.

Así que hoy `pbi_gateway` lee las 19 vistas de `pbi_bnpl` y **2 de las 12** tablas de `bnpl`. Si
alguna vez el tablero se repunta a `pbi_bnpl.concurso_base` y `pbi_bnpl.concurso_clientes` (esa vista
ya existe, sin consumir), se borra el bloque y el rol vuelve a ver únicamente `pbi_bnpl`.

Para aplicarlos sin esperar una corrida completa:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -h localhost -p 9553 -U russell_quiroz `
  -d rabbit-bi-local -f sql\16_pbi_grants.sql
```

Cuando algo falle en el refresh, empieza por
[`sql/pbi/README.md` → Cuando falla el refresh](sql/pbi/README.md#cuando-falla-el-refresh).

## Despliegue a la VM

El pipeline está pensado para correr desatendido en una VM. En orden:

**1. Preparar la máquina**

```powershell
git clone https://github.com/russellquiroz-spec/buy_now_pay_later.git
cd buy_now_pay_later
python -m venv .venv
.venv\Scripts\python.exe -m pip install pandas python-dotenv openpyxl matplotlib seaborn
```

`pandas` y `matplotlib` son para los scripts de análisis; `openpyxl` lo necesita
`carga_clientes_concurso.py` para leer el Excel; `seaborn` **no lo usa el pipeline** sino los 9
visuales de Python del tablero (ver *Requisitos*), y se instala aquí para que el venv que apunte
Power BI Desktop ya lo traiga. El resto de las dependencias (SQLAlchemy, psycopg, sshtunnel) las
arrastran las librerías internas del paso 2.

**2. Instalar las librerías internas** (editable, desde donde estén en la VM):

```powershell
.venv\Scripts\python.exe -m pip install -e <ruta>\mongo_extractor
.venv\Scripts\python.exe -m pip install -e <ruta>\redshift_extractor
.venv\Scripts\python.exe -m pip install -e <ruta>\postgresql_extractor_uploader
```

**3. No hay `.env` que crear en la raíz.** Cada librería lee el suyo (`.env.mongo_extractor`,
`.env.redshift_extractor`, `.env.postgres_local_client`), que debe existir en la VM con el perfil
correspondiente. Si ves un `.env` en la raíz, no lo creaste tú y no lo mantienes tú: lo genera
`postgresql_extractor_uploader` y ningún script del pipeline lo lee — ver *Requisitos*. Ninguno de
los tres se versiona, y los alias que el pipeline nombra tienen que existir con esos nombres
exactos, o la primera llamada falla con `ConfigError` diciendo cuáles hay disponibles.

**4. Verificar los accesos antes de programar nada.** Es donde suele fallar:

```powershell
.venv\Scripts\python.exe ops\check_freshness.py
```

Si eso corre, la VM tiene lo que necesita: túnel SSM a Mongo (AWS CLI + Session Manager plugin +
credenciales del rol), Redshift y PostgreSQL.

**5. Programar la tarea diaria** — hecho el 2026-08-14. Así quedó registrada:

```powershell
$raiz = "C:\Users\Administrator\Documents\Proyectos\buy_now_pay_later"
Register-ScheduledTask -TaskName "BNPL Pipeline" -Force `
  -Action    (New-ScheduledTaskAction -Execute "$raiz\run_pipeline.bat" -WorkingDirectory $raiz) `
  -Trigger   (New-ScheduledTaskTrigger -Daily -At "06:00") `
  -Principal (New-ScheduledTaskPrincipal -UserId "$env:COMPUTERNAME\Administrator" `
                -LogonType S4U -RunLevel Highest) `
  -Settings  (New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
                -ExecutionTimeLimit (New-TimeSpan -Hours 4))
```

**Las 06:00 del disparador son UTC y son las 00:00 de CDMX.** El reloj de la VM está en UTC
(`tzutil /g` → `UTC`) y el Task Scheduler dispara en la hora del sistema operativo, no en la del
negocio — que es la misma trampa que `main.py` ya resuelve con `TZ_OFFSET_HOURS` para las fechas y
para el log. Como México **ya no usa horario de verano**, el UTC−6 no se mueve en el año: no hay que
corregir el disparador en abril ni en octubre. Las otras dos tareas de BI de esta VM siguen la misma
convención (15:15 UTC = 09:15 CDMX).

**Corre como `Administrator` con `LogonType S4U`.** Tres razones, en orden de importancia:

- Con `SYSTEM` **el túnel SSM no levanta**: las credenciales AWS viven en el perfil del usuario.
- S4U corre haya o no sesión abierta, igual que una tarea con contraseña guardada, pero **sin
  guardar la contraseña** en el Task Scheduler.
- Lo único que S4U no da son credenciales de *red* de Windows, y el pipeline no las usa: el túnel
  autentica contra AWS por HTTPS con los archivos de `~\.aws`, PostgreSQL es loopback y Redshift sale
  con lo de su `.env`. El Drive de `D:\Shared drives\` sí las necesitaría, pero de ahí sólo comen las
  dos cargas manuales, que a propósito no cuelgan de `main.py`.

No hace falta una segunda tarea para la recarga completa: `--full` se dispara solo cada 30 días
desde dentro del ETL.

**Verificado el 2026-08-14**, y valía la pena: hasta ese día `run_pipeline.bat` no se había ejecutado
nunca, así que la ruta desatendida —usuario sin sesión, túnel SSM sin consola— estaba sin probar. Se
lanzó con `Start-ScheduledTask` para ejercitar esa ruta y no la de la consola. Resultado:

| | |
|---|---|
| `LastTaskResult` | `0` |
| Duración | **20.9 min** — el ~20 esperado, no los 17 de antes del paso 3 |
| Tablas con `started_at` de hoy | **27 de 27** |
| Cuadre origen → destino | las 15 identidades (`identidad_*` en `ops/quality_checks.py`), incluida la de `grid_bnpl` en **exactamente −71** |
| Alertas de calidad | las dos de siempre (1,469 y 276), las que la sección de arriba dice no perseguir |
| Túnel SSM | levantó y resolvió `~/.aws/credentials` sin sesión interactiva |

Lo único que ensucia el log es un `UserWarning` de `redshift_extractor` (pandas pidiendo un
connectable de SQLAlchemy) y el aviso de que la sesión SSM queda `Active` hasta que la barra el idle
timeout. Ninguno de los dos es nuevo ni afecta el resultado.

**Ventana de tiempo.** La corrida arranca 06:00 UTC (00:00 CDMX) y el refresh de Power BI es a las
**08:30 CDMX**: 8 h 30 min para una corrida de ~20. Los tres escenarios:

| Escenario | Cierre | Margen al refresh |
|---|---|---|
| Corrida normal (~20 min) | ~00:20 | 8 h 10 min |
| Túnel SSM lento — la variación medida en una misma extracción va de 166 s a 356 s | ~00:30 | 8 h |
| Día de la recarga completa mensual de `credit-order` (+~20 min) | ~00:40 | 7 h 50 min |

Y **el refresh de Power BI se lleva sus propios 32 s de lectura** más la carga del modelo.

**Por qué 00:00 y no 07:30 ni 08:00.** El 2026-08-14 la tarea pasó por tres horarios el mismo día.
Primero las 08:00, contra un refresh que se acababa de mover de las 07:00 a las 08:30: **10 minutos**
de margen, que la variación del túnel se come sola y que el día de la recarga completa no alcanzan.
Se adelantó a las 07:30 —40 minutos— y ese mismo día se movió a **medianoche**, que es la única hora
que deja el margen fuera de discusión: 8 h 30 min contra el refresh de las 08:30, o sea que ni el
túnel lento ni el `--full` mensual pueden acercarse. Se movió la corrida y no el tablero porque a
medianoche no hay nadie esperando el dato, y el refresh a las 08:30 sí tiene quien lo espere.

Si algún día hay que volver a moverla, esto es lo que no se puede perder de vista: **el paso 4 hace
`DROP VIEW` + `CREATE VIEW` de las 19 vistas de `pbi_bnpl` en cada corrida**. Un refresh que caiga
dentro de la corrida no devuelve tranquilamente el dato de ayer — puede **fallar** por vista
inexistente. El refresh se cambia en el Power BI Service (*Configuración del conjunto de datos →
Actualización programada*), no en la VM.

`logs\pipeline_YYYY-MM.log` tiene el detalle paso a paso y `logs\scheduler.log` lo que el `.bat`
capturó, incluido lo que falle antes de que arranque el logging.

## Migrar los datos a la VM — hecho, y `migrar_a_vm.py` quedó deprecado

Los datos ya están en `rabbit-bi-local` (migrados el 2026-08-12) y **el script que lo hizo ya no
corre**: se detiene con un mensaje explicando por qué.

Copiaba de la base local en `localhost:9558` a la VM. Hoy no queda ninguna de las dos mitades de esa
operación: `postgres_local_extractor` fue sustituida por `postgres_local_client`, y el PostgreSQL del
9558 no existe — el único servicio es `postgresql-x64-17` en `localhost:9553`, que sirve
`rabbit-bi-local`, o sea el **destino** de aquella migración, no el origen. Traducir sus imports
haría que origen y destino fueran la misma base y el script se copiaría encima de sí mismo.

El código queda como referencia de cómo se hizo la carga (COPY por lotes, `credit_order_production`
por meses para no repetir los 2.5 GB de RAM). Si alguna vez hay que mover datos entre dos bases
distintas, se revive definiendo dos alias separados y pasando `db=` a cada llamada.

## Respaldo y reconstrucción

Esto es un data mart derivado: casi todo se rehace corriendo el pipeline. El riesgo no es perder el
dato, es **cuánto tarda volver a tenerlo**. Hoy no hay respaldo de ningún tipo.

| Schema | ¿Se rehace solo? | Con qué | Cuánto tarda |
|---|---|---|---|
| `mongo_bnpl` | sí | `etl_mongo_to_postgres.py --full` | 20–40 min (la variación es del túnel SSM) |
| `redshift_bnpl` | sí | `etl_redshift_to_postgres.py` | 3.5 min · 1.29M filas |
| `bnpl` (11 matviews) | sí | `build_bnpl.py --rebuild` | 1.4 min |
| `pbi_bnpl` (19 vistas) | sí | `build_bnpl.py` | < 1 s |
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

## Estructura

```
main.py                     Orquestador: el punto de entrada de la corrida desatendida
run_pipeline.bat            Lo que ejecuta el Task Scheduler
etl_mongo_to_postgres.py    Extracción Mongo → staging (10 colecciones)
etl_redshift_to_postgres.py Extracción Redshift → rutas, ventas, cosechas, estacionalidad (6 tablas)
build_bnpl.py               Construye bnpl.* (11 matviews) y pbi_bnpl.* (19 vistas)
carga_archivos_bnpl.py      MANUAL: 4 CSV del Drive → archivos_bnpl.*
carga_clientes_concurso.py  MANUAL: Excel de negocio → bnpl.bnpl_clientes_concurso
migrar_a_vm.py              DEPRECADO: su base origen ya no existe (ver arriba)
DICCIONARIO.md              GENERADO: 21 tablas, 59 campos, 66 medidas. Sale de ayuda_tablero/conocimiento.py
ayuda_tablero/              MANUAL: los 168 tooltips del PBIP (ver su README)
  conocimiento.py           El catálogo: 21 tablas, 59 campos, 66 medidas. Fuente de DICCIONARIO.md
  documentar_tablero.py     La entrada: sin flags dice qué cambiaría, --aplicar lo escribe
  _datos/                   inventario.json y textos.json: derivados, no se versionan
ops/
  config.py                 Fuentes, umbrales, alias
  check_freshness.py        Frescura de Mongo vs staging
  quality_checks.py         Chequeos de calidad sobre el staging
sql/
  00_bnpl_ops.sql           Schema de operación: frescura, calidad, bitácora
  01_staging.sql            DDL del staging: 10 tablas, 23 índices
  02_bnpl_funciones.sql     Las reglas de negocio, como funciones
  03..11_bnpl_*.sql         Una por vista materializada de la capa de negocio
  12_redshift_staging.sql   DDL de las 6 tablas de Redshift
  13_bnpl_clientes_concurso.sql  DDL de la tabla del concurso
  14_archivos_bnpl.sql      DDL de archivos_bnpl + sus 4 vistas de traducción
  15_pbi_vistas.sql         Sólo crea el schema pbi_bnpl; el cuerpo lo pone build_bnpl.py
  pbi/                      Las 19 consultas del tablero + PASOS_M.md (ver su README)
pbi_new/                    PRODUCTIVO. El PBIP publicado: .pbip + .Report/ + .SemanticModel/, sobre pbi_bnpl
                            (pbi/ era el modelo deprecado de orígenes CSV; salió del repo el 2026-08-14)
analisis/                   Scripts que respaldan cada decisión de diseño (ver su README)
analisis_one_shot/          Análisis puntual: activos Rabbit vs BNPL, línea de crédito vs drop size
legacy/                     Notebooks y .pbix originales. NO se versionan: traen credenciales en claro
.kiro/specs/                Diseño y plan de implementación
PENDIENTES_NEGOCIO.md       Lo que falta confirmar con negocio (no bloquea el desarrollo)
```

Del PBIP se versionan el `.pbip` y las carpetas `.Report/` / `.SemanticModel/`: son texto y sí se
pueden revisar en un diff. **No** se versionan el `.pbix` ni la carpeta `.pbi/`, y las dos razones
importan: `cache.abf` pesa ~135 MiB y GitHub rechaza en duro cualquier archivo de más de 100 MB, y
`localSettings.json` guarda el `reportId`/`datasetId` del artefacto **productivo** más una firma
atada a la máquina que lo abrió — versionarlo es lo que hace que un clon cualquiera pueda publicar
encima de producción sin enterarse.

## Cosas que conviene saber

- **La fuente de verdad del revenue es `payment-report-production`**, no `revenue-orders-production`:
  esta última tiene el 48% de sus filas sin datos financieros y `comisionPorCobrar` 20x inflado.
- **`comisionPorCobrar` no es la comisión de Rabbit**: es `interests × 1.16`, el interés con IVA que se
  le cobra al tendero. La comisión de Rabbit es el 14.2% del interés.
- **Un pago puede llegar hasta 519 días tarde** (recuperaciones de mora), así que el PAR de un mes ya
  cerrado cambia retroactivamente. Las tablas de vintage no pueden ser incrementales.
- **Hay dos rutas y no dan lo mismo.** La mora usa la ruta **histórica** (quién tenía la cuenta cuando
  se originó el crédito); el grid y los cortes usan la **vigente** (quién la atiende hoy). Las órdenes
  de 2023–2024 no tienen ruta de su época y salen marcadas con `ruta_inferida = true`.
- **`netsuiteId` es `text` en PostgreSQL y `bigint` en el modelo de Power BI.** Ese cast es el origen
  de casi todos los problemas de relación del tablero. Ver las notas de traducción en
  [`sql/pbi/README.md`](sql/pbi/README.md#notas-de-traducción-que-valen-para-todas).
- Las credenciales de los notebooks en `legacy/` estuvieron en texto plano en OneDrive. **Se deben
  considerar comprometidas y rotarse.**

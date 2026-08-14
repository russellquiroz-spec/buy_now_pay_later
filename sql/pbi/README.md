# La capa de consumo del tablero: `sql/pbi/` → `pbi_bnpl`

Este directorio es **la única fuente** de lo que ve Power BI. Cada `.sql` de aquí se publica como una
vista en el schema `pbi_bnpl`, con el mismo nombre que la tabla del modelo.

```
sql/pbi/06_grid_bnpl.sql  ──build_bnpl.py──▶  pbi_bnpl.grid_bnpl  ──Value.NativeQuery──▶  grid_bnpl
   el archivo                                    la vista                                 la tabla del modelo
```

`build_bnpl.py` hace `glob("[0-8][0-9]_*.sql")`, descarta el número del nombre y envuelve el
contenido en un `CREATE VIEW`. **No hay copia del SQL en ningún otro lado**: ni en el `.pbix`, ni en
`sql/15_pbi_vistas.sql` (que sólo crea el schema). La vista no puede quedar desfasada del archivo
porque se reconstruye desde él en cada corrida del pipeline.

Los alias van en camelCase entre comillas dobles: son los nombres **exactos** de las columnas del CSV
original, porque de ellos cuelgan 66 medidas DAX, 22 relaciones y ~50 columnas calculadas del modelo.

## Índice

- [Las 18 vistas](#las-18-vistas)
- [Cómo conectarlas](#cómo-conectarlas)
- [Cambiar una consulta](#cambiar-una-consulta)
- [Agregar una tabla nueva al tablero](#agregar-una-tabla-nueva-al-tablero)
- [Cuando falla el refresh](#cuando-falla-el-refresh)
- [Lo que no se reemplaza, y por qué](#lo-que-no-se-reemplaza-y-por-qué)
- [Concurso Crédito Rabbit](#concurso-crédito-rabbit-18-al-30-de-agosto)
- [Notas de traducción que valen para todas](#notas-de-traducción-que-valen-para-todas)

## Las 18 vistas

De dónde venía cada tabla del modelo y de dónde viene ahora. Filas y columnas verificadas contra la
base el 2026-08-14.

| # | Vista en `pbi_bnpl` | Origen anterior | Fuente ahora | Filas | Cols |
|---|---|---|---|---:|---:|
| 01 | `bnpl_grouped_orders` | CSV local | `bnpl.grouped_orders` + `dim_ruta_actual` | 99,019 | 31 |
| 02 | `bnpl_loss_rates` | CSV local | `bnpl.loss_rates` + conteo de activados | 92,009 | 37 |
| 03 | `bnpl_par` | CSV local | `bnpl.par_snapshot` + `loss_rates` | 1,061,120 | 32 |
| 04 | `months_closes` | CSV local | `bnpl.par_snapshot` + `loss_rates` | 1,061,120 | 31 |
| 05 | `vintage_analysis` | CSV local | `bnpl.vintage_analysis` | 530 | 21 |
| 06 | `grid_bnpl` | CSV local | `bnpl.grid_bnpl` | 146,542 | 55 |
| 07 | `bnpl_audiencia_agg` | CSV SharePoint | `bnpl.grouped_orders` (panel cliente×mes) | 214 | 5 |
| 08 | `loans_matured_default_profile` | CSV local | `bnpl.loss_rates` + `grid_bnpl` + `ventas_cliente` | 90,262 | 50 |
| 09 | `bnpl_cosechas_agg` | CSV SharePoint (196 MB) | `redshift_bnpl.cosechas_agg` | 51,721 | 11 |
| 10 | `overall_prev_post_bnpl_sales` | CSV SharePoint (171 MB) | `redshift_bnpl.ventas_cliente` + `grid_bnpl` | 1,293,358 | 22 |
| 11 | `seasonality_delta` | CSV local (oct-2024) | `redshift_bnpl.estacionalidad_mes` | 132 | 10 |
| 12 | `odds_table` | CSV local | `bnpl.loss_rates` + `grid_bnpl` | 18 | 14 |
| 13 | `vars_and_iv` | CSV local | `bnpl.loss_rates` + `grid_bnpl` | 6 | 4 |
| 14 | `odds_combinations` | CSV local | `archivos_bnpl.odds_combinations` | 84,986 | 15 |
| 15 | `atr_combinations_iv` | CSV local | `archivos_bnpl.atr_combinations_iv` | 468 | 5 |
| 16 | `ps_transactional_profile` | CSV local | `archivos_bnpl.ps_transactional_profile` | 100,793 | 2 |
| 17 | `bnpl_cac` | CSV local | `archivos_bnpl.bnpl_cac` | 25 | 2 |
| 20 | `concurso_base` | — (dataset nuevo) | `bnpl.bnpl_clientes_concurso` + `grouped_orders` | 1,098 | 44 |

El `90_redshift_ventas_cliente_mes.sql` **no** se publica como vista: el glob de `build_bnpl.py` sólo
toma los `[0-8][0-9]_`. Los 90+ son documentación de piezas del pipeline, no consultas del tablero.

### Las que no son mapeos 1 a 1

**14–17 son el espejo de cuatro archivos** que ninguna consulta puede reemplazar (dos del modelo de
riesgo, uno de Pago de Servicios, el CAC manual). Viven en `archivos_bnpl` y los carga
[`carga_archivos_bnpl.py`](../../carga_archivos_bnpl.py) a mano. El schema es aparte de `bnpl` a
propósito: `bnpl` lo reconstruye `build_bnpl.py` y se puede tirar sin perder nada; esto no. El
procedimiento de recarga está en el [README raíz](../../README.md#los-archivos-del-drive).

**La 07 es la única rehecha, no traducida.** `tipoActual` es la clasificación mensual de ciclo de
vida del cliente (Nuevo / Recurrente / Intermitente / Reactivado / Dormant / Inactivo / Dropped), la
misma regla de `analytics.clasificacion_mensual_clientes.tipo_actual_fin` aplicada sobre pedidos
BNPL. Es un panel cliente×mes: Dormant, Inactivo y Dropped son clientes que **no** compraron ese mes,
así que ningún `GROUP BY` sobre órdenes puede reproducirla. Reproduce el CSV con ~5% de error en
gross sales y órdenes (exacta en los primeros meses); el detalle está en el encabezado del archivo.

**La 06 devuelve 71 filas menos que su vista de origen**, y tiene que ser así — ver
[Notas de traducción](#notas-de-traducción-que-valen-para-todas).

**Los CSV originales están en `D:\Shared drives\Data Room - BI & Data Analytics\Rabbit Risk
Analytics\Buy Now Pay Later\`.** Cotejar contra ellos antes de dar una consulta por buena: así se
descubrió que la primera versión de la 07 estaba mal.

### Costo de lectura

El refresh lee las 18 vistas completas. Medido con `EXPLAIN ANALYZE` (sólo el lado del servidor):

| Vista | s | Vista | s |
|---|---:|---|---:|
| `overall_prev_post_bnpl_sales` | 8.7 | `odds_table` | 1.0 |
| `months_closes` | 5.5 | `vars_and_iv` | 0.8 |
| `bnpl_par` | 5.2 | `grid_bnpl` | 0.7 |
| `loans_matured_default_profile` | 4.0 | `bnpl_grouped_orders` | 0.3 |
| `bnpl_audiencia_agg` | 3.5 | `bnpl_loss_rates` | 0.2 |
| `concurso_base` | 2.1 | las otras 7 | < 0.1 |
| | | **total** | **32.0 s** |

Son **vistas simples, no materializadas, a propósito**: casi todas son proyecciones delgadas sobre
las materializadas de `bnpl`, que ya pagaron el costo de calcularse. Volver a materializarlas
duplicaría ~3.4M filas y agregaría un refresh que puede quedar desfasado del de abajo. Si algún día
la ventana se aprieta, las tres pesadas se materializan cambiando `CREATE VIEW` por
`CREATE MATERIALIZED VIEW` y agregándolas al refresh.

## Cómo conectarlas

**No hay que pegar el SQL.** El paso M queda en una línea, sin una sola comilla que escapar:

```m
let
    Origen = Value.NativeQuery(
        PostgreSQL.Database("localhost:9553", "rabbit-bi-local",
                            [CreateNavigationProperties=false]),
        "select * from pbi_bnpl.grid_bnpl", null, [EnableFolding=true])
in
    Origen
```

Cambiando sólo el nombre de la vista. Los 18 pasos M, listos para copiar, están en
[`PASOS_M.md`](PASOS_M.md).

**Reemplazar el paso `Origen` completo y no dejar nada después.** En particular hay que borrar
`Table.TransformColumnTypes` y `Table.RemoveColumns` — ver [Cuando falla el refresh](#cuando-falla-el-refresh).

### Estado de la migración

El modelo **productivo** es **`pbi_new/`** en la raíz del repo: sus 17 tablas leen de `pbi_bnpl`, no
queda un solo `Csv.Document`, ni `SharePoint.Files`, ni `Table.TransformColumnTypes`, ni
`excludeFromModelRefresh`, ni la consulta muerta `Consulta1` — verificado sobre **todo** el
`.SemanticModel/`, no sólo sobre `definition\tables\` (ver [Pasos M que sobran](#2-pasos-m-que-sobran)).

**`pbi/` está deprecado**: es la copia con orígenes de archivo, no se refresca por gateway y **no se
abre ni se publica**. Salió del repo el 2026-08-14 a `..\_deprecado_pbi_origenes_csv_2026-08-14`, sin
su `.pbi/` y con el `.pbip` renombrado, para que nadie lo publique por error sobre el mismo `reportId`.

Desde el 2026-08-14 está publicado en el Service y refresca por `Gateway_BI` — la configuración de la
conexión y del rol `pbi_gateway` está en [`README.md` → El gateway](../../README.md#el-gateway--configurado-el-2026-08-14).
Ese mismo día se le quitaron **16 consultas auxiliares** heredadas del modelo de archivos
(`Parámetro1..4` y sus ayudantes `Archivo de ejemplo` / `Transformar archivo`, en 4 grupos): ninguna
tabla las usaba, pero llegaban por `SharePoint.Files` a una OneDrive personal y bloqueaban el refresh
completo. Ver [Cuando falla el refresh → El gateway](#4-el-gateway).

**Se publica el `.pbip`, no el `.pbix`** — y ya no hay `.pbix` en el repo: el que habia era
anterior a esta limpieza y publicarlo la deshacia. Si hace falta uno, se abre el `.pbip` en Desktop y
*Archivo -> Guardar como*.

`concurso_base` no está en ninguno de los dos modelos: es un tablero aparte, todavía sin construir.

## Cambiar una consulta

```powershell
# 1. Editar el .sql
code sql\pbi\06_grid_bnpl.sql

# 2. Reconstruir las 18 vistas (DROP + CREATE; menos de un segundo)
.venv\Scripts\python.exe build_bnpl.py

# 3. Refrescar en Power BI Desktop. El paso M NO cambia.
```

`build_bnpl.py` usa **DROP + CREATE y no `CREATE OR REPLACE`**: este último falla si cambian los
nombres, el orden o el tipo de las columnas, que es justo lo que pasa al corregir una consulta.

> `build_bnpl.py --solo <vista>` **no** reconstruye `pbi_bnpl`. Si cambiaste un `.sql` de aquí, corre
> `build_bnpl.py` sin flags.

Antes de abrir Power BI, comprueba contra la base:

```sql
select count(*) from pbi_bnpl.grid_bnpl;
select column_name, data_type from information_schema.columns
where table_schema = 'pbi_bnpl' and table_name = 'grid_bnpl'
order by ordinal_position;
```

Si sólo cambiaste el cuerpo y ninguna columna, el refresh de Power BI toma el cambio sin tocar el
`.pbix`. Si cambiaste **nombres o tipos** de columnas, tienes que revisar las medidas DAX que las
usan: un rename no falla el refresh, falla la medida tres páginas más allá.

## Agregar una tabla nueva al tablero

**1. Escribe el `.sql`.**

```powershell
code sql\pbi\18_mi_tabla_nueva.sql
```

Reglas del archivo, que vienen de cómo lo lee `build_bnpl.py`:

| Regla | Por qué |
|---|---|
| Nombre `NN_<nombre>.sql`, con `NN` entre `01` y `89` | el glob es `[0-8][0-9]_*.sql`; los 90+ se ignoran |
| `<nombre>` = el nombre **exacto** de la tabla en el modelo de Power BI | la vista se llama así y el paso M la busca por ese nombre |
| `<nombre>` único entre todos los archivos | dos archivos con el mismo sufijo se pisan la vista |
| **Un solo `SELECT`**, sin `CREATE VIEW` propio ni `;` de más | el archivo se envuelve entero: `CREATE VIEW … AS <cuerpo>;` |
| Alias en camelCase entre comillas dobles | `SELECT netsuite_id::bigint AS "netsuiteId"` |
| Los tipos ya correctos desde SQL | así el paso M no necesita `Table.TransformColumnTypes` |

Encabeza el archivo con un comentario que diga qué reemplaza, de dónde sale, cuál es el grano y qué
página alimenta — es la convención de los otros 18 y es lo primero que lee quien venga después.

**2. Si necesita datos que no están en la base**, agrégalos primero: una vista en `bnpl`
(`sql/03..11_*.sql` + entrada en `CAPAS` de `build_bnpl.py`), una tabla de Redshift
(`sql/12_redshift_staging.sql` + un bloque en `etl_redshift_to_postgres.py`) o un archivo del Drive
(`sql/14_archivos_bnpl.sql` + entrada en `ARCHIVOS` de `carga_archivos_bnpl.py`). La consulta de
`sql/pbi/` sólo proyecta y renombra; no debería estar bajando datos nuevos por su cuenta.

**3. Publica la vista.**

```powershell
.venv\Scripts\python.exe build_bnpl.py
# -> "pbi_bnpl: 19 vistas creadas para Power BI"
```

Si el número no subió, el archivo no entró en el glob: revisa el nombre.

**4. Verifica contra la base antes de tocar Power BI.**

```sql
select count(*) from pbi_bnpl.mi_tabla_nueva;
select * from pbi_bnpl.mi_tabla_nueva limit 5;
select column_name, data_type from information_schema.columns
where table_schema = 'pbi_bnpl' and table_name = 'mi_tabla_nueva'
order by ordinal_position;
```

Y si reemplaza un CSV, **cuadra contra el CSV** antes de seguir. Una tabla a la vez.

**5. Agrega el paso M a [`PASOS_M.md`](PASOS_M.md)** — misma plantilla, cambiando el nombre — y
actualiza su tabla de filas/columnas.

**6. Conéctala en Power BI Desktop**: *Obtener datos → Consulta en blanco → Editor avanzado*, pega el
M, y **no agregues ningún paso después**. Nombra la consulta igual que la vista.

**7. Piensa en el costo.** Es una vista simple: su consulta se ejecuta entera en **cada** refresh. Si
tarda más de unos segundos, apóyala en una materializada de `bnpl` en vez de calcular sobre el
staging.

## Cuando falla el refresh

Los cuatro que ya nos pasaron, en orden de qué tan difícil es darse cuenta.

### 1. El esquema equivocado — el que no falla y por eso es el peor

`grid_bnpl` y `vintage_analysis` existen **tanto en `bnpl` como en `pbi_bnpl`**, y no traen lo mismo:

```
bnpl.grid_bnpl       (matview, 62 cols)  ->  customer_id, shopkeeper_id, netsuite_id, shop_name…
pbi_bnpl.grid_bnpl   (vista,   55 cols)  ->  netsuiteId,  customerId,    shopkeeperId, shopName…

bnpl.vintage_analysis     (matview, 21)  ->  enrollment_cohort, cohort_year, months_from_enrollment_to_month, ever_activated…
pbi_bnpl.vintage_analysis (vista,   21)  ->  enrollment_cohort, cohortYear,  monthsFromEnrollmentToMonth,     n, everActivated…
```

El de `bnpl` es la capa de negocio y usa snake_case; el de `pbi_bnpl` es el que espera el modelo.

**Síntoma:** el refresh **no falla**. Carga bien. Lo que falla es después: cada medida DAX que busque
`grid_bnpl[netsuiteId]` se rompe, y Power BI además reescribe las relaciones apuntando a
`netsuite_id`. Aparecen errores en visuales de páginas que nadie tocó.

**Causa:** haber usado el navegador de Power BI para elegir la tabla — ahí las dos aparecen con el
mismo nombre — o un `Value.NativeQuery` sin schema calificado.

**Arreglo:** siempre `select * from pbi_bnpl.<vista>`, con el schema escrito. En Power BI Desktop,
*Editor avanzado* sobre la consulta: si el string dice `"select * from grid_bnpl"` sin schema, o
`"bnpl.grid_bnpl"`, está mal.

Del lado de la base, para ver los dos homónimos y confirmar cuál trae los nombres del modelo:

```sql
select n.nspname as schema,
       case c.relkind when 'm' then 'matview' when 'v' then 'vista' end as tipo,
       count(*) as cols,
       bool_or(a.attname = 'netsuiteId') as tiene_netsuiteid
from pg_class c
join pg_namespace n  on n.oid = c.relnamespace
join pg_attribute a  on a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped
where c.relname = 'grid_bnpl' and n.nspname in ('bnpl', 'pbi_bnpl')
group by 1, 2;
```

```
 schema   | tipo    | cols | tiene_netsuiteid
----------+---------+------+------------------
 bnpl     | matview |   62 | f                 <- capa de negocio, snake_case
 pbi_bnpl | vista   |   55 | t                 <- el que va al modelo
```

Las otras 16 vistas no tienen homónima: el riesgo se concentra en esas dos.

### 2. Pasos M que sobran

Las vistas ya devuelven el tipo correcto y no traen la columna sin nombre que traía el CSV. Dejar los
pasos que el CSV necesitaba **rompe el refresh**.

| Paso a borrar | Error que produce | Por qué |
|---|---|---|
| `Table.TransformColumnTypes` | *"No se pudo convertir…"* / comparación `Integer` vs `Text` | El caso clásico es `loanDisbursementIndexRange`: sus valores son `'1'`, `'2'` y **`'3+'`**. El cast a `Int64` que traía el M revienta con el `3+`. |
| `Table.RemoveColumns` | *"No se encontró la columna 'Column1' de la tabla"* | Los CSV de riesgo traían el índice de pandas como primera columna sin nombre y el M la quitaba. La vista no la trae: `carga_archivos_bnpl.py` ya la descarta. |

**Arreglo:** el paso `Origen` debe ser el **único** paso de la consulta. Si abres *Editor avanzado* y
ves algo después del `in`, sobra.

Para detectar los residuales en el modelo, sobre **todo** el `.SemanticModel/` — no sólo sobre
`definition\tables\`: las consultas huérfanas (las que no cargan ninguna tabla) viven en
`definition\expressions.tmdl`, y un barrido acotado a `tables\` nunca las ve. Es exactamente cómo
sobrevivieron 16 consultas auxiliares con `SharePoint.Files` a una OneDrive personal:

```powershell
Get-ChildItem "pbi_new\Buy Now Pay Later.SemanticModel" -Recurse -Include *.tmdl,*.json -Force |
  Select-String -Pattern "TransformColumnTypes|RemoveColumns|Csv\.Document|File\.Contents|SharePoint\.Files|excludeFromModelRefresh"
```

Hoy no devuelve nada, y así debe quedarse. Dos detalles del comando: el `-Recurse` es lo que lo lleva a
`expressions.tmdl` y a `cultures\`, y los puntos van escapados (`Csv\.Document`) porque `Select-String`
toma el patrón como regex — sin escapar, `Csv.Document` también casa con `CsvXDocument`.

### 3. Los tipos de las columnas llave

Lo que hoy devuelve cada vista, verificado el 2026-08-14. Si el modelo espera otra cosa, hay que
retipar **en el modelo**, no agregar un paso M.

| Columna | `pbi_bnpl` | Ojo con |
|---|---|---|
| `netsuiteId` | `bigint` en 01…10 salvo dos | **`bnpl_grouped_orders` y `concurso_base` lo traen `text`**: en el modelo `bnpl_grouped_orders[netsuiteId]` es texto y no participa en ninguna relación. Se respeta tal cual. |
| `netsuiteIdNum` | `bigint` (sólo `concurso_base`) | es la columna que cruza contra `bnpl_clientes_concurso`, no la versión texto |
| `salesOrderId` | `text` en las 7 que lo traen | nunca castear a número: hay ids con prefijo |
| `customerId`, `shopkeeperId` | `text` | son ids de Mongo, no números |
| `enrollment_cohort` | **`text` en 01, 02, 05, 06, 10 · `date` en 03 y 04** | no es un descuido: es como está tipado el modelo |
| `enrollmentCohort` | `text` (`bnpl_cac`) | `'YYYY-MM'` |
| `loanDisbursementIndexRange` | `text` en las 5 que lo traen | **el modelo lo tiene como `Int64`** porque el `.pbix` cargó una versión vieja en la que el rango era numérico. Al conectar hay que retiparlo a texto en `loans_matured_default_profile` **y también en `vars_and_iv`**, o la relación entre las dos deja de cruzar. |
| `Id cliente` | `bigint` (`ps_transactional_profile`) | sí, con espacio: es el nombre en el modelo |

Consulta para revisar cualquier columna en las 18 vistas de una vez:

```sql
select table_name, column_name, data_type
from information_schema.columns
where table_schema = 'pbi_bnpl' and column_name = 'netsuiteId'
order by 1;
```

### 4. El gateway

Los cinco errores que ha dado. Los dos primeros mienten sobre su causa; el último dice la verdad
pero apunta al schema equivocado.

| Lo que dice el portal | Lo que realmente pasa | Arreglo |
|---|---|---|
| *"Credenciales de conexión no válidas"* al crear la conexión | **nada que ver con la credencial**: la casilla de conexión cifrada viene marcada y el servidor tiene `ssl = off`. El log lo llama `EncryptedConnectionFailed` | desmarcar *Usar conexión cifrada* en Configuración avanzada |
| *"17 consultas están bloqueadas"* + 404 de OData en `Parámetro1..4` | `Parámetro1..4` son **parámetros**, y Power Query los evalúa antes que todo lo demás: al dar 404 bloquean las 17 tablas aunque ninguna los use | borrar los 4 grupos `Transformar archivo de …`; ya está hecho, ver [Estado de la migración](#estado-de-la-migración) |
| `Gateway_BI` → *"Configuración incorrecta"* | el modelo **publicado** es el viejo, el de orígenes de archivo. Un gateway empresarial no puede servir CSV del disco de otra persona, y ese modelo no tiene ni un origen de PostgreSQL | republicar desde el `.pbip` reemplazando el modelo semántico |
| `permission denied for view …` en el refresh del día siguiente | el `DROP VIEW` de `build_bnpl.py` se llevó los `GRANT` de `pbi_gateway` | ya no debería pasar: lo repara [`sql/16_pbi_grants.sql`](../16_pbi_grants.sql) en cada corrida |
| `42501: permission denied for schema bnpl` — y `pbi_gateway` sólo consulta `pbi_bnpl` | seis vistas llaman funciones de `bnpl` (`ahora_mx()`, `hoy_mx()`, `estados_activacion()`, `dias_credito()`), y PostgreSQL cobra las **funciones** al que consulta, no al dueño de la vista: la regla del dueño sólo cubre las tablas | ya no debería pasar: [`sql/16_pbi_grants.sql`](../16_pbi_grants.sql) deduce de `pg_depend` los schemas a los que dar `USAGE` |

Los dos últimos son fallas de **permisos**, y desde el 2026-08-14 el pipeline los repara solo. Si
vuelve a aparecer uno, la pregunta no es qué `GRANT` falta sino por qué no corrió el paso de permisos
— revisa el final del log de `build_bnpl.py`, que imprime `permisos de pbi_gateway aplicados`.

**El mensaje del portal casi nunca es el motivo.** El bueno está en el log del gateway, en la VM:

```powershell
$log = "$env:WINDIR\ServiceProfiles\PBIEgwService\AppData\Local\Microsoft\" +
       "On-premises data gateway\GatewayErrors$(Get-Date -Format yyyyMMdd).000000001.log"
Select-String -Path $log -Pattern 'Reason =|MashupCredentialException' | Select-Object -Last 5
```

Ojo: ahí sólo van los **fallos**. Un intento que sí funcionó no aparece, y da la impresión de que
nadie lo intentó — los éxitos viven en `GatewayInfo<fecha>.log`, que pesa ~40 MB por día.

Y el que no da error: **el servidor del origen debe coincidir letra por letra** con el de la conexión
del gateway. El paso M dice `PostgreSQL.Database("localhost:9553", …)`, así que la conexión va con
`localhost:9553`, no con el nombre de la máquina ni con `127.0.0.1`. Si no empatan, el modelo reporta
que no hay gateway disponible y todo lo demás se ve bien.

### 5. Otros

| Error | Causa | Arreglo |
|---|---|---|
| `relation "pbi_bnpl.X" does not exist` | no se corrió `build_bnpl.py` después de agregar el `.sql`, o se corrió con `--solo` | `.venv\Scripts\python.exe build_bnpl.py` sin flags |
| La tabla carga pero con datos de hace días | `pbi_bnpl` es una vista sobre `bnpl.*`, que **sí** es materializada | corre el pipeline; revisa `bnpl_ops.etl_runs` |
| Los números de `bnpl_audiencia_agg` se movieron | tenía `excludeFromModelRefresh` y estaba congelada al CSV | es lo esperado: el CSV quedó fijo en la fecha en que se generó |
| Falla la conexión a `localhost:9553` desde el Service | la conexión del gateway o su credencial | [El gateway](#4-el-gateway) |

## Lo que no se reemplaza, y por qué

| Tabla | Páginas | Por qué |
|---|---|---|
| `odds_table`, `odds_combinations`, `vars_and_iv`, `atr_combinations_iv` | Default Customer Profile | No son extracciones: son la salida de un modelo de riesgo (WOE/IV por atributo). Se rehacen re-corriendo ese análisis, no con una consulta. |
| `bnpl_cac` | Return On Investment | CAC por cohorte, capturado a mano. Conviene volverlo una tabla versionada, pero el dato lo pone negocio. |
| `ps_transactional_profile` | Fraud (vía DAX) | Producto Pago de Servicios, fuera del alcance de este pipeline. Se intentó derivarlo del schema `fintech` de Redshift y no alcanza: la regla que separa "Potential" de "Mostly Fraud" la pone el equipo de PS. |
| `Consulta1` | ninguna | Era el listado de archivos de un OneDrive personal. **Ya está borrada en `pbi_new/`.** |

Las cuatro primeras siguen siendo archivos, pero ya no se leen del disco de nadie: viven en
`archivos_bnpl` y las carga `carga_archivos_bnpl.py`.

`bnpl_loss_rates_temp_table`, `bnpl_loss_rates_with_lead`, `CacTable` y las tablas de tipo
`Cohort Type` / `X Axis Type` son tablas calculadas en DAX. No tienen origen externo y se
recalculan solas.

## Concurso Crédito Rabbit (18 al 30 de agosto)

Una consulta aparte, para un tablero propio. No toca el modelo existente: es un dataset nuevo,
con su propia vigencia.

| # | Tabla | Grano | Filas |
|---|---|---|---|
| 20 | `pbi_bnpl.concurso_base` | cliente × sales order creada en la ventana | 1,098 |
| — | `bnpl.bnpl_clientes_concurso` | 1 fila por cliente del universo | 51,294 |

`bnpl_clientes_concurso` no es una consulta: es una **tabla física** con el universo de lanzamiento
y su línea de crédito, cargada a mano desde `BBDD tablero BNPL LANZAMIENTO.xlsx` (Drive de BI,
`Dashboards/Venta/Punto de encuentro (Compromisos)/concurso_bnpl/`) con
`carga_clientes_concurso.py`. Es la única tabla de `bnpl` que no reconstruye `build_bnpl.py`; el
dato lo pone negocio, no sale de Mongo ni de Redshift.

Se carga la hoja `bbdd`, ya filtrada a clasificación `ajuste` (33,476) y `nuevo` (17,818). La otra
hoja del libro (`Hoja1`) trae 20,004 filas más de `baja` y `corrientes`, que quedan fuera.

Para relacionarla con `concurso_base` va `netsuite_id_num` (bigint) contra `netsuiteIdNum`, no la
versión texto: es exactamente el caso para el que esa columna existe. Los 51,294 cruzan al 100%
contra `bnpl.grid_bnpl`, pero sólo 89 tienen orden BNPL — es el universo objetivo, no el colocado.

Dos cosas de la fuente que ya vienen resueltas en la carga: la columna del Excel llamada
`Ruta preventa` es en realidad el **supervisor** (códigos `SV*`, homónima de `Ruta Preventa` salvo
por una mayúscula), y 65 filas traen `oficina_venta = '0'`, que se cargan como NULL para que no
aparezcan como una oficina más en los desgloses.

Tabla plana y **sin reglas del concurso**: no trae brackets, ni bono, ni ranking. Los brackets
cambian de redacción, el umbral del premio está en duda y la tarifa puede ser retroactiva o
marginal — todo eso vive en DAX, donde se corrige sin volver a tocar el origen ni republicar.
La consulta sólo entrega hechos y dimensiones.

La vigencia va en el CTE `parametros` (`'2026-08-18'` a `'2026-08-30'`). Trae **dos periodos del
mismo largo** — `'Concurso'` y `'Previo'` (los 13 días inmediatos anteriores) — con `diaVentana`
1..13 en ambos, para comparar contra la línea base sin escribir DAX de time intelligence. Casi todos
los visuales quieren `periodo = 'Concurso'`.

**El grano es la orden, no el cliente.** Para contar clientes colocados va `DISTINCTCOUNT`,
nunca `COUNTROWS`. Detalle fino: si un cliente compra en dos rutas dentro de la ventana, la
suma de `DISTINCTCOUNT` por aliado da más que el total. Por eso viene
`esPrimeraOrdenEntregadaEnVentana`, que ancla cada cliente a una sola ruta y hace que la suma
por aliado cuadre exacto con el total. En el ensayo de julio ningún cliente cayó en ese caso,
pero el día que pase, el pago del bono se desviaría sin avisar.

**Ensayo sobre el 18–30 de julio** (misma ventana, ya cerrada), corrido contra la base:

| | |
|---|---|
| Órdenes en la ventana | 1,690 |
| Clientes con orden entregada | 1,232 (57 nuevos en crédito) |
| Rutas con colocación | 309 · 31 supervisores |
| Mejor aliado | 19 clientes |

Tres cosas que conviene revisar antes de publicar el tablero:

1. **Nadie cruza 30 clientes** (máximo 19). Con ese comportamiento la motocicleta y las 16
   pantallas quedan desiertas, y el bracket de $100 nunca se activa: el 76% de las rutas se
   queda en el primero. O el umbral baja, o el premio adicional es decorativo.
2. **El tercer bracket del arte dice "DE 1 A 20"** y se solapa con los dos anteriores. La única
   lectura que deja la escalera completa es 11 a 20. Confirmar antes de pagar.
3. **El objetivo de 8,000 no tiene denominador en el arte.** La base histórica de clientes que
   han usado crédito ya va en **9,286** (y los enrolados con crédito aprobado, en 10,713), así
   que no es esa. Los activos a 30 días van en ~1,870, así que 8,000 es 4.3x el corriente. Hay
   que elegir la lectura y ponerla en el título del visual.

## Notas de traducción que valen para todas

- **`netsuiteId`**: `text` en PostgreSQL, `bigint` en la vista y `Int64` en el modelo — salvo en
  `bnpl_grouped_orders` y `concurso_base`, donde va como texto y no participa en ninguna relación.
  Ojo con el cast: `bnpl.grid_bnpl` tiene índice único sobre `netsuite_id`, pero es **texto**, así
  que `' 351229'` y `'351229'` conviven. Al pasar a `bigint` colapsan y dejan 70 duplicados, que
  rompen las cinco relaciones que apuntan a esa columna como lado "uno" — Power BI no admite
  blancos ni duplicados ahí. Por eso la 06 lleva un `DISTINCT ON`, y por eso devuelve
  **146,542 filas contra las 146,613 de `bnpl.grid_bnpl`: 70 con espacio + 1 con el id vacío**. Las
  70 están todas vacías (0 órdenes, 0 enroladas, sin ruta, sin `shopName`): son registros fantasma
  de `fintech-customers` y cada una tiene su gemela buena. Órdenes y revenue cuadran al centavo; lo
  único que se mueve es el conteo de enrolados, que baja de 10,713 a 10,712.
- **`enrollment_cohort`**: texto `'YYYY-MM'` en 01, 02, 05, 06 y 10; **fecha** en 03 y 04. No es un
  descuido de las consultas, es como está tipado el modelo.
- **`tipo` vs `tipoActual`**: `tipo` es la estructura comercial del momento de la orden (ruta
  histórica); `tipoActual`, la de hoy. La mora usa la primera, las audiencias la segunda.
- **`inferredGender` ← `gender`**: el legacy adivinaba el género del nombre con `gender_guesser`;
  la vista usa el campo que Mongo ya trae. El nombre de la columna se conserva para no romper
  nada, pero ya no es "inferido".
- **`fromcAvgMonthlyVolume`** (en `seasonality_delta`) trae esa `c` de más desde el CSV original. Se
  conserva tal cual: es el nombre de la columna en el modelo.
- **Columnas que salen NULL o en cero a propósito.** En `loans_matured_default_profile`,
  `PSOnboardedAt` y `TPVOnboardedAt` y los tres flags de otros productos fintech: el CSV original
  también los trae así, nunca se calcularon. En `overall_prev_post_bnpl_sales`, `comparable` y
  `externalId` no se pueden derivar y ningún visual ni medida los usa. Están documentados en el
  encabezado de cada archivo.

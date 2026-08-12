# Pipeline BNPL — Rabbit

BNPL (*Buy Now Pay Later*) es el producto de crédito que Rabbit ofrece a los tenderos: compran a
crédito y pagan **15 días después de recibir el pedido**. El crédito lo otorga **Propaga**, nuestro
partner, y Rabbit se lleva una **comisión sobre el interés**.

La información que Propaga nos devuelve vive en MongoDB. Este pipeline la baja a PostgreSQL, la
convierte en las tablas de riesgo y venta, y alimenta Power BI.

## Estado

| Fase | Qué hace | Estado |
|---|---|---|
| 0 | Tablero de frescura y calidad de las fuentes | **listo** |
| 1 | ETL Mongo → staging PostgreSQL | **listo** |
| 2 | DDL tipado e índices | **listo** |
| 3 | Tablas finales (PAR, vintage, grid, KPIs, revenue, cortes) | **listo** |
| 4 | Dimensiones de ruta y cierre de huecos | **listo** |
| 5 | Orquestación y despliegue a la VM | **listo** (falta programar la tarea en la VM) |
| 6 | Power BI Service + Gateway | pendiente |

Plan detallado con las decisiones y sus mediciones:
[`.kiro/specs/migracion-pipeline-bnpl/plan_implementacion.md`](.kiro/specs/migracion-pipeline-bnpl/plan_implementacion.md).

## Arquitectura

```
MongoDB (BNPL, 52 colecciones)          Redshift (data-rabbit-prod)
        │  túnel SSM                            │  rutas / estructura comercial
        ▼                                       ▼
  mongo_bnpl.*  ← staging, espejo fiel     bnpl.dim_ruta_* (Fase 4)
        │
        ▼
  bnpl.*  ← capa de negocio: PAR, vintage, grid, KPIs, revenue (Fase 3)
        │
        ▼
  Power BI Service vía Gateway (Fase 6)

  bnpl_ops.*  ← frescura de fuentes, calidad de datos, bitácora de cargas
```

**El staging es un espejo fiel de Mongo**: no deduplica ni corrige. Si Mongo trae basura, la trae
igual y lo reporta `bnpl_ops.data_quality_checks`. La limpieza vive en la capa `bnpl`.

## Requisitos

- Python 3.11+ con el venv del proyecto (`.venv/`).
- Librerías internas instaladas como editable desde `Documents/Funciones/`:
  `mongo_extractor`, `redshift_extractor`, `postgres_local_extractor`, `analytics`.
  **Toda extracción va por ellas**, no con clientes propios.
- `.env` en la raíz con `BD_ENGINE_RABBIT_LOCAL` (PostgreSQL destino). Nunca se versiona.
- Credenciales AWS para el túnel SSM de Mongo (perfil `bnpl` en `.env.mongo_extractor`).

## Cómo se corre

**Un solo comando** hace todo, en orden y con log:

```powershell
.venv\Scripts\python.exe main.py
```

| Flag | Para qué |
|---|---|
| `--full` | fuerza recarga completa del staging |
| `--sin-redshift` | omite la estructura comercial (no cambia a diario) |
| `--rebuild` | reconstruye las vistas desde los `.sql` en vez de refrescarlas |

`main.py` corre seis pasos: frescura → staging Mongo → estructura comercial → capa de negocio →
calidad → frescura final. Deja todo en `logs/pipeline_YYYY-MM.log` y en las tablas de `bnpl_ops`, y
devuelve código 1 si algo falló, para que el Task Scheduler lo reporte.

**Se detiene si una fuente crítica está en CRIT** (`credit-order`, `payment-report`,
`state-of-delivery`): cargar datos viejos encima del tablero es peor que no cargar. Las demás
fuentes en CRIT solo generan una advertencia — `fintech-customers` lleva semanas caída y eso no
invalida la mora ni el revenue. La lista está en `ops/config.py` → `FUENTES_CRITICAS`.

Cada paso también se puede correr solo:

```powershell
.venv\Scripts\python.exe ops\check_freshness.py        # frescura
.venv\Scripts\python.exe ops\quality_checks.py         # calidad
.venv\Scripts\python.exe etl_mongo_to_postgres.py      # staging Mongo
.venv\Scripts\python.exe etl_redshift_to_postgres.py   # rutas (Redshift), ~2 min
.venv\Scripts\python.exe build_bnpl.py                 # capa de negocio, ~65 s
```

### Tablas de la capa de negocio

| Vista | Grano | Para qué |
|---|---|---|
| `bnpl.dim_ruta_actual` | cliente | ruta, supervisor y oficina **vigentes** |
| `bnpl.dim_ruta_cliente_scd` | cliente × tramo | ruta **histórica**, como intervalos de vigencia |
| `bnpl.grouped_orders` | cliente + sales order | base: cohort, índice de pedido, entrega |
| `bnpl.loss_rates` | orden entregada | morosidad (PAR), días de atraso, revenue |
| `bnpl.par_snapshot` | orden × corte mensual | auditar de dónde sale cada tasa del vintage |
| `bnpl.vintage_analysis` | cohort × mes de maduración | evolución del PAR por cohort |
| `bnpl.grid_bnpl` | cliente | maestro: embudo, conteos, revenue por cliente |
| `bnpl.kpis_daily` | día | serie diaria sin huecos, con acumulados y tasas |
| `bnpl.revenue_comision` | orden | el ingreso del producto, orden por orden |
| `bnpl.corte_venta_sku` / `_so` | SKU / sales order | corte semanal, ventana de 8 días desde jueves |

`build_bnpl.py --rebuild` reconstruye las vistas desde los `.sql` (usar al cambiar la lógica);
sin flags solo las refresca. El refresh es completo, no incremental, **y tiene que serlo**: un pago
puede llegar 519 días tarde, así que el PAR de un mes cerrado cambia retroactivamente.

Las reglas de negocio (plazo del crédito, 14.2% de comisión, interés moratorio, exención del primer
pedido, buckets PAR) viven como funciones en `sql/02_bnpl_funciones.sql`, no incrustadas en cada
vista. Cambiar una regla es cambiar una función y refrescar.

### Modos del ETL

| Comando | Qué hace | Cuándo |
|---|---|---|
| (sin flags) | Ventana de 60 días en `credit-order` + recarga completa del resto | corrida diaria |
| `--full` | Recarga completa de todo por TRUNCATE (preserva DDL e índices) | se dispara solo cada 30 días |
| `--recrear` | DROP y recrea desde `sql/01_staging.sql` | al cambiar la proyección, **actualizando ese `.sql` primero** |
| `--solo col1,col2` | Solo esas colecciones o tablas | recargas puntuales; evita los ~20 min de `credit-order` |

**Tiempos esperados**: la corrida diaria tarda entre 3 y 6 minutos y la recarga completa entre 20 y
40. La variación es del túnel SSM, no del pipeline (medido: la misma extracción tardó 166 s y 356 s
en corridas consecutivas).

### Por qué una ventana y no un incremental

Un incremental por `_id` solo vería inserciones y perdería los cambios de estado — una orden pasa de
`CREATED` a `COMPLETED` y se le llena `deliveryAt` al entregarse. Medido sobre el histórico: una orden
se entrega **a más tardar 17 días** después de creada, así que reprocesar 60 días da 3.5x de margen y
baja el 8% de las filas en vez del 100%.

Lo que la ventana no cubre son las órdenes que quedaron en estado no final hace más tiempo (~225
sales orders atascados). Esas se re-extraen dirigidas por `salesOrderId` en la misma llamada.

## Interpretar el tablero

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
| `CRIT` en fuente | más de 48 h sin escrituras en Mongo | **es de ingeniería, no del pipeline**: la fuente dejó de alimentarse |
| `CRIT` en staging | falta más del 1% de los documentos | correr el ETL; si persiste, `--full` |
| `FALTA` | la tabla no existe en el staging | correr el ETL |

Para saber **desde cuándo** una fuente dejó de actualizarse, `bnpl_ops.freshness_history` guarda una
fila por colección por corrida.

> Al 2026-08-12, `fintech-customers-production` lleva 20 días en CRIT: dejó de recibir escrituras el
> 23-jul y `bo-file-upload-info-production` se detuvo el mismo día. Está reportado a ingeniería.
> Impacto: los clientes enrolados desde entonces no tienen `shopName` ni teléfono.

## Migrar los datos a la VM

Los datos de la base local ya están en `rabbit-bi-local` (migrados el 2026-08-12). Para repetirlo o
sincronizar de nuevo:

```powershell
.venv\Scripts\python.exe migrar_a_vm.py            # todo
.venv\Scripts\python.exe migrar_a_vm.py --ddl      # solo schemas, tablas e índices
.venv\Scripts\python.exe migrar_a_vm.py --datos    # solo los datos de las tablas base
.venv\Scripts\python.exe migrar_a_vm.py --vistas   # solo materializar la capa de negocio
.venv\Scripts\python.exe migrar_a_vm.py --validar  # comparar conteos origen vs VM
```

Lee del origen con `postgres_local_extractor` y escribe en la VM con `postgres_local_client` (COPY
sobre túnel SSH). El alias de escritura necesita `ALLOW_DDL=true` en `.env.postgres_local_client`.

**Solo viajan las tablas base** (856 MB, 2.65M filas, ~6.6 min). Las 11 vistas materializadas de
`bnpl` no se copian: se recrean desde los `.sql` y se materializan en la VM en 105 segundos, así que
mandar sus 663 MB por el túnel no tendría sentido. `credit_order_production` va por meses en 33
lotes para no repetir los 2.5 GB de RAM que consume de un golpe.

El paso `--datos` es re-ejecutable: vacía cada tabla destino antes de cargarla.

## Despliegue a la VM

El pipeline está pensado para correr desatendido en una VM. En orden:

**1. Preparar la máquina**

```powershell
git clone https://github.com/russellquiroz-spec/buy_now_pay_later.git
cd buy_now_pay_later
python -m venv .venv
.venv\Scripts\python.exe -m pip install pandas sqlalchemy psycopg2-binary python-dotenv openpyxl
```

**2. Instalar las librerías internas** (editable, desde donde estén en la VM):

```powershell
.venv\Scripts\python.exe -m pip install -e <ruta>\mongo_extractor
.venv\Scripts\python.exe -m pip install -e <ruta>\redshift_extractor
.venv\Scripts\python.exe -m pip install -e <ruta>\postgres_local_extractor
```

**3. Crear el `.env`** en la raíz, con `BD_ENGINE_RABBIT_LOCAL` apuntando al PostgreSQL de la VM.
Nunca se versiona. Los extractores además leen su propio `.env.<paquete>`, que debe existir en la VM
con el perfil `bnpl` de Mongo y el de Redshift.

**4. Verificar los accesos antes de programar nada.** Es donde suele fallar:

```powershell
.venv\Scripts\python.exe ops\check_freshness.py
```

Si eso corre, la VM tiene lo que necesita: túnel SSM a Mongo (AWS CLI + Session Manager plugin +
credenciales del rol), Redshift y PostgreSQL.

**5. Programar la tarea diaria** a las 06:00, una hora antes del refresh de Power BI:

```powershell
schtasks /Create /TN "BNPL Pipeline" /SC DAILY /ST 05:30 ^
  /TR "C:\ruta\buy_now_pay_later\run_pipeline.bat" ^
  /RU <usuario> /RP * /RL HIGHEST
```

El usuario tiene que ser uno con las credenciales AWS configuradas: con `SYSTEM` el túnel SSM no
levanta. Y debe quedar como "ejecutar aunque el usuario no haya iniciado sesión", que es lo que hace
`/RP`.

**Presupuesto de tiempo — medido, no estimado.** Corrida completa del 2026-08-12: **23.2 minutos**
(sin el paso de Redshift; con él, ~26).

| Paso | Tiempo |
|---|---|
| Staging Mongo (10 colecciones) | 21.8 min |
| Estructura comercial (Redshift) | 2.3 min |
| Capa de negocio (11 vistas) | 51 s |
| Calidad + frescura ×2 | 31 s |

Las tres colecciones más lentas del staging: `fintech-customers` 221 s, `credit-order` 174 s (por
ventana) y `payment-report` 156 s. El día de la recarga completa mensual de `credit-order`, sumar
~20 minutos más.

Con la tarea a las 06:00 y el refresh de Power BI a las 07:00 hay margen, pero **no es el margen
holgado de una corrida de 5 minutos**: si el túnel SSM se pone lento, 26 minutos pueden volverse 40.
Conviene dejar la tarea a las 05:30 si Power BI refresca a las 07:00.

**Verificar que corrió:**

```sql
select * from bnpl_ops.etl_runs where tabla = 'pipeline' order by started_at desc limit 5;
select * from bnpl_ops.v_freshness_status;
select * from bnpl_ops.v_quality_alerts;
```

`logs\pipeline_YYYY-MM.log` tiene el detalle paso a paso y `logs\scheduler.log` lo que el `.bat`
capturó, incluido lo que falle antes de que arranque el logging.

## Estructura

```
main.py                    Orquestador: el punto de entrada de la corrida desatendida
run_pipeline.bat           Lo que ejecuta el Task Scheduler
etl_mongo_to_postgres.py   Extracción Mongo → staging (10 colecciones)
etl_redshift_to_postgres.py Extracción Redshift → estructura comercial y rutas
build_bnpl.py              Construye y refresca la capa de negocio
migrar_a_vm.py             Copia los datos de la base local a la VM rabbit-bi-local
ops/
  config.py                Fuentes, umbrales, conexión
  check_freshness.py       Frescura de Mongo vs staging
  quality_checks.py        Chequeos de calidad sobre el staging
sql/
  00_bnpl_ops.sql          Schema de operación: frescura, calidad, bitácora
  01_staging.sql           DDL del staging: 10 tablas, 23 índices
analisis/                  Scripts que respaldan cada decisión de diseño (ver su README)
analisis_one_shot/         Análisis puntual: activos Rabbit vs BNPL, línea de crédito vs drop size
legacy/                    Notebooks y .pbix originales. NO se versionan: traen credenciales en claro
.kiro/specs/               Diseño y plan de implementación
PENDIENTES_NEGOCIO.md      Lo que falta confirmar con negocio (no bloquea el desarrollo)
```

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
- Las credenciales de los notebooks en `legacy/` estuvieron en texto plano en OneDrive. **Se deben
  considerar comprometidas y rotarse.**

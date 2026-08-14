# Plan de implementación — Revivir y automatizar el pipeline BNPL

Estado: **en revisión** · Diagnóstico verificado contra Mongo/Redshift/PG el 2026-08-11/12.

Complementa `design.md` (vigente en arquitectura) y lo corrige donde el diagnóstico contra las
fuentes reales lo desmintió.

**Alcance**: robot de riesgo **y** corte de venta semanal.
**Destino de ejecución**: máquina virtual. Se desarrolla local y se pushea.

---

## Punto de partida real

| Qué | Estado |
|---|---|
| Mongo `BNPL` (52 colecciones, túnel SSM) | **Vivo**, escrituras cada minuto |
| Staging `mongo_bnpl.*` en PG local | **Congelado en el snapshot del 2026-06-25** (47 días de atraso) |
| `etl_mongo_to_postgres.py` | Corre, pero con 6 defectos silenciosos |
| Schemas `bnpl` / `bnpl_analytics` | No existen |
| `rutas_fintech.xlsx` | Ya no está en el proyecto — se reemplaza por Redshift |
| Control de versiones | **No hay repo git** — prerequisito para el flujo local → VM |

Crecimiento no capturado desde el snapshot: credit-order 1,110,531 → 1,189,807.

### Defectos confirmados del ETL

Campos que se proyectan y **no existen en Mongo** — la columna nunca llega y nadie se entera:

| Tabla | Se pide | Nombre real |
|---|---|---|
| `payment_report` | `status` | `state` (+ `transactionStatus`, que es el que usa el negocio) |
| `state_of_delivery` | `salesOrderId` | `orderId` — **rompe el join con órdenes** |
| `fintech_credit_approval` | `approvalDate` | `createdAt` (string ISO) |
| `fintech_credit_approval` | `enrollmentChannel` | `origin` |
| `fintech_customers` | `latitude` / `longitude` | viven en `fintech-credit-request-production` |
| `fintech_pre_authorization_status` | colección inexistente | `fintech-pre-authorization-status-production` (62,334 docs) |

### Historia a cubrir

Primera orden BNPL: **2023-12-04**. SOs por año — 2023: 25 · 2024: 13,223 · 2025: 53,182 · 2026: 26,112 (a junio).

---

## Fuente de verdad del revenue — RESUELTO con datos

Comparación de las 290K filas de ambas colecciones (extracción completa, 2026-08-12):

| | payment-report | revenue-orders |
|---|---|---|
| Filas | 98,768 | 190,618 |
| `transactionId` distintos | 98,764 | 184,250 |
| Filas con `transactionId` repetido | **3** | **6,367** |
| Filas con `interests`/`movementDate`/`comisionPorCobrar` nulos | 0 | **91,611 (48%)** |
| Suma `comisionPorCobrar` | $10,741,664 | $215,402,016 (**20x**) |
| Ratio comisión/interés (mediana) | **1.16 exacto** | 15.05 (máx 258) |

**Veredicto: `payment-report-production` es la fuente de verdad.** `revenue-orders-production` es un
espejo degradado — la mitad de sus filas son esqueletos `fintechStatus = TO_PAY` sin datos
financieros, tiene duplicados por transacción y su `comisionPorCobrar` está corrupto (solo coincide
con payment-report en el 4.6% de las transacciones comunes). Se conserva únicamente si se necesita
`fintechStatus`; no se usa para montos.

### Qué significa cada campo (validado sobre 94,198 filas)

- `interests` = interés **sin** IVA.
- `comisionPorCobrar` = `interests × 1.16` → interés **con** IVA (coincidencia exacta 92.4%).
  **No es la comisión de Rabbit**: es lo que se le cobra al tendero.
- `totalAmountToPay − totalAmount` = interés con IVA (74% coincide con `comisionPorCobrar`;
  solo 1.8% coincide con `interests` sin IVA).

### Volumen del negocio (payment-report, `transactionStatus = 'paid'`)

| Año | Transacciones | Monto financiado | Interés sin IVA | Rabbit @ 14.2% |
|---|---|---|---|---|
| 2024 | 10,899 | $17,242,860 | $614,792 | $87,300 |
| 2025 | 47,165 | $88,900,462 | $3,350,933 | $475,832 |
| 2026 (a jun) | 27,422 | $56,889,164 | $2,180,661 | $309,654 |

---

## Reglas de negocio extraídas del notebook legacy

Verificadas en `legacy/Buy Now Pay Later Robot.ipynb`, celdas 70 y 82. Se externalizan a `config.py`.

```
expectedPaymentDate = deliveryAt + 15 días
                      → si cae sábado, +2 días; si cae domingo, +1 día   (mover a lunes)
endOfTheMonthexpectedPaymentDate = expectedPaymentDate + fin de mes

daysPastDue = (paidDate − expectedPaymentDate).days
              si no hay paidDate → (hoy − expectedPaymentDate).days

defaultInterest = 0 si daysPastDue <= 0
                  si no → 200 × floor(daysPastDue / 7)      ($200 por semana de atraso)

totalRevenue  = 0 si no hay paidDate, si no (totalAmountToPay − totalAmount)
rabbitRevenue = totalRevenue × 0.142
```

**Buckets PAR reales** (el `design.md` los tenía mal — decía Current/DQ 0-29/30-59/60-89/90+):

```
Paid    → tiene paidDate
Ongoing → expectedPaymentDate >= hoy, o daysPastDue < 1
DQ 1-6 · DQ 7-14 · DQ 15-29 · DQ 30-59 · DQ 60-89 · DQ 90+
```

En el vintage aparecen además `PaidPrev` (pagado en un corte anterior; su `totalAmount` se pone en 0
para no sumar al saldo vivo) y `Ongoing`.

### Dos defectos del legacy a resolver antes de portar

**1. La regla de intereses no hace lo que parece.** Tal como está escrita:

```python
(rank == 1) & (((createdAt >= '2024-04-22') & (createdAt >= '2024-04-22'))
             | ((createdAt >= '2024-09-01') & (createdAt >= '2024-10-13')))  → interests = 0
```

La primera condición está duplicada consigo misma y la segunda es un subconjunto de la primera, así
que toda la expresión colapsa a `rank == 1 AND createdAt >= '2024-04-22'`. Las fechas 2024-09-01 y
2024-10-13 **no tienen ningún efecto**. La regla efectiva hoy es: *el primer pedido de un cliente
creado desde el 2024-04-22 no paga intereses*. Hay que confirmar si esa era la intención o si se
perdieron ventanas de promoción intermedias.

**2. El revenue de Rabbit está calculado de dos formas distintas en el mismo notebook.**

| Origen | Fórmula | Histórico |
|---|---|---|
| Celda 70 | `interests × 0.142` (sin IVA) | $872,863 |
| Celda 82 | `(totalAmountToPay − totalAmount) × 0.142` (con IVA) | $1,023,550 |

Diferencia: **$150,687 (17.3%)**. Hay además una tercera fórmula, `commission = totalAmount × 0.04`
($6.5M histórico), que se calcula pero no alimenta el revenue final. **Requiere decisión de negocio**:
el 14.2% del contrato con Propaga, ¿se aplica sobre el interés con IVA o sin IVA?

---

## Fase 0 — Tablero de validación (frescura + calidad) — **COMPLETADA 2026-08-12**

Responde las dos preguntas que motivan el proyecto: *¿se está actualizando?* y *¿desde cuándo no?*

**Entregado**: `sql/00_bnpl_ops.sql`, `ops/config.py`, `ops/check_freshness.py`, `ops/quality_checks.py`.
Corre en **~15 segundos**: una sola llamada a Mongo (los `$lookup` uncorrelated evitan abrir un túnel
por colección — `$unionWith` no existe en este cluster) y una sola consulta al staging.
Extracción vía `mongo_extractor` y `postgres_local_extractor`; escritura con SQLAlchemy Core.

**Primer hallazgo del tablero**: `fintech-customers-production` lleva **20 días sin una sola escritura**
(última: 2026-07-23 03:49 UTC), ni inserciones ni updates — verificado también contra `max(updatedAt)`.
`bo-file-upload-info-production` se detuvo el mismo día a las 03:31 UTC. El resto de las colecciones
escribe cada minuto. Sugiere que un proceso de sincronización de clientes se cayó ese día; hay que
reportarlo a ingeniería. Impacto: los clientes enrolados desde el 23-jul no tienen `shopName` ni
teléfono en `grid_bnpl`.

**Entregables**

- Schema `bnpl_ops`.
- `ops/check_freshness.py` — abre el túnel SSM **una sola vez** y recorre las colecciones core.
  Por cada una: `docs_mongo`, `last_write` (derivada del `ObjectId` del último `_id`, sin escanear),
  `docs_staging`, última fecha de negocio en staging, `lag_horas`, semáforo.
- `bnpl_ops.source_freshness` — foto actual, 1 fila por colección.
- `bnpl_ops.freshness_history` — append por corrida. **Es lo que contesta "desde cuándo"**.
- `bnpl_ops.data_quality_checks` — 1 fila por chequeo por corrida:
  - `salesOrderId` nulo o vacío en credit-order (~1,425 conocidos en el legacy)
  - un `salesOrderId` con más de un `netsuiteId`
  - órdenes sin registro de delivery
  - pagos huérfanos sin orden
  - `netsuiteId` duplicado en approval
  - `deliveryAt` nulo → rompe el cálculo de PAR
  - `transactionId` duplicado en payment-report (hoy: 3)
- `bnpl_ops.v_freshness_status` — vista plana para Power BI.

**Umbrales**: OK < 24h · WARN 24–48h · CRIT > 48h. El pipeline aborta en CRIT.

**Aceptación**: corre en menos de 2 minutos; por cada colección dice si está fresca y desde cuándo no
lo está; los chequeos devuelven conteos, no booleanos.

---

## Fase 1 — Reparar y extender el ETL — **COMPLETADA 2026-08-12**

Hecho: los 6 defectos corregidos; agregadas `propaga-transaction-dev`,
`credit-limit-history-management-production` y `fintech-pre-authorization-status-production`;
`revenue-orders-production` reducida a llaves + `fintechStatus` (sin montos);
`replace` → TRUNCATE + append con ventana de reproceso; credencial de
`analisis_one_shot/config.py` movida a `.env`; repo git inicializado con `.gitignore`.

**Staging al día, las 10 tablas al 100%** (`docs_mongo == docs_staging`):

| Tabla | Filas |
|---|---|
| credit_order_production | 1,189,935 |
| revenue_orders_production | 190,619 |
| fintech_customers_production | 146,614 |
| credit_limit_history_management | 114,560 |
| propaga_transaction | 101,686 |
| payment_report_production | 98,769 |
| state_of_delivery_report_production | 96,790 |
| fintech_pre_authorization_status_production | 62,334 |
| fintech_credit_request_production | 13,082 |
| fintech_credit_approval_production | 10,708 |

### Decisiones de implementación

- **Ventana en vez de incremental por `_id`.** Un incremental por `_id` solo ve inserciones y
  perdería los cambios de estado (CREATED → COMPLETED, `deliveryAt` que se llena al entregar).
  `credit-order` reprocesa los últimos `VENTANA_DIAS = 60` días por `createdAt`; el resto de las
  tablas es TRUNCATE + append completo (son chicas). Modo `--full` recrea las tablas: necesario
  cuando cambia la proyección.
- **`--solo coleccion1,coleccion2`** para recargar tablas puntuales sin repetir los ~20 minutos que
  tarda `credit-order`.
- **`json_normalize` limitado a `max_level=1`.** Más profundo genera nombres que Postgres trunca a
  63 caracteres y llegan a colisionar entre sí (`wholesaler_userValidationRules_…` en
  propaga-transaction producía dos columnas idénticas → `DuplicateColumn`). Lo que queda anidado se
  guarda como JSON. El campo `wholesaler` no se proyecta: unas veces es `"Rabbit"` y otras el objeto
  completo de configuración del mayorista.

### Lo que destrabó la reparación (verificado con el tablero)

| Chequeo | Antes | Ahora |
|---|---|---|
| `ordenes_sin_delivery` | imposible (faltaba `salesOrderId`) | **0** |
| `pagos_sin_orden` | imposible (faltaba `transactionId`) | 276 |
| `payment_report_transaction_id_duplicado` | imposible | 1 |
| `credit_order_delivery_at_nulo` | 0 | **0** — ninguna orden COMPLETED sin `deliveryAt`, el PAR se puede calcular sobre todo el histórico |
| `credit_order_sales_order_id_nulo` | 1,425 (datos de junio) | 1,469 |

### Hallazgo para la Fase 3: el join de pagos necesita una llave secundaria

De los 276 pagos sin orden, **193 se recuperan** uniendo
`payment_report.marketplaceOrderId = credit_order.orderId`; los 83 restantes no cruzan por ninguna
llave. Sus `transactionId` son UUID en vez de `SO…`, y se concentran en 2024 (217 de 276), bajando a
49 en 2025 y 10 en 2026.

El legacy unía solo por `transactionId = salesOrderId`, así que perdía los 276 completos. `loss_rates`
debe unir por `salesOrderId` y caer a `orderId` cuando el primero no cruce.

---

## Estrategia de carga: qué se congela y qué se reprocesa

Medido sobre el staging completo el 2026-08-12. La pregunta es cuánto tiempo después de creado sigue
cambiando un documento.

### Mutabilidad observada

| Tabla | Filas | Disco | Cuánto tarda en dejar de cambiar | Congelable |
|---|---|---|---|---|
| credit_order_production | 1,189,935 | 358 MB | entrega a ≤ **17 días** (p50 0.8 · p99 4.5 · p99.99 9.5) | **sí, 91.4%** |
| credit_limit_history_management | 114,560 | 40 MB | 27% se actualiza en los últimos 60 días | no |
| propaga_transaction | 101,686 | 36 MB | 0.87% cambia tras 60d, máx **519 días** | no |
| payment_report_production | 98,769 | 27 MB | pago efectivo hasta **519 días** después (p99 56d) | no |
| revenue_orders_production | 190,619 | 21 MB | sin fecha confiable | no |
| resto (fintech_*, delivery) | 10K–146K | ≤ 18 MB | — | no vale |

**Solo `credit-order` justifica congelarse.** Es el 67% del disco y ~20 de los ~25 minutos de carga.
Las otras nueve suman ~735K filas y se recargan completas en pocos minutos, así que partirlas agrega
complejidad sin ganancia.

Y no se pueden congelar por una razón de negocio, no de tamaño: **los pagos tardíos llegan hasta 519
días después del movimiento** (el 1% pasa de 56 días). Son justamente las recuperaciones de mora.
Recortarlas por fecha rompería el PAR.

### Peso de la ventana en credit-order

| Ventana | Líneas a reprocesar | % del total |
|---|---|---|
| 15 días | 25,779 | 2.2% |
| 30 días | 50,988 | 4.3% |
| 45 días | 74,427 | 6.3% |
| **60 días** | **99,166** | **8.3%** |
| 90 días | 151,751 | 12.8% |

La ventana de 60 días queda en 3.5x el máximo observado de entrega (17 días) y solo baja 99K líneas
en vez de 1.19M. Se mantiene: el margen extra cubre un cambio en la operación logística sin tocar
código.

### El hueco de la ventana: 225 órdenes zombie

Fuera de la ventana de 60 días quedan órdenes en estado **no final** que la ventana nunca refresca:

| Estado | Líneas | Sales orders |
|---|---|---|
| CREATED | 2,232 | 146 |
| IN_DELIVERY | 883 | 73 |
| TEMPORAL_REJECTED | 82 | 6 |
| VALIDATION_IN_PROGRESS | 489 | 0 (todas con `salesOrderId` nulo) |

Son órdenes atascadas (IN_DELIVERY no registra nada nuevo desde abril 2026). Es improbable que
despierten, pero la ventana sola no las cubriría.

**Implementado 2026-08-12**: en modo ventana el ETL consulta los registros en estado no final que
salieron de la ventana y los agrega al mismo `$match` con un `$in` por `salesOrderId`, así que se
re-extraen en la misma llamada. Los 489 registros de VALIDATION_IN_PROGRESS con `salesOrderId` nulo
no se pueden refrescar dirigido — no tienen llave — y solo se corrigen en la recarga completa.

Resultado medido: **102,363 filas en 166 segundos** (99,166 de ventana + 3,197 de los 225 sales
orders no finales), contra 1,189,935 filas en ~20 minutos del full. El total de la tabla quedó en
1,189,935 exacto, sin duplicados y sin huecos en la serie mensual.

### Por qué se puede congelar con confianza

`check_freshness` compara `docs_mongo` contra `docs_staging` en cada corrida: si Mongo inserta o
borra algo en la zona congelada, el conteo se desalinea y sale CRIT. **Límite real**: un conteo no
detecta modificaciones in-place, que no cambian el número de documentos.

**Implementado 2026-08-12**: `bnpl_ops.etl_runs` registra cada carga (tabla, modo, filas, segundos).
Si la última recarga completa de una tabla tiene `FULL_CADA_DIAS = 30` días o más, la siguiente
corrida la recarga completa sola — sin depender de una segunda entrada en el Task Scheduler. La carga
del 2026-08-12 quedó registrada retroactivamente para no disparar un full inmediato.

### Implicación para las Fases 3 y 4

Como un pago puede llegar 519 días tarde, **el PAR de un mes ya cerrado puede cambiar
retroactivamente** cuando se recupera un moroso viejo. Las tablas de `vintage_analysis` y `par_monthly`
no se pueden construir de forma incremental: hay que recalcular el histórico completo en cada corrida.
A la escala actual (1.19M filas) eso es barato en SQL.

---

## Fase 2 — DDL tipado — **COMPLETADA 2026-08-12**

`sql/01_staging.sql` declara las 10 tablas del staging con 23 índices, y crea los schemas
`mongo_bnpl` y `bnpl`. El ETL lo aplica en cada corrida: **el esquema lo gobierna el DDL, no la
inferencia de pandas**. Modos nuevos: `--full` recarga completa por TRUNCATE (preserva DDL e
índices), `--recrear` hace DROP y deja que el `.sql` reconstruya la tabla.

### Dos decisiones que se apartan de lo planeado, con evidencia

**Sin PK ni UNIQUE.** Seis tablas soportarían PK hoy (verificado: `state_of_delivery.salesOrderId`,
`credit_limit_history.netsuiteId`, `fintech_credit_approval.netsuiteId`, entre otras), pero esa última
es justo la que el README legacy documenta como "posibles múltiples aprobaciones por cliente". Una PK
ahí convierte un problema de calidad de datos en una caída del pipeline a las 6am. El staging es un
espejo fiel: si Mongo duplica, lo reporta `bnpl_ops.data_quality_checks`. Las restricciones de
unicidad van en la capa `bnpl`, donde se controla la deduplicación.

**Epoch ms en `double precision`, no BIGINT.** `deliveryAt` ya tiene 5 nulos y pandas manda `NaN`,
que no entra en un BIGINT. `double` representa enteros exactos hasta 2⁵³ y el epoch ms actual está en
1.8×10¹², así que no se pierde precisión. Se alinearon 6 columnas que pandas había dejado en bigint
(`quantity`, los `creditLimit`) con `ALTER`, en 28 segundos, sin recargar nada.

### Qué índices se usan de verdad (medido con EXPLAIN ANALYZE)

| Consulta del pipeline | Plan | Tiempo |
|---|---|---|
| filas de la ventana (`createdAt >=`) | Index Only Scan | 59.9 ms |
| lookup por `salesOrderId` (el `$in` de zombies) | Index Only Scan | 0.08 ms |
| join pagos-órdenes (Fase 3) | Parallel Hash Join | 314 ms |
| localizar zombies (`orderStatus NOT IN`) | Parallel Seq Scan | 455 ms |

El índice `("orderStatus", "createdAt")` se creó y **se eliminó**: el planner lo ignora porque un
B-tree no sirve para un `NOT IN`. Un índice parcial lo forzaría, pero acoplaría el DDL a la lista de
estados finales del ETL por un ahorro irrelevante. Los joins masivos usan hash join y no necesitan
índice; los índices pagan en las consultas selectivas y los lookups puntuales.

**Costo de los índices en escritura: 1.8 segundos** por 99K filas (1.0 s → 2.8 s medido con
`INSERT … SELECT` sobre copias con y sin índices). Despreciable. El staging pasó de 531 MB a 647 MB.

### Dato operativo para la VM

La misma extracción de la ventana tardó **166 s y luego 356 s** en dos corridas consecutivas. La
diferencia no son los índices — es la variabilidad del túnel SSM. La carga diaria hay que presupuestarla
entre 3 y 6 minutos, y el `--full` mensual entre 20 y 40.

---

## Fase 3 — Tablas finales — **COMPLETADA 2026-08-12**

Nueve vistas materializadas en el schema `bnpl`, orquestadas por `build_bnpl.py`
(`--rebuild` reconstruye desde los `.sql`, sin flags refresca). **La capa completa se refresca en
~65 segundos.**

| Vista | Grano | Filas |
|---|---|---|
| `grouped_orders` | cliente + sales order | 98,854 |
| `loss_rates` | orden entregada | 91,864 |
| `par_snapshot` | orden × corte mensual | 1,060,975 |
| `vintage_analysis` | cohort × mes de maduración | 530 |
| `grid_bnpl` | cliente | 146,613 |
| `kpis_daily` | día | 983 |
| `revenue_comision` | orden | 91,864 |
| `corte_venta_sku` | línea de SKU en la ventana | 23,797 |
| `corte_venta_so` | sales order en la ventana | 1,883 |

### Validación contra el legacy

Las dos definiciones de revenue del notebook se reproducen **con 0.04% de desviación cada una**:

| Definición | Legacy | Esta capa | Δ |
|---|---|---|---|
| Celda 82 — 14.2% sobre interés **con** IVA (`loss_rates`) | $1,023,550.32 | $1,023,125.91 | 0.04% |
| Celda 70 — 14.2% sobre interés **sin** IVA (`grid_bnpl`) | $872,863.38 | $872,496.98 | 0.04% |

La desviación es la misma en ambas y tiene explicación: los ~49 pagos que existen en
`payment-report` pero cuya orden no está COMPLETED. Entre sí difieren 17.3%, exactamente lo medido
en el análisis previo — la capa conserva la inconsistencia del legacy en vez de taparla, y expone
las dos columnas en `revenue_comision` para poder decidir con números (PENDIENTE 1).

Embudo del producto en `grid_bnpl`: 146,613 clientes → 62,334 preautorizados → 10,708 enrolados →
9,294 activados (86.8% de los enrolados) → 1,898 activos en los últimos 30 días.

### Reglas de negocio que se descubrieron al portar

- **`orderGrossSales` se agrega con MAX, no SUM.** El monto total de la orden viene repetido en cada
  línea de SKU; sumarlo infla las ventas por el número de SKUs. El `design.md` decía sum.
- **El cohort sale de la aprobación del crédito**, no de la primera orden: `bnpl_enrolled_at` es el
  `createdAt` de `fintech-credit-approval` con `status = APPROVED`.
- **El vencimiento se calcula sobre el día de entrega, no el instante.** `epoch_to_date()` del legacy
  devuelve `'%Y-%m-%d'`, así que allá las fechas ya venían truncadas a día.
- **`epoch_to_date()` era sensible a la zona de la máquina**: usaba `fromtimestamp` (hora local) menos
  6 horas, así que solo daba hora México si corría en un host en UTC. Había un notebook
  `Cortes de Venta-EC2AMAZ-...`, lo que sugiere que sí. En esta capa el offset es explícito.
- **El join con Propaga era por posición.** El legacy unía por `(netsuiteId, rank)` porque el Excel de
  conciliaciones no traía el sales order. `propaga_transaction` sí lo trae, así que ahora se une por
  `salesOrderId` — se acabó el riesgo de cruzar el pago con la orden equivocada.

### Decisiones de alcance

- **`par_monthly` y `vintage_analysis` son la misma tabla** en el legacy (`parfinal`), así que no se
  duplicó: `vintage_analysis` es la de cohort × maduración con las tasas PAR, y `par_snapshot`
  guarda el grano fino orden × corte para poder auditar de dónde sale cada tasa.
- **`loan_disbursement_index` no se creó.** Su contenido — el rank de crédito por cliente — ya vive
  en `grouped_orders.customer_order_try_index` y `loss_rates.rank_completadas`. Una tabla aparte
  sería la misma lógica en dos lugares.
- **Los buckets PAR corrigen un solapamiento del legacy.** Allá `DQ 7-14` se asignaba con
  `>= 7 AND <= 15` y `DQ 15-29` con `>= 15`: un atraso de 15 días caía en el bucket equivocado por
  orden de evaluación. Aquí `DQ 7-14` termina en 14.
- **`customerAgeAtEnrollment` se calcula contra la fecha de enrolamiento.** El legacy usaba
  `bnplEligibleAt` en esa columna y en `customerAgeAtEligibility`, así que le salían idénticas.
- Se amplió la proyección del ETL con `address`, `business_category`, `shopkeeperId`, `name` y
  `lastNames`: el grid las necesita y no estaban.

### Lo que queda para la Fase 4

`grouped_orders`, `grid_bnpl` y los cortes salen **sin las columnas de ruta**
(`ruta`, `supervisor`, `oficina`, `tipo`), que llegan de Redshift. `grid_bnpl` tampoco trae
`manualValidation`: el `clean_manual_validation.csv` no existe en el proyecto.

---

## Fase 4 — Dimensiones y cierre de huecos — **COMPLETADA 2026-08-12**

`etl_redshift_to_postgres.py` carga el schema `redshift_bnpl` y `sql/11_bnpl_dim_ruta.sql` crea las
dos dims. La ruta ya fluye a `grouped_orders`, `loss_rates`, `grid_bnpl` y los cortes.

| Tabla | Filas | Tiempo |
|---|---|---|
| `redshift_bnpl.estructura_comercial` | 611,179 | 36.5 s |
| `redshift_bnpl.route_mapping` | 340 | 4.7 s |
| `redshift_bnpl.ruta_cliente_scd` | 13,885 | 92.8 s |
| `bnpl.dim_ruta_actual` | 611,179 | 9.1 s |
| `bnpl.dim_ruta_cliente_scd` | 13,885 | — |

**El SCD se comprime en Redshift, no en Postgres.** La vigencia diaria son 301M filas y 5.3M para
el universo BNPL; comprimida por cambio de ruta con window functions baja a 13,885 tramos de 10,713
clientes. Traer 5.3M filas por el túnel para comprimirlas después no tenía sentido.

### Cobertura lograda

| Medida | Resultado |
|---|---|
| Órdenes con ruta histórica | **98,841 de 98,854 (99.99%)** |
| Órdenes con ruta inferida | 13,248 — exactamente las de 2023 y 2024 |
| Clientes del grid con ruta vigente | 146,520 de 146,613 (99.94%) |
| Enrolados con ruta | 10,707 de 10,708 |
| Sales orders del corte semanal con ruta | 1,883 de 1,883, en 30 supervisores |

Verificado que ninguno de los joins duplica filas: los conteos de las nueve vistas quedaron
idénticos a antes de agregar las dims. Y el SCD no tiene intervalos solapados (0 casos).

**Para esto era la ruta histórica** — ya se puede medir mora por supervisor. Ejemplo: `SVLRY04`
(Los Reyes) tiene 6.68% de DQ 90+ sobre 2,202 órdenes, contra ~4.5% del promedio.

### Paridad de Propaga: validada, pero no contra el Excel

Las conciliaciones `revenue*.xlsx` **no existen en el proyecto**, así que la comparación planeada era
imposible. Se hizo algo mejor: contrastar `propaga_transaction` contra `payment_report`, que es la
fuente que el pipeline ya usaba.

| | Rabbit | Propaga | Δ |
|---|---|---|---|
| Monto financiado | $188,694,899 | $188,546,506 | 0.08% |
| Interés | $7,114,154 | $7,107,173 | 0.10% |

En agregado cuentan la misma historia. Fila por fila el interés coincide en 94.1% y el monto en
66.2% — diferencias de redondeo y de versión del registro (Propaga actualiza el documento; se toma
el último por `updatedAt`). Y Propaga aporta datos reales: de las 182 órdenes COMPLETED sin pago en
Rabbit, **rescata 118**.

### Ruta histórica vs vigente: cuál usa cada tabla

- `grouped_orders` y `loss_rates` → **histórica** (`dim_ruta_cliente_scd`, range join por
  `created_at`). La mora se atribuye a quien tenía la cuenta cuando se originó el crédito.
- `grid_bnpl` y los cortes → **vigente** (`dim_ruta_actual`). Ahí la pregunta es quién atiende la
  cuenta hoy.

### `tipo`: qué dicen los datos sobre organico/aliado

| tipo | Órdenes | DQ 90+ |
|---|---|---|
| PREVENTA | 77,466 | 4.10% |
| UNKNOWN | 10,083 | **7.29%** |
| ORGANICO | 4,303 | 4.28% |

PREVENTA es el 84% del volumen, así que si "aliado" del Excel legacy equivalía a PREVENTA, la
mayoría de los créditos serían de aliados. Sigue sin confirmarse (PENDIENTE 4). Dato aparte que
merece atención: los UNKNOWN mora 78% más que el resto.

---

## Detalle original de la Fase 4

**Dos dims de ruta, no una:**

- `bnpl.dim_ruta_actual` — transaccional. `catalog.cat_estructura_comercial_v3` +
  `catalog.route_mapping`. Para el grid y el corte semanal. Cobertura: 10,519 / 10,520 clientes.
- `bnpl.dim_ruta_cliente_scd` — histórica. **Decidido**: comprimir
  `catalog.cat_estructura_comercial_vigencia_diaria` por cambio de ruta →
  `[valido_desde, valido_hasta)`. **13,630 filas** para 10,519 clientes, cubre 2025-01-01 → hoy.
  Range join contra la fecha de creación de la orden, para atribuir la mora al supervisor que tenía
  la cuenta cuando se originó el crédito.
  - `catalog.catalog_clientes_historico` (semanal, desde 2025-11-01) queda como fuente de contraste.
    Si se usa: deduplicar (snapshots viejos vienen 2x–4x) y filtrar tres `fecha_inicio` futuras.
  - **Hueco**: dic-2023 a dic-2024 (~13,250 SOs, 14% del total) sin ruta histórica en ninguna fuente.
    Fallback a la ruta más antigua conocida del cliente, con flag `ruta_inferida`.

**Propaga**: extraer de `propaga-transaction-dev` y validar paridad contra un `revenue*.xlsx` de un
mes cerrado antes de retirar la carga manual.

**Pendiente menor**: el Excel legacy clasificaba `tipo` en organico/aliado; Redshift trae
ORGANICO / PREVENTA / UNKNOWN. Confirmar si aliado ≡ PREVENTA.

---

## Fase 5 — Orquestación y despliegue a la VM — **COMPLETADA 2026-08-12**

`main.py` es el único punto de entrada de la corrida desatendida y `run_pipeline.bat` lo que ejecuta
el Task Scheduler. Seis pasos: frescura → staging Mongo → estructura comercial → capa de negocio →
calidad → frescura final. Devuelve código 1 si algo falla, para que el scheduler lo reporte.

### El aborto es selectivo, no ante cualquier CRIT

Detenerse ante cualquier fuente en CRIT habría dejado el pipeline congelado indefinidamente:
`fintech-customers` lleva más de 480 horas sin escrituras y no va a recuperarse solo. Pero eso no
invalida la mora ni el revenue — solo deja a los clientes nuevos sin `shopName`.

`ops/config.py` → `FUENTES_CRITICAS` lista las tres cuya falta sí invalida el resultado:
`credit-order`, `payment-report` y `state-of-delivery`. Si una de esas está en CRIT el pipeline se
detiene antes de cargar nada; las demás solo generan una advertencia en el log y la corrida sigue.

### Decisiones

- **No hay `run_cortes.py` semanal.** Los cortes son vistas materializadas cuya ventana se calcula
  con `bnpl.ancla_corte()`, así que el refresh diario ya los deja al día. Un script aparte sería un
  segundo punto de entrada que mantener para nada.
- **La estructura comercial se puede omitir** con `--sin-redshift`: cambia por semanas, no por horas,
  y son ~2 de los 5-10 minutos de la corrida.
- **El log va a stdout, no a stderr.** PowerShell trata todo lo que llega por stderr como error y
  marcaba como fallida una corrida exitosa.
- **La tarea programada no puede correr como `SYSTEM`**: el túnel SSM necesita las credenciales AWS
  de un usuario real. Va con `/RU <usuario> /RP`.

### Presupuesto de tiempo — medido en la corrida end-to-end

**23.2 minutos** sin el paso de Redshift; ~26 con él. La estimación previa de 5–10 minutos era
incorrecta: solo contaba la ventana de `credit-order`, cuando el staging recarga las diez
colecciones.

| Paso | Tiempo |
|---|---|
| Staging Mongo (10 colecciones) | 21.8 min |
| Estructura comercial (Redshift) | 2.3 min |
| Capa de negocio (11 vistas) | 51 s |
| Calidad + frescura ×2 | 31 s |

Las más lentas: `fintech-customers` 221 s, `credit-order` 174 s (ventana), `payment-report` 156 s.
La capa de negocio completa cuesta menos de un minuto — el peso está en traer datos por el túnel, no
en calcular.

Por eso el plan pedía la tarea a las **05:30** y no a las 06:00: si el túnel SSM se pone lento (ya se
midió 2x de variación en la misma extracción), 26 minutos pueden volverse 40, y el refresh de Power BI
es a las 07:00.

**Corregido el 2026-08-14: la tarea quedó a las 07:30 CDMX** (`13:30` en el disparador, porque el reloj
de la VM está en UTC) y el refresh de Power BI pasó de las 07:00 a las **08:30**. La corrida estuvo un
rato en las 08:00, por decisión de negocio, y se adelantó media hora cuando quedó claro que contra un
refresh a las 08:30 eso dejaba **10 minutos** — exactamente el margen que el argumento de arriba dice
que el 2x de variación del túnel se come, y que el día de la recarga completa no alcanza. Con 07:30 el
margen es de 40 min en un día normal y 20 el de la recarga completa. El razonamiento no cambió; sólo se
movió media hora más tarde de lo que pedía el plan. Ver el bloque de despliegue del README.

### Optimización identificada, no implementada

`fintech-customers` tarda 221 s y **no recibe escrituras desde el 2026-07-23**. Recargarla completa
cada día es trabajo puro perdido. Con `source_freshness.last_write_mongo` y `etl_runs.started_at` ya
está toda la información para saltarse una tabla cuya fuente no escribió desde la última carga.

Ahorro en un día como hoy: ~4 minutos de 26. No se implementó porque el resto del tiempo es
irreducible — `payment-report` no se puede acotar por fecha (los pagos llegan hasta 519 días tarde) y
las demás colecciones sí escriben a diario.

## Migración de los datos a la VM — **COMPLETADA 2026-08-12**

`migrar_a_vm.py` copia los datos de la base local a `rabbit-bi-local` usando
`postgres_local_client` (COPY sobre túnel SSH). Cuatro pasos independientes: `--ddl`, `--datos`,
`--vistas`, `--validar`.

| Paso | Resultado |
|---|---|
| Tablas base copiadas | 17 tablas, **2,650,675 filas en 6.6 min** (~2.4 MB/s) |
| Capa de negocio | 11 vistas materializadas **en la VM**, 105 s |
| Validación | 17 de 17 tablas con conteo idéntico |

Totales de control, origen vs VM: revenue $1,023,125.91 = $1,023,125.91 · grid 146,613 = 146,613 ·
enrolados 10,708 = 10,708 · órdenes con ruta 98,841 = 98,841.

### Lo que no se copió, a propósito

Las **11 vistas materializadas de `bnpl` (663 MB)**. Son datos derivados: se recrean desde los `.sql`
y se materializan en la VM en 105 segundos. Mandarlas por el túnel habría sido transferir 663 MB
para obtener lo mismo que el servidor calcula solo. Solo viajaron las tablas base (856 MB).

También se omitió `mongo_bnpl.fintech_pre_authorization_status`, la tabla del nombre de colección
equivocado que la Fase 1 reemplazó — 0 filas.

### Tres cosas que la migración destapó

**1. La librería sí hace DDL, estaba apagado.** `postgres_local_client` soporta DDL controlado por
alias; `POSTGRES__local_rw__ALLOW_DDL` venía en `false` por el default seguro de la plantilla. Se
puso en `true` en `.env.postgres_local_client`. Eso habilita DDL para cualquier proceso que use ese
alias, no solo para esta migración.

**2. `redshift_bnpl` no tenía DDL y eso era un bug latente.** Sus tres tablas las creaba
`to_sql(if_exists="replace")` desde los dtypes de pandas. En local las fechas de Redshift llegaban
como `datetime` y quedaban `date`; en la VM llegaron como `object` y quedaron **`text`**, así que
`dim_ruta_cliente_scd` no compiló (`CASE types text and date cannot be matched`).

Se corrigió en los dos lados: `sql/12_redshift_staging.sql` con los tipos explícitos, y
`etl_redshift_to_postgres.py` ya no usa `replace` sino DDL + TRUNCATE + append. Sin ese segundo
cambio, la próxima corrida del ETL habría vuelto a crear las columnas como text y el error habría
regresado solo.

**3. Enteros con nulos rompen COPY.** `freshness_history.docs_staging` es `bigint`, pero pandas la
entrega como `float64` porque tiene NULLs, y COPY rechaza `"1110531.0"`. El migrador consulta los
tipos del destino y convierte esas columnas a `Int64` (entero nullable de pandas).

Además, cada tabla se vacía con TRUNCATE antes de cargarse: el primer intento murió a media copia
con una tabla ya escrita, y sin eso un reintento la habría duplicado.

### Lo que falta para que la VM sea autónoma

La migración resuelve el arranque, no la operación. Para que el pipeline corra allá hay que
verificar en la VM: credenciales AWS para el túnel SSM de Mongo, acceso a Redshift, y el `.env`
propio. El paso de verificación es `ops\check_freshness.py` — si corre en la VM, los tres accesos
están.

---

## Fase 6 — Power BI

`.pbix` repuntado de CSVs a PostgreSQL, On-Premises Gateway en la VM, refresh 07:00. Página de estado
del pipeline alimentada por `bnpl_ops.v_freshness_status`.

---

## Puntos abiertos

1. **Revenue de Rabbit: ¿14.2% sobre el interés con IVA o sin IVA?** 17.3% de diferencia. Decisión de
   negocio, hay que contrastar con el contrato de Propaga. Bloquea `revenue_comision`.
2. **La regla de intereses del legacy colapsa** a `rank == 1 AND createdAt >= 2024-04-22`. ¿Era esa la
   intención, o se perdieron ventanas de promoción? Bloquea `loss_rates`.
3. **LGD** — la proyección del vintage necesita un supuesto confirmado con riesgo.
4. **`fintech-credit-status-state-production` (31M docs)** — ¿entra? Si `payment-report` ya cubre la
   necesidad, no; si se necesita la curva de estados, requiere carga incremental.
5. **`clean_manual_validation.csv`** — no está en el proyecto. ¿Sigue vigente el override manual?
6. **`get_report()` con Selenium** del legacy — ¿qué campos aportaba y existen ya en Mongo/Redshift?
7. **Salidas** — ¿se siguen generando CSVs para el `.pbix` actual, o se corta directo a PostgreSQL?
   (el legacy escribía en latin1, y publicaba además a Slack, Google Sheets y SharePoint).
8. **VM** — ¿cuál es, y tiene ya Python, credenciales AWS y acceso a PostgreSQL? ¿El PostgreSQL
   destino es el local de tu máquina o uno en la VM?

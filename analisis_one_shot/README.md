# Análisis BNPL One-Shot

## ¿Qué hace este proceso?

Dos análisis cruzados entre la base de clientes de Rabbit y el programa BNPL:

### Análisis 1 — Clientes activos Rabbit vs uso BNPL
**Universo**: clientes con al menos 1 compra en los últimos 6 meses cerrados (>$10 MXN).  
**Segmentación por uso de BNPL**:

| Segmento | Condición |
|---|---|
| Con uso BNPL | `netsuite_id` tiene ≥1 orden en `credit_order_production` con status COMPLETED / CREATED / IN_DELIVERY |
| Enrollado sin uso | Aprobado en `fintech_credit_approval_production` pero sin órdenes activas |
| Sin BNPL | No aparece en `fintech_credit_approval_production` |

**Métricas por segmento**: clientes, pedidos, monto total, % del universo, drop size promedio.

---

### Análisis 2 — Línea de crédito vs drop size
**Universo**: todos los clientes aprobados en BNPL (`fintech_credit_approval_production`).  
- **Línea de crédito**: campo `creditLimit` de la colección de aprobaciones.  
- **Drop size**: `sum(monto_venta) / count(distinct sales_order_id)` en los últimos 6 meses cerrados desde Redshift.  
- Si el cliente no tiene órdenes en el período → `drop_size_6m = NaN`.  
- **Histograma** (PNG separado): conteo de clientes por rango de línea de crédito, bins de $1,000.

---

## Cómo ejecutar

Desde la raíz del proyecto BNPL:

```powershell
.venv\Scripts\python.exe analisis_one_shot\run.py
```

---

## Outputs generados

| Archivo | Contenido |
|---|---|
| `analisis_bnpl_one_shot.xlsx` | Excel con 3 pestañas (ver abajo) |
| `histograma_linea_credito.png` | Distribución de clientes BNPL por línea de crédito, bins $1,000 |
| `base_minima.csv` | Base completa SO-nivel, todos los activos Rabbit (>1M filas — usar en DBeaver / Power BI) |

### Pestañas del Excel

| Pestaña | Contenido | Filas |
|---|---|---|
| `Analisis 1 - Activos vs BNPL` | Resumen 3 segmentos + TOTAL | 4 |
| `Analisis 2 - LC vs DropSize` | Una fila por cliente BNPL: linea_credito + drop_size_6m | ~10,500 |
| `Base Minima (BNPL)` | Detalle SO-nivel, solo clientes BNPL enrolled | ~100K |

---

## Fuentes de datos

| Dato | Fuente | Tabla / Vista |
|---|---|---|
| Órdenes Rabbit | Redshift `data-rabbit-prod` | `analytics.mv_pedidos_enriquecidos_2025_v2` + `2026_v2` |
| Clientes aprobados BNPL | PostgreSQL `rabbit-bi-local` (alias `mongo_bnpl` de `postgres_local_client`) | `mongo_bnpl.fintech_credit_approval_production` |
| Órdenes BNPL | PostgreSQL local | `mongo_bnpl.credit_order_production` |

### Definición de ventana temporal

```
6 meses cerrados = [date_trunc('month', today - 1 day) - 6 months,
                    date_trunc('month', today - 1 day))
```

Con fecha de ejecución `2026-06-25` → `2025-12-01` a `2026-05-31`.

---

## Manejo de duplicados y calidad de datos

| Fuente | Problema conocido | Tratamiento en el código |
|---|---|---|
| `fintech_credit_approval_production` | Posibles múltiples aprobaciones por cliente (histórico) | `groupby(netsuite_id).max(creditLimit)` en `extract_bnpl_postgres.py` |
| `credit_order_production` | 1,425 filas con `salesOrderId = NULL` | `WHERE salesOrderId IS NOT NULL AND trim(salesOrderId) <> ''` |
| `credit_order_production` | 1 `salesOrderId` asignado a 2 `netsuiteId` | Se asigna al cliente con más pedidos totales (`drop_duplicates` por `sales_order_id`) |
| Redshift órdenes | Posibles SOs duplicados por SKU multi-fecha | `GROUP BY (netsuite_id, so_id, fecha_creacion)` + `drop_duplicates` post-fetch |

---

## Estructura de archivos

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

---

## Cómo modificar partes específicas

### Cambiar la lógica de línea de crédito
→ `analisis_2.py`, función `build_analisis_2()`.  
Por ejemplo: usar la línea de crédito original (pre-ajuste) en lugar de la vigente → cambiar
la fuente en `extract_bnpl_postgres.py` o agregar un campo en `get_enrolled_clients()`.

### Cambiar fuente o filtros de órdenes BNPL
→ `extract_bnpl_postgres.py`, función `get_bnpl_orders()`.  
Por ejemplo: incluir status `REJECTED`, o filtrar por canal de venta.

### Cambiar el período de análisis
→ `extract_redshift.py`, constante `SQL_ORDENES_6M_CERRADOS`.  
El intervalo está en la cláusula `WHERE`. Ejemplo de 12 meses:
```sql
fecha_creacion >= (date_trunc('month', current_date - 1)::date - interval '12 month')::date
```

### Cambiar la definición de "cliente activo"
→ `extract_redshift.py` (ventana temporal) + `analisis_1.py` (segmentación).  
La segmentación en `_asignar_segmento()` es independiente del período.

### Cambiar los bins del histograma
→ `exportar.py`, función `exportar_histograma()`.  
El step de los bins está en `range(0, bin_max + 1001, 1000)`. Cambiar `1000` por el step deseado.

### Cambiar los segmentos BNPL
→ `analisis_1.py`, función `_asignar_segmento()` y la lista `_SEG_ORDER`.

### Agregar métricas al Análisis 2
→ `analisis_2.py`, función `build_analisis_2()`.  
El drop size ya viene calculado en `_calcular_dropsize()`; agregar columnas ahí o en el merge.

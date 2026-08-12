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
| 3 | Tablas finales (PAR, vintage, grid, KPIs, revenue, cortes) | pendiente |
| 4 | Dimensiones de ruta y cierre de huecos | pendiente |
| 5 | Orquestación y despliegue a la VM | pendiente |
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

```powershell
# 1. ¿Están frescas las fuentes? Escribe bnpl_ops.source_freshness + freshness_history
.venv\Scripts\python.exe ops\check_freshness.py

# 2. ¿Hay problemas de calidad? Escribe bnpl_ops.data_quality_checks
.venv\Scripts\python.exe ops\quality_checks.py

# 3. Carga el staging
.venv\Scripts\python.exe etl_mongo_to_postgres.py
```

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

## Estructura

```
etl_mongo_to_postgres.py   Extracción Mongo → staging (10 colecciones)
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
- Las credenciales de los notebooks en `legacy/` estuvieron en texto plano en OneDrive. **Se deben
  considerar comprometidas y rotarse.**

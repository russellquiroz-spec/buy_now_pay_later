# Análisis de respaldo

Cada script de aquí responde **una pregunta concreta** que se tomó como decisión de diseño. No son
parte del pipeline: se corren a mano cuando hay que re-verificar algo o cuando alguien pregunta por
qué se decidió así.

Correr desde la raíz del proyecto:

```powershell
.venv\Scripts\python.exe analisis\<script>.py
```

| Script | Pregunta que responde | Conclusión (fecha de la medición) |
|---|---|---|
| `probe_fields.py` | ¿Qué campos existen de verdad en cada colección de Mongo? | Reveló los 6 defectos del ETL: `status`→`state`, `salesOrderId`→`orderId`, `approvalDate`→`createdAt`, etc. (2026-08-12) |
| `analisis_fuente_revenue.py` | ¿`payment-report` o `revenue-orders` es la fuente de verdad del revenue? | payment-report. revenue-orders tiene 48% de filas vacías, 6,367 duplicados y `comisionPorCobrar` 20x inflado (2026-08-12) |
| `analisis_revenue_def.py` | ¿Qué es exactamente `interests` vs `comisionPorCobrar`? | `comisionPorCobrar = interests × 1.16` (interés con IVA). Requiere `analisis_fuente_revenue.py` antes, que deja los parquets (2026-08-12) |
| `ventana_mutabilidad.py` | ¿Cuánto tiempo después de creado sigue cambiando un documento? | Órdenes: 17 días máximo. Pagos: hasta 519 días (recuperaciones de mora) (2026-08-12) |
| `dimensionar_ventana.py` | ¿Cuánto pesa cada ventana de reproceso? | 60 días = 8.3% de las filas. 91.4% del histórico es congelable (2026-08-12) |
| `unicidad_llaves.py` | ¿Qué llaves soportan PK y cuáles no? | 6 tablas soportarían PK; se decidió no poner ninguna en el staging (2026-08-12) |
| `tipos_actuales.py` | ¿Qué tipos infirió pandas y cuáles hay que corregir? | 6 columnas en bigint que debían ser double precision (2026-08-12) |
| `pagos_sin_orden.py` | ¿Qué son los 276 pagos que no cruzan con ninguna orden? | `transactionId` en formato UUID en vez de `SO…`, concentrados en 2024 (2026-08-12) |
| `rescate_pagos.py` | ¿Se recuperan por otra llave? | 193 de 276 con `marketplaceOrderId = credit_order.orderId`; 83 no cruzan por nada (2026-08-12) |
| `probe_cobertura_rutas.py` | ¿Redshift cubre las rutas del universo BNPL? | 10,519 de 10,520 clientes aprobados (2026-08-11) |
| `probe_rutas_cols.py` | ¿Qué columnas tienen los candidatos de dimensión de rutas? | `cat_estructura_comercial_v3` trae ruta, supervisor, oficina, region, tipo_cliente (2026-08-11) |
| `probe_hist_cobertura.py` | ¿Qué cobertura temporal tiene cada fuente de ruta histórica? | `catalog_clientes_historico` arranca 2025-11-01; `vigencia_diaria` arranca 2025-01-01 (2026-08-11) |
| `probe_scd_rutas.py` | ¿Cuánto pesa la dim de ruta histórica comprimida? | 13,630 filas para 10,519 clientes (2026-08-11) |
| `probe_tipo_cliente.py` | ¿`tipo_cliente` mapea al organico/aliado del Excel legacy? | Trae ORGANICO / PREVENTA / UNKNOWN — pendiente de confirmar (2026-08-11) |
| `medir_indices.py` | ¿Los índices del staging se usan? | La ventana y los lookups sí; el `NOT IN` de estados no finales no (2026-08-12) |
| `costo_indices_escritura.py` | ¿Cuánto cuestan los índices al cargar? | 1.8 s por 99K filas. Despreciable (2026-08-12) |

Las conclusiones detalladas, con los números completos, están en
[`plan_implementacion.md`](../.kiro/specs/migracion-pipeline-bnpl/plan_implementacion.md).

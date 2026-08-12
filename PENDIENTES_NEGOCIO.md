# Pendientes por confirmar con negocio — BNPL

Cosas que quedaron sueltas al portar el pipeline legacy. **Ninguna bloquea el desarrollo**: en cada
caso se implementó la opción que reproduce el layout/los números actuales, para no romper la paridad
con lo que hoy consume Power BI. Lo que falta es la confirmación de negocio; si cambia, se cambia la
constante en `config.py` y se re-materializa.

Última actualización: 2026-08-12

---

## 1. Comisión de Rabbit: ¿14.2% sobre el interés con IVA o sin IVA?

**Estado**: implementado con IVA (el que coincide con el layout final de `bnpl_loss_rates`).

El notebook legacy calcula el revenue de Rabbit de dos maneras distintas:

| Origen | Fórmula | Alimenta | Histórico |
|---|---|---|---|
| Celda 82 | `(totalAmountToPay − totalAmount) × 0.142` — interés **con** IVA | `bnpl_loss_rates.rabbitRevenue` | $1,023,550 |
| Celda 70 | `interests × 0.142` — interés **sin** IVA | `grid_bnpl.bnplRevenueShare` | $872,863 |

Diferencia: **$150,687 (17.3%)** sobre el histórico completo.

Existe además una tercera fórmula, `commission = totalAmount × 0.04` ($6.5M histórico), que se
calcula en la celda 70 pero no alimenta ninguna salida final.

**Qué confirmar**: qué dice el contrato con Propaga — si el 14.2% se aplica sobre el interés facturado
al tendero (con IVA) o sobre el interés neto (sin IVA). Y si el 4% sobre el monto financiado sigue
vigente o es código muerto.

**Dónde vive**: `config.py` → `RABBIT_REVENUE_SHARE = 0.142`, `RABBIT_COMMISSION_RATE = 0.04`.

---

## 2. Regla de exención de intereses: las fechas de septiembre y octubre no hacen nada

**Estado**: implementado tal cual el legacy (misma salida numérica).

La condición del notebook (celda 82) está escrita así:

```python
(rank == 1) & (((createdAt >= '2024-04-22') & (createdAt >= '2024-04-22'))
             | ((createdAt >= '2024-09-01') & (createdAt >= '2024-10-13')))  → interests = 0
```

La primera condición está duplicada consigo misma y la segunda es un subconjunto de la primera, así
que toda la expresión colapsa a:

```
rank == 1  AND  createdAt >= '2024-04-22'   →  sin intereses
```

Las fechas **2024-09-01 y 2024-10-13 no tienen ningún efecto** sobre el resultado.

**Qué confirmar**: si la regla vigente es realmente "el primer pedido de cada cliente desde el
2024-04-22 no paga intereses", o si hubo ventanas de promoción intermedias que se perdieron al
escribir la condición (por ejemplo, exención solo entre ciertas fechas, o para el 2º y 3er pedido).

**Impacto**: afecta el interés imputado de todos los primeros pedidos desde abril 2024, y con eso el
revenue reportado.

**Dónde vive**: `config.py` → `INTEREST_EXEMPTION_FROM = '2024-04-22'`, `INTEREST_EXEMPTION_RANK = 1`.

---

## 3. LGD para la proyección del vintage

**Estado**: sin implementar. El `vintage_analysis` se materializa sin la columna de proyección hasta
tener el supuesto.

El `design.md` menciona una proyección de pérdida (`LGD_SUPUESTO`) sobre el saldo en DQ 90+, pero el
valor nunca se confirmó con riesgo.

**Qué confirmar**: valor único o curva por meses de maduración. Con área de riesgo.

---

## 4. Clasificación organico / aliado

**Estado**: implementado con `tipo_cliente` de Redshift tal cual.

El `rutas_fintech.xlsx` legacy clasificaba cada cliente como `organico` o `aliado`. La fuente
equivalente en Redshift (`catalog.cat_estructura_comercial_v3.tipo_cliente`) trae
**ORGANICO / PREVENTA / UNKNOWN**.

**Qué confirmar**: si `aliado ≡ PREVENTA`, o si "aliado" era una clasificación propia de fintech que
no existe en el catálogo comercial. El Excel original ya no está en el proyecto, así que no hay con
qué contrastar.

---

## 5. Override de validación manual

**Estado**: no implementado. `grid_bnpl` sale sin la columna `validacion_manual`.

El legacy leía `clean_manual_validation.csv` para sobrescribir manualmente la validación de ciertos
clientes. El archivo no está en el proyecto.

**Qué confirmar**: si el override sigue vigente, quién lo mantiene y dónde vive el archivo.

---

## 6. `get_report()` con Selenium

**Estado**: no portado.

El pipeline legacy hacía scraping del backoffice con Selenium.

**Qué confirmar**: qué campos aportaba y si ya existen en Mongo o Redshift. Si existen, el scraping
se elimina; si no, hay que decidir si vale la pena mantener una dependencia de navegador.

---

## 7. Destinos de publicación

**Estado**: implementado solo a PostgreSQL (+ CSV para compatibilidad con el `.pbix` actual).

El legacy publicaba además a Slack, Google Sheets y SharePoint, y escribía los CSV en `latin1`.

**Qué confirmar**: si esas publicaciones siguen siendo necesarias. El CSV de CAC (`bnpl_cac.csv`)
dependía de un tracking en Google Sheets.

---

## 8. 83 pagos que no corresponden a ninguna orden

**Estado**: quedan fuera del join de `loss_rates` (no hay llave con la que cruzarlos).

Al unir `payment-report` con `credit-order` quedan 276 pagos huérfanos. 193 se recuperan uniendo
`marketplaceOrderId` contra `credit_order.orderId`, pero **83 no cruzan por ninguna llave**: su
`transactionId` es un UUID en vez de un `SO…` y el `marketplaceOrderId` no existe en las órdenes.

Se concentran en 2024 (217 de los 276 originales), bajan a 49 en 2025 y 10 en 2026 — parece un
formato antiguo que se fue corrigiendo.

**Qué confirmar**: si esos pagos corresponden a órdenes de otro canal, a ajustes manuales, o a
pedidos que se borraron. Importa porque incluyen pagos con `transactionStatus = 'paid'` (dinero
efectivamente cobrado) que hoy no se atribuye a ninguna venta.

---

## 9. `fintech-credit-status-state-production` (31M documentos)

**Estado**: fuera del pipeline.

Trae el estado del crédito por día (`date`, `currentState`, `creditStatusInfo`).

**Qué confirmar**: si se necesita la curva de estados para algún análisis. De entrar, requiere carga
incremental — no cabe un full reload.

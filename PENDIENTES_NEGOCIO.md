# Pendientes por confirmar con negocio — BNPL

Cosas que quedaron sueltas al portar el pipeline legacy. **Ninguna bloquea el desarrollo**: en cada
caso se implementó la opción que reproduce el layout/los números actuales, para no romper la paridad
con lo que hoy consume Power BI. Lo que falta es la confirmación de negocio; si cambia, se cambia la
constante en `config.py` y se re-materializa.

Última actualización: 2026-08-14

---

## Prioridad por impacto medido

Medido contra la base el 2026-08-14, no por orden de lista. "Cierra con datos" significa que la
consulta ya está corrida y la recomendación está abajo, en su sección; lo que queda es ejecutar.
Lo demás necesita que alguien decida.

| # | Pendiente | Impacto medido | Estado |
|---|---|---|---|
| §1 | Comisión 14.2% con o sin IVA | **$150,875** histórico, ~$7,500/mes de sobredeclaración | **Cerrado con datos** |
| §12 | Cuál es la tasa PAR oficial | dos gráficas con el **mismo título** muestran 6.0% y 31.3% | **Cerrado con datos** |
| §4 | `UNKNOWN` no es un tipo de cliente | **$564,570** de exceso de pérdida, 1,486 clientes | Medido; falta decidir |
| §2 | Exención de intereses del 1er pedido | **$507,328** de interés condonado, 9,031 clientes | Medido; falta confirmar |
| §3 | LGD del vintage | **$8.71M** en DQ 90+; recuperación observada 10% → **LGD ≈ 90%** | **Propuesta con datos** |
| §13 | `lossAmount` excluye `DQ 60-89` | **$308,974** (3.25% de la mora) | **Cerrado con datos** |
| §11 | CAC sin fuente | 8 cohortes / 821 clientes sin CAC — pero su página está **oculta** | **Cerrado con datos** |
| §10 · §15 | Modelo de riesgo | las 4 tablas alimentan **una sola página, oculta** | **Cerrado con datos** |
| §14 | Escalón de enero-2025 | el salto es **+14.5%**, no ~6% como decía este documento | **Cerrado con datos** |
| §8 | Pagos sin orden | **$1,139** de interés cobrado sin atribuir | **Cerrado con datos** |
| §5 §6 §7 §9 | Override manual, Selenium, destinos, credit-status | sin dato que los cierre | Decisión de negocio |
| §13b.1 | Quitar `PaidPrev` **no** era inocuo | **$1,684M** de venta bruta en 2 gráficas | **Corrige a §13** |
| §13b.2 | `Cumulative Deployed & Matured Capital` es saldo, no capital | 3 gráficas de *Salud del Portafolio* | Medido; falta decidir |
| §13b.3 | `PercentageOfAmountChargedOff` mezcla universos | numerador y denominador distintos | Medido; falta decidir |
| §13b.4 | Un filtro del grid tira $3.88M sin avisar | 1,747 pedidos fuera de la cadena | Medido; falta decidir |

Tres hallazgos nuevos que no estaban en la lista y valen más que varios de los pendientes:

1. **`dynamicTotalRevenue` está al revés** (ver §1). Elegir "Sin IVA" en el selector del Resumen
   Ejecutivo **sube** el Revenue Total 16%, porque el `SWITCH` compara contra etiquetas que la
   tabla del selector no contiene.
2. **39 órdenes de junio-2025 con `totalAmount = 0`** inflan `rabbit_revenue` en **$11,029**
   (ver §1). Es un defecto de `payment-report`, independiente de la discusión del IVA.
3. **El `mtime` de los archivos del Drive no sirve para medir frescura** (ver §15). `bnpl_cac.csv`
   tiene fecha 2026-06-10 y su contenido se detiene en la cohorte 2025-12.

---

## 1. Comisión de Rabbit: ¿14.2% sobre el interés con IVA o sin IVA?

**Estado**: implementadas **las dos**, lado a lado, en `bnpl.revenue_comision`
(`rabbit_revenue` con IVA y `rabbit_revenue_sin_iva` sin IVA). Ambas reproducen su cifra del legacy
con 0.04% de desviación, así que la decisión se puede tomar con los números a la vista. Cuando se
confirme cuál es la del contrato, se borra la otra columna.

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

### Resuelto con datos (2026-08-14): la base es el interés SIN IVA

Tres evidencias independientes, todas medidas, apuntan al mismo lado.

**1. Propaga desglosa el IVA en su propio registro.** `propaga_transaction` trae un campo
`iVAAmount` que no se estaba usando. Donde existe (34,953 filas, desde 2025-12, que es cuando
Propaga lo empezó a poblar):

```
iVAAmount = interests × 0.16       exacto en 21,827 filas; el resto cae en 0.1599–0.1602 por redondeo
interests + iVAAmount = totalAmountWithInterests − totalAmount     residuo promedio ≈ $1
```

O sea que para Propaga `interests` **es la base gravable** y el IVA es un traslado. Cobrar 14.2%
sobre el interés con IVA es cobrar comisión sobre el impuesto que Propaga entera al SAT.

**2. La misma identidad está en `payment-report`.** De las 92,999 órdenes cobradas con interés
positivo, el spread `totalAmountToPay − totalAmount` es exactamente `interests × 1.16` en **80,140**;
otras 1,537 traen spread = interés (sin IVA, son las viejas) y 3,871 traen ambos en cero.

**3. El tablero ya lo resolvió, y nadie lo había notado.** El modelo trae:

```dax
revenueAfterTaxes  = SUM(bnpl_loss_rates[rabbitRevenue]) / 1.16
revenueBeforeTaxes = SUM(bnpl_loss_rates[rabbitRevenue])
dynamicRevenue     = SWITCH(SELECTEDVALUE(revenue_view_selector[ViewType], "Sin IVA"), ...)
```

La página **Resumen Ejecutivo** muestra `dynamicRevenue`, cuyo valor por defecto es *Sin IVA* →
`rabbitRevenue / 1.16`. Es decir: **el negocio ya está leyendo la cifra sin IVA**, sólo que la
obtiene dividiendo la de con IVA en vez de calcularla en el origen.

**Recomendación**: quedarse con `rabbit_revenue_sin_iva` y retirar `rabbit_revenue`.

**Qué números se mueven**: la línea de revenue baja de **$1,024,912 a $874,036** (−$150,875,
−14.7% sobre el histórico). Por año: 2024 −$11,638, 2025 −$85,874, 2026 −$53,354 (a agosto). El
ritmo corriente es de **~$7,500/mes**. Ninguna otra medida del tablero depende de esa columna.

**No son idénticas las dos rutas.** `rabbitRevenue/1.16` del DAX da $883,544 y
`rabbit_revenue_sin_iva` del SQL da $874,036: **$9,508 de diferencia (1.09%)**, porque el ÷1.16
también divide las 1,537 órdenes que nunca llevaron IVA y las 39 anómalas de aquí abajo. Calcularlo
en el origen es lo correcto; el ÷1.16 en DAX debería quitarse junto con la columna.

### Defecto aparte: 39 órdenes de junio-2025 con `totalAmount = 0`

Al descomponer la diferencia aparecieron 39 órdenes cobradas (todas `SO15456xxx`/`SO15458xxx`, todas
de 2025-06) donde `payment-report` trae `totalAmount = 0` pero `totalAmountToPay` completo. El
spread queda siendo el pedido entero, **26.2 veces el interés**, y `rabbit_revenue` se infla
**$11,029** — el 7.3% de toda la diferencia con/sin IVA sale de esas 39 filas.

**Qué confirmar**: si ese lote de junio-2025 se cargó mal en `payment-report` y puede corregirse en
origen. Mientras tanto conviene excluir de `rabbit_revenue*` las filas con `total_amount = 0` y
`total_amount_to_pay > 0`. Avisa antes: mueve el revenue histórico $11,029 hacia abajo.

### Defecto aparte: el selector de IVA del Resumen Ejecutivo está invertido

```dax
dynamicTotalRevenue =
    VAR selectedView = SELECTEDVALUE('revenue_view_selector'[ViewType], "After Taxes")
    RETURN SWITCH(selectedView,
        "After Taxes",  SUM(bnpl_loss_rates[totalRevenue]) / 1.16,
        "Before Taxes", SUM(bnpl_loss_rates[totalRevenue]),
        SUM(bnpl_loss_rates[totalRevenue]))
```

La tabla `revenue_view_selector` sólo contiene **"Sin IVA"** y **"Con IVA"**. Ninguna de las dos
casa con `"After Taxes"` ni con `"Before Taxes"`, así que en cuanto alguien toca el slicer el
`SWITCH` cae al último argumento y devuelve el **bruto**. Sin selección, `SELECTEDVALUE` devuelve
su default `"After Taxes"` y sí divide.

Resultado: **elegir "Sin IVA" sube el Revenue Total 16%**. `dynamicRevenue` (la de Rabbit) sí está
bien escrita; la que está mal es la del revenue total. Se arregla cambiando las dos etiquetas del
`SWITCH` a `"Sin IVA"` / `"Con IVA"`.

### La comisión del 4% sigue sin explicación

`comision_sobre_monto` suma **$6,529,898** en el histórico: **7.5 veces** todo el revenue por
intereses. Si ese 4% fuera real, sería el negocio entero de BNPL y el tablero no lo muestra en
ningún lado. Sigue sin alimentar nada. Ver la pregunta redactada al final del documento.

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

### Medido (2026-08-14): la regla vale $507K; las fechas fantasma valen $28K

| | Órdenes | Clientes | Interés | Revenue Rabbit | Financiado |
|---|---|---|---|---|---|
| Exentas hoy (regla vigente) | 9,031 | 9,031 | **$507,328** | $72,041 | $15,469,583 |
| Dejarían de serlo si la exención arrancara el 2024-10-13 | 2,138 | — | $28,567 | $4,056 | — |

Un cliente, una orden exenta: los 9,031 son primeros pedidos distintos, así que la regla toca a
**9,031 tenderos**, el 97% de la base con crédito.

Lo importante del desglose: **las fechas fantasma casi no valen dinero**. Aunque la intención
original hubiera sido arrancar el 2024-10-13, sólo cambian 2,138 órdenes y **$28,567** de interés
—$13 por orden contra $56 de las demás— porque en 2024 la mayoría de los primeros pedidos venían ya
con interés cero desde Propaga. La pregunta de si `2024-09-01` y `2024-10-13` querían decir algo es
de higiene del código, no de dinero.

Lo que sí vale es la regla misma: **$507,328 de interés condonado**, $72,041 de comisión que Rabbit
no cobra. Ahí es donde conviene gastar la conversación.

---

## 3. LGD para la proyección del vintage

**Estado**: sin implementar. El `vintage_analysis` se materializa sin la columna de proyección hasta
tener el supuesto.

El `design.md` menciona una proyección de pérdida (`LGD_SUPUESTO`) sobre el saldo en DQ 90+, pero el
valor nunca se confirmó con riesgo.

**Qué confirmar**: valor único o curva por meses de maduración. Con área de riesgo.

### Propuesta con datos (2026-08-14): LGD ≈ 90%

No hace falta que riesgo lo invente: el histórico ya tiene la respuesta. Base expuesta hoy:
**4,103 órdenes, 3,403 clientes, $8,712,498**.

Curva de recuperación, agrupando las órdenes que alguna vez llegaron a 90+ días por cuánto tiempo
llevan vencidas:

| Antigüedad del vencimiento | Órdenes | Recuperadas | % monto recuperado |
|---|---|---|---|
| 3–4 meses | 166 | 3 | 1.09% |
| 4–6 meses | 339 | 16 | 4.56% |
| 6–9 meses | 644 | 58 | 7.91% |
| 9–12 meses | 814 | 63 | 6.28% |
| 12–18 meses | 1,378 | 79 | 6.15% |
| **18+ meses** | 1,107 | 126 | **9.96%** |

La recuperación se aplana alrededor del **10%** una vez que la orden tuvo tiempo de recuperarse.
De ahí sale **LGD = 0.90**.

Dos advertencias antes de tomarlo como verdad:

- No es una curva de cosecha: cada renglón son vintages distintos, no el mismo grupo seguido en el
  tiempo. El 9–12 y el 12–18 salen por debajo del 6–9, lo que sugiere que las cosechas viejas
  recuperaban mejor que las nuevas, no que la recuperación baje con el tiempo.
- Los tramos cortos están censurados por construcción: una orden de 3 meses todavía puede pagar.

**Recomendación**: llevar a riesgo `LGD = 0.90` como valor único y esta tabla como respaldo. Si
riesgo prefiere curva, el dato para construirla ya está y sólo hay que decidir el grano.

---

## 4. Clasificación organico / aliado

**Estado**: implementado con `tipo_cliente` de Redshift tal cual, en la columna `tipo`.

El `rutas_fintech.xlsx` legacy clasificaba cada cliente como `organico` o `aliado`. La fuente
equivalente en Redshift (`catalog.cat_estructura_comercial_v3.tipo_cliente`) trae
**ORGANICO / PREVENTA / UNKNOWN**. Lo que se ve en los créditos:

| tipo | Órdenes | DQ 90+ |
|---|---|---|
| PREVENTA | 77,466 | 4.10% |
| UNKNOWN | 10,083 | **7.29%** |
| ORGANICO | 4,303 | 4.28% |

**Qué confirmar**: si `aliado ≡ PREVENTA`, o si "aliado" era una clasificación propia de fintech que
no existe en el catálogo comercial. Importa porque PREVENTA es el 84% del volumen: si equivale a
aliado, casi todo el crédito va por ese canal. El Excel original ya no está en el proyecto.

**Hallazgo aparte que merece revisión**: los clientes con `tipo = UNKNOWN` mora un **78% más** que
el resto (7.29% vs ~4.1%). Son 10,083 órdenes. Vale la pena entender qué son antes de seguir
prestándoles igual.

### Medido (2026-08-14): el `UNKNOWN` cuesta $564,570

Actualizado contra la base, ahora también con dinero y clientes, no sólo órdenes:

| tipo | Órdenes | Clientes | Financiado | % órdenes DQ 90+ | Monto DQ 90+ | % monto DQ 90+ |
|---|---|---|---|---|---|---|
| PREVENTA | 77,594 | 7,454 | $148,341,025 | 4.10% | $6,869,068 | 4.63% |
| **UNKNOWN** | 10,095 | **1,486** | $19,334,607 | **7.29%** | $1,453,260 | **7.52%** |
| ORGANICO | 4,308 | 369 | $9,519,459 | 4.27% | $382,909 | 4.02% |
| (nulo) | 12 | 12 | $23,459 | 8.33% | $7,261 | 30.95% |

El exceso de pérdida del `UNKNOWN` contra todo lo demás (7.52% vs 4.60%) sobre sus $19.3M
financiados es de **$564,570**. Son **1,486 tenderos** que hoy reciben el mismo trato que el resto.

Esto pesa más que la pregunta original de `aliado ≡ PREVENTA`: la taxonomía es un tema de
etiquetas, pero medio millón de pesos de sobrepérdida concentrado en un grupo que ni siquiera está
clasificado es una decisión de crédito. Van juntas al mismo dueño, pero el orden importa.

---

## 4b. Las conciliaciones de Propaga en Excel no existen

**Estado**: la paridad se validó contra `payment_report` en vez del Excel, con mejor resultado.

El plan era comparar `propaga-transaction` contra un `revenue*.xlsx` de un mes cerrado. **Esos
archivos no están en el proyecto** (solo hay `data/input/Elegibles BNPL Abril 2026.xlsx`), así que se
contrastó contra la fuente que el pipeline ya usaba:

| | Rabbit | Propaga | Δ |
|---|---|---|---|
| Monto financiado | $188,694,899 | $188,546,506 | 0.08% |
| Interés | $7,114,154 | $7,107,173 | 0.10% |

**Qué confirmar**: si todavía existe algún `revenue*.xlsx` en SharePoint para un contraste adicional.
No es bloqueante — la validación contra `payment_report` es más relevante que contra un Excel viejo.

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

## 8. Los pagos que no corresponden a ninguna orden (157, de los que 15 son dinero cobrado)

**Estado**: quedan fuera del join de `loss_rates` (no hay llave con la que cruzarlos).

Al unir `payment-report` con `credit-order` quedan 276 pagos huérfanos. 193 se recuperan uniendo
`marketplaceOrderId` contra `credit_order.orderId`, pero **83 no cruzan por ninguna llave**: su
`transactionId` es un UUID en vez de un `SO…` y el `marketplaceOrderId` no existe en las órdenes.

Se concentran en 2024 (217 de los 276 originales), bajan a 49 en 2025 y 10 en 2026 — parece un
formato antiguo que se fue corrigiendo.

**Qué confirmar**: si esos pagos corresponden a órdenes de otro canal, a ajustes manuales, o a
pedidos que se borraron. Importa porque incluyen pagos con `transactionStatus = 'paid'` (dinero
efectivamente cobrado) que hoy no se atribuye a ninguna venta.

### Medido (2026-08-14): son $1,139 de interés. Es el último de la lista

Primero, **el 83 de arriba no reproduce**. Contado hoy contra las mismas llaves:

| Definición | Pagos |
|---|---|
| No cruzan por `transactionId` | 276 |
| No cruzan por **ninguna** de las dos llaves | **157** |
| …y además no están cancelados | 32 |

Los 157 se reparten así:

| `transactionStatus` | Pagos | Financiado | Interés | Rango |
|---|---|---|---|---|
| cancel | 125 | $188,077 | $7,132 | 2024-01 → 2025-05 |
| on-hold | 17 | $33,096 | $1,289 | 2025-06 → 2026-08 |
| **paid** | **15** | **$28,472** | **$1,139** | 2024-05 → 2026-07 |

Los cancelados no son dinero cobrado y los `on-hold` tampoco. Lo único que de verdad es "dinero
que entró y no se atribuye a ninguna venta" son **15 pagos, $28,472 financiados, $1,139 de
interés**, repartidos en 6 meses distintos a lo largo de dos años (máximo 6 pagos en un mes).

**Recomendación**: bajarlo al fondo de la lista. No amerita reunión; si alguien tiene cinco minutos
puede mirar los 15, pero no hay decisión que dependa de esto. El "83" del diagnóstico original no
se pudo reproducir con ninguna de las tres definiciones de llave; queda corregido a 157 / 15.

---

## 9. `fintech-credit-status-state-production` (31M documentos)

**Estado**: fuera del pipeline.

Trae el estado del crédito por día (`date`, `currentState`, `creditStatusInfo`).

**Qué confirmar**: si se necesita la curva de estados para algún análisis. De entrar, requiere carga
incremental — no cabe un full reload.

---

## Reportar a ingeniería: diciembre-2023 corrupto en `mv_pedidos_enriquecidos_2023`

**No es un pendiente de negocio sino un bug de una fuente de Redshift**, pero se anota aquí porque
afecta cualquier análisis de cosechas o de venta Rabbit que cruce ese mes.

`analytics.mv_pedidos_enriquecidos_2023` trae diciembre-2023 con monto y cantidad inflados ~25x,
con el mismo número de líneas que los meses vecinos. Medido:

| mes | líneas | monto promedio/línea | piezas promedio/línea |
|---|---|---|---|
| 2023-10 | 1,595,123 | $130.2 | 6.31 |
| 2023-11 | 1,573,946 | $162.6 | 8.26 |
| **2023-12** | 1,352,053 | **$4,012.3** | **163.11** |

El mes solo suma $5,425M cuando los demás van entre $120M y $256M. No son outliers sueltos: es
todo el mes, y la tabla equivalente en `analytics_beta` está peor ($10,278M).

Que el CSV histórico `bnpl_cosecha_agg.csv` ponga 2023 en $2,113M — coherente con $1,071M en 2022
y $3,287M en 2024 — confirma que la corrupción es posterior a cuando se generó ese archivo.

**Mientras no se corrija**, las consultas de cosechas dividen ese mes entre 20. Es un parche
acordado con negocio, no un valor derivado: la razón medida contra noviembre es 24.7x en monto y
19.7x en piezas. Al corregirse la fuente hay que quitar el `/ 20.0`.

**Qué confirmar**: quién es dueño de esas vistas y si puede recargarse diciembre-2023.

**Revisado el 2026-08-14: sigue igual.** Vuelto a medir contra Redshift hoy, los números no se han
movido ni un peso — $4,012.3 por línea contra $162.6 de noviembre (24.7×) y 163.11 piezas contra
8.27 (19.7×). Nadie ha tocado la vista. El parche `/ 20.0` sigue siendo necesario y sigue sin ser
un valor derivado. Han pasado dos meses desde que se reportó.

---

## 10. Modelo de riesgo BNPL: qué se reprodujo y qué falta confirmar

Las cuatro tablas de odds/IV del tablero (`odds_table`, `vars_and_iv`, `odds_combinations`,
`atr_combinations_iv`) no eran extracciones sino la salida de un análisis de WOE/IV. Se
recuperaron sus fórmulas del CSV original, al dígito:

```
%good = good / Σgood   (dentro del corte rango × flag)
%bad  = bad  / Σbad
woe   = ln(%bad / %good)        ← invertido respecto a la convención habitual
iv    = (%bad − %good) × woe
```

Lo de invertido importa: con `ln(%good/%bad)` el signo sale al revés en las 18 filas.

`sql/pbi/12_odds_table.sql` y `13_vars_and_iv.sql` ya reproducen las dos tablas chicas en SQL.
Quedan tres cosas por confirmar con quien lleve el modelo.

### 1. El corte del bin está congelado

El CSV parte la distancia onboarding-tienda en dos bins con un corte distinto por rango:
**8.98 m** para el rango 1, **8.31** para el 2 y **7.24** para 3+. O sea que el original lo
derivaba de los datos — un split supervisado, no un cuantil fijo. Esos tres números están
congelados en el CTE `cortes` de ambas consultas.

**Qué confirmar**: si el corte debe recalcularse en cada corrida o quedarse fijo. Si se
recalcula, esto deja de ser una consulta y vuelve a ser modelo.

### 2. `odds_combinations` y `atr_combinations_iv` no se reprodujeron

Son 84,986 y 468 filas de combinaciones por pares de 11 atributos. Las fórmulas son las mismas de
arriba, pero el binning no se puede recuperar: cambia por cada corte (el mismo atributo aparece
como `'0.0_6.22'`, `'0.0_7.06'` y `'0.0_7.6'` según el slice), `shopTown` entra con 647 valores y
las filas de `ruta` traen el bin vacío.

**Además tres de los 11 atributos están rotos en origen**, así que buena parte de esas
combinaciones son degeneradas:

- `previousFintechProductToBnpl` y `psrtaPreviousToBnpl` son constante `0` — nunca se calcularon.
- `grossSalesVolume3Months` es **idéntica** a `grossSalesVolume6Months` en el 100% de las filas.

**Qué confirmar**: si el modelo de riesgo sigue vivo. Reconstruir 85 mil filas de combinaciones
con tres variables inservibles dentro solo tiene sentido si alguien las está usando. Mientras
tanto esas dos tablas siguen leyendo su CSV.

### 3. `ps_transactional_profile`: los buckets sí, las etiquetas de fraude no

Tiene seis perfiles. Tres son conteos de transacciones (`2 to 3 TX`, `4 to 10 TX`,
`More than 10 TX`) y salen directo de contar `fintech.transactions_ps` en Redshift. Los otros tres
—`01-Enrolled`, `02-Potential Fraud`, `03-Mostly Fraud`— necesitan una regla que no está en el
archivo, y son justo los que alimentan `crossFraudFlag` en la página Fraud.

**Qué confirmar**: la regla que separa "Potential Fraud" de "Mostly Fraud" en Pago de Servicios.

### Resuelto con datos (2026-08-14): las cuatro tablas de riesgo alimentan una sola página, y está oculta

Recorrido el `.Report` visual por visual, las cuatro tablas se consumen exactamente en un lugar:

| Tabla | Páginas que la usan |
|---|---|
| `odds_table` | Default Customer Profile — **HiddenInViewMode** |
| `vars_and_iv` | Default Customer Profile — **HiddenInViewMode** |
| `odds_combinations` | Default Customer Profile — **HiddenInViewMode** |
| `atr_combinations_iv` | Default Customer Profile — **HiddenInViewMode** |

`HiddenInViewMode` significa que quien abre el reporte publicado **no ve esa página**: sólo aparece
para quien edita. De 15 páginas del tablero, 12 son visibles; las ocultas son *Default Customer
Profile*, *Return On Investment* y *Search*. (La 15ª es la portada *Cómo leer este tablero*.)

**Qué se simplifica al quitarlas**: el modelo baja de **18 orígenes externos a 14**, se dejan de
cargar a mano **85,454 filas** de espejo (84,986 + 468), y desaparece la pregunta §10.1 del corte
congelado del bin, porque `odds_table` y `vars_and_iv` sólo existen para esa página. No se toca
ninguna cifra de ninguna página visible.

**Cuidado con qué NO se puede quitar.** `loans_matured_default_profile` la usan *Default Customer
Profile* **y** *Fraud*, que sí es visible. Y `ps_transactional_profile`, aunque no aparece en
ningún visual, alimenta la columna DAX `psTransactionalProfile` → `crossFraudFlag`, que la página
Fraud sí muestra:

```dax
crossFraudFlag = SWITCH(TRUE(),
    [psTransactionalProfile] = "03-Mostly Fraud" && [fraudFlag] == "Potential Fraud", 1, 0)
```

Hoy **584 clientes BNPL** (5,142 órdenes, **$11,050,504** financiados) traen perfil
`03-Mostly Fraud` y por lo tanto son candidatos a `crossFraudFlag = 1`. Esa tabla se queda.

**Recomendación**: separar las dos decisiones. Quitar las 4 tablas de odds/IV es barato y no rompe
nada visible — la pregunta a riesgo es sólo si van a volver a abrir esa página. Mantener
`ps_transactional_profile`, que sí se usa, y perseguir aparte la regla de fraude de §10.3.

### Cobertura de `ps_transactional_profile`: 40% de los clientes BNPL no tiene perfil

De los 9,283 clientes con crédito, **3,751 no cruzan** contra el archivo. `LOOKUPVALUE` devuelve
BLANK y `crossFraudFlag` queda en 0: quedan clasificados como no-fraude sin que nada lo advierta.

Separando por si se enrolaron antes o después del corte del archivo (2026-01-08):

| Grupo | Clientes | Con perfil | Cobertura |
|---|---|---|---|
| Enrolados antes del corte | 8,478 | 5,197 | 61.3% |
| Enrolados después | 805 | 335 | 41.6% |

La caída de 61.3% a 41.6% es lo que cuesta que el archivo esté viejo: **unos 160 clientes**. El
resto de la brecha no es obsolescencia — son tenderos que simplemente no usan Pago de Servicios, y
para ésos el perfil nunca va a existir. Conviene decidir si "sin perfil" debe pintarse distinto de
"con perfil limpio" en la página Fraud.

---

## 11. `bnpl_cac`: no hay fuente para el CAC

`bnpl_cac.csv` da el costo de adquisición por cohorte de enrolamiento. Es gasto de marketing
dividido entre clientes enrolados, y **el gasto no vive en ninguna fuente del pipeline** — ni en
Mongo, ni en Redshift, ni en la capa `bnpl`. Hoy es captura manual.

Alimenta la columna `cac` de `bnpl_loss_rates` y la página Return On Investment.

**Qué confirmar**: quién publica el gasto de marketing de BNPL y con qué periodicidad. Con eso se
puede volver una tabla en `bnpl_ops` y versionarla; sin eso seguirá siendo un CSV a mano.

### Medido (2026-08-14): lleva 8 meses sin actualizarse, y su página está oculta

`archivos_bnpl.bnpl_cac` tiene **25 cohortes, de 2023-12 a 2025-12**. Las cohortes reales de
enrolamiento van hasta **2026-08** y son 33.

| | Cohortes | Clientes | Financiado |
|---|---|---|---|
| Con CAC (≤ 2025-12) | 25 | 8,457 | $171,105,699 |
| **Sin CAC (2026-01 en adelante)** | **8** | **821** | $6,103,912 |

O sea que el CAC no se publica desde diciembre de 2025 y hay 8 cohortes con 821 tenderos sin costo
de adquisición. **El archivo en el Drive tiene fecha 2026-06-10**, lo que sugeriría que se
republicó hace dos meses; el contenido dice que no. Ver §15.

**Pero**: la única página que consume `bnpl_cac` —vía la tabla calculada `CacTable`— es *Return On
Investment*, y está **HiddenInViewMode**. Nadie que abra el tablero publicado ve el ROI, así que
nadie ve el hueco.

**Recomendación**: preguntar primero si la página de ROI va a volver a abrirse. Si la respuesta es
que no, esto deja de ser un pendiente y las dos —tabla y página— se borran. Si es que sí, entonces
sí hay que conseguir la fuente del gasto, y de paso rellenar las 8 cohortes faltantes antes de
volver a publicarla. Es la pregunta barata antes de la cara.

---

## 12. Dos definiciones de la tasa PAR conviven, y difieren 6.4x

En el vintage hay dos cifras que se llaman "la tasa PAR30" y no son la misma:

| Dónde vive | Fórmula | Resultado histórico |
|---|---|---|
| Columna `par30Rate` (de `bnpl.vintage_analysis`, y del CSV antes) | `PAR30 / outstandingBalance` | **38.4%** |
| Medida `par30RateAmount` (la que usan los visuales) | `SUM(PAR30) / SUM(deployedCapital)` | **6.0%** |

El saldo vivo son $276M y el capital desplegado $1,760M: de ahí la diferencia. El tablero muestra
la segunda, así que las seis columnas de tasa que trae la tabla (`par30Rate`, `par60Rate`,
`par90Rate` y las tres de clientes) están ahí sin que nadie las consuma.

No estorban — son 530 filas — pero si alguien cita "el PAR30 del vintage" conviene saber cuál de
las dos está leyendo.

**Qué confirmar**: cuál es la tasa que el negocio considera oficial. Si es la de capital
desplegado, las columnas de la vista sobran y se pueden borrar; si es la de saldo vivo, las
medidas del tablero están midiendo otra cosa.

### Resuelto con datos (2026-08-14): no son dos, son tres — y dos compartían título en la misma página

Medido sobre `bnpl.vintage_analysis` (530 filas):

| Nombre | Fórmula | Valor | ¿Lo consume algún visual? |
|---|---|---|---|
| Columna `par30_rate` | PAR30 / outstandingBalance | **38.42%** | **No** |
| Medida `par30RateAmount` | Σ PAR30 / Σ deployedCapital | **6.02%** | Sí |
| Medida `par30RateCustomers` | Σ PAR30N / Σ everActivated | **31.30%** | Sí |

La tercera es la que faltaba en el diagnóstico original. Y lo grave es dónde vive:

En la página **Vintage Analysis** —visible— hay **dos gráficas de línea, lado a lado**
(x=286 y x=926, misma altura) que hasta el 2026-08-14 **se titulaban exactamente igual** y sólo se
distinguían por el subtítulo. Ya están renombradas: hoy son
`PAR 30+ Rate per Enrollment Cohort (over Deployed Capital)` y
`PAR 30+ Rate per Enrollment Cohort (over Activated Customers)`.

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

Quien mire la de la izquierda concluye "estamos a 1.7× del break-even". Quien mire la de la derecha
concluye "estamos a **7.8×** del break-even". Era el mismo título, la misma página, la misma junta.

**El umbral de la derecha casi seguro está mal.** Un umbral de 4% tiene sentido como fracción de
capital desplegado; como fracción de clientes activados no, porque esa serie no ha estado por
debajo de 4% en ninguna cohorte madura. Se ve como un copiar-pegar del umbral de la gráfica de al
lado.

**Y la brecha se está abriendo.** No es una diferencia estable:

| Alcance | PAR30 | Saldo vivo | Capital desplegado | Tasa saldo | Tasa capital | Razón |
|---|---|---|---|---|---|---|
| Histórico | $106,023,386 | $275,964,858 | $1,760,170,361 | 38.42% | 6.02% | 6.38× |
| **Último corte** | $9,275,500 | $18,066,154 | $170,021,493 | **51.34%** | **5.46%** | **9.41×** |

**Recomendación**, en tres pasos y de menor a mayor riesgo:

1. ~~**Renombrar las seis gráficas de tasa**, no dos~~ — **hecho el 2026-08-14.** El problema se
   repetía idéntico en PAR 60 (`18f1d6ffead214e615a8` sobre capital vs `5a0d21450822b2cc87ac` sobre
   clientes) y en PAR 90 (`8a726824316a777192ae` vs `75ae87cd796169d70244`). En los tres pares las
   dos gráficas nombraban la serie exactamente igual (`nativeQueryRef` y `displayName` en :102-103),
   así que ni el eje ni el tooltip las distinguían; el subtítulo sí. Hoy las seis se llaman
   `PAR NN+ Rate per Enrollment Cohort (over Deployed Capital)` y `(over Activated Customers)`, y la
   serie de cada una lleva el sufijo correspondiente. No cambió ninguna cifra.
2. **Revisar el BEP de 4%** de la gráfica de clientes con quien lo definió. Si no hay quién lo
   sostenga, quitar la línea: una referencia sin dueño es peor que ninguna.
3. **Borrar las 6 columnas de tasa** de `bnpl.vintage_analysis` (`par30_rate`, `par60_rate`,
   `par90_rate` y las tres de clientes). Ningún visual las lee y son la fuente del 38.42% que no
   corresponde a nada de lo que se muestra. Son 530 filas: no estorban al rendimiento, estorban a
   la conversación.

---

## 13. Dos defectos del modelo que la migración dejó a la vista (y una falsa alarma)

Ninguno lo causa el cambio de origen: ya estaban. Se listan porque ahora hay quien los pueda
arreglar. El tercero que aparecía aquí —el visual apuntando a un campo inexistente— se revisó el
2026-08-14 y **no era un defecto**; el detalle está más abajo.

**`lossAmount` excluye un bucket por un error de dedo.** En `bnpl_loss_rates`:

```dax
lossAmount = IF(bnpl_loss_rates[PAR] IN {"DQ 15-29", "DQ 30-59", "60-89", "DQ 90+"}, ...)
```

Dice `"60-89"` en vez de `"DQ 60-89"`, así que ese bucket nunca entra en el monto de pérdida. Hoy
son 128 órdenes.

**Medido (2026-08-14): son $308,974, el 3.25% de la mora.**

| PAR | Órdenes | Monto | % del total en mora |
|---|---|---|---|
| DQ 15-29 | 65 | $145,926 | 1.54% |
| DQ 30-59 | 135 | $328,373 | 3.46% |
| **DQ 60-89** | **128** | **$308,974** | **3.25%** |
| DQ 90+ | 4,103 | $8,712,498 | 91.75% |

Arreglar el typo sube `lossAmount` **$308,974 (+3.4%)**. Es la corrección más barata de toda la
lista: un carácter en una fórmula DAX, sin tocar el pipeline. Como `DQ 90+` concentra el 91.75%,
el orden de magnitud de la pérdida no cambia — pero la cifra deja de estar mal.

**Corrección: el visual del eje Y sí funciona.** Este documento decía que un `lineChart` de
*Vintage Analysis* apunta a `vintage_analysis[par30Cumulative]`, un campo inexistente, y que por eso
"sale vacío o marcando error". Revisado el JSON del visual, no es así:

```json
"Y": { "projections": [ {
    "field": { "Measure": { "Expression": { "SourceRef": { "Entity": "vintage_analysis" } },
                            "Property": "par30RateAmount" } },
    "queryRef": "vintage_analysis.par30Cumulative",
    "nativeQueryRef": "PAR 30+ Rate" } ] }
```

El campo enlazado es la **medida `par30RateAmount`**, que sí existe (`vintage_analysis.tmdl:4`).
`par30Cumulative` aparece únicamente como `queryRef` —el alias con el que se nombra la proyección—
y no figura en ningún `.tmdl`. Es un nombre viejo que quedó pegado cuando se cambió la medida, no
un enlace roto: la gráfica es la de `PAR 30+ Rate per Enrollment Cohort (over Deployed Capital)`
(`0ff2052f3312e68375b0`) de §12, y dibuja el 6.02%.

Vale limpiar el `queryRef` para que no vuelva a confundir a quien lea el modelo, pero **no hay
nada que decidir sobre qué debería mostrar** y no hay visual en blanco en el tablero. Este punto
sale de la lista de pendientes.

**`PaidPrev` no está en `dq_order`.** El 85.9% de las filas de `bnpl_par` y `months_closes` traen
ese bucket, que no existe entre los 8 valores de la tabla `dq_order`, así que caen en la fila en
blanco de esa relación. Es inocuo para los montos — su `totalAmount` suma exactamente $0.00 porque
`par_snapshot` lo pone en cero a propósito — pero aparece como categoría en el slicer.

Se puede arreglar agregando `{"PaidPrev", 0}` al `DATATABLE` de `dq_order`, o filtrando esas filas
en las consultas 03 y 04 (el filtro ya está escrito y probado en el encabezado de la 04, sin
activar). Hoy no cambia ninguna cifra.

---

## 13b. Lo que salió al documentar los 168 visuales (2026-08-14)

Al escribir el texto de ayuda de cada gráfica hubo que leer su DAX y sus filtros uno por uno.
Cuatro cosas no estaban en esta lista y **una corrige lo que decía §13**.

### 1. Quitar `PaidPrev` NO es inocuo: mueve $1,684M en una gráfica

§13 dice que filtrar `PaidPrev` "no cambia ninguna cifra" porque su `totalAmount` suma $0.00.
Eso es cierto **solo para las gráficas de saldo**. Medido contra la base:

| `PAR` | Filas | Σ `totalAmount` | Σ `orderGrossSales` |
|---|---:|---:|---:|
| **PaidPrev** | 911,713 | **$0.00** | **$1,683,728,100** |
| Resto | 149,407 | $292,672,054 | $296,701,953 |

`par_snapshot` pone en cero el **saldo**, no la **venta bruta**. Y en *Salud del Portafolio* hay dos
gráficas —*Active Portfolio by Month and Delinquency Bucket*, en barras y en 100%— que suman
`orderGrossSales`, no `totalAmount`. Ahí `PaidPrev` es el **88%** de lo que se dibuja.

**Consecuencia**: el `WHERE p.par <> 'PaidPrev'` que viene escrito y sin activar en el encabezado de
`sql/pbi/04_months_closes.sql` **no se puede activar tal cual** para la 03. Sobre `months_closes`
(que solo se consume con `Sum(totalAmount)`) sí es inocuo; sobre `bnpl_par` vaciaría esas dos
gráficas.

**Qué confirmar**: si esas dos gráficas quieren decir "toda la venta financiada que existió en cada
mes" (entonces `PaidPrev` debe quedarse y el título es correcto) o "la venta que seguía viva en cada
mes" (entonces sobra, y hay que quitarla del filtro y no del origen).

**Aplicado mientras tanto**: se agregó `{"PaidPrev", 0}` al `DATATABLE` de `dq_order`, que era la
acción ya aprobada en *Lo que se puede ejecutar sin preguntarle a nadie*. Con eso esas filas dejan de
caer en la fila en blanco de la relación y aparecen con su nombre y al principio del orden. No mueve
ninguna cifra.

### 2. `Cumulative Deployed & Matured Capital` no es capital desplegado

Tres gráficas de *Salud del Portafolio* dividen entre la medida `closeMonthDenominator`:

```dax
closeMonthDenominator = CALCULATE(SUM(months_closes[totalAmount]),
                                  ALLEXCEPT(months_closes, months_closes[corte]))
```

Es la suma del **saldo** de todas las filas del mismo corte. El nombre que se le puso a la
proyección en el visual —y que sale en la leyenda y en el tooltip— dice *Deployed Capital*, que es
otra cosa ($1,760M contra $276M). Es el mismo problema de §12 pero en otra página: ahí eran dos
gráficas con el mismo título, aquí es un denominador con nombre de otro.

**Qué confirmar**: junto con §16.5, cuál es la tasa oficial. Si es sobre capital desplegado, estas
tres gráficas no la están midiendo.

### 3. `PercentageOfAmountChargedOff` mezcla dos universos

En la tarjeta de roll rates de *Salud del Portafolio*:

```dax
AmountOfDisbursedLoans      = CALCULATE(SUM(...[totalAmount]), ...[stage] = "Ongoing")
AmountOfPaidLoans           = SUMX(DISTINCT(FILTER(..., ...[lead_stage] = "Paid")), ...[totalAmount])
PercentageOfAmountChargedOff = 1 - ([AmountOfPaidLoans] / [AmountOfDisbursedLoans])
```

El denominador son los pedidos **que aún no vencen** (`stage = "Ongoing"`) y el numerador los que
**pasaron a pagado**. No son el mismo conjunto, así que el cociente no es una tasa de castigo.
`PercentageOfLoansChargedOff`, la de conteo, sí compara contra el total de pedidos.

**Qué confirmar**: qué debía medir esa tarjeta. Si es "del capital que ya venció, cuánto no se
pagó", el denominador tendría que ser el capital maduro, no el vigente.

### 4. Un filtro del grid tira $3.88M sin avisar

`months_closes` **sí** se filtra con los slicers de oficina, ruta, edad y género, pero no por su
relación directa con `grid_bnpl` (que está inactiva) sino por la cadena
`grid_bnpl → loans_matured_default_profile → months_closes`. `loans_matured_default_profile` solo
tiene los pedidos ya vencidos:

| | |
|---|---:|
| Filas de `months_closes` alcanzables por la cadena | **99.84%** |
| Pedidos que se caen al aplicar cualquier filtro del grid | 1,747 |
| Saldo que se cae con ellos | **$3,879,320** |

Sin filtro se ven $292.7M; con cualquier filtro del grid el universo baja a $288.8M **antes** de
aplicar el filtro en sí. No es un error de nadie —es cómo quedó la cadena de relaciones— pero
explica diferencias que hoy nadie sabe de dónde salen.

**Qué confirmar**: si conviene activar la relación directa `months_closes[netsuiteId] →
grid_bnpl[netsuiteId]` y desactivar el paso por `loans_matured_default_profile`. Es un cambio de
modelo, no de origen, y hay que revisar que no rompa las medidas que hoy cuelgan de esa cadena.

---

## 14. Tres decisiones que tomé en la migración y conviene ratificar

Están implementadas y medidas, pero cambian números respecto al CSV original.

**Audiencias: `Nuevo` se ancla al mes corriente, no al anterior.** La regla de Rabbit
(`clasificacion_mensual_clientes`) define `Nuevo` como *activo y primera compra el mes anterior*.
Aplicada a BNPL deja diciembre-2023 —el primer mes del producto— con cero Nuevos, y el CSV real
tiene 11. Contrastado sobre los meses estables:

| Ancla | Error en clientes | Error en gross |
|---|---|---|
| mes anterior (regla Rabbit) | 28.6% | 36.8% |
| **mes corriente (implementada)** | **11.0%** | **6.7%** |

Tiene sentido: en Rabbit un cliente lleva meses comprando antes de que lo clasifiques, pero en
BNPL el alta y la primera compra son casi el mismo evento. **Qué confirmar**: si se prefiere
paridad estricta con la regla Rabbit, es cambiar una línea en `sql/pbi/07_bnpl_audiencia_agg.sql`.

**Cosechas pierde la segmentación por oficina y ruta.** La tabla pasa de 22 a 11 columnas: se van
`canal_venta`, `oficina`, `route_name` y los seis desgloses `_bnpl`/`_ff`. Se verificó que ninguna
medida ni visual los usa. Quitarlos además **arregla** un conteo: con las dimensiones del pedido en
la llave, un cliente que compró por dos canales el mismo mes se contaba dos veces en
`cliente_activo` y en `clientes_cosecha`, y `supervivencia` es el cociente de esas dos sumas.
**Qué confirmar**: si alguien va a querer segmentar cosechas por oficina, hay que rehacer el
extract y definir antes qué significa `clientes_cosecha` en ese grano.

**El monto tiene un escalón en enero-2025.** De 2025 en adelante se usa
`amount_completed + amount_in_progress` (venta surtida) y antes `monto_venta` (venta ordenada),
porque el desglose solo existe en las tablas `_v2`. Afecta a `cosechas_agg`, `ventas_cliente` y
`estacionalidad_mes`. **Qué confirmar**: si se prefiere `monto_venta` en toda la serie —continua
pero ~6% arriba de lo que mide el resto del pipeline— o el escalón.

**Medido (2026-08-14): el escalón es +14.5%, no ~6%.** Comparadas las dos definiciones sobre las
mismas filas de `analytics.mv_pedidos_enriquecidos_2025_v2`, donde ambas existen:

| Mes | Líneas | Venta ordenada | Venta surtida | Ordenada sobre surtida |
|---|---|---|---|---|
| 2025-01 | 1,634,284 | $340,399,250 | $289,061,324 | +17.76% |
| 2025-02 | 1,567,637 | $289,978,426 | $241,584,058 | +20.03% |
| 2025-03 | 1,789,195 | $349,123,606 | $306,775,659 | +13.80% |
| 2025-04 | 1,884,948 | $371,523,004 | $327,861,362 | +13.32% |
| 2025-05 | 2,116,707 | $375,261,268 | $333,505,925 | +12.52% |
| 2025-06 | 1,659,023 | $328,773,547 | $295,925,916 | +11.10% |
| **Ene–jun 2025** | | **$2,055,059,101** | **$1,794,714,244** | **+14.51%** |

El ~6% de este documento estaba mal. La brecha real está entre 11% y 20% según el mes, y viene
bajando —de 17.8% en enero a 11.1% en junio—, lo que sugiere que la proporción de pedido no surtido
se ha ido reduciendo.

Eso cambia la decisión: pasar toda la serie a `monto_venta` no es un ajuste cosmético de 6%, es
subir la venta de 2025 en adelante **~14.5%** y desalinearla de lo que mide el resto del pipeline.
**Recomendación**: quedarse con el escalón y anotarlo en la página, no unificar hacia arriba.

---

## 15. Las tablas del tablero que NO salen del pipeline

De las 18 tablas con origen externo del modelo, 13 se derivan de la capa `bnpl` o de Redshift y se
recalculan solas con el pipeline. Las otras 5 no, y conviene tener claro por qué cada una — es lo
que hay que resolver para que el tablero sea 100% autosuficiente.

### Espejo de archivo (4): `archivos_bnpl.*`

Se cargan a mano con `carga_archivos_bnpl.py` desde el Drive compartido. No se calculan: se copian.
Si nadie vuelve a publicar el archivo, la tabla se queda como esté.

| Tabla | Filas | Por qué no se puede calcular | Quién la publica |
|---|---|---|---|
| `odds_combinations` | 84,986 | Binning supervisado que cambia por cada corte; `shopTown` entra con 647 valores y las filas de `ruta` traen el bin vacío | Riesgo |
| `atr_combinations_iv` | 468 | Depende del anterior | Riesgo |
| `ps_transactional_profile` | 100,793 | La regla que separa "Potential" de "Mostly Fraud" no está en el schema `fintech` (ver §10.3) | Pago de Servicios |
| `bnpl_cac` | 25 | El gasto de marketing no vive en ninguna fuente (ver §11) | Negocio |

**Riesgo operativo**: los archivos del Drive tenían fecha de febrero de 2026 cuando se migraron.
Si el proceso que los genera dejó de correr, el tablero muestra datos viejos sin avisar. Vale la
pena que alguien confirme si esos cuatro procesos siguen vivos y con qué periodicidad.

### Verificado (2026-08-14): ninguno de los cuatro está claramente vivo

Consultada la API de Drive por el `modifiedTime` real (no el `mtime` del disco montado, que refleja
la sincronización local y no la publicación) y contrastado contra el contenido ya cargado:

| Tabla | `modifiedTime` en Drive | Qué dice el contenido | Veredicto |
|---|---|---|---|
| `odds_combinations` | 2026-06-10 | 84,986 filas, sin columna de fecha | Indeterminado |
| `atr_combinations_iv` | 2026-06-10 | 468 filas, sin columna de fecha | Indeterminado |
| `ps_transactional_profile` | **2026-01-08** | 100,793 filas; cobertura cae de 61% a 42% para altas posteriores | **7 meses viejo** |
| `bnpl_cac` | 2026-06-10 | **última cohorte 2025-12**, faltan 8 | **8 meses viejo** |

**El `mtime` no sirve como medida de frescura y `bnpl_cac` lo prueba**: su archivo dice 2026-06-10
y su contenido se detiene en diciembre de 2025. Los timestamps de 2026-06-10 vienen todos del mismo
minuto (21:59–22:21) sobre una veintena de archivos sin relación entre sí —incluidos los 345 MB de
`bnpl_clean_history_orders.csv`—, así que o el notebook legacy corrió completo ese día, o alguien
recopió la carpeta. Los tamaños no ayudan a distinguirlo: el `odds_combinations.csv` de esa carpeta
pesa 13 MB, mientras que las otras copias del mismo archivo en el Drive pesan 28 y 30 MB.

Para las dos tablas de riesgo no hay forma de fecharlas por contenido: no traen columna de fecha.
Sólo quien corre el proceso puede decir si sigue vivo — y ésa es justo la pregunta de §10.

**Lo que sí quedó descartado**: que baste con mirar fechas. Para las tablas que sí tienen cómo
fecharse, el contenido contradice al archivo. Cualquier alerta de frescura sobre `archivos_bnpl`
tiene que mirar el dato, no el `mtime`.

**Recomendación operativa**: agregar a `bnpl_ops.data_quality_checks` una verificación por
contenido para las dos tablas que la admiten — que la última cohorte de `bnpl_cac` no esté a más de
dos meses de la última cohorte real, y que la cobertura de `ps_transactional_profile` sobre clientes
BNPL recientes no caiga por debajo de un umbral. Para `odds_combinations` y `atr_combinations_iv` no
hay chequeo posible; si se quedan, se quedan sin red.

### Derivadas pero con un supuesto congelado (2)

`odds_table` y `vars_and_iv` sí se calculan en SQL (`sql/pbi/12` y `13`), pero el corte del bin
está congelado del CSV de feb-2026 — 8.98 m / 8.31 / 7.24 según el rango. El original lo derivaba
de los datos. Ver §10.1.

### Muerta (1)

`Consulta1` no alimenta ningún visual: es el listado de archivos de un OneDrive personal. **Se
borra**, no se migra. Con ella salen sobrando las expresiones auxiliares de SharePoint que quedan
en `expressions.tmdl` (`Parámetro1` a `Parámetro4`, `Archivo de ejemplo`, `Transformar archivo` y
sus variantes), que solo existían para leer los CSV de SharePoint.

**Hecho el 2026-08-14**: se borraron las 16 expresiones y los 8 grupos que las contenían. No era
cosmético. `Parámetro1..4` son **parámetros**, y Power Query los evalúa antes que todo lo demás: su
404 contra la OneDrive bloqueaba el refresh de las 17 tablas, aunque ninguna los usara. Fue lo que
trabó la conexión al gateway.

### Para que el tablero sea autosuficiente

Ordenado por lo que más destraba:

1. **Confirmar si el modelo de riesgo sigue vivo.** Si nadie usa las páginas de odds/IV, las cuatro
   tablas de riesgo sobran y el tablero baja de 18 orígenes a 14. Si sí se usa, hay que decidir si
   el binning se recalcula (y entonces alguien tiene que mantener ese proceso) o se congela.
2. **La regla de fraude de PS**, que es lo único que falta para que `ps_transactional_profile` se
   calcule sola desde Redshift.
3. **La fuente del gasto de marketing**, para que el CAC deje de ser captura manual.

---

## 16. Las preguntas que faltan, redactadas para llevarlas

Lo que no se cierra con datos, listo para copiar y pegar. Ordenado por lo que está en juego. Cada
una dice qué se pregunta, a quién y qué cambia según la respuesta — para que nadie tenga que
reconstruir el contexto en la reunión.

### 16.1 · Contrato con Propaga — a Finanzas / quien firmó el acuerdo

> El contrato con Propaga dice 14.2% de participación sobre el interés. Necesito confirmar sobre
> qué base se calcula: ¿sobre el interés neto que Propaga factura, o sobre el interés más IVA que
> paga el tendero? Lo pregunto porque en los datos de Propaga el IVA viene desglosado aparte
> (`iVAAmount = interés × 0.16`), lo que sugiere que la base es el neto. Si es así, el revenue
> histórico de BNPL es **$874,036** y no **$1,024,912** como se venía reportando.

**Qué cambia**: si es sin IVA (lo que indica la evidencia), se borra `rabbit_revenue` y el tablero
reporta $150,875 menos en el histórico, ~$7,500/mes menos hacia adelante. Si es con IVA, hay que
quitar el `÷1.16` del DAX, porque hoy el Resumen Ejecutivo ya está mostrando la cifra neta por
defecto y estaría subdeclarando.

### 16.2 · La comisión del 4% — a Finanzas, en la misma conversación

> Además del 14.2%, en el pipeline legacy hay una comisión de 4% sobre el monto financiado que se
> calcula pero no alimenta ningún reporte. En el histórico serían **$6,529,898** — siete veces y
> media todo lo que se reporta hoy como revenue de BNPL. ¿Ese 4% existe en el contrato, existió y
> se canceló, o nunca fue más que una prueba?

**Qué cambia**: si está vigente, el revenue de BNPL que reporta el tablero está mal por un orden de
magnitud y hay que rehacer la página de Resumen Ejecutivo. Si no, se borra
`bnpl.comision_sobre_monto()` y deja de confundir a quien lea el código.

### 16.3 · Los 1,486 tenderos sin clasificar — a Riesgo y a Comercial

> 1,486 tenderos con crédito activo tienen `tipo_cliente = UNKNOWN` en el catálogo comercial. Como
> grupo pierden **7.52%** de lo financiado contra 4.60% del resto, lo que son **$564,570** de
> sobrepérdida sobre sus $19.3M. ¿Qué son esos clientes — altas que no pasaron por el catálogo,
> rutas dadas de baja, otra cosa? ¿Y hay razón para seguir dándoles el mismo límite que a un
> PREVENTA?

**Qué cambia**: si son un artefacto del catálogo, se arregla la fuente y desaparecen. Si son un
segmento real, es una decisión de política de crédito con medio millón de pesos anuales encima.

**Pregunta secundaria, misma reunión** (§4): el `rutas_fintech.xlsx` legacy clasificaba como
`organico` / `aliado`; el catálogo de hoy trae `ORGANICO` / `PREVENTA` / `UNKNOWN`. ¿`aliado` era
lo mismo que `PREVENTA`? Importa porque PREVENTA es el 84% del volumen.

### 16.4 · La exención de intereses del primer pedido — a quien fijó la promoción

> Desde el 2024-04-22, el primer pedido de cada cliente no paga intereses. Van **9,031 tenderos** y
> **$507,328** de interés condonado ($72,041 de comisión que Rabbit no cobró). ¿Sigue vigente esa
> promoción, o era una campaña que debió cerrarse en alguna fecha?

**Qué cambia**: si sigue vigente, no se toca nada. Si debió cerrarse, hay que fijar la fecha de
corte y volver a calcular el revenue desde ahí.

**Nota**: en el código aparecen `2024-09-01` y `2024-10-13` sin efecto (§2). Ya está medido que
mover el arranque al 2024-10-13 sólo cambia **$28,567**, así que no vale la pena gastar la reunión
en esa parte — basta con preguntar si la promoción sigue viva.

### 16.5 · Cuál es "la" tasa PAR30 — a quien presenta el vintage en comité

> En la página Vintage Analysis hay dos gráficas, una junto a la otra, que hasta el 2026-08-14
> **compartían título** y hoy se llaman `PAR 30+ Rate per Enrollment Cohort (over Deployed Capital)`
> y `PAR 30+ Rate per Enrollment Cohort (over Activated Customers)`. La primera mide PAR30 sobre
> capital desplegado y hoy marca **6.02%**, con una línea de referencia `'BEP'` en 3.5%. La segunda
> mide PAR30 sobre clientes activados, marca **31.30%**, y tiene una línea `'Healthy Value'` en
> 4.0%. ¿Cuál es la que se cita en comité, y de dónde salió el 4% de la segunda?

**Qué cambia**: los títulos ya se separaron, así que lo que queda por decidir es el umbral. Si la
oficial es la de capital, se quita la línea de 4% que no aplica y se borran las 6 columnas de tasa
de la vista que nadie lee. Si la oficial es la de clientes, hay que revisar ese umbral, porque
ninguna cohorte madura ha estado cerca de 4%.

### 16.6 · ¿Vuelve a abrirse la página de ROI? — a Negocio

> `bnpl_cac` no se actualiza desde la cohorte 2025-12: faltan 8 cohortes con 821 tenderos. Antes de
> buscar quién publica el gasto de marketing: la página *Return On Investment* está oculta en modo
> lectura, así que hoy nadie la ve. ¿Se va a volver a abrir?

**Qué cambia**: si no, se borran la página, la tabla `CacTable` y el archivo, y §11 desaparece. Si
sí, hace falta la fuente del gasto **y** rellenar las 8 cohortes antes de publicarla.

### 16.7 · ¿Sigue vivo el modelo de riesgo? — a Riesgo

> Las cuatro tablas de odds/IV (`odds_table`, `vars_and_iv`, `odds_combinations`,
> `atr_combinations_iv`) alimentan una sola página, *Default Customer Profile*, que está oculta en
> modo lectura. Dos de ellas se cargan a mano desde el Drive (85,454 filas) y no hay forma de saber
> si el proceso que las genera sigue corriendo. ¿Alguien sigue usando ese análisis?

**Qué cambia**: si no, el tablero baja de 18 orígenes externos a 14, se elimina la carga manual y
se cae la pregunta del corte congelado del bin (§10.1). Si sí, hay que decidir quién mantiene el
proceso y si el binning se recalcula o se congela — y, de paso, avisarles que tres de los once
atributos están rotos en origen (`previousFintechProductToBnpl` y `psrtaPreviousToBnpl` son
constante 0; `grossSalesVolume3Months` es idéntica a la de 6 meses en el 100% de las filas).

### 16.8 · La regla de fraude de Pago de Servicios — a PS

> `ps_transactional_profile` clasifica a 100,793 clientes, y tres de sus seis categorías
> (`01-Enrolled`, `02-Potential Fraud`, `03-Mostly Fraud`) no se pueden reproducir desde el schema
> `fintech`: se enciman todas entre 0 y 3 transacciones. ¿Cuál es la regla que separa "Potential"
> de "Mostly Fraud"? El archivo tampoco se ha republicado desde el 2026-01-08.

**Qué cambia**: con la regla, la tabla se calcula sola desde Redshift y deja de ser espejo de
archivo. Sin ella, la página Fraud sigue corriendo con datos de enero: hoy **584 clientes BNPL**
($11.05M financiados) traen perfil `03-Mostly Fraud`, y **3,751** no traen ninguno y quedan
marcados como no-fraude por omisión.

### 16.9 · Dueño de `mv_pedidos_enriquecidos_2023` — a Ingeniería de Datos

> Diciembre-2023 de `analytics.mv_pedidos_enriquecidos_2023` viene inflado ~25× en monto y ~20× en
> piezas, con el mismo número de líneas que los meses vecinos. Se reportó hace dos meses y hoy
> sigue igual. La versión de `analytics_beta` está peor. ¿Quién es dueño de esa vista y se puede
> recargar el mes?

**Qué cambia**: mientras no se corrija, todas las consultas de cosechas dividen ese mes entre 20,
que es un parche acordado y no un valor derivado. Al corregirse hay que quitar el `/ 20.0` de
`etl_redshift_to_postgres.py`.

### 16.10 · Los cuatro chicos — a quien corresponda, sin urgencia

Ninguno tiene dinero medible detrás. Van juntos para no gastar cuatro reuniones:

- **§5 · Override de validación manual**: ¿sigue existiendo `clean_manual_validation.csv`, quién lo
  mantiene? Si nadie, `grid_bnpl` se queda sin la columna y ya.
- **§6 · `get_report()` con Selenium**: ¿qué campos aportaba el scraping del backoffice? Si ya
  están en Mongo o Redshift, se elimina la dependencia de navegador.
- **§7 · Destinos de publicación**: ¿hacen falta Slack, Google Sheets y SharePoint, o basta con
  PostgreSQL?
- **§9 · `fintech-credit-status-state-production`** (31M documentos, hoy fuera del staging): ¿hay
  algún análisis que necesite la curva de estados por día? De entrar, requiere carga incremental.

---

## 17. Las cinco relaciones que cambió la migración, y el PII de `Top100InactiveCustomers`

Hasta hoy **no existía ningún documento** que listara qué relaciones del modelo cambiaron al
repuntarlo a PostgreSQL. Quedan escritas aquí para que la próxima migración no las vuelva a perder
sin que nadie lo note. Todas se verifican en
`pbi_new/Buy Now Pay Later.SemanticModel/definition/relationships.tmdl`.

| # | Relación | Qué pasó |
|---|---|---|
| a | `grid_bnpl[bnplEnrolledAt] → enrollment_dates[Date]` (`ec74a7f6-…`) | **se perdió** — restaurada el 2026-08-14 |
| b | `bnpl_loss_rates_with_lead[netsuiteId] → grid_bnpl[netsuiteId]` (`eef16e8f-…`) | **se perdió** — restaurada el 2026-08-14 |
| c | `grid_bnpl[netsuiteId] → Top100InactiveCustomers[netsuiteId]`, bidireccional (`43b9c13a-…`) | **se perdió** — no se restaura: la tabla está en decisión (ver abajo) |
| d | `loans_matured_default_profile[netsuiteId] → grid_bnpl[netsuiteId]` (`AutoDetected_3645b986`) | **nueva**, la inventó Power BI |
| e | `months_closes[netsuiteId] → grid_bnpl[netsuiteId]` (`AutoDetected_c6522e8d`) | **desactivada**, como consecuencia de (d) |

La (e) es la que está detrás de §13b.4: el filtro del grid que tira $3.88M en *Salud del
Portafolio*. Ese cambio **sí espera a Riesgo/Finanzas** y no se toca aquí.

### El PII que `Top100InactiveCustomers` publica al modelo

Es lo que hace urgente la pregunta a negocio. La tabla es **calculada sobre `grid_bnpl`**: no trae
origen nuevo, duplica en memoria un subconjunto con datos personales y **ningún visual la consume**
(0 referencias, ni en el modelo migrado ni en el viejo). Los campos, en
`Top100InactiveCustomers.tmdl`:

| Campo | Línea |
|---|---|
| `shopName` | :420 |
| `shopZipCode` | :444 |
| `customerName` | :488 |
| `customerLastNames` | :496 |
| `customerBirthdate` | :512 |
| `customerPhoneNumber` | :553 |
| `customerLatitude` | :561 |
| `customerLongitude` | :571 |

Son **100 tenderos identificados con nombre, teléfono y coordenadas**, dentro de un modelo que se
manda por correo.

**Lo que espera respuesta**: si esa lista sigue haciendo falta, y si necesita nombre y teléfono o le
basta `netsuiteId`. Si la respuesta es "ya no", la tabla se borra desde Power BI Desktop y se lleva
consigo sus 7 `LocalDateTable`.

---

## Lo que se puede ejecutar sin preguntarle a nadie

Cambios donde la evidencia ya alcanza y el riesgo es bajo. Los tachados se aplicaron el 2026-08-14;
los demás siguen pendientes.

| Acción | Efecto en los números | Dónde |
|---|---|---|
| Corregir `"60-89"` → `"DQ 60-89"` en `lossAmount` | `lossAmount` **+$308,974 (+3.4%)** | `bnpl_loss_rates.tmdl:643` |
| Corregir las etiquetas del `SWITCH` de `dynamicTotalRevenue` | quita un salto de 16% al mover el slicer | `bnpl_loss_rates.tmdl:29` |
| Limpiar el `queryRef` muerto `par30Cumulative` | ninguno | visual `0ff2052f3312e68375b0` |
| Chequeo de frescura por contenido para `bnpl_cac` y `ps_transactional_profile` | ninguno | `ops/quality_checks.py` |
| ~~Renombrar las dos gráficas de tasa PAR 30 que compartían título~~ | **hecho el 2026-08-14**, ninguno | página *Vintage Analysis* |
| ~~Agregar `{"PaidPrev", 0}` al `DATATABLE` de `dq_order`~~ | **hecho el 2026-08-14**, ninguno | `dq_order.tmdl` |
| ~~Borrar `Consulta1` y las expresiones de SharePoint~~ | **hecho el 2026-08-14**, ninguno (§15) | `expressions.tmdl` |
| ~~Borrar la carpeta del modelo viejo, donde seguían las 8 `Csv.Document` y las 4 `SharePoint.Files`~~ | **hecho el 2026-08-14**, ninguno; publicar ese `.pbix` por error habría sobrescrito el productivo | salió del repo a `..\_deprecado_pbi_origenes_csv_2026-08-14` |

> **Ya no está en esta lista**: activar el `WHERE p.par <> 'PaidPrev'` de las consultas 03 y 04.
> Sobre `bnpl_par` **sí mueve cifras** —$1,684M de venta bruta en dos gráficas— y necesita decisión
> de negocio. Ver §13b.1.

Los que **sí** mueven cifras del negocio —retirar `rabbit_revenue` (§1) y excluir las 39 órdenes
con `total_amount = 0`— quedan detenidos hasta que Finanzas conteste 16.1, porque juntos bajan el
revenue reportado $150,875.

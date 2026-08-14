# El texto de ayuda del tablero: `ayuda_tablero/` → los 168 tooltips

Cada gráfica del tablero explica lo que muestra sin que nadie tenga que preguntar. El texto no se
escribe a mano visual por visual en Power BI Desktop: **se genera leyendo lo que el visual realmente
hace** —sus campos, el DAX de sus medidas, sus filtros— y se escribe en los `visual.json` del PBIP.

```
ayuda_tablero/conocimiento.py  ──componer.py──▶  _datos/textos.json  ──aplicar.py──▶  visual.json
   qué es cada tabla                              un texto por visual                  el PBIP
```

Correrlo es idempotente: dos veces seguidas deja los archivos igual.

## Índice

- [Cómo se regenera](#cómo-se-regenera)
- [Por qué hacen falta DOS propiedades](#por-qué-hacen-falta-dos-propiedades)
- [Qué dice cada texto](#qué-dice-cada-texto)
- [Los archivos](#los-archivos)
- [Cambiar un texto](#cambiar-un-texto)
- [Cuando cambia el modelo](#cuando-cambia-el-modelo)
- [Lo que se verificó, y cómo](#lo-que-se-verificó-y-cómo)

## Cómo se regenera

```powershell
# 1. Ver qué cambiaría. No escribe nada.
.venv\Scripts\python.exe ayuda_tablero\documentar_tablero.py

# 2. Escribirlo en el PBIP
.venv\Scripts\python.exe ayuda_tablero\documentar_tablero.py --aplicar

# 3. Si además hay que rehacer la portada
.venv\Scripts\python.exe ayuda_tablero\documentar_tablero.py --aplicar --portada
```

**Cierra Power BI Desktop antes de aplicar.** Si el reporte está abierto, Desktop tiene su propia
copia en memoria y al guardar sobrescribe lo que acaba de escribirse en disco.

El modo por defecto es diagnóstico a propósito: dice cuántos visuales cambiarían y cuáles, para que
un cambio en el modelo no se cuele sin que nadie lo vea.

## Por qué hacen falta DOS propiedades

Esto es lo que no se puede adivinar leyendo el esquema, y por lo que este directorio existe en vez
de ser tres líneas de código.

El texto que se ve al pasar el mouse por el ícono ⓘ del encabezado vive en
`visualContainerObjects.visualHeaderTooltip[0].properties.text`. **Escribir eso solo no produce
nada.** El motor de Power BI (`bin\WebView2Resources\minerva\SCRIPTS\DESKTOP.MIN.JS`, versión
2.148) lo resuelve así:

```js
setHeaderTooltip(){
  var e = this.evaluatedObjects?.visualHeader,
      t = this.evaluatedObjects?.visualHeaderTooltip;
  this.headerTooltip = e && e.showTooltipButton && t ? t : void 0
}
```

Es decir: **el texto solo se muestra si además `visualHeader.showTooltipButton` está en `true`**.
Y ojo con el nombre — no es `showVisualInformationButton`, que también existe en el esquema y es
justo el que uno escogería. `aplicar.py` escribe las dos, más `general.altText` para lectores de
pantalla:

| Propiedad | Para qué | Dónde |
|---|---|---|
| `visualHeaderTooltip[0].properties.text` | el texto | `visualContainerObjects` |
| `visualHeaderTooltip[0].properties.type` | `'Default'` = texto plano (la otra opción es una página de tooltip) | `visualContainerObjects` |
| `visualHeader[0].properties.showTooltipButton` | **enciende el ícono ⓘ**; sin esto no se ve nada | `visualContainerObjects` |
| `general[0].properties.altText` | lectores de pantalla | `visualContainerObjects` |

Dos detalles del formato:

- **Los apóstrofes se duplican.** El valor va como literal entre comillas simples, así que
  `KPI's` se escribe `'KPI''s'`. Lo hace `aplicar.py`; no hay que pensarlo.
- **Los saltos de línea pueden no respetarse.** El motor pasa el texto como un solo elemento
  (`dataItems:[{displayName: n}]`), así que no está garantizado que pinte los `\n`. Por eso cada
  una de las tres partes del texto **termina en punto**: si el salto se pierde, se lee corrido y
  sigue siendo correcto.

## Qué dice cada texto

Tres partes, siempre en el mismo orden:

```
Qué mide: una frase en lenguaje de negocio.
Universo y corte: el grano, los filtros del visual y las advertencias que apliquen.
De dónde sale: la vista de pbi_bnpl y su fuente original.
```

La segunda parte es la que vale. El tablero tiene definiciones que no se deducen del título, y cada
tooltip dice **cuál usa su gráfica**:

| Advertencia | Dónde aplica |
|---|---|
| Ruta **histórica** (quién tenía la cuenta al originarse el crédito) vs **vigente** (quién la atiende hoy) | mora vs grid — ver `sql/11_bnpl_dim_ruta.sql` |
| Tasa PAR sobre **capital desplegado** ($1,760M) o sobre **saldo vivo** ($276M) | medidas del vintage vs columnas y cierres mensuales |
| El último corte es el **mes en curso**, incompleto | todo lo que sale de `par_snapshot` |
| `PaidPrev` = 85.9% de las filas, **saldo cero pero venta bruta $1,684M** | `bnpl_par` y `months_closes` |
| Comisión de Rabbit sobre interés **con** o **sin** IVA (17.3% de diferencia) | `bnpl_loss_rates` vs `grid_bnpl` |
| Qué slicers alcanzan la gráfica y cuáles no | tablas sin relación con el grid |

Los textos **describen, no opinan**. Cuando una definición no es la que sugiere el título, el
tooltip dice qué calcula y con qué denominador, y la discusión de si debería cambiar vive en
[`PENDIENTES_NEGOCIO.md`](../PENDIENTES_NEGOCIO.md) §13b — porque mover una regla necesita que
negocio la confirme.

## Los archivos

| Archivo | Qué hace |
|---|---|
| `documentar_tablero.py` | **la entrada**: corre todo y dice qué cambiaría |
| `inventario.py` | lee el PBIP: TMDL del modelo (tablas, columnas, medidas con su DAX) y los 196 `visual.json` (tipo, campos por rol, agregación real, filtros, cálculos del visual) |
| `conocimiento.py` | **lo que hay que saber**: qué es cada tabla, su grano, su vista de origen y sus advertencias. Es lo que se edita cuando cambia el negocio |
| `textos_a_mano.py` | los 27 visuales cuya definición no se deduce de su estructura y llevan texto escrito a mano |
| `componer.py` | arma las tres partes y corrige acentos |
| `aplicar.py` | escribe las cuatro propiedades en los `visual.json` |
| `portada.py` | crea la página *Cómo leer este tablero* y la pone primero |
| `volcado.py` | vuelca en texto lo que hace cada visual — para leerlo antes de escribir un texto a mano |
| `revisar_referencias.py` | resuelve cada campo contra el modelo y reporta los que no existen |
| `medir_en_base.py` | las consultas que respaldan los números citados en los textos |

`_datos/` guarda `inventario.json` y `textos.json`. Son derivados: se regeneran y no se versionan.

## Cambiar un texto

**No lo edites en Power BI Desktop**: la próxima corrida de `documentar_tablero.py --aplicar` lo
sobrescribe.

- Si el texto está mal **para toda una tabla** (cambió el grano, la fuente, una advertencia dejó de
  aplicar) → `conocimiento.py`, en `T[...]`. Un cambio ahí arregla todos sus visuales.
- Si es **un visual en particular** → agrégalo a `textos_a_mano.py` con su `id`. El `id` sale del
  nombre de su carpeta en `pbi_new\Buy Now Pay Later.Report\definition\pages\<página>\visuals\`, y
  también lo imprime `volcado.py`.
- Si es **el significado de un campo o una medida** → los diccionarios `C` y `M` de
  `conocimiento.py`.

Antes de escribir un texto a mano, mira qué hace el visual de verdad:

```powershell
.venv\Scripts\python.exe ayuda_tablero\volcado.py "Salud del Portafolio"
```

Imprime, por visual: el rol de cada campo, la **agregación real**, el DAX de cada medida, los
cálculos del propio visual y los filtros con sus valores.

## Cuando cambia el modelo

El generador lee el modelo en cada corrida, así que un campo nuevo o una medida nueva entran solos.
Lo que **no** entra solo es su significado de negocio: si `componer.py` no encuentra la medida en
`M`, cae a humanizar el nombre (`avgTicketTotal` → "avg ticket total"), que es legible pero pobre.
Para ver qué quedó sin significado:

```powershell
.venv\Scripts\python.exe ayuda_tablero\revisar_referencias.py
```

Y siempre corre primero en modo diagnóstico: si cambiaron 40 visuales y esperabas 2, algo se movió
en el modelo que conviene entender antes de escribirlo.

## Lo que se verificó, y cómo

Para no dejar el mecanismo en "debería funcionar":

1. **El esquema oficial.** `visualConfiguration/2.2.0` declara `additionalProperties: false` en
   `visualContainerObjects`, así que solo admite claves conocidas — y las tres están.
2. **El motor instalado.** La función `setHeaderTooltip` de `DESKTOP.MIN.JS` es la que reveló que
   hacen falta las dos propiedades, no una.
3. **Ida y vuelta con Power BI.** Se escribió el tooltip en un visual, se abrió el PBIP en Desktop y
   se guardó desde la aplicación: Desktop **reescribió el archivo y conservó las tres propiedades**
   con acentos y el apóstrofe escapado. Si no las hubiera entendido, las habría descartado al
   re-serializar.
4. **El reporte completo abre.** Con los 168 textos y la portada nueva, verificado en Desktop.

Dos cosas que salieron al hacerlo y que conviene saber si algún día se toca este código:

- **`queryRef` miente.** Es un alias y puede quedar viejo: hay 58 proyecciones donde dice
  `Min(salesOrderId)` o `CountNonNull(...)` y la agregación real es `DistinctCount`. La verdad está
  en `Aggregation.Function` (0=Sum, 2=DistinctCount, 3=Min…). `inventario.py` lee esa, no el alias.
  Es el mismo tipo de artefacto que el `par30Cumulative` de `PENDIENTES_NEGOCIO.md` §13.
- **TMDL admite expresiones multilínea sin backticks.** Una medida puede venir como
  `measure X =` seguida de líneas con tres tabuladores. Un parser que solo entienda los bloques
  ` ``` ` reporta 26 medidas vacías que en realidad tienen DAX.

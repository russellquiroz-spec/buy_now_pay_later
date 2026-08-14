# -*- coding: utf-8 -*-
"""Textos escritos a mano para los visuales donde la definicion no es la que sugiere el titulo.

Descriptivos, no editoriales: dicen que calcula el visual y con que denominador, sin
proponer que deberia calcular. Las decisiones van a PENDIENTES_NEGOCIO.md.
"""

OVERRIDES = {

# ---------- Resumen Ejecutivo ----------
"ceb3c416848990d01b8e": """
Que mide: La comision que gana Rabbit sobre el interes del credito, por mes de pago.
Universo y corte: Solo pedidos efectivamente pagados, contados en el mes en que entro el pago
(paidDate), no en el que se origino el credito. Por defecto la cifra va SIN IVA: la medida
divide la comision entre 1.16. El slicer 'Tipo de Revenue' cambia entre con y sin IVA.
Ojo con la base: en esta tabla el 14.2% se aplica sobre el interes CON IVA y luego se divide,
mientras que en el grid el mismo 14.2% se aplica sobre el interes sin IVA; las dos rutas no dan
lo mismo.
De donde sale: la vista pbi_bnpl.bnpl_loss_rates, sobre bnpl.loss_rates.
""",

"467d1a5f6fe8fee01a7e": """
Que mide: El interes total del credito (lo que se reparten Propaga y Rabbit), por mes de pago.
Universo y corte: Solo pedidos pagados, por fecha de pago. La medida usa un selector cuyas
etiquetas son 'After Taxes' y 'Before Taxes', mientras que la tabla del slicer contiene
'Sin IVA' y 'Con IVA': al tocar el slicer ninguna coincide y la medida cae al valor bruto,
por lo que la cifra sube 16%. Sin tocar el slicer si divide entre 1.16.
De donde sale: la vista pbi_bnpl.bnpl_loss_rates, sobre bnpl.loss_rates.
""",

"9cdd3c9f8d93d9c2cb20": """
Que mide: No es una metrica, es un selector: cambia si el revenue se muestra con IVA o sin IVA.
Universo y corte: Afecta a las dos graficas de ingresos de esta pagina. La de la comision de
Rabbit responde bien. La del revenue total no: sus etiquetas internas no coinciden con las de
esta tabla, asi que al elegir cualquier opcion muestra el bruto.
De donde sale: una tabla capturada en el modelo (revenue_view_selector), no del pipeline.
""",

"3cdf491f1dcb837fc1fc": """
Que mide: Todo el capital que se ha prestado desde diciembre de 2023.
Universo y corte: Suma el monto financiado de los 92,009 pedidos entregados, sin filtro de
estado: incluye lo ya pagado y lo vigente. No es saldo por cobrar.
De donde sale: la vista pbi_bnpl.bnpl_loss_rates, sobre bnpl.loss_rates.
""",

"7f4f5c03e163fff32a30": """
Que mide: El saldo que los tenderos todavia deben.
Universo y corte: Suma el monto financiado de los pedidos que hoy no estan pagados (excluye el
bucket 'Paid'), incluyendo los que estan al corriente y los vencidos. Es el estado de hoy, no un
corte de fin de mes.
De donde sale: la vista pbi_bnpl.bnpl_loss_rates, sobre bnpl.loss_rates.
""",

"5fcb3ba0b600e028de0c": """
Que mide: Cómo se reparte el saldo por cobrar entre los buckets de mora, en porcentaje.
Universo y corte: Pedidos completados que hoy no estan pagados. El subtitulo dice 'Current
Month', pero el visual no lleva filtro de fecha: muestra el estado actual de todo el historico,
que para saldo vivo es lo mismo. El porcentaje es sobre el total mostrado en la grafica.
De donde sale: la vista pbi_bnpl.bnpl_loss_rates, sobre bnpl.loss_rates.
""",

"71d18d2067746ecd7447": """
Que mide: Cuánto saldo por cobrar hay en cada bucket de mora, en pesos.
Universo y corte: Pedidos completados que hoy no estan pagados. El subtitulo dice 'Current
Month', pero el visual no lleva filtro de fecha: es el estado actual de todo el historico.
De donde sale: la vista pbi_bnpl.bnpl_loss_rates, sobre bnpl.loss_rates.
""",

"686508ac1c0fffe2958b": """
Que mide: Qué porcentaje del capital ya vencido cayo en cada bucket de mora.
Universo y corte: Excluye los pedidos que aun no vencen ('Ongoing'), asi que el denominador es
capital maduro, no todo lo desplegado. Cubre de diciembre de 2023 a la fecha.
De donde sale: la vista pbi_bnpl.bnpl_loss_rates, sobre bnpl.loss_rates.
""",

"3bb52095208f3107c583": """
Que mide: Cuánto capital ya vencido hay en cada bucket de mora, en pesos.
Universo y corte: Excluye los pedidos que aun no vencen ('Ongoing'). Cubre de diciembre de 2023
a la fecha. La ruta y la oficina de esta tabla son las historicas, las del momento del credito.
De donde sale: la vista pbi_bnpl.bnpl_loss_rates, sobre bnpl.loss_rates.
""",

"67d3f96751cc974eb1d5": """
Que mide: El volumen de venta financiada por periodo, con el uso de la linea de credito como
dato de apoyo al pasar el mouse.
Universo y corte: Solo pedidos efectivamente entregados: excluye cancelados, rechazados, en
ruta y no visitados. El eje se reagrupa por dia, semana o mes con el slicer 'Periodicidad'.
El uso de linea es venta sobre linea autorizada, y ambas se filtran igual.
De donde sale: la vista pbi_bnpl.bnpl_grouped_orders, sobre bnpl.grouped_orders.
""",

# ---------- Salud del Portafolio ----------
"7bff25e9edb4546672da": """
Que mide: No es una metrica, es un filtro: acota la pagina por oficina de preventa y, dentro de
ella, por ruta.
Universo y corte: Usa la ruta VIGENTE, la que atiende la cuenta hoy, no la que tenia el cliente
cuando se origino el credito. Alcanza las graficas de mora por dos caminos distintos: a las de
bnpl_par y bnpl_loss_rates las filtra directo, y a las de cierre mensual por la via de
loans_matured_default_profile, que cubre el 99.84% de las filas. Al elegir una oficina se caen
1,747 pedidos ($3.88M de saldo) que no estan en esa tabla.
De donde sale: la vista pbi_bnpl.grid_bnpl, que toma ruta y oficina de bnpl.dim_ruta_actual
(estructura comercial vigente, desde Redshift).
""",

"a419f4a6b3e841c3c405": """
Que mide: Cuánta venta financiada hay viva en cada mes, repartida por bucket de mora.
Universo y corte: Una fila por pedido y por corte de fin de mes; la altura es la venta bruta del
pedido, no el saldo pendiente. La ruta de esta tabla es la HISTORICA: quien tenia la cuenta
cuando se origino el credito. El 85.9% de las filas son pedidos ya pagados en cortes anteriores
('PaidPrev'). Su saldo es cero, pero esta grafica NO mide saldo sino venta bruta, y ahi
'PaidPrev' si suma: son $1,684M, el 88% del total de la tabla, y domina la grafica. El ultimo mes
del eje es el mes en curso y esta incompleto.
De donde sale: la vista pbi_bnpl.bnpl_par, sobre bnpl.par_snapshot con la estructura comercial
de bnpl.loss_rates.
""",

"db7672f18e68429c61c1": """
Que mide: Cómo se reparte porcentualmente la venta financiada viva entre los buckets de mora,
mes a mes.
Universo y corte: Mismo universo que la grafica de barras de arriba: una fila por pedido y por
corte de fin de mes, con la venta bruta del pedido como altura, no el saldo. Ruta historica.
El 85.9% de las filas son 'PaidPrev': su saldo es cero, pero su venta bruta si suma ($1,684M, el
88% del total), asi que domina el reparto. El ultimo mes esta incompleto.
De donde sale: la vista pbi_bnpl.bnpl_par, sobre bnpl.par_snapshot.
""",

"8b340c00cf26999459f3": """
Que mide: Cómo se reparte el saldo por estado de pago en cada cierre de mes.
Universo y corte: La altura es el saldo vivo al corte, no el monto originalmente desembolsado,
pese a que el titulo diga 'Disbursed'. Los pedidos pagados en cortes anteriores entran como
'PaidPrev' con saldo cero: son el 85.9% de las filas y engordan la leyenda sin aportar monto.
El ultimo corte es el mes en curso y esta incompleto. Los slicers del grid la filtran por la via
de loans_matured_default_profile, que cubre el 99.84% de las filas.
De donde sale: la vista pbi_bnpl.months_closes, la misma bnpl.par_snapshot que bnpl_par con
otros nombres de columna.
""",

"e041ff79805ef0f730ba": """
Que mide: El mismo reparto del saldo por estado de pago en cada cierre, en porcentaje.
Universo y corte: La altura es saldo vivo al corte, no monto desembolsado. El 85.9% de las filas
son 'PaidPrev' con saldo cero. El ultimo corte es el mes en curso y esta incompleto.
De donde sale: la vista pbi_bnpl.months_closes, sobre bnpl.par_snapshot.
""",

"ff9919fbe69dcc98d027": """
Que mide: Qué porcentaje del saldo de cada cierre esta en mora, abierto por tramo de dias de
atraso.
Universo y corte: El porcentaje es un calculo del propio visual: saldo del bucket entre
'Cumulative Deployed & Matured Capital'. Ese denominador es la suma del saldo de TODAS las filas
del mismo corte, ignorando los filtros de bucket y de dias del visual. Es decir, saldo vivo, no
capital desplegado. Las medidas PAR de Vintage Analysis dividen entre capital desplegado
($1,760M contra $276M de saldo), asi que las dos cifras no son la misma tasa. El visual excluye
los pedidos pagados y los de 120 dias o mas. El ultimo corte es el mes en curso, incompleto.
De donde sale: la vista pbi_bnpl.months_closes, sobre bnpl.par_snapshot.
""",

"10d2c4259a50003b9807": """
Que mide: Qué porcentaje del saldo de cada cierre esta en mora, incluyendo lo castigado, por
tramo de dias de atraso.
Universo y corte: El porcentaje es un calculo del visual: saldo del bucket entre la suma del
saldo de todas las filas del mismo corte. Ese denominador es saldo vivo, no capital desplegado,
pese al titulo. Aqui los pedidos de 120 dias o mas se agrupan como 'Written Off'. El ultimo
corte es el mes en curso, incompleto.
De donde sale: la vista pbi_bnpl.months_closes, sobre bnpl.par_snapshot.
""",

"38a27113006c226323cd": """
Que mide: Cuánto saldo en mora hay en cada cierre de mes, en pesos, incluyendo lo castigado.
Universo y corte: Los pedidos con 120 dias o mas de atraso se agrupan como 'Written Off'. La
altura es saldo vivo al corte. El ultimo corte es el mes en curso y esta incompleto.
De donde sale: la vista pbi_bnpl.months_closes, sobre bnpl.par_snapshot.
""",

"8037fdef0c16ba75e4b4": """
Que mide: Cuánto saldo vencido hay en cada cierre de mes, en pesos, por tramo de dias de atraso.
Universo y corte: Excluye los pedidos pagados y los de 120 dias o mas. La altura es saldo vivo
al corte. El ultimo corte es el mes en curso y esta incompleto.
De donde sale: la vista pbi_bnpl.months_closes, sobre bnpl.par_snapshot.
""",

"43181269a4927887c058": """
Que mide: Saldo en pedidos vigentes, saldo que llego a pagado, y el porcentaje que resulta de
restar uno del otro.
Universo y corte: Las definiciones no son las que sugieren los nombres. 'Amount Of Disbursed
Loans' no es todo lo desembolsado: es el saldo solo de las filas en etapa 'Ongoing', las que aun
no vencen. 'Amount Of Paid Loans' suma las filas cuya etapa SIGUIENTE es 'Paid'. El porcentaje
es 1 menos pagado entre vigente, con numerador y denominador de universos distintos. La tabla no
tiene relacion con el grid, asi que los slicers de la pagina no la afectan.
De donde sale: la tabla calculada en DAX bnpl_loss_rates_with_lead, derivada de
pbi_bnpl.bnpl_loss_rates (columnas stage1 a stage7).
""",

"e61d48d8360b398620ad": """
Que mide: Clientes, pedidos desembolsados, pedidos pagados y el porcentaje que no se pago.
Universo y corte: Cuenta pedidos distintos desplegados por etapa de mora alcanzada, asi que un
mismo pedido aparece en varias etapas. 'Pedidos pagados' son los que llegaron a la etapa 'Paid'.
La tabla no tiene relacion con el grid: los slicers de oficina, ruta, edad y genero de la pagina
no la afectan.
De donde sale: la tabla calculada en DAX bnpl_loss_rates_with_lead, derivada de
pbi_bnpl.bnpl_loss_rates.
""",

"329dfe5f21b4a710974a": """
Que mide: Cuántos clientes pasan de una etapa de mora a la siguiente (roll rates).
Universo y corte: Cada pedido se despliega en una fila por etapa alcanzada; las columnas son la
etapa SIGUIENTE del mismo pedido. Cuenta pedidos distintos, no clientes, pese al subtitulo.
La tabla no tiene relacion con el grid: los slicers de la pagina no la afectan.
De donde sale: la tabla calculada en DAX bnpl_loss_rates_with_lead, derivada de
pbi_bnpl.bnpl_loss_rates.
""",

"bee6d8c159bacc355305": """
Que mide: Qué porcentaje de los que estaban en una etapa de mora pasa a cada etapa siguiente.
Universo y corte: El porcentaje es sobre el total de la etapa anterior (la fila). Cada pedido se
despliega en una fila por etapa alcanzada. La tabla no tiene relacion con el grid: los slicers
de la pagina no la afectan.
De donde sale: la tabla calculada en DAX bnpl_loss_rates_with_lead, derivada de
pbi_bnpl.bnpl_loss_rates.
""",

"cbceea75131872e0738b": """
Que mide: Cuánto monto pasa de una etapa de mora a la siguiente (roll rates por capital).
Universo y corte: Suma el monto financiado de los pedidos desplegados por etapa alcanzada; las
columnas son la etapa siguiente del mismo pedido. La tabla no tiene relacion con el grid: los
slicers de la pagina no la afectan.
De donde sale: la tabla calculada en DAX bnpl_loss_rates_with_lead, derivada de
pbi_bnpl.bnpl_loss_rates.
""",

"c1dd49270127c6c601ca": """
Que mide: Qué porcentaje del monto que estaba en una etapa de mora pasa a cada etapa siguiente.
Universo y corte: El porcentaje es sobre el monto total de la etapa anterior (la fila). La tabla
no tiene relacion con el grid: los slicers de la pagina no la afectan.
De donde sale: la tabla calculada en DAX bnpl_loss_rates_with_lead, derivada de
pbi_bnpl.bnpl_loss_rates.
""",

"d0ab979d830d90d87cc0": """
Que mide: Cuánto capital desembolsado hay en cada bucket de mora, mes a mes.
Universo y corte: El eje es la fecha ESPERADA de pago del credito, no la fecha del pedido ni la
del pago real. Una fila por pedido entregado. La ruta de esta tabla es la historica. El ultimo
mes del eje esta incompleto.
De donde sale: la vista pbi_bnpl.bnpl_loss_rates, sobre bnpl.loss_rates.
""",

"a06d7f67dd080a08ed06": """
Que mide: Cómo se reparte porcentualmente el capital desembolsado entre buckets de mora, mes a
mes.
Universo y corte: El eje es la fecha ESPERADA de pago, no la del pedido ni la del pago real.
Ruta historica. El ultimo mes del eje esta incompleto.
De donde sale: la vista pbi_bnpl.bnpl_loss_rates, sobre bnpl.loss_rates.
""",
}

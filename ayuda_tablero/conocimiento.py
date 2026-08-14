# -*- coding: utf-8 -*-
"""Base de conocimiento verificada: que es cada tabla, de donde sale y que hay que advertir.

Todo lo de aqui esta comprobado contra sql/pbi/*.sql, el TMDL del modelo y la base
(medido 2026-08-14). Los numeros que se citan salieron de consultas, no de estimaciones.
"""

# ---------- advertencias reutilizables ----------
RUTA_HIST = ("La ruta, el supervisor y la oficina son los que tenia el cliente cuando se "
             "origino el credito (ruta historica), no los de hoy.")
RUTA_VIG = ("La ruta, el supervisor y la oficina son los vigentes: quien atiende la cuenta hoy.")
PAIDPREV = ("El 85.9% de las filas son pedidos ya pagados en cortes anteriores ('PaidPrev'). "
            "par_snapshot les pone SALDO cero, asi que no suman en las graficas de saldo; su VENTA "
            "BRUTA en cambio si suma ($1,684M, el 88% del total de la tabla), asi que en las "
            "graficas que miden venta bruta 'PaidPrev' es la barra dominante.")
MES_CURSO = ("El ultimo corte del eje es el mes en curso y esta incompleto: hoy llega al "
             "2026-08-31 con datos solo hasta el dia 12.")
ALCANCE_GRID = ("Los slicers que salen del grid la filtran por la via de "
                "loans_matured_default_profile, que cubre el 99.84% de las filas: al usar "
                "cualquiera de esos filtros se caen 1,747 pedidos ($3.88M de saldo) que no "
                "estan en esa tabla.")
SIN_GRID = ("No tiene relacion con el grid, asi que los slicers de oficina, ruta, edad o "
            "genero de la pagina no la afectan.")

# ---------- tablas ----------
T = {
 "bnpl_loss_rates": dict(
    grano="una fila por pedido BNPL entregado (92,009)",
    fuente="la vista pbi_bnpl.bnpl_loss_rates, sobre bnpl.loss_rates (Mongo: credit-order + payment-report)",
    notas=[RUTA_HIST]),
 "bnpl_grouped_orders": dict(
    grano="una fila por pedido BNPL (99,019)",
    fuente="la vista pbi_bnpl.bnpl_grouped_orders, sobre bnpl.grouped_orders",
    notas=["Trae las dos rutas: 'tipo' es la estructura comercial del momento del pedido y "
           "'tipoActual' la de hoy."]),
 "grid_bnpl": dict(
    grano="una fila por cliente (146,542)",
    fuente="la vista pbi_bnpl.grid_bnpl, sobre bnpl.grid_bnpl mas bnpl.dim_ruta_actual",
    notas=[RUTA_VIG]),
 "bnpl_par": dict(
    grano="una fila por pedido y por corte de fin de mes (1,061,120)",
    fuente="la vista pbi_bnpl.bnpl_par, sobre bnpl.par_snapshot con la estructura comercial de bnpl.loss_rates",
    notas=[RUTA_HIST, PAIDPREV, MES_CURSO]),
 "months_closes": dict(
    grano="una fila por pedido y por corte de fin de mes (1,061,120)",
    fuente="la vista pbi_bnpl.months_closes, la misma bnpl.par_snapshot que bnpl_par con otros nombres de columna",
    notas=[RUTA_HIST, PAIDPREV, MES_CURSO, ALCANCE_GRID]),
 "vintage_analysis": dict(
    grano="una fila por cohorte de enrolamiento y mes de maduracion (530)",
    fuente="la vista pbi_bnpl.vintage_analysis, sobre bnpl.vintage_analysis",
    notas=["La pagina excluye el mes de maduracion -1.", SIN_GRID]),
 "loans_matured_default_profile": dict(
    grano="una fila por pedido ya vencido (90,262)",
    fuente="la vista pbi_bnpl.loans_matured_default_profile, sobre bnpl.loss_rates, bnpl.grid_bnpl y las ventas de Redshift",
    notas=[]),
 "overall_prev_post_bnpl_sales": dict(
    grano="una fila por cliente y mes relativo al enrolamiento (1,293,358)",
    fuente="la vista pbi_bnpl.overall_prev_post_bnpl_sales, sobre las ventas de Redshift mas bnpl.grid_bnpl",
    notas=["Compara la venta del cliente antes y despues de entrar a BNPL, no solo su venta BNPL."]),
 "bnpl_cosechas_agg": dict(
    grano="una fila por cosecha y mes (51,721)",
    fuente="la vista pbi_bnpl.bnpl_cosechas_agg, sobre redshift_bnpl.cosechas_agg",
    notas=["Diciembre-2023 viene dividido entre 20 por un defecto de la fuente de Redshift.",
           "De 2025 en adelante el monto es venta surtida y antes venta ordenada: hay un "
           "escalon de +14.5% en enero-2025.", SIN_GRID]),
 "bnpl_audiencia_agg": dict(
    grano="un panel de cliente por mes (214 filas agregadas)",
    fuente="la vista pbi_bnpl.bnpl_audiencia_agg, derivada de bnpl.grouped_orders",
    notas=["Clasifica con 'tipoActual', la ruta vigente.",
           "Dormant, Inactivo y Dropped son clientes que NO compraron ese mes.", SIN_GRID]),
 "bnpl_loss_rates_with_lead": dict(
    grano="una fila por pedido y por etapa de mora alcanzada",
    fuente="una tabla calculada en DAX sobre pbi_bnpl.bnpl_loss_rates (columnas stage1 a stage7)",
    notas=["'lead_stage' es la etapa siguiente del mismo pedido: de ahi salen las tasas de transicion.",
           SIN_GRID]),
 "odds_table": dict(grano="una fila por atributo y rango (18)",
    fuente="la vista pbi_bnpl.odds_table, sobre bnpl.loss_rates y bnpl.grid_bnpl",
    notas=["Es la salida de un analisis de riesgo (WOE/IV), no una extraccion.",
           "El corte del bin esta congelado del archivo original."]),
 "vars_and_iv": dict(grano="una fila por variable (6)",
    fuente="la vista pbi_bnpl.vars_and_iv, sobre bnpl.loss_rates y bnpl.grid_bnpl",
    notas=["Es la salida de un analisis de riesgo (WOE/IV), no una extraccion."]),
 "odds_combinations": dict(grano="una fila por combinacion de atributos (84,986)",
    fuente="la vista pbi_bnpl.odds_combinations, espejo del archivo que publica Riesgo",
    notas=["Se carga a mano desde el Drive; no se recalcula con el pipeline.",
           "Tres de los once atributos estan rotos en origen (dos son constante cero y "
           "grossSalesVolume3Months es identica a la de 6 meses)."]),
 "atr_combinations_iv": dict(grano="una fila por par de atributos (468)",
    fuente="la vista pbi_bnpl.atr_combinations_iv, espejo del archivo que publica Riesgo",
    notas=["Se carga a mano desde el Drive; no se recalcula con el pipeline."]),
 "ps_transactional_profile": dict(grano="una fila por cliente de Pago de Servicios (100,793)",
    fuente="la vista pbi_bnpl.ps_transactional_profile, espejo del archivo que publica Pago de Servicios",
    notas=["El archivo no se republica desde el 2026-01-08.",
           "El 40% de los clientes BNPL no cruza contra el: quedan sin perfil, no en cero."]),
 "bnpl_cac": dict(grano="una fila por cohorte de enrolamiento (25)",
    fuente="la vista pbi_bnpl.bnpl_cac, espejo de un archivo que captura negocio a mano",
    notas=["No se actualiza desde la cohorte 2025-12: faltan 8 cohortes con 821 clientes."]),
 "seasonality_delta": dict(grano="una fila por mes y segmento (132)",
    fuente="la vista pbi_bnpl.seasonality_delta, sobre redshift_bnpl.estacionalidad_mes", notas=[]),
 "CacTable": dict(grano="tabla calculada en DAX", fuente="derivada de pbi_bnpl.bnpl_cac", notas=[]),
 "Top100InactiveCustomers": dict(grano="tabla calculada en DAX sobre el grid",
    fuente="derivada de pbi_bnpl.grid_bnpl", notas=[]),
 "dq_order": dict(grano="catalogo de buckets de mora", fuente="tabla capturada en DAX",
    notas=["No contiene 'PaidPrev', asi que esas filas caen en la fila en blanco de la relacion."]),
}

# tablas auxiliares de apoyo (selectores, ejes dinamicos): no llevan advertencias
AUX = {"revenue_view_selector", "dynamic_sales_orders_dates", "dynamic_enrollment_dates",
       "sales_order_dates", "enrollment_dates", "x_axis_type", "X Axis Type", "cohort_type",
       "Cohort Type", "Cohorte (Total)", "Cohort X Axis Type", "Cosecha Enrolamiento",
       "Cosecha activacion", "Medidas Audiencia", "Clientes_Mensual", "TablaParaGrafica",
       "revenue_view_selector"}

# ---------- significado de campos (los que se usan) ----------
C = {
 "totalAmount": "el monto financiado del pedido",
 "totalAmountToPay": "el monto que el tendero debe pagar (capital mas interes con IVA)",
 "orderGrossSales": "la venta bruta del pedido",
 "totalPrice": "el importe del pedido",
 "interests": "el interes del credito, sin IVA",
 "rabbitRevenue": "la comision de Rabbit (14.2% sobre el interes con IVA)",
 "totalRevenue": "el interes total del credito (Propaga mas Rabbit)",
 "defaultInterest": "el interes moratorio (200 pesos por semana completa de atraso)",
 "creditLimit": "la linea de credito autorizada",
 "enrolledCreditLimit": "la linea de credito de la cohorte al enrolarse",
 "netsuiteId": "el cliente",
 "salesOrderId": "el pedido",
 "quantity": "las piezas del pedido",
 "skus": "los SKU distintos del pedido",
 "daysPastDue": "los dias de atraso",
 "PAR": "el bucket de mora del pedido",
 "dqBucket": "el bucket de mora al corte",
 "newDQBucket": "el bucket de mora al corte, marcando como 'Written Off' todo lo de 120 dias o mas",
 "deployedCapital": "el capital desplegado (la suma de lo prestado)",
 "outstandingBalance": "el saldo vivo",
 "PAR30": "el saldo con 30 dias o mas de atraso",
 "PAR60": "el saldo con 60 dias o mas de atraso",
 "PAR90": "el saldo con 90 dias o mas de atraso",
 "everActivated": "los clientes de la cohorte que alguna vez usaron el credito",
 "enrolled_customers": "los clientes enrolados de la cohorte",
 "EnrolledCustomers": "los clientes enrolados de la cohorte",
 "everActivatedCustomers": "los clientes de la cohorte que alguna vez usaron el credito",
 "enrollment_cohort": "la cohorte de enrolamiento",
 "monthsSinceEnrollment": "los meses transcurridos desde que el cliente se enrolo",
 "monthsFromEnrollmentToMonth": "los meses de maduracion de la cohorte",
 "corte": "el cierre de mes",
 "createdAt": "la fecha de creacion del pedido",
 "deliveryAt": "la fecha de entrega",
 "paidDate": "la fecha en que se pago",
 "expectedPaymentDate": "la fecha en que se esperaba el pago",
 "bnplEnrolledAt": "la fecha de enrolamiento",
 "ruta": "la ruta de preventa",
 "oficina": "la oficina de preventa",
 "supervisor": "el supervisor",
 "tipo": "el tipo de cliente de la estructura comercial del momento del pedido",
 "tipoActual": "el tipo de cliente de la estructura comercial vigente",
 "shopName": "la tienda",
 "inferredGender": "el genero del cliente que reporta Mongo",
 "deliveryStatus": "el estado de entrega del pedido",
 "orderStatus": "el estado del pedido",
 "salesChannel": "el canal de venta",
 "loanDisbursementIndex": "el numero de credito del cliente (1, 2, 3 o 4 y mas)",
 "stage": "la etapa de mora",
 "lead_stage": "la etapa de mora siguiente del mismo pedido",
 "grossSales": "la venta bruta",
 "customerAgeAtEligibility": "la edad del cliente al volverse elegible",
 "customerAgeRangeAtEligibility": "el rango de edad del cliente al volverse elegible",
 "bnplOrdersCount": "el numero de pedidos BNPL del cliente",
 "cliente_activo": "los clientes activos de la cosecha",
 "clientes_cosecha": "los clientes de la cosecha",
 "ordenes": "los pedidos",
 "mes_tx": "el mes de la transaccion",
 "woe": "el peso de la evidencia (WOE) del atributo",
 "iv": "el valor de informacion (IV) del atributo",
}

# medidas: frase de negocio (el DAX exacto va en el volcado, aqui va el significado)
M = {
 "dynamicRevenue": ("la comision de Rabbit, que por defecto se muestra SIN IVA "
                    "(rabbitRevenue dividido entre 1.16); el selector 'Tipo de Revenue' la cambia"),
 "revenueAfterTaxes": "la comision de Rabbit sin IVA (rabbitRevenue entre 1.16)",
 "revenueBeforeTaxes": "la comision de Rabbit con IVA",
 "dynamicTotalRevenue": ("el interes total del credito, que por defecto se muestra sin IVA "
                         "(entre 1.16)"),
 "totalActiveCustomers": "el numero de clientes distintos con pedido",
 "totalNumberOfTransactions": "el numero de pedidos",
 "totalGrossSales": "la venta bruta total",
 "frequency": "los pedidos por cliente",
 "avgTicket": "el ticket promedio por pedido",
 "avgSkus": "los SKU promedio por pedido",
 "avgItems": "las piezas promedio por pedido",
 "avgGrossSalesCustomer": "la compra promedio por cliente",
 "avgNumberOfTransactionsCustomer": "los pedidos promedio por cliente",
 "locPenetration": "el uso de la linea de credito (venta sobre linea autorizada)",
 "activeCusomerRate": "la proporcion de clientes enrolados que compraron",
 "cumulativeEnrolledCustomers": "los clientes enrolados acumulados hasta la fecha del eje",
 "activeCustomers": "los clientes distintos con pedido",
 "par30RateAmount": "la tasa PAR30 sobre CAPITAL DESPLEGADO (hoy 6.02%)",
 "par60RateAmount": "la tasa PAR60 sobre capital desplegado",
 "par90RateAmount": "la tasa PAR90 sobre capital desplegado",
 "par30RateCustomers": "la tasa PAR30 sobre CLIENTES ACTIVADOS (hoy 31.30%)",
 "par60RateCustomers": "la tasa PAR60 sobre clientes activados",
 "par90RateCustomers": "la tasa PAR90 sobre clientes activados",
 "par30RateAmountNotFilters": "la tasa PAR30 sobre capital desplegado, ignorando el filtro de cohorte",
 "closeMonthDenominator": ("la suma del saldo de TODAS las filas del mismo corte, ignorando los "
                           "filtros de bucket y de dias del propio visual"),
 "NumberOfCustomers": "el numero de clientes distintos",
 "NumberOfLoansDisbursed": "el numero de pedidos distintos",
 "NumberOfLoansPaid": "el numero de pedidos que llegaron a la etapa 'Paid'",
 "PercentageOfLoansChargedOff": ("1 menos los pedidos pagados entre los pedidos totales"),
 "AmountOfDisbursedLoans": "el saldo de los pedidos en etapa 'Ongoing' (los que aun no vencen)",
 "AmountOfPaidLoans": "el saldo de los pedidos cuya etapa siguiente es 'Paid'",
 "PercentageOfAmountChargedOff": ("1 menos el saldo pagado entre el saldo vigente; el numerador y "
                                  "el denominador salen de universos distintos"),
 "supervivencia": "la proporcion de clientes de la cosecha que siguen activos",
 "dropSizeM": "el ticket promedio por pedido de la cosecha",
 "frequenciaM": "los pedidos por cliente activo de la cosecha",
 "grossSalesMetric": "la venta bruta por cliente",
 "frequencyOP": "los pedidos por cliente",
 "historicalFrequency": "los pedidos por cliente en el historico",
 "MonthlyGrossSales": "la venta bruta mensual por cliente",
 "EnrolledCustomersMetric": "los clientes enrolados de la cohorte",
 "avgMonthSale": "la compra promedio por cliente",
 "avgTicketTotal": "el ticket promedio ignorando el filtro de cohorte",
 "activeCustomersOverCumulativeEnrolledCustomersRate":
     "los clientes activos sobre los enrolados acumulados",
 "% variación Gross Sales": "la variacion de venta bruta contra el grupo sin BNPL",
 "incrementoDropSize": "el incremento de ticket contra el grupo sin BNPL",
 "incrementoFrecuencia": "el incremento de frecuencia contra el grupo sin BNPL",
 "incrementoSupervivencia": "el incremento de supervivencia contra el grupo sin BNPL",
 "bnplCustomersInSelection": "los clientes BNPL activos de la seleccion",
}

# medidas que faltaban (leidas del DAX del modelo)
M.update({
 "AverageTotalActiveCustomersRow": "los clientes activos: el valor de la celda si hay cohorte y mes en contexto, y si no el promedio de las celdas",
 "AverageNumberOfTransactionsRow": "los pedidos: el valor de la celda, o el promedio de las celdas cuando no hay cohorte y mes en contexto",
 "AverageTotalGrossSalesRow": "la venta bruta: el valor de la celda, o el promedio de las celdas cuando no hay cohorte y mes en contexto",
 "avgGrossSalesCustomerRow": "la compra promedio por cliente, con el mismo promedio de celdas cuando no hay cohorte y mes en contexto",
 "avgNumberOfTransactionsCustomerRow": "los pedidos promedio por cliente, con el mismo promedio de celdas fuera de contexto",
 "ActiveCustomerRateRow": "la tasa de clientes activos, con el mismo promedio de celdas fuera de contexto",
 "dropSizePlot": "el ticket promedio de la cohorte seleccionada, o el promedio ponderado de todas si se elige 'WAVG'",
 "frecuencyPlot": "la frecuencia de la cohorte seleccionada, o el promedio ponderado de todas si se elige 'WAVG'",
 "TasaSupervivencia": "la tasa de supervivencia de la cohorte",
 "baseTendencia": "la venta de referencia del mes previo al primer pedido BNPL, usada como linea base",
 "RebaseSobreTendencia": "la venta acumulada desde el primer pedido BNPL, reexpresada sobre esa linea base",
 "tendenciaEnroladosProyectada": "la tendencia proyectada de los clientes enrolados",
 "tendenciaNoEnroladosProyectada": "la tendencia proyectada de los clientes no enrolados",
 "tendenciaEnroladosDropProyectada": "la tendencia proyectada de ticket de los clientes enrolados",
 "tendenciaNoEnroladosDropProyectada": "la tendencia proyectada de ticket de los clientes no enrolados",
 "ft tx bnpl min": "el primer mes con transaccion BNPL",
 "Fecha 10% Y": "el mes en que la cohorte BNPL alcanza el 10% de sus clientes",
 "valor": "el valor de la audiencia seleccionada",
})

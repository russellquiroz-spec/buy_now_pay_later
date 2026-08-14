"""Configuracion de la capa de operacion (frescura y calidad) del pipeline BNPL."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SQL_DIR = BASE_DIR / "sql"

# Alias de postgres_local_client. La conexion ya no se arma aca: la libreria resuelve
# host, credenciales y schema por alias desde su propio .env, y cada alias trae su
# nivel de permiso. Los `_rw` son los unicos que aceptan escritura y DDL.
DB_OPS = "bnpl_ops"
DB_OPS_RW = "bnpl_ops_rw"
DB_STAGING = "mongo_bnpl"
# Alias de lectura de la capa de negocio. Lo usan los checks de identidad entre capas, que son
# los unicos que no miran el staging.
DB_BNPL = "bnpl"

MONGO_PROFILE = "bnpl"
OPS_SCHEMA = "bnpl_ops"
STAGING_SCHEMA = "mongo_bnpl"

# Las fechas del negocio se manejan en hora Mexico; Mongo entrega UTC.
TZ_OFFSET_HOURS = -6

# Umbrales de frescura de la fuente (horas desde la ultima escritura en Mongo).
LAG_WARN_HORAS = 24
LAG_CRIT_HORAS = 48

# Fuentes cuya falta de frescura invalida el resultado: si una de estas esta en CRIT, el
# pipeline se detiene porque las tablas finales saldrian mal.
#
# El resto puede estar en CRIT sin abortar. fintech-customers, por ejemplo, lleva sin escrituras
# desde el 2026-07-23: eso deja a los clientes nuevos sin shopName, pero no invalida la mora ni el
# revenue. Abortar por eso seria dejar el tablero congelado por un problema que no lo afecta.
FUENTES_CRITICAS = [
    "credit-order-production",
    "payment-report-production",
    "state-of-delivery-report-production",
]

# Tolerancia de desfase del staging respecto a Mongo, como fraccion de los documentos.
FALTANTES_WARN_PCT = 0.01


# Definicion de cada fuente:
#   tabla        tabla espejo en el staging
#   col_fecha    columna epoch ms del staging para la ultima fecha de negocio (None si es string ISO)
#   campo_update campo epoch ms de Mongo que marca actualizaciones in-place.
#                Solo se declara donde la coleccion se modifica sin insertar: ahi el _id
#                (que solo refleja inserciones) subestima la frescura real.
FUENTES = {
    "credit-order-production": {
        "tabla": "credit_order_production", "col_fecha": "createdAt", "campo_update": None,
    },
    "payment-report-production": {
        "tabla": "payment_report_production", "col_fecha": "movementDate", "campo_update": None,
    },
    "state-of-delivery-report-production": {
        "tabla": "state_of_delivery_report_production", "col_fecha": "deliveryDate",
        "campo_update": None,
    },
    "fintech-customers-production": {
        "tabla": "fintech_customers_production", "col_fecha": None, "campo_update": "updatedAt",
    },
    "fintech-credit-request-production": {
        "tabla": "fintech_credit_request_production", "col_fecha": "createdAt",
        "campo_update": None,
    },
    "fintech-credit-approval-production": {
        "tabla": "fintech_credit_approval_production", "col_fecha": None, "campo_update": None,
    },
    "fintech-pre-authorization-status-production": {
        "tabla": "fintech_pre_authorization_status_production", "col_fecha": None,
        "campo_update": None,
    },
    "revenue-orders-production": {
        "tabla": "revenue_orders_production", "col_fecha": None, "campo_update": None,
    },
    "propaga-transaction-dev": {
        "tabla": "propaga_transaction", "col_fecha": None, "campo_update": None,
    },
    "credit-limit-history-management-production": {
        "tabla": "credit_limit_history_management", "col_fecha": "creditLimitUpdateDate",
        "campo_update": None,
    },
}

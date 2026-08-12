"""Extraccion Mongo BNPL -> staging PostgreSQL (schema mongo_bnpl).

Modos de carga:
  normal    TRUNCATE + append; para credit-order reprocesa solo una ventana reciente.
  --full    recarga completa de todas las tablas (TRUNCATE, preserva el DDL y los indices).
  --recrear DROP + recrea desde sql/01_staging.sql. Solo cuando cambia la proyeccion, y
            actualizando ese .sql primero: el esquema lo gobierna el DDL, no la inferencia de pandas.

La ventana existe porque las ordenes cambian de estado despues de creadas (CREATED -> COMPLETED,
deliveryAt se llena al entregar). Un incremental por _id solo veria inserciones y perderia esos
cambios, asi que se re-extraen los ultimos VENTANA_DIAS dias por createdAt.

Medido sobre el historico: una orden se entrega a mas tardar 17 dias despues de creada, asi que
60 dias dan 3.5x de margen y bajan el 8% de las filas en vez del 100%. Lo que la ventana no cubre
son las ordenes que quedaron en estado no final hace mas tiempo; esas se re-extraen dirigidas por
salesOrderId. Y cada FULL_CADA_DIAS se recarga la tabla completa, porque comparar conteos detecta
inserciones y borrados pero no modificaciones in-place del historico congelado.
"""
import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from mongo_extractor import extract_aggregate
from sqlalchemy import create_engine, inspect, text

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
PG_URL = os.environ["BD_ENGINE_RABBIT_LOCAL"].strip("'\"")
engine = create_engine(PG_URL)

SCHEMA = "mongo_bnpl"
OPS_SCHEMA = "bnpl_ops"
MONGO_PROFILE = "bnpl"
VENTANA_DIAS = 60
FULL_CADA_DIAS = 30
TZ_OFFSET_HOURS = -6

COLLECTIONS = [
    {
        "collection": "credit-order-production",
        "table": "credit_order_production",
        "modo": "ventana",
        "campo_ventana": "createdAt",
        # Las ordenes que no esten en un estado final se re-extraen aunque hayan salido
        # de la ventana: son las unicas que todavia pueden cambiar.
        "campo_estado": "orderStatus",
        "estados_finales": ["COMPLETED", "REJECTED", "CANCELLED", "NO_VISITED"],
        "llave_refresco": "salesOrderId",
        "pipeline": [
            {
                "$project": {
                    "_id": 0,
                    "createdAt": 1,
                    "netsuiteId": 1,
                    "salesOrderId": 1,
                    "orderId": 1,
                    "totalPrice": 1,
                    "totalPriceFinal": 1,
                    "orderGrossSales": 1,
                    "quantity": 1,
                    "productId": 1,
                    "productDescription": 1,
                    "category": 1,
                    "brand": 1,
                    "subcategory": 1,
                    "vendor": 1,
                    "iva": 1,
                    "ieps": 1,
                    "couponCode": 1,
                    "couponValue": 1,
                    "orderStatus": 1,
                    "salesChannel": 1,
                    "shortId": 1,
                    "deliveryAt": 1,
                }
            }
        ],
    },
    {
        # 'status' no existe: el estado del pago es 'state' y el de la transaccion
        # 'transactionStatus'. transactionId es la llave contra salesOrderId.
        "collection": "payment-report-production",
        "table": "payment_report_production",
        "modo": "full",
        "pipeline": [
            {
                "$project": {
                    "_id": 0,
                    "clientId": 1,
                    "creditId": 1,
                    "transactionId": 1,
                    "transactionPropagaId": 1,
                    "marketplaceOrderId": 1,
                    "movementDate": 1,
                    "paymentDateFromToPay": 1,
                    "paymentDateFromPaid": 1,
                    "totalAmount": 1,
                    "totalAmountToPay": 1,
                    "totalAmountDefault": 1,
                    "interests": 1,
                    "comisionPorCobrar": 1,
                    "creditLimit": 1,
                    "state": 1,
                    "transactionStatus": 1,
                }
            }
        ],
    },
    {
        # latitude/longitude no viven aqui sino en credit-request. customerId es la
        # llave contra credit-request y approval.
        "collection": "fintech-customers-production",
        "table": "fintech_customers_production",
        "modo": "full",
        "pipeline": [
            {
                "$project": {
                    "_id": 0,
                    "netsuiteId": 1,
                    "customerId": 1,
                    "shopkeeperId": 1,
                    "shopName": "$name",
                    "phoneNumber": 1,
                    "gender": 1,
                    "business_category": 1,
                    "address": 1,
                    "hasMarketplace": 1,
                    "hasPresales": 1,
                    "updatedAt": 1,
                }
            }
        ],
    },
    {
        "collection": "fintech-credit-request-production",
        "table": "fintech_credit_request_production",
        "modo": "full",
        "pipeline": [
            {
                "$project": {
                    "_id": 0,
                    "customerId": 1,
                    "requestId": 1,
                    "createdAt": 1,
                    "name": 1,
                    "lastNames": 1,
                    "birthdate": 1,
                    "phoneNumber": 1,
                    "gender": 1,
                    "latitude": 1,
                    "longitude": 1,
                    "origin": 1,
                    "requestType": 1,
                    "requestResult": 1,
                }
            }
        ],
    },
    {
        # 'approvalDate' no existe: la fecha de aprobacion es createdAt (string ISO).
        # 'enrollmentChannel' tampoco: el canal es 'origin'.
        "collection": "fintech-credit-approval-production",
        "table": "fintech_credit_approval_production",
        "modo": "full",
        "pipeline": [
            {
                "$project": {
                    "_id": 0,
                    "netsuiteId": 1,
                    "customerId": 1,
                    "approvalId": 1,
                    "createdAt": 1,
                    "creditLimit": 1,
                    "creditLimitAvailable": 1,
                    "origin": 1,
                    "approvalType": 1,
                    "status": 1,
                }
            }
        ],
    },
    {
        # La coleccion sin sufijo -production no existe.
        "collection": "fintech-pre-authorization-status-production",
        "table": "fintech_pre_authorization_status_production",
        "modo": "full",
        "pipeline": [
            {
                "$project": {
                    "_id": 0,
                    "netsuiteId": 1,
                    "customerId": 1,
                    "preAuthorizationId": 1,
                    "preAuthorized": 1,
                    "authorizationDate": 1,
                    "authorizationExpirationDate": 1,
                    "clientOfferDate": 1,
                    "propagaCreditData": 1,
                }
            }
        ],
    },
    {
        # El sales order vive en 'orderId' (SO...), no en 'salesOrderId'.
        "collection": "state-of-delivery-report-production",
        "table": "state_of_delivery_report_production",
        "modo": "full",
        "pipeline": [
            {
                "$project": {
                    "_id": 0,
                    "netsuiteId": "$clientId",
                    "salesOrderId": "$orderId",
                    "marketplaceOrderId": 1,
                    "deliveryStatus": "$status",
                    "deliveryDate": 1,
                    "orderAmount": 1,
                    "salesChannel": 1,
                    "reason": 1,
                }
            }
        ],
    },
    {
        # Solo llaves y estado: sus montos estan corruptos (ver PENDIENTES_NEGOCIO.md).
        # La fuente de verdad del revenue es payment-report-production.
        "collection": "revenue-orders-production",
        "table": "revenue_orders_production",
        "modo": "full",
        "pipeline": [
            {
                "$project": {
                    "_id": 0,
                    "transactionId": 1,
                    "salesOrderId": 1,
                    "clientId": 1,
                    "creditId": 1,
                    "propagaTransactionId": 1,
                    "fintechStatus": 1,
                    "state": 1,
                }
            }
        ],
    },
    {
        # Espejo de la transaccion en Propaga: reemplaza las conciliaciones revenue*.xlsx.
        "collection": "propaga-transaction-dev",
        "table": "propaga_transaction",
        "modo": "full",
        "pipeline": [
            {
                "$project": {
                    "_id": 0,
                    "id": 1,
                    "netsuiteId": 1,
                    "customerId": 1,
                    "salesOrderId": 1,
                    "wholesalerTransactionId": 1,
                    "verificationId": 1,
                    "totalAmount": 1,
                    "totalAmountWithInterests": 1,
                    "interests": 1,
                    "iVAAmount": 1,
                    "amountPaid": 1,
                    "status": 1,
                    "currentState": 1,
                    "movementDate": 1,
                    "paymentDate": 1,
                    "paidDate": 1,
                    "deliveryDate": 1,
                    "createdAt": 1,
                    "updatedAt": 1,
                    # 'wholesaler' no se proyecta: unas veces es "Rabbit" y otras el objeto
                    # completo de configuracion del mayorista, que no aporta al analisis.
                }
            }
        ],
    },
    {
        # Linea original vs vigente para grid_bnpl.
        "collection": "credit-limit-history-management-production",
        "table": "credit_limit_history_management",
        "modo": "full",
        "pipeline": [
            {
                "$project": {
                    "_id": 0,
                    "netsuiteId": 1,
                    "customerId": 1,
                    "originalCreditLimit": 1,
                    "currentCreditLimit": 1,
                    "creditLimitAvailable": 1,
                    "creditLimitUpdateDate": 1,
                    "customerStatus": 1,
                    "creditHistory": 1,
                }
            }
        ],
    },
]


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    # max_level=1: mas profundo genera nombres que Postgres trunca a 63 caracteres y
    # llega a colisionar entre si. Lo que quede anidado se guarda como JSON.
    records = df.to_dict(orient="records")
    flat = pd.json_normalize(records, sep="_", max_level=1)

    # Un dict opcional (address en customers) deja dos rastros: las columnas aplanadas de los
    # documentos que lo traen y una columna con el nombre pelado, siempre nula, de los que no.
    # Esa segunda no existe en el DDL, asi que se descarta.
    residuos = [
        col for col in flat.columns
        if flat[col].isna().all() and any(c.startswith(f"{col}_") for c in flat.columns)
    ]
    if residuos:
        flat = flat.drop(columns=residuos)

    for col in flat.columns:
        if flat[col].apply(lambda x: isinstance(x, (list, dict))).any():
            flat[col] = flat[col].apply(
                lambda x: json.dumps(x, default=str) if isinstance(x, (list, dict)) else x
            )
    return flat


def _corte_ventana_ms() -> int:
    corte = datetime.now(timezone.utc) - timedelta(days=VENTANA_DIAS)
    return int(corte.timestamp() * 1000)


def _ahora_mx() -> datetime:
    return (datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)).replace(tzinfo=None)


def _tabla_existe(nombre: str) -> bool:
    return inspect(engine).has_table(nombre, schema=SCHEMA)


def _dias_desde_ultimo_full(tabla: str):
    """Dias desde la ultima recarga completa de la tabla; None si nunca hubo una."""
    with engine.connect() as conn:
        ultimo = conn.execute(
            text(
                f"SELECT max(started_at) FROM {OPS_SCHEMA}.etl_runs "
                f"WHERE tabla = :tabla AND modo = 'full'"
            ),
            {"tabla": f"{SCHEMA}.{tabla}"},
        ).scalar()
    return None if ultimo is None else (_ahora_mx() - ultimo).days


def _llaves_no_finales(defn: dict, corte_ms) -> list:
    """Llaves de los registros en estado no final que ya salieron de la ventana."""
    tabla, campo_estado = defn["table"], defn.get("campo_estado")
    if not campo_estado:
        return []
    finales = defn["estados_finales"]
    llave = defn["llave_refresco"]
    marcadores = ", ".join(f":e{i}" for i in range(len(finales)))
    params = {f"e{i}": estado for i, estado in enumerate(finales)}
    params["corte"] = corte_ms
    with engine.connect() as conn:
        filas = conn.execute(
            text(
                f'SELECT DISTINCT "{llave}" FROM {SCHEMA}."{tabla}" '
                f'WHERE ("{campo_estado}" IS NULL OR "{campo_estado}" NOT IN ({marcadores})) '
                f'  AND "{defn["campo_ventana"]}" < :corte '
                f'  AND "{llave}" IS NOT NULL AND trim("{llave}") <> \'\''
            ),
            params,
        ).fetchall()
    return [f[0] for f in filas]


def _aplicar_ddl(tablas_a_recrear: list = None) -> None:
    """Aplica el DDL. Si se piden tablas a recrear, las dropea antes para que el .sql las
    vuelva a crear con los tipos declarados."""
    with engine.begin() as conn:
        for tabla in tablas_a_recrear or []:
            conn.execute(text(f'DROP TABLE IF EXISTS {SCHEMA}."{tabla}"'))
        conn.execute(text((BASE_DIR / "sql" / "00_bnpl_ops.sql").read_text(encoding="utf-8")))
        conn.execute(text((BASE_DIR / "sql" / "01_staging.sql").read_text(encoding="utf-8")))


def _preparar_destino(defn: dict, full: bool, corte_ms) -> tuple:
    """Deja la tabla lista para el append. Devuelve (modo efectivo, llaves a refrescar)."""
    tabla = defn["table"]
    completa = full

    if defn["modo"] == "ventana" and not completa:
        dias = _dias_desde_ultimo_full(tabla)
        if dias is None or dias >= FULL_CADA_DIAS:
            motivo = "sin registro de full previo" if dias is None else f"ultimo full hace {dias}d"
            print(f"  recarga completa programada ({motivo})")
            completa = True

    if completa:
        with engine.begin() as conn:
            conn.execute(text(f'TRUNCATE {SCHEMA}."{tabla}"'))
        return "full", []

    if defn["modo"] == "ventana":
        campo = defn["campo_ventana"]
        llaves = _llaves_no_finales(defn, corte_ms)
        with engine.begin() as conn:
            conn.execute(
                text(f'DELETE FROM {SCHEMA}."{tabla}" WHERE "{campo}" >= :corte'),
                {"corte": corte_ms},
            )
            if llaves:
                conn.execute(
                    text(
                        f'DELETE FROM {SCHEMA}."{tabla}" '
                        f'WHERE "{defn["llave_refresco"]}" = ANY(:llaves)'
                    ),
                    {"llaves": llaves},
                )
        return "ventana", llaves

    with engine.begin() as conn:
        conn.execute(text(f'TRUNCATE {SCHEMA}."{tabla}"'))
    return "full", []


def _registrar_corrida(tabla: str, modo: str, filas: int, segundos: float, inicio) -> None:
    # Con el schema por delante, igual que el resto del pipeline: la bitacora queda consultable
    # con un solo criterio (tabla LIKE 'mongo_bnpl.%').
    with engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {OPS_SCHEMA}.etl_runs (started_at, tabla, modo, filas, segundos) "
                f"VALUES (:inicio, :tabla, :modo, :filas, :segundos) "
                f"ON CONFLICT (started_at, tabla) DO NOTHING"
            ),
            {
                "inicio": inicio,
                "tabla": f"{SCHEMA}.{tabla}",
                "modo": modo,
                "filas": filas,
                "segundos": round(segundos, 1),
            },
        )


def run(full: bool = False, solo: list = None, recrear: bool = False) -> None:
    definiciones = COLLECTIONS
    if solo:
        definiciones = [d for d in COLLECTIONS if d["collection"] in solo or d["table"] in solo]
        desconocidas = set(solo) - {d["collection"] for d in COLLECTIONS} - {
            d["table"] for d in COLLECTIONS
        }
        if desconocidas:
            raise SystemExit(f"No existen en COLLECTIONS: {', '.join(sorted(desconocidas))}")

    _aplicar_ddl([d["table"] for d in definiciones] if recrear else None)
    corte_ms = _corte_ventana_ms()

    for defn in definiciones:
        print(f"Extrayendo {defn['collection']}...")
        inicio = _ahora_mx()
        t0 = time.time()

        modo, llaves = _preparar_destino(defn, full or recrear, corte_ms)
        pipeline = list(defn["pipeline"])
        if modo == "ventana":
            condiciones = [{defn["campo_ventana"]: {"$gte": corte_ms}}]
            if llaves:
                condiciones.append({defn["llave_refresco"]: {"$in": llaves}})
                print(
                    f"  ventana {VENTANA_DIAS}d + {len(llaves):,} "
                    f"{defn['llave_refresco']} en estado no final"
                )
            else:
                print(f"  ventana {VENTANA_DIAS}d")
            pipeline.insert(0, {"$match": {"$or": condiciones}})

        df = extract_aggregate(MONGO_PROFILE, defn["collection"], pipeline)
        filas = len(df)
        if filas:
            df = _flatten(df)
            df.to_sql(defn["table"], engine, schema=SCHEMA, if_exists="append", index=False)

        segundos = time.time() - t0
        _registrar_corrida(defn["table"], modo, filas, segundos, inicio)
        print(f"  -> {SCHEMA}.{defn['table']}: {filas:,} filas en {segundos:.0f}s ({modo})")

    engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carga el staging BNPL desde Mongo")
    parser.add_argument(
        "--full",
        action="store_true",
        help="recarga completa (TRUNCATE); preserva el DDL y los indices",
    )
    parser.add_argument(
        "--recrear",
        action="store_true",
        help="DROP y recrea desde sql/01_staging.sql; usar al cambiar la proyeccion",
    )
    parser.add_argument(
        "--solo",
        help="colecciones o tablas a cargar, separadas por coma (default: todas)",
    )
    args = parser.parse_args()
    run(
        full=args.full,
        solo=args.solo.split(",") if args.solo else None,
        recrear=args.recrear,
    )

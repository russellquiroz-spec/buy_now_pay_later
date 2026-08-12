-- Staging BNPL: espejo fiel de Mongo. Idempotente (CREATE ... IF NOT EXISTS).
--
-- Criterios:
--   * Sin PK ni UNIQUE. El staging refleja lo que Mongo tenga, incluidos duplicados; si Mongo
--     duplica, lo reporta bnpl_ops.data_quality_checks en vez de caerse la carga de las 6am.
--     Las restricciones de unicidad van en la capa `bnpl`, donde se controla la deduplicacion.
--   * Numericos de Mongo como double precision, no bigint: pandas manda NaN donde el documento
--     no trae el campo (deliveryAt ya tiene 5 nulos) y NaN no entra en un bigint. double
--     representa enteros exactos hasta 2^53 y el epoch ms actual esta en 1.8e12.
--   * Fechas: se guardan como vienen. Epoch ms en double, ISO 8601 en text. La conversion a
--     timestamp de hora Mexico vive en la capa `bnpl`, no aqui.

CREATE SCHEMA IF NOT EXISTS mongo_bnpl;
CREATE SCHEMA IF NOT EXISTS bnpl;

-- ─────────────────────────────────────────────────────────────────────────────
-- credit-order-production: 1 fila por linea de SKU de una orden a credito
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mongo_bnpl.credit_order_production (
    "createdAt"          double precision,
    "deliveryAt"         double precision,
    "netsuiteId"         text,
    "salesOrderId"       text,
    "orderId"            text,
    "shortId"            text,
    "productId"          text,
    "productDescription" text,
    category             text,
    brand                text,
    subcategory          text,
    vendor               text,
    quantity             double precision,
    "orderGrossSales"    double precision,
    "totalPrice"         double precision,
    "totalPriceFinal"    double precision,
    iva                  double precision,
    ieps                 double precision,
    "couponCode"         text,
    "couponValue"        double precision,
    "orderStatus"        text,
    "salesChannel"       text
);

CREATE INDEX IF NOT EXISTS ix_credit_order_created_at
    ON mongo_bnpl.credit_order_production ("createdAt");
CREATE INDEX IF NOT EXISTS ix_credit_order_sales_order
    ON mongo_bnpl.credit_order_production ("salesOrderId");
CREATE INDEX IF NOT EXISTS ix_credit_order_order_id
    ON mongo_bnpl.credit_order_production ("orderId");
CREATE INDEX IF NOT EXISTS ix_credit_order_netsuite
    ON mongo_bnpl.credit_order_production ("netsuiteId");

-- Nota: no hay indice para localizar las ordenes en estado no final. Se probo
-- ("orderStatus", "createdAt") y el planner lo ignora: un B-tree no sirve para el NOT IN
-- y prefiere un seq scan paralelo (455 ms). Un indice parcial lo forzaria, pero acoplaria
-- este DDL a la lista de estados finales del ETL por un ahorro irrelevante frente a los
-- ~166 s que tarda la extraccion.

-- ─────────────────────────────────────────────────────────────────────────────
-- payment-report-production: fuente de verdad del revenue. transactionId = salesOrderId
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mongo_bnpl.payment_report_production (
    "clientId"             text,
    "creditId"             text,
    "transactionId"        text,
    "transactionPropagaId" text,
    "marketplaceOrderId"   text,
    "movementDate"         double precision,
    "paymentDateFromToPay" text,
    "paymentDateFromPaid"  text,
    "totalAmount"          double precision,
    "totalAmountToPay"     double precision,
    "totalAmountDefault"   double precision,
    interests              double precision,
    "comisionPorCobrar"    double precision,
    "creditLimit"          double precision,
    state                  text,
    "transactionStatus"    text
);

CREATE INDEX IF NOT EXISTS ix_payment_transaction
    ON mongo_bnpl.payment_report_production ("transactionId");
-- Llave secundaria: recupera 193 de los 276 pagos que no cruzan por transactionId.
CREATE INDEX IF NOT EXISTS ix_payment_marketplace_order
    ON mongo_bnpl.payment_report_production ("marketplaceOrderId");
CREATE INDEX IF NOT EXISTS ix_payment_client
    ON mongo_bnpl.payment_report_production ("clientId");
CREATE INDEX IF NOT EXISTS ix_payment_status
    ON mongo_bnpl.payment_report_production ("transactionStatus");

-- ─────────────────────────────────────────────────────────────────────────────
-- state-of-delivery-report-production: 1 fila por sales order (verificado unico)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mongo_bnpl.state_of_delivery_report_production (
    "netsuiteId"         text,
    "salesOrderId"       text,
    "marketplaceOrderId" text,
    "deliveryStatus"     text,
    "deliveryDate"       double precision,
    "orderAmount"        double precision,
    "salesChannel"       text,
    reason               text
);

CREATE INDEX IF NOT EXISTS ix_delivery_sales_order
    ON mongo_bnpl.state_of_delivery_report_production ("salesOrderId");
CREATE INDEX IF NOT EXISTS ix_delivery_netsuite
    ON mongo_bnpl.state_of_delivery_report_production ("netsuiteId");

-- ─────────────────────────────────────────────────────────────────────────────
-- fintech-customers-production
-- ─────────────────────────────────────────────────────────────────────────────
-- El dict `address` llega aplanado a un nivel. latitude/longitude vienen como texto en Mongo
-- y se quedan asi: el staging no corrige tipos, eso pasa en la capa bnpl.
CREATE TABLE IF NOT EXISTS mongo_bnpl.fintech_customers_production (
    "netsuiteId"             text,
    "customerId"             text,
    "shopkeeperId"           text,
    "shopName"               text,
    "phoneNumber"            text,
    gender                   text,
    business_category        text,
    "address_street"         text,
    "address_exteriorNumber" text,
    "address_interiorNumber" text,
    "address_neighborhood"   text,
    "address_zipCode"        text,
    "address_town"           text,
    "address_state"          text,
    "address_country"        text,
    "address_latitude"       text,
    "address_longitude"      text,
    "hasMarketplace"         boolean,
    "hasPresales"            boolean,
    "updatedAt"              double precision
);

CREATE INDEX IF NOT EXISTS ix_customers_netsuite
    ON mongo_bnpl.fintech_customers_production ("netsuiteId");
CREATE INDEX IF NOT EXISTS ix_customers_customer
    ON mongo_bnpl.fintech_customers_production ("customerId");

-- ─────────────────────────────────────────────────────────────────────────────
-- fintech-credit-request-production: aqui viven latitude/longitude (llegan como texto)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mongo_bnpl.fintech_credit_request_production (
    "customerId"    text,
    "requestId"     text,
    "createdAt"     double precision,
    name            text,
    "lastNames"     text,
    birthdate       text,
    "phoneNumber"   text,
    gender          text,
    latitude        text,
    longitude       text,
    origin          text,
    "requestType"   text,
    "requestResult" text
);

CREATE INDEX IF NOT EXISTS ix_request_customer
    ON mongo_bnpl.fintech_credit_request_production ("customerId");

-- ─────────────────────────────────────────────────────────────────────────────
-- fintech-credit-approval-production: createdAt es la fecha de aprobacion (ISO)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mongo_bnpl.fintech_credit_approval_production (
    "netsuiteId"           text,
    "customerId"           text,
    "approvalId"           text,
    "createdAt"            text,
    "creditLimit"          double precision,
    "creditLimitAvailable" double precision,
    origin                 text,
    "approvalType"         text,
    status                 text
);

CREATE INDEX IF NOT EXISTS ix_approval_netsuite
    ON mongo_bnpl.fintech_credit_approval_production ("netsuiteId");
CREATE INDEX IF NOT EXISTS ix_approval_customer
    ON mongo_bnpl.fintech_credit_approval_production ("customerId");

-- ─────────────────────────────────────────────────────────────────────────────
-- fintech-pre-authorization-status-production (propagaCreditData viene aplanado)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mongo_bnpl.fintech_pre_authorization_status_production (
    "netsuiteId"                             text,
    "customerId"                             text,
    "preAuthorizationId"                     text,
    "preAuthorized"                          text,
    "authorizationDate"                      text,
    "authorizationExpirationDate"            text,
    "clientOfferDate"                        text,
    "propagaCreditData_propagaUserId"        text,
    "propagaCreditData_propagaCornerStoreId" text,
    "propagaCreditData_creditLimit"          double precision,
    "propagaCreditData_creditLimitAvailable" double precision,
    "propagaCreditData_propagaStatus"        text
);

CREATE INDEX IF NOT EXISTS ix_preauth_netsuite
    ON mongo_bnpl.fintech_pre_authorization_status_production ("netsuiteId");
CREATE INDEX IF NOT EXISTS ix_preauth_customer
    ON mongo_bnpl.fintech_pre_authorization_status_production ("customerId");

-- ─────────────────────────────────────────────────────────────────────────────
-- revenue-orders-production: solo llaves y estado, sus montos estan corruptos
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mongo_bnpl.revenue_orders_production (
    "transactionId"        text,
    "salesOrderId"         text,
    "clientId"             text,
    "creditId"             text,
    "propagaTransactionId" text,
    "fintechStatus"        text,
    state                  text
);

CREATE INDEX IF NOT EXISTS ix_revenue_transaction
    ON mongo_bnpl.revenue_orders_production ("transactionId");
CREATE INDEX IF NOT EXISTS ix_revenue_client
    ON mongo_bnpl.revenue_orders_production ("clientId");

-- ─────────────────────────────────────────────────────────────────────────────
-- propaga-transaction: espejo de la transaccion en Propaga (fechas en ISO)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mongo_bnpl.propaga_transaction (
    id                         text,
    "netsuiteId"               text,
    "customerId"               text,
    "salesOrderId"             text,
    "wholesalerTransactionId"  text,
    "verificationId"           text,
    "totalAmount"              double precision,
    "totalAmountWithInterests" double precision,
    interests                  double precision,
    "iVAAmount"                double precision,
    "amountPaid"               double precision,
    status                     text,
    "currentState"             text,
    "movementDate"             text,
    "paymentDate"              text,
    "paidDate"                 text,
    "deliveryDate"             text,
    "createdAt"                text,
    "updatedAt"                text
);

CREATE INDEX IF NOT EXISTS ix_propaga_sales_order
    ON mongo_bnpl.propaga_transaction ("salesOrderId");
CREATE INDEX IF NOT EXISTS ix_propaga_netsuite
    ON mongo_bnpl.propaga_transaction ("netsuiteId");

-- ─────────────────────────────────────────────────────────────────────────────
-- credit-limit-history-management-production: linea original vs vigente
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mongo_bnpl.credit_limit_history_management (
    "netsuiteId"            text,
    "customerId"            text,
    "originalCreditLimit"   double precision,
    "currentCreditLimit"    double precision,
    "creditLimitAvailable"  double precision,
    "creditLimitUpdateDate" double precision,
    "customerStatus"        text,
    "creditHistory"         text
);

CREATE INDEX IF NOT EXISTS ix_credit_limit_netsuite
    ON mongo_bnpl.credit_limit_history_management ("netsuiteId");
CREATE INDEX IF NOT EXISTS ix_credit_limit_customer
    ON mongo_bnpl.credit_limit_history_management ("customerId");

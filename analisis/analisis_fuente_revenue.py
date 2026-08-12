"""payment-report vs revenue-orders: cual es la fuente de verdad del revenue."""
import pandas as pd
from mongo_extractor import extract_aggregate

pd.set_option("display.width", 200)

CAMPOS_PAY = ["clientId", "creditId", "transactionId", "transactionPropagaId", "transactionStatus",
              "state", "totalAmount", "totalAmountToPay", "interests", "comisionPorCobrar",
              "totalAmountDefault", "movementDate", "paymentDateFromToPay", "paymentDateFromPaid"]
CAMPOS_REV = ["clientId", "creditId", "transactionId", "salesOrderId", "orderId",
              "propagaTransactionId", "fintechStatus", "state", "totalAmount", "totalAmountToPay",
              "interests", "comisionPorCobrar", "totalAmountDefault", "movementDate",
              "paymentDateFromToPay", "paymentDateFromPaid"]

proj = lambda campos: [{"$project": {**{"_id": 0}, **{c: 1 for c in campos}}}]

print("extrayendo payment-report-production...")
pay = extract_aggregate("bnpl", "payment-report-production", proj(CAMPOS_PAY))
print(f"  {len(pay):,} filas")

print("extrayendo revenue-orders-production...")
rev = extract_aggregate("bnpl", "revenue-orders-production", proj(CAMPOS_REV))
print(f"  {len(rev):,} filas")

pay.to_parquet("scratch_pay.parquet")
rev.to_parquet("scratch_rev.parquet")

print("\n" + "=" * 70)
print("1. GRANO Y DUPLICADOS")
for nombre, df in [("payment-report", pay), ("revenue-orders", rev)]:
    print(f"\n{nombre}: {len(df):,} filas")
    print(f"  transactionId distintos: {df['transactionId'].nunique():,}")
    print(f"  creditId distintos:      {df['creditId'].nunique():,}")
    print(f"  clientId distintos:      {df['clientId'].nunique():,}")
    dup = df['transactionId'].duplicated().sum()
    print(f"  filas con transactionId repetido: {dup:,}")

print("\n" + "=" * 70)
print("2. SOLAPAMIENTO por transactionId")
s_pay, s_rev = set(pay["transactionId"].dropna()), set(rev["transactionId"].dropna())
print(f"  en ambas:            {len(s_pay & s_rev):,}")
print(f"  solo payment-report: {len(s_pay - s_rev):,}")
print(f"  solo revenue-orders: {len(s_rev - s_pay):,}")

print("\n" + "=" * 70)
print("3. COINCIDENCIA DE MONTOS (transacciones en ambas)")
p1 = pay.drop_duplicates("transactionId").set_index("transactionId")
r1 = rev.drop_duplicates("transactionId").set_index("transactionId")
comun = list(s_pay & s_rev)
for col in ["totalAmount", "totalAmountToPay", "interests", "comisionPorCobrar", "totalAmountDefault"]:
    a = pd.to_numeric(p1.loc[comun, col], errors="coerce")
    b = pd.to_numeric(r1.loc[comun, col], errors="coerce")
    iguales = (a.round(2) == b.round(2)).sum()
    print(f"  {col:20s}: {iguales:>7,} / {len(comun):,} iguales ({iguales/len(comun):.1%})")

print("\n" + "=" * 70)
print("4. CALIDAD DE CAMPOS")
for nombre, df in [("payment-report", pay), ("revenue-orders", rev)]:
    print(f"\n{nombre}:")
    md = pd.to_numeric(df["movementDate"], errors="coerce")
    print(f"  movementDate == 0:              {(md == 0).sum():>7,} ({(md == 0).mean():.1%})")
    print(f"  movementDate nulo:              {md.isna().sum():>7,}")
    pdp = df["paymentDateFromPaid"].astype(str)
    print(f"  paymentDateFromPaid 'No Information': {pdp.eq('No Information').sum():>7,}")
    print(f"  paymentDateFromPaid nulo/None:  {pdp.isin(['None', 'nan']).sum():>7,}")
    ints = pd.to_numeric(df["interests"], errors="coerce")
    print(f"  interests nulo:                 {ints.isna().sum():>7,}")
    com = pd.to_numeric(df["comisionPorCobrar"], errors="coerce")
    print(f"  comisionPorCobrar nulo:         {com.isna().sum():>7,}")
    print(f"  comisionPorCobrar suma:         {com.sum():>15,.2f}")
    print(f"  interests suma:                 {ints.sum():>15,.2f}")

print("\n" + "=" * 70)
print("5. ESTADOS")
print("\npayment-report.transactionStatus:")
print(pay["transactionStatus"].value_counts(dropna=False).to_string())
print("\npayment-report.state:")
print(pay["state"].value_counts(dropna=False).to_string())
print("\nrevenue-orders.fintechStatus:")
print(rev["fintechStatus"].value_counts(dropna=False).to_string())
print("\nrevenue-orders.state:")
print(rev["state"].value_counts(dropna=False).to_string())

print("\n" + "=" * 70)
print("6. RELACION comisionPorCobrar vs interests (misma fila)")
for nombre, df in [("payment-report", pay), ("revenue-orders", rev)]:
    d = df.copy()
    d["i"] = pd.to_numeric(d["interests"], errors="coerce")
    d["c"] = pd.to_numeric(d["comisionPorCobrar"], errors="coerce")
    d = d[(d["i"] > 0) & (d["c"].notna())]
    if len(d):
        ratio = (d["c"] / d["i"])
        print(f"\n{nombre} (n={len(d):,}) ratio comision/intereses:")
        print(ratio.describe().to_string())

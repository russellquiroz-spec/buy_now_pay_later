"""Definicion exacta de intereses, IVA y comision de Rabbit."""
import numpy as np
import pandas as pd

pay = pd.read_parquet("scratch_pay.parquet")
for c in ["totalAmount", "totalAmountToPay", "interests", "comisionPorCobrar"]:
    pay[c] = pd.to_numeric(pay[c], errors="coerce")

print("=== Hipotesis A: comisionPorCobrar == interests * 1.16 (interes + IVA) ===")
d = pay[pay["interests"] > 0].copy()
d["esperado"] = (d["interests"] * 1.16).round(2)
ok = (d["comisionPorCobrar"].round(2) == d["esperado"]).sum()
print(f"  {ok:,} / {len(d):,} ({ok/len(d):.1%})")

print("\n=== Hipotesis B: totalAmountToPay - totalAmount == comisionPorCobrar ===")
d["spread"] = (d["totalAmountToPay"] - d["totalAmount"]).round(2)
ok = (d["spread"] == d["comisionPorCobrar"].round(2)).sum()
print(f"  {ok:,} / {len(d):,} ({ok/len(d):.1%})")

print("\n=== Hipotesis C: totalAmountToPay - totalAmount == interests (sin IVA) ===")
ok = (d["spread"] == d["interests"].round(2)).sum()
print(f"  {ok:,} / {len(d):,} ({ok/len(d):.1%})")

print("\n=== Las dos definiciones de revenue del notebook, sobre lo COBRADO ===")
paid = pay[pay["transactionStatus"] == "paid"].copy()
v_celda70 = (paid["interests"] * 0.142).sum()
v_celda82 = ((paid["totalAmountToPay"] - paid["totalAmount"]) * 0.142).sum()
print(f"  filas 'paid': {len(paid):,}")
print(f"  interes cobrado sin IVA (sum interests):        ${paid['interests'].sum():>15,.2f}")
print(f"  interes cobrado con IVA (sum comisionPorCobrar):${paid['comisionPorCobrar'].sum():>15,.2f}")
print(f"  celda 70  interests * 0.142:                    ${v_celda70:>15,.2f}")
print(f"  celda 82  (toPay - total) * 0.142:              ${v_celda82:>15,.2f}")
print(f"  diferencia entre ambas:                         ${v_celda82 - v_celda70:>15,.2f}  ({(v_celda82/v_celda70 - 1):.1%})")
print(f"  celda 70  commission = totalAmount * 0.04:      ${(paid['totalAmount'] * 0.04).sum():>15,.2f}")

print("\n=== Revenue historico por año (base: payment-report, transactionStatus='paid') ===")
paid["fecha"] = pd.to_datetime(pd.to_numeric(paid["movementDate"], errors="coerce"), unit="ms")
paid["anio"] = paid["fecha"].dt.year
g = paid.groupby("anio").agg(
    transacciones=("transactionId", "count"),
    monto_financiado=("totalAmount", "sum"),
    interes_sin_iva=("interests", "sum"),
    rabbit_14_2=("interests", lambda s: (s * 0.142).sum()),
)
print(g.to_string(float_format=lambda x: f"{x:,.0f}"))

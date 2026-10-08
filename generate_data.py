"""Generate a synthetic monthly brand/SKU P&L dataset for an FMCG manufacturer.

All figures are randomly generated. No real company data is included.
Usage: python generate_data.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

RNG = np.random.default_rng(20)
OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)

BRANDS = {
    "Brand A - Cheese": 0.42, "Brand B - Yoghurt": 0.38, "Brand C - Ice Cream": 0.35,
    "Brand D - Bakery": 0.30, "Brand E - Butter": 0.40, "Brand F - Cream": 0.36,
    "Brand G - Deli Meats": 0.33, "Brand H - Sauces": 0.45, "Brand I - Juice": 0.28,
    "Brand J - Snacks": 0.31,
}
CHANNELS = ["Modern Trade", "Wholesale", "HoReCa", "E-commerce"]
MONTHS = pd.period_range("2024-01", "2025-12", freq="M")

rows = []
for brand, base_margin in BRANDS.items():
    n_skus = RNG.integers(4, 9)
    for s in range(1, n_skus + 1):
        sku = f"{brand.split(' - ')[0].replace('Brand ', '')}-{s:02d}"
        price = RNG.uniform(150, 1200)  # KES per unit
        base_vol = RNG.uniform(800, 9000)
        # Some SKUs are structurally inefficient: heavy trade spend, weak volume response
        inefficient = RNG.random() < 0.3
        for ch in CHANNELS:
            ch_share = {"Modern Trade": .45, "Wholesale": .35, "HoReCa": .12, "E-commerce": .08}[ch]
            for i, m in enumerate(MONTHS):
                season = 1 + 0.12 * np.sin(2 * np.pi * (m.month - 3) / 12)
                trend = 1 + 0.01 * i
                units = max(0, RNG.normal(base_vol * ch_share * season * trend, base_vol * ch_share * .1))
                gross = units * price
                discount_rate = RNG.uniform(.08, .16) if inefficient else RNG.uniform(.02, .08)
                net = gross * (1 - discount_rate)
                cogs = net * (1 - base_margin) * RNG.uniform(.97, 1.05)
                logistics = units * RNG.uniform(6, 14) * (1.4 if ch == "HoReCa" else 1)
                marketing = net * (RNG.uniform(.06, .12) if inefficient else RNG.uniform(.02, .05))
                merch = net * RNG.uniform(.01, .025)
                rows.append(dict(month=str(m), brand=brand, sku=sku, channel=ch,
                                 units=round(units), gross_sales=round(gross, 2),
                                 trade_discounts=round(gross - net, 2), net_sales=round(net, 2),
                                 cogs=round(cogs, 2), logistics=round(logistics, 2),
                                 marketing=round(marketing, 2), merchandising=round(merch, 2)))

df = pd.DataFrame(rows)
df.to_csv(OUT / "pnl_monthly.csv", index=False)
print(f"Wrote {len(df):,} rows, {df.sku.nunique()} SKUs -> data/pnl_monthly.csv")

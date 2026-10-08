"""Brand/SKU P&L analysis, cost-lever simulation and target cascade.

Steps
1. Build a contribution-margin P&L by brand, SKU and channel.
2. Score every SKU-channel on cost efficiency (spend per KES of contribution).
3. Simulate a cost programme: trim discounts and marketing on the least
   efficient tail, apply an elasticity-based volume penalty, measure the
   impact on total spend and contribution.
4. Cascade next-year revenue and expense targets from brand -> SKU -> channel.

Usage: python pnl_optimisation.py   (run generate_data.py first)
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).parent
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)

SPEND_COLS = ["trade_discounts", "logistics", "marketing", "merchandising"]
CUT = {"trade_discounts": 0.35, "marketing": 0.40}   # cut applied to inefficient tail
VOLUME_ELASTICITY = 0.25                              # % volume lost per % net-price-support cut
GROWTH_TARGET = 0.08                                  # next-year net sales growth


def load() -> pd.DataFrame:
    df = pd.read_csv(ROOT / "data" / "pnl_monthly.csv")
    df["gross_margin"] = df.net_sales - df.cogs
    df["contribution"] = df.gross_margin - df.logistics - df.marketing - df.merchandising
    return df


def pnl(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    cols = ["gross_sales", "net_sales", "cogs", "gross_margin", "contribution"] + SPEND_COLS
    t = df.groupby(by)[cols].sum()
    t["gm_pct"] = t.gross_margin / t.net_sales
    t["cm_pct"] = t.contribution / t.net_sales
    t["spend"] = t[SPEND_COLS].sum(axis=1)
    return t


def efficiency(df: pd.DataFrame) -> pd.DataFrame:
    t = pnl(df[df.month >= "2025-01"], ["brand", "sku", "channel"])
    t["spend_per_contribution"] = t.spend / t.contribution.clip(lower=1)
    # Inefficient tail = top quartile by spend per unit of contribution
    t["inefficient"] = t.spend_per_contribution >= t.spend_per_contribution.quantile(0.75)
    return t


def simulate(df: pd.DataFrame, eff: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    base = df[df.month >= "2025-01"].copy()
    base["units"] = base["units"].astype(float)
    flags = eff["inefficient"].reset_index()
    sim = base.merge(flags, on=["brand", "sku", "channel"])
    m = sim.inefficient
    support_before = sim.loc[m, "trade_discounts"] + sim.loc[m, "marketing"]
    for col, cut in CUT.items():
        sim.loc[m, col] *= 1 - cut
    support_after = sim.loc[m, "trade_discounts"] + sim.loc[m, "marketing"]
    support_cut_pct = 1 - support_after / support_before
    vol_factor = 1 - VOLUME_ELASTICITY * support_cut_pct * (support_before / sim.loc[m, "gross_sales"]) * 4
    for col in ["units", "gross_sales", "cogs", "logistics", "merchandising"]:
        sim.loc[m, col] *= vol_factor
    sim["net_sales"] = sim.gross_sales - sim.trade_discounts
    sim["gross_margin"] = sim.net_sales - sim.cogs
    sim["contribution"] = sim.gross_margin - sim.logistics - sim.marketing - sim.merchandising

    b, s = pnl(base, ["channel"]).sum(), pnl(sim, ["channel"]).sum()
    summary = {
        "spend_change_pct": (s.spend / b.spend - 1) * 100,
        "net_sales_change_pct": (s.net_sales / b.net_sales - 1) * 100,
        "contribution_change_pct": (s.contribution / b.contribution - 1) * 100,
        "sku_channels_flagged": int(eff.inefficient.sum()),
    }
    return sim, summary


def cascade_targets(sim: pd.DataFrame) -> pd.DataFrame:
    t = pnl(sim, ["brand", "sku", "channel"])[["net_sales", "spend", "contribution"]]
    t["net_sales_target"] = t.net_sales * (1 + GROWTH_TARGET)
    t["spend_budget"] = t.spend * (1 + GROWTH_TARGET * 0.5)  # spend grows at half the sales rate
    t["contribution_target"] = t.contribution + (t.net_sales_target - t.net_sales) * (t.contribution / t.net_sales).clip(lower=0)
    return t.round(0)


def charts(df: pd.DataFrame, eff: pd.DataFrame, summary: dict) -> None:
    brand = pnl(df[df.month >= "2025-01"], ["brand"]).sort_values("cm_pct")
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(brand.index, brand.cm_pct * 100, color="#0f766e")
    ax.set_xlabel("Contribution margin, % of net sales (2025)")
    ax.set_title("Contribution margin by brand")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(OUT / "contribution_by_brand.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    colors = eff.inefficient.map({True: "#b45309", False: "#94a3b8"})
    ax.scatter(eff.net_sales / 1e6, eff.cm_pct * 100, c=colors, s=18, alpha=.8)
    ax.set_xlabel("Net sales 2025 (KES m)"); ax.set_ylabel("Contribution margin %")
    ax.set_title("SKU-channel efficiency (orange = flagged for cost action)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(OUT / "sku_efficiency.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4))
    keys = ["spend_change_pct", "net_sales_change_pct", "contribution_change_pct"]
    vals = [summary[k] for k in keys]
    ax.bar(["Spend", "Net sales", "Contribution"], vals,
           color=["#0f766e" if v < 0 else "#b45309" for v in vals[:1]] + ["#94a3b8", "#0f766e"])
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:+.1f}%", ha="center", va="bottom" if v >= 0 else "top")
    ax.axhline(0, color="black", lw=.8); ax.set_title("Simulated programme impact vs 2025 baseline")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(OUT / "programme_impact.png", dpi=150); plt.close(fig)


def main() -> None:
    df = load()
    pnl(df, ["brand"]).round(0).to_csv(OUT / "pnl_by_brand.csv")
    eff = efficiency(df)
    sim, summary = simulate(df, eff)
    cascade_targets(sim).to_csv(OUT / "targets_2026.csv")
    charts(df, eff, summary)
    print("Programme simulation (2025 baseline):")
    for k, v in summary.items():
        print(f"  {k:28s} {v:+.1f}" if isinstance(v, float) else f"  {k:28s} {v}")


if __name__ == "__main__":
    main()

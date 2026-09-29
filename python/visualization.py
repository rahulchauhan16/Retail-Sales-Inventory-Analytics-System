"""Portfolio charts (matplotlib + seaborn). Run from the project root:

    python python/visualization.py                 # writes 8 PNGs to docs/images/
    python python/visualization.py --out some/dir

Design rules followed (see the dataviz method):
  * one hue for one measure (blue); a second series takes the next categorical colour; never a rainbow
  * inventory health uses the reserved status colours, and every bar is also labelled, so colour is never the only cue
  * text uses ink colours (never the series colour); recessive grid; direct value labels instead of a number on every point
  * a legend appears whenever two or more series share a plot
  * amounts are shown in INR lakh (L) or crore (Cr)
"""
import argparse
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.ticker import FuncFormatter

# ---- palette (validated reference palette, light surface) -----------------------------------------------
SURFACE, GRID, BASELINE = "#fcfcfb", "#e1e0d9", "#c3c2b7"
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
BLUE, ORANGE = "#2a78d6", "#eb6834"                      # categorical slots 1 and 2
BLUE_LIGHT = "#9ec5f4"                                   # sequential blue, step 200 (secondary emphasis)
STATUS = {"OUT_OF_STOCK": "#d03b3b", "LOW_STOCK": "#ec835a", "HEALTHY": "#0ca30c", "OVERSTOCKED": "#fab219", "DEAD_STOCK": "#898781"}
STATUS_LABEL = {"OUT_OF_STOCK": "Out of stock", "LOW_STOCK": "Low stock", "HEALTHY": "Healthy", "OVERSTOCKED": "Overstocked",
                "DEAD_STOCK": "Dead stock"}
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "docs" / "images"


def inr(x: float, pos=None) -> str:
    """Compact rupee label: 12,345 / 4.2 L / 1.5 Cr."""
    a = abs(x)
    if a >= 1e7:
        return f"₹{x / 1e7:.1f} Cr"
    if a >= 1e5:
        return f"₹{x / 1e5:.1f} L"
    return f"₹{x:,.0f}"


def _style(ax, grid_axis="y"):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(BASELINE)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _figure(title: str, subtitle: str, size=(9, 5.2)):
    fig, ax = plt.subplots(figsize=size, facecolor=SURFACE)
    fig.suptitle(title, x=0.01, y=0.985, ha="left", fontsize=14, fontweight="bold", color=INK)
    fig.text(0.01, 0.905, subtitle, ha="left", fontsize=9.5, color=INK_2)
    fig.subplots_adjust(top=0.82, left=0.08, right=0.97, bottom=0.11)
    return fig, ax


def _fit_left(fig, ax, pad: float = 0.02):
    """Give the plot exactly the left margin its y-axis labels need (long category names are otherwise clipped)."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    widest = max(t.get_window_extent(renderer).width for t in ax.get_yticklabels())
    fig.subplots_adjust(left=min(widest / fig.bbox.width + pad + 0.01, 0.6))


def _barh(ax, labels, values, color, fmt, highlight=None, base_color=None):
    y = np.arange(len(labels))[::-1]
    colors = [color if highlight is None or i in highlight else (base_color or BLUE_LIGHT) for i in range(len(labels))]
    ax.barh(y, values, color=colors, height=0.62)
    ax.set_yticks(y, labels, fontsize=9.5, color=INK_2)
    for yi, v in zip(y, values):
        ax.text(v, yi, "  " + fmt(v), va="center", ha="left", fontsize=9, color=INK_2)
    ax.set_xlim(0, max(values) * 1.18)
    ax.xaxis.set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.grid(False)


# ---- 1. monthly revenue trend ------------------------------------------------------------------------------
def monthly_revenue_trend(monthly: pd.DataFrame):
    m = monthly.sort_values("month").copy()
    m["month"] = pd.to_datetime(m["month"])
    m["ma3"] = m["net_revenue"].rolling(3).mean()
    fig, ax = _figure("Monthly net revenue", "Net of GST, completed orders. Revenue peaks every October-November and grows year on year.")
    _style(ax)
    ax.plot(m["month"], m["net_revenue"], color=BLUE, linewidth=2, label="Monthly net revenue")
    ax.plot(m["month"], m["ma3"], color=ORANGE, linewidth=2, label="3-month moving average")
    peak = m.loc[m["net_revenue"].idxmax()]
    ax.annotate(f"Peak {peak['month']:%b %Y}\n{inr(peak['net_revenue'])}", (peak["month"], peak["net_revenue"]), xytext=(-70, -6),
                textcoords="offset points", fontsize=9, color=INK_2, ha="right", arrowprops=dict(arrowstyle="-", color=MUTED))
    ax.yaxis.set_major_formatter(FuncFormatter(inr))
    ax.set_ylim(0, m["net_revenue"].max() * 1.12)
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK_2)
    return fig


# ---- 2. top products ------------------------------------------------------------------------------------------
def top_products(products: pd.DataFrame, n: int = 10):
    t = products.sort_values("net_revenue", ascending=False).head(n)
    share = 100 * t["net_revenue"].sum() / products["net_revenue"].sum()
    fig, ax = _figure(f"Top {n} products by net revenue", f"These {n} products bring in {share:.0f} % of all net revenue.")
    _barh(ax, t["product_name"].str.slice(0, 34), t["net_revenue"], BLUE, inr)
    _fit_left(fig, ax)
    return fig


# ---- 3. category revenue ---------------------------------------------------------------------------------------
def category_revenue(category_perf: pd.DataFrame):
    latest = int(category_perf["year"].max())
    t = category_perf[category_perf["year"] == latest].sort_values("net_revenue", ascending=False)
    fig, ax = _figure(f"Net revenue by category, {latest}", "Bars are net revenue; the label adds year-on-year change.", size=(9, 6.2))
    y = np.arange(len(t))[::-1]
    ax.barh(y, t["net_revenue"], color=BLUE, height=0.62)
    ax.set_yticks(y, t["category_name"], fontsize=9.5, color=INK_2)
    for yi, rev, g in zip(y, t["net_revenue"], t["yoy_growth_pct"]):
        change = "" if pd.isna(g) else f"   {g:+.0f} % vs {latest - 1}"
        ax.text(rev, yi, f"  {inr(rev)}{change}", va="center", fontsize=9, color=INK_2)
    ax.set_xlim(0, t["net_revenue"].max() * 1.45)
    ax.xaxis.set_visible(False)
    _clean_bars(ax)
    _fit_left(fig, ax)
    return fig


def _clean_bars(ax):
    ax.grid(False)
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.set_facecolor(SURFACE)
    ax.tick_params(length=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


# ---- 4. store revenue ---------------------------------------------------------------------------------------------
def store_revenue(stores: pd.DataFrame):
    t = stores.sort_values("net_revenue", ascending=False)
    fig, ax = _figure("Net revenue by store", "The online fulfilment hub serves all online orders.", size=(9, 5.6))
    _barh(ax, t["store_name"], t["net_revenue"], BLUE, inr)
    _fit_left(fig, ax)
    return fig


# ---- 5. inventory health ------------------------------------------------------------------------------------------
def inventory_health(inv: pd.DataFrame):
    t = inv.groupby("health_status").agg(positions=("inventory_id", "count"), value=("inventory_value", "sum")).reindex(list(STATUS))
    fig, ax = _figure("Inventory health", "Store-product positions by status. Labels show the count and the share of stock value at cost.")
    y = np.arange(len(t))[::-1]
    ax.barh(y, t["positions"], color=[STATUS[s] for s in t.index], height=0.62)
    ax.set_yticks(y, [STATUS_LABEL[s] for s in t.index], fontsize=10, color=INK_2)
    for yi, (s, row) in zip(y, t.iterrows()):
        ax.text(row["positions"], yi, f"  {int(row['positions']):,} positions  |  {100 * row['value'] / t['value'].sum():.0f} % of value",
                va="center", fontsize=9, color=INK_2)
    ax.set_xlim(0, t["positions"].max() * 1.5)
    ax.xaxis.set_visible(False)
    _clean_bars(ax)
    _fit_left(fig, ax)
    return fig


# ---- 6. customer segments (RFM) -------------------------------------------------------------------------------------
def customer_segments(customers: pd.DataFrame):
    from customer_analysis import RFM_ORDER, rfm_summary
    t = rfm_summary(customers).set_index("rfm_segment").reindex(RFM_ORDER)
    fig, ax = _figure("Customer segments (RFM)", "Share of buying customers versus share of net revenue. Labels are analytical groupings.")
    _style(ax)
    x = np.arange(len(t))
    w = 0.36
    ax.bar(x - w / 2 - 0.01, t["customer_share_pct"], w, color=BLUE, label="Share of customers")
    ax.bar(x + w / 2 + 0.01, t["revenue_share_pct"], w, color=ORANGE, label="Share of net revenue")
    for xi, a, b in zip(x, t["customer_share_pct"], t["revenue_share_pct"]):
        ax.text(xi - w / 2 - 0.01, a + 0.8, f"{a:.0f} %", ha="center", fontsize=9, color=INK_2)
        ax.text(xi + w / 2 + 0.01, b + 0.8, f"{b:.0f} %", ha="center", fontsize=9, color=INK_2)
    ax.set_xticks(x, t.index, fontsize=9.5, color=INK_2)
    ax.set_ylim(0, max(t["customer_share_pct"].max(), t["revenue_share_pct"].max()) * 1.2)
    ax.yaxis.set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.legend(loc="upper right", frameon=False, fontsize=9, labelcolor=INK_2)
    return fig


# ---- 7. return rate ---------------------------------------------------------------------------------------------------
def return_rate_by_category(category_perf: pd.DataFrame):
    latest = category_perf.groupby("category_name").agg(sold=("units_sold", "sum"), returned=("units_returned", "sum"))
    latest["rate"] = 100 * latest["returned"] / latest["sold"]
    latest = latest.sort_values("rate", ascending=False)
    overall = 100 * latest["returned"].sum() / latest["sold"].sum()
    fig, ax = _figure("Unit return rate by category", f"Returned units as a share of units sold, 2023-2025. Overall: {overall:.1f} %.", size=(9, 6.2))
    y = np.arange(len(latest))[::-1]
    ax.barh(y, latest["rate"], color=BLUE, height=0.62)
    ax.axvline(overall, color=INK_2, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(overall, len(latest) - 0.35, f" overall {overall:.1f} %", fontsize=9, color=INK_2, va="bottom")
    ax.set_yticks(y, latest.index, fontsize=9.5, color=INK_2)
    for yi, v in zip(y, latest["rate"]):
        ax.text(v, yi, f"  {v:.1f} %", va="center", fontsize=9, color=INK_2)
    ax.set_xlim(0, latest["rate"].max() * 1.18)
    ax.xaxis.set_visible(False)
    _clean_bars(ax)
    _fit_left(fig, ax)
    return fig


# ---- 8. sales distribution ---------------------------------------------------------------------------------------------
def order_value_distribution(orders: pd.DataFrame):
    v = orders.loc[orders["order_status"] == "COMPLETED", "total_amount"].astype(float)
    median, mean = v.median(), v.mean()
    fig, ax = _figure("Distribution of order values", "Log scale. A few very large orders pull the mean well above the typical (median) order.")
    _style(ax)
    sns.histplot(v, bins=60, log_scale=True, color=BLUE, edgecolor=SURFACE, linewidth=0.5, ax=ax)
    ax.axvline(median, color=INK_2, linewidth=1.2)
    ax.axvline(mean, color=ORANGE, linewidth=1.6)
    top = ax.get_ylim()[1]
    ax.text(median / 1.06, top * 0.95, f"median {inr(median)}", ha="right", fontsize=9, color=INK_2)
    ax.text(mean * 1.06, top * 0.95, f"mean {inr(mean)}", ha="left", fontsize=9, color=INK_2)
    ax.xaxis.set_major_formatter(FuncFormatter(inr))
    ax.set_xlabel("Order value (GST-inclusive, log scale)", color=MUTED, fontsize=9)
    ax.set_ylabel("Orders", color=MUTED, fontsize=9)
    return fig


CHARTS = {
    "01_monthly_revenue_trend": ("vw_monthly_sales", monthly_revenue_trend),
    "02_top_products": ("vw_product_performance", top_products),
    "03_category_revenue": ("vw_category_performance", category_revenue),
    "04_store_revenue": ("vw_store_performance", store_revenue),
    "05_inventory_health": ("vw_inventory_health", inventory_health),
    "06_customer_segments": ("vw_customer_summary", customer_segments),
    "07_return_rate_by_category": ("vw_category_performance", return_rate_by_category),
    "08_order_value_distribution": ("vw_orders", order_value_distribution),
}


def save(fig, name: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.png"
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return path


def make_all(out_dir: Path = DEFAULT_OUT, data: dict | None = None) -> list[Path]:
    """Build every chart; `data` maps view name -> DataFrame (loaded from the database when omitted)."""
    from data_extraction import get_view
    data = dict(data or {})
    paths = []
    for name, (view, func) in CHARTS.items():
        if view not in data:
            data[view] = get_view(view)
        paths.append(save(func(data[view]), name, out_dir))
    return paths


if __name__ == "__main__":
    matplotlib.use("Agg")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    for p in make_all(Path(ap.parse_args().out)):
        print("saved", p)

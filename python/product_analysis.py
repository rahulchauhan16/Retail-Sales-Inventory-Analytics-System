"""Product and returns analysis in pandas: top products, Pareto, margin, declining categories, high-return products.

Run from the project root:   python python/product_analysis.py
"""
import pandas as pd

from data_extraction import get_view
from kpis import pareto


def top_products(products: pd.DataFrame, n: int = 10, by: str = "net_revenue") -> pd.DataFrame:
    cols = ["product_name", "category", "units_sold", "net_revenue", "gross_profit", "margin_pct", "return_rate_pct", "abc_class"]
    return products.sort_values(by, ascending=False).head(n)[cols].reset_index(drop=True)


def abc_summary(products: pd.DataFrame) -> pd.DataFrame:
    sold = products[products["units_sold"] > 0]
    t = sold.groupby("abc_class").agg(products=("product_id", "count"), net_revenue=("net_revenue", "sum")).reindex(["A", "B", "C"])
    t["product_share_pct"] = 100 * t["products"] / t["products"].sum()
    t["revenue_share_pct"] = 100 * t["net_revenue"] / t["net_revenue"].sum()
    return t.reset_index()


def concentration(products: pd.DataFrame) -> dict:
    """Share of revenue from the top 10 / top 50 / top 20 % of products, and the Herfindahl index (0 = spread out, 1 = one product)."""
    rev = products.loc[products["net_revenue"] > 0, "net_revenue"].sort_values(ascending=False).reset_index(drop=True)
    share = rev / rev.sum()
    return {"products_sold": len(rev), "top_10_pct_of_revenue": round(100 * float(share.head(10).sum()), 1),
            "top_50_pct_of_revenue": round(100 * float(share.head(50).sum()), 1),
            "top_20pct_products_pct_of_revenue": round(100 * float(share.head(int(len(rev) * 0.2)).sum()), 1),
            "herfindahl_index": round(float((share ** 2).sum()), 4)}


def category_trends(category_perf: pd.DataFrame) -> pd.DataFrame:
    """Revenue by category and year side by side, with a flag for categories that fell in both 2024 and 2025."""
    p = category_perf.pivot_table(index="category_name", columns="year", values="net_revenue", aggfunc="sum")
    p["growth_2024_pct"] = 100 * (p[2024] / p[2023] - 1)
    p["growth_2025_pct"] = 100 * (p[2025] / p[2024] - 1)
    p["trend"] = "Growing / stable"
    p.loc[p[2025] < p[2024], "trend"] = "Declined in 2025"
    p.loc[(p[2025] < p[2024]) & (p[2024] < p[2023]), "trend"] = "Declining two years in a row"
    return p.sort_values("growth_2025_pct").reset_index()


def high_return_products(products: pd.DataFrame, min_units: int = 40, min_returned: int = 8, times_category: float = 2.5) -> pd.DataFrame:
    """Products returned at >= times_category x their category's rate (needs a minimum volume to avoid small-sample noise)."""
    g = products[products["units_sold"] > 0].copy()
    cat = g.groupby("category").agg(cat_sold=("units_sold", "sum"), cat_returned=("units_returned", "sum"))
    cat["category_rate_pct"] = 100 * cat["cat_returned"] / cat["cat_sold"]
    g = g.join(cat["category_rate_pct"], on="category")
    g["times_category_rate"] = g["return_rate_pct"] / g["category_rate_pct"].where(g["category_rate_pct"] > 0)
    flag = (g["units_sold"] >= min_units) & (g["units_returned"] >= min_returned) & (g["times_category_rate"] >= times_category)
    return g[flag].sort_values("times_category_rate", ascending=False)[
        ["product_name", "category", "units_sold", "units_returned", "return_rate_pct", "category_rate_pct", "times_category_rate"]].reset_index(drop=True)


def return_reasons(returns: pd.DataFrame) -> pd.DataFrame:
    """Recorded reasons only: the data shows what staff recorded, not the root cause."""
    t = returns.groupby("return_reason").agg(return_lines=("return_item_id", "count"), units=("units_returned", "sum"),
                                              refund_net=("refund_net_of_gst", "sum"))
    t["share_pct"] = 100 * t["return_lines"] / t["return_lines"].sum()
    return t.sort_values("return_lines", ascending=False).reset_index()


def main() -> None:
    pd.set_option("display.width", 200, "display.max_columns", 20, "display.float_format", "{:,.1f}".format)
    products, cats, returns = get_view("vw_product_performance"), get_view("vw_category_performance"), get_view("vw_return_analysis")
    print("== Top 10 products by revenue ==");   print(top_products(products).to_string(index=False))
    print("\n== ABC summary ==");                 print(abc_summary(products).to_string(index=False))
    print("\n== Concentration ==");               print(concentration(products))
    print("\n== Category trends ==");             print(category_trends(cats).to_string(index=False))
    print("\n== High-return products ==");        print(high_return_products(products).to_string(index=False))
    print("\n== Return reasons ==");              print(return_reasons(returns).to_string(index=False))


if __name__ == "__main__":
    main()

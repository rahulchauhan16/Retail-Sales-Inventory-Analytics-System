"""Inventory analysis in pandas: stock health, value at risk, replenishment, aging, turnover, coverage.

Run from the project root:   python python/inventory_analysis.py
Health classes come from vw_inventory_health. The rules are project assumptions (docs/06_inventory_metrics.md):
OUT_OF_STOCK, DEAD_STOCK (no sale at the store in 365 days), LOW_STOCK (<= reorder level),
OVERSTOCKED (> max level or > 180 days cover), HEALTHY.
"""
import pandas as pd

from data_extraction import get_view

STATUS_ORDER = ["OUT_OF_STOCK", "LOW_STOCK", "HEALTHY", "OVERSTOCKED", "DEAD_STOCK"]


def health_summary(inv: pd.DataFrame) -> pd.DataFrame:
    t = inv.groupby("health_status").agg(positions=("inventory_id", "count"), units=("quantity_on_hand", "sum"),
                                         value_at_cost=("inventory_value", "sum")).reindex(STATUS_ORDER)
    t["position_share_pct"] = 100 * t["positions"] / t["positions"].sum()
    t["value_share_pct"] = 100 * t["value_at_cost"] / t["value_at_cost"].sum()
    return t.reset_index()


def store_risk(inv: pd.DataFrame) -> pd.DataFrame:
    """Per store: stock-out risk (out + low positions) and surplus (overstocked + dead value)."""
    g = inv.assign(at_risk=inv["health_status"].isin(["OUT_OF_STOCK", "LOW_STOCK"]),
                   surplus_value=inv["inventory_value"].where(inv["health_status"].isin(["OVERSTOCKED", "DEAD_STOCK"]), 0))
    t = g.groupby("store_name").agg(positions=("inventory_id", "count"), at_risk_positions=("at_risk", "sum"),
                                    inventory_value=("inventory_value", "sum"), surplus_value=("surplus_value", "sum"))
    t["stock_out_risk_pct"] = 100 * t["at_risk_positions"] / t["positions"]
    t["surplus_share_pct"] = 100 * t["surplus_value"] / t["inventory_value"]
    return t.sort_values("surplus_value", ascending=False).reset_index()


def replenishment_list(inv: pd.DataFrame, n: int = 25) -> pd.DataFrame:
    """Positions that sold in the last 90 days and are at/below reorder level, fastest sellers first."""
    need = inv[(inv["quantity_on_hand"] <= inv["reorder_level"]) & (inv["units_sold_90d"] > 0)]
    cols = ["store_name", "product_name", "quantity_on_hand", "reorder_level", "avg_daily_demand", "inbound_quantity", "suggested_order_qty"]
    return need.sort_values("avg_daily_demand", ascending=False).head(n)[cols].reset_index(drop=True)


def aging(inv: pd.DataFrame) -> pd.DataFrame:
    stocked = inv[inv["quantity_on_hand"] > 0].copy()
    stocked["stock_age"] = pd.cut(stocked["days_since_restock"], bins=[-1, 30, 90, 180, 365, 100_000],
                                  labels=["0-30 days", "31-90 days", "91-180 days", "181-365 days", "over 365 days"])
    t = stocked.groupby("stock_age", observed=True).agg(positions=("inventory_id", "count"), value_at_cost=("inventory_value", "sum"))
    t["value_share_pct"] = 100 * t["value_at_cost"] / t["value_at_cost"].sum()
    return t.reset_index()


def coverage_bands(inv: pd.DataFrame) -> pd.DataFrame:
    """Days of cover for positions that had sales in the last 90 days."""
    sel = inv[inv["days_of_cover"].notna()].copy()
    sel["cover"] = pd.cut(sel["days_of_cover"], bins=[-0.01, 7, 30, 90, 180, 1e9],
                          labels=["under 7 days", "7-29 days", "30-89 days", "90-179 days", "180+ days"])
    t = sel.groupby("cover", observed=True).agg(positions=("inventory_id", "count"), value_at_cost=("inventory_value", "sum"))
    t["position_share_pct"] = 100 * t["positions"] / t["positions"].sum()
    return t.reset_index()


def turnover_by_category(products: pd.DataFrame) -> pd.DataFrame:
    """12-month cost of goods sold divided by current inventory value, per category (ending-inventory approximation)."""
    g = products.copy()
    g["cogs_12m_est"] = g["inventory_turnover_12m"].fillna(0) * g["inventory_value"]      # turnover * value = COGS of the last 12 months
    t = g.groupby("category").agg(cogs_12m=("cogs_12m_est", "sum"), inventory_value=("inventory_value", "sum"))
    t["inventory_turnover"] = t["cogs_12m"] / t["inventory_value"].where(t["inventory_value"] > 0)
    t["days_of_inventory"] = 365 / t["inventory_turnover"]
    return t.sort_values("inventory_turnover", ascending=False).reset_index()


def product_classes(products: pd.DataFrame) -> pd.DataFrame:
    t = products.dropna(subset=["product_class"]).groupby("product_class").agg(
        products=("product_id", "count"), inventory_value=("inventory_value", "sum"))
    return t.reset_index()


def main() -> None:
    pd.set_option("display.width", 200, "display.max_columns", 20, "display.float_format", "{:,.1f}".format)
    inv, products = get_view("vw_inventory_health"), get_view("vw_product_performance")
    print("== Stock health ==");            print(health_summary(inv).to_string(index=False))
    print("\n== Store risk ==");            print(store_risk(inv).to_string(index=False))
    print("\n== Stock aging ==");           print(aging(inv).to_string(index=False))
    print("\n== Days of cover ==");         print(coverage_bands(inv).to_string(index=False))
    print("\n== Turnover by category ==");  print(turnover_by_category(products).to_string(index=False))
    print("\n== Product classes ==");       print(product_classes(products).to_string(index=False))
    print("\n== Replenishment (top 10) =="); print(replenishment_list(inv, 10).to_string(index=False))


if __name__ == "__main__":
    main()

"""Validate the data before analysing it: view shapes, null rates, value ranges and cross-view reconciliation.

Run from the project root:   python python/data_validation.py
Exit code 0 = all checks passed, 1 = at least one failed (so it can gate a pipeline).

These are checks on the ANALYTICAL layer (the views). Source-data problems (duplicates, bad e-mails ...) are
reported by queries/10_data_quality_checks.sql and documented in docs/09_data_quality.md.
"""
import sys
from dataclasses import dataclass

import pandas as pd

from data_extraction import extract_core, get_query


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


EXPECTED_COLUMNS = {
    "vw_monthly_sales": ["month", "orders", "net_revenue", "gross_profit", "gross_sales_incl_gst", "cogs", "refunded_net"],
    "vw_product_performance": ["product_id", "category", "units_sold", "net_revenue", "margin_pct", "abc_class", "inventory_value"],
    "vw_customer_summary": ["customer_id", "segment", "orders", "net_revenue", "rfm_segment", "activity_status"],
    "vw_inventory_health": ["store_id", "product_id", "quantity_on_hand", "inventory_value", "health_status"],
    "vw_store_performance": ["store_name", "orders", "net_revenue", "avg_order_value", "return_rate_pct"],
    "vw_category_performance": ["category_name", "year", "net_revenue", "margin_pct", "yoy_growth_pct"],
    "vw_supplier_performance": ["supplier_name", "on_time_pct", "fill_rate_pct", "purchase_spend"],
    "vw_return_analysis": ["return_reason", "category", "units_returned", "refund_net_of_gst"],
}


def run_checks(data: dict[str, pd.DataFrame] | None = None) -> list[Check]:
    data = data or extract_core()
    checks: list[Check] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append(Check(name, bool(ok), detail))

    # 1. shape: every view loaded, is non-empty and has the columns downstream code relies on
    for view, columns in EXPECTED_COLUMNS.items():
        df = data[view]
        missing = [c for c in columns if c not in df.columns]
        add(f"{view}: non-empty with expected columns", len(df) > 0 and not missing, f"{len(df):,} rows; missing={missing}")

    monthly, products, customers = data["vw_monthly_sales"], data["vw_product_performance"], data["vw_customer_summary"]
    inventory, stores, returns = data["vw_inventory_health"], data["vw_store_performance"], data["vw_return_analysis"]
    categories = data["vw_category_performance"]

    # 2. uniqueness of keys
    add("customer_id is unique in vw_customer_summary", customers["customer_id"].is_unique)
    add("product_id is unique in vw_product_performance", products["product_id"].is_unique)
    add("(store_id, product_id) is unique in vw_inventory_health", not inventory.duplicated(["store_id", "product_id"]).any())
    add("36 distinct months in vw_monthly_sales", monthly["month"].nunique() == 36, f"{monthly['month'].nunique()} months")

    # 3. value ranges
    add("no negative revenue, units or stock", (monthly["net_revenue"] >= 0).all() and (products["units_sold"] >= 0).all()
        and (inventory["quantity_on_hand"] >= 0).all())
    add("percentages are within 0-100 where they must be",
        products["return_rate_pct"].dropna().between(0, 100).all() and stores["return_rate_pct"].between(0, 100).all()
        and stores["repeat_customer_rate_pct"].between(0, 100).all())
    add("gross margin is below 100 % everywhere", (products["margin_pct"].dropna() < 100).all())
    add("reserved stock never exceeds stock on hand", (inventory["reserved_quantity"] <= inventory["quantity_on_hand"]).all())

    # 4. categorical domains
    add("inventory health statuses are the five defined classes",
        set(inventory["health_status"].unique()) <= {"OUT_OF_STOCK", "LOW_STOCK", "HEALTHY", "OVERSTOCKED", "DEAD_STOCK"})
    add("RFM segments are the five defined labels", set(customers["rfm_segment"].dropna().unique()) ==
        {"Champions", "Loyal Customers", "Potential Loyalists", "At Risk", "Lost Customers"})
    lowered = categories["category_name"].str.lower()
    add("category names are canonical (no case-variant duplicates)", lowered.nunique() == categories["category_name"].nunique())

    # 5. cross-view reconciliation (same number, different route)
    def close(a: float, b: float, tol: float) -> bool:
        return abs(float(a) - float(b)) <= tol

    revenue = float(monthly["net_revenue"].sum())
    add("net revenue: monthly view = product view", close(revenue, products["net_revenue"].sum(), 5),
        f"{revenue:,.0f} vs {products['net_revenue'].sum():,.0f}")
    add("net revenue: monthly view = store view", close(revenue, stores["net_revenue"].sum(), 5))
    add("net revenue: monthly view = category view", close(revenue, categories["net_revenue"].sum(), 5))
    add("net revenue: monthly view = customer view", close(revenue, customers["net_revenue"].sum(), 5))
    add("gross profit: monthly view = product view", close(monthly["gross_profit"].sum(), products["gross_profit"].sum(), 5))
    add("inventory value: health view = product view = store view",
        close(inventory["inventory_value"].sum(), products["inventory_value"].sum(), 5)
        and close(inventory["inventory_value"].sum(), stores["inventory_value"].sum(), 5))
    add("units sold: monthly view = product view", int(monthly["units_sold"].sum()) == int(products["units_sold"].sum()))
    add("completed orders: monthly view = store view = customer view",
        int(monthly["orders"].sum()) == int(stores["orders"].sum()) == int(customers["orders"].sum()))

    # 6. Python view data vs the base tables (an independent route through SQL)
    base = get_query("SELECT SUM(total_amount - gst_amount) AS revenue, COUNT(*) AS orders FROM sales_orders WHERE order_status = 'COMPLETED'").iloc[0]
    add("net revenue: views = base table sales_orders", close(revenue, base["revenue"], 5), f"{revenue:,.0f} vs {base['revenue']:,.0f}")
    add("orders: views = base table sales_orders", int(monthly["orders"].sum()) == int(base["orders"]))
    refunds = get_query("SELECT SUM(refund_amount) AS refunds FROM returns").iloc[0]["refunds"]
    add("refund value: return view = returns table", close(returns["refund_amount"].sum(), refunds, 1))
    return checks


def report(checks: list[Check]) -> pd.DataFrame:
    return pd.DataFrame([{"status": "PASS" if c.passed else "FAIL", "check": c.name, "detail": c.detail} for c in checks])


def main() -> int:
    checks = run_checks()
    df = report(checks)
    pd.set_option("display.width", 200, "display.max_colwidth", 90)
    print(df.to_string(index=False))
    failed = int((df["status"] == "FAIL").sum())
    print(f"\n{len(df) - failed}/{len(df)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

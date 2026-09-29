"""Compute the value every Power BI measure in dashboard/measures.dax should show, and write dashboard/expected_kpis.md.

Run from the project root:   python python/expected_kpis.py

Use it to check your dashboard: with no slicers selected each card must equal the "All data" column, and after selecting a
year the values must equal that year's column. The numbers come straight from the SQL views (not from the DAX), so a
mismatch means the Power BI model or a measure is wrong.
"""
from datetime import datetime
from pathlib import Path

import pandas as pd

from data_extraction import get_query

OUT = Path(__file__).resolve().parents[1] / "dashboard" / "expected_kpis.md"


def _one(sql: str) -> float:
    return float(get_query(sql).iloc[0, 0] or 0)


def all_data() -> dict[str, float]:
    m = {}
    sl = "FROM vw_sales_lines"
    m["Net Revenue"] = _one(f"SELECT SUM(net_revenue) {sl}")
    m["Gross Profit"] = _one(f"SELECT SUM(gross_profit) {sl}")
    m["COGS"] = _one(f"SELECT SUM(cogs) {sl}")
    m["Gross Margin %"] = 100 * m["Gross Profit"] / m["Net Revenue"]
    m["Units Sold"] = _one(f"SELECT SUM(quantity) {sl}")
    m["Discount Given"] = _one(f"SELECT SUM(discount_amount) {sl}")
    m["Orders (line basis)"] = _one(f"SELECT COUNT(DISTINCT order_id) {sl}")
    m["Completed Orders"] = _one("SELECT COUNT(*) FROM vw_orders WHERE order_status = 'COMPLETED'")
    m["Cancelled Orders"] = _one("SELECT COUNT(*) FROM vw_orders WHERE order_status = 'CANCELLED'")
    m["Cancellation Rate %"] = 100 * m["Cancelled Orders"] / _one("SELECT COUNT(*) FROM vw_orders")
    m["Order Sales incl GST"] = _one("SELECT SUM(total_amount) FROM vw_orders WHERE order_status = 'COMPLETED'")
    m["Average Order Value"] = m["Order Sales incl GST"] / m["Completed Orders"]
    m["Total Customers"] = _one("SELECT COUNT(DISTINCT customer_id) FROM vw_orders WHERE order_status = 'COMPLETED'")
    m["Purchase Frequency"] = m["Completed Orders"] / m["Total Customers"]
    m["Online Order Share %"] = 100 * _one("SELECT COUNT(*) FROM vw_orders WHERE order_status = 'COMPLETED' AND channel = 'ONLINE'") / m["Completed Orders"]
    m["Buying Customers (lifetime)"] = _one("SELECT COUNT(*) FROM vw_customer_summary WHERE orders > 0")
    m["Repeat Customers"] = _one("SELECT COUNT(*) FROM vw_customer_summary WHERE is_repeat_customer")
    m["Repeat Customer Rate %"] = 100 * m["Repeat Customers"] / m["Buying Customers (lifetime)"]
    m["Avg Customer Lifetime Revenue"] = _one("SELECT SUM(net_revenue) FROM vw_customer_summary") / m["Buying Customers (lifetime)"]
    m["Active Customers (90d)"] = _one("SELECT COUNT(*) FROM vw_customer_summary WHERE activity_status = 'Active (last 90 days)'")
    m["Orders With Returns"] = _one("SELECT COUNT(*) FROM vw_orders WHERE order_status = 'COMPLETED' AND has_return")
    m["Order Return Rate %"] = 100 * m["Orders With Returns"] / m["Completed Orders"]
    m["Units Returned"] = _one("SELECT SUM(units_returned) FROM vw_return_analysis")
    m["Unit Return Rate %"] = 100 * m["Units Returned"] / m["Units Sold"]
    m["Refunded Net of GST"] = _one("SELECT SUM(refund_net_of_gst) FROM vw_return_analysis")
    m["Refund % of Net Revenue"] = 100 * m["Refunded Net of GST"] / m["Net Revenue"]
    m["Write-off Cost"] = _one("SELECT SUM(cost_value) FROM vw_return_analysis WHERE NOT restocked")
    inv = get_query("SELECT health_status, COUNT(*) AS n, SUM(inventory_value) AS value, SUM(quantity_on_hand) AS units, "
                    "SUM(suggested_order_qty) AS suggested FROM vw_inventory_health GROUP BY 1").set_index("health_status")
    m["Inventory Value"] = float(inv["value"].sum())
    m["Units On Hand"] = float(inv["units"].sum())
    m["Stock Positions"] = float(inv["n"].sum())
    for status, label in [("OUT_OF_STOCK", "Out of Stock Positions"), ("LOW_STOCK", "Low Stock Positions"), ("HEALTHY", "Healthy Positions"),
                          ("OVERSTOCKED", "Overstocked Positions"), ("DEAD_STOCK", "Dead Stock Positions")]:
        m[label] = float(inv.loc[status, "n"])
    m["Overstock Value"] = float(inv.loc["OVERSTOCKED", "value"])
    m["Dead Stock Value"] = float(inv.loc["DEAD_STOCK", "value"])
    m["Surplus Share of Value %"] = 100 * (m["Overstock Value"] + m["Dead Stock Value"]) / m["Inventory Value"]
    m["Stock-out Risk %"] = 100 * (m["Out of Stock Positions"] + m["Low Stock Positions"]) / m["Stock Positions"]
    m["Suggested Order Qty"] = float(inv.loc[["OUT_OF_STOCK", "LOW_STOCK"], "suggested"].sum())
    m["COGS Last 12M"] = _one("SELECT SUM(cogs) FROM vw_sales_lines WHERE order_day > (SELECT asof_date FROM vw_asof) - 365")
    m["Inventory Turnover"] = m["COGS Last 12M"] / m["Inventory Value"]
    m["Days of Inventory"] = 365 / m["Inventory Turnover"]
    m["Class A Products"] = _one("SELECT COUNT(*) FROM vw_product_performance WHERE abc_class = 'A'")
    m["Class A Revenue Share %"] = 100 * _one("SELECT SUM(net_revenue) FROM vw_product_performance WHERE abc_class = 'A'") / _one("SELECT SUM(net_revenue) FROM vw_product_performance")
    return m


def by_year() -> pd.DataFrame:
    sales = get_query("SELECT order_year AS year, SUM(net_revenue) AS net_revenue, SUM(gross_profit) AS gross_profit, SUM(quantity) AS units_sold, "
                      "SUM(discount_amount) AS discount_given FROM vw_sales_lines GROUP BY 1").set_index("year")
    orders = get_query("SELECT EXTRACT(YEAR FROM order_day)::int AS year, COUNT(*) AS completed_orders, COUNT(DISTINCT customer_id) AS total_customers, "
                       "SUM(total_amount) AS order_sales_incl_gst, COUNT(*) FILTER (WHERE has_return) AS orders_with_returns "
                       "FROM vw_orders WHERE order_status = 'COMPLETED' GROUP BY 1").set_index("year")
    cancelled = get_query("SELECT EXTRACT(YEAR FROM order_day)::int AS year, COUNT(*) AS cancelled_orders FROM vw_orders "
                          "WHERE order_status = 'CANCELLED' GROUP BY 1").set_index("year")
    t = sales.join(orders).join(cancelled)
    t["Gross Margin %"] = 100 * t["gross_profit"] / t["net_revenue"]
    t["Average Order Value"] = t["order_sales_incl_gst"] / t["completed_orders"]
    t["Order Return Rate %"] = 100 * t["orders_with_returns"] / t["completed_orders"]
    t["Net Revenue YoY %"] = 100 * t["net_revenue"].pct_change()
    t = t.rename(columns={"net_revenue": "Net Revenue", "gross_profit": "Gross Profit", "units_sold": "Units Sold", "discount_given": "Discount Given",
                          "completed_orders": "Completed Orders", "total_customers": "Total Customers", "cancelled_orders": "Cancelled Orders"})
    cols = ["Net Revenue", "Gross Profit", "Gross Margin %", "Units Sold", "Discount Given", "Completed Orders", "Cancelled Orders",
            "Total Customers", "Average Order Value", "Order Return Rate %", "Net Revenue YoY %"]
    return t[cols].T


def _fmt(name: str, value) -> str:
    if pd.isna(value):
        return "blank"
    if name.endswith("%") or name in ("Purchase Frequency", "Inventory Turnover"):
        return f"{value:,.2f}"
    return f"{value:,.0f}"


def write_markdown(m: dict, yearly: pd.DataFrame) -> str:
    lines = ["# Expected KPI values for the Power BI dashboard", "",
             f"*Generated by `python python/expected_kpis.py` on {datetime.now():%Y-%m-%d} from the PostgreSQL views (data seed 42).*", "",
             "Use this file to test your dashboard. With **no slicer selected**, each card must show the value in the *All data* table "
             "(rounding to the last digit is fine; amounts are INR). After selecting a **year** on the date slicer, "
             "the year-based measures must match the *By year* table.", "",
             "Measure names match [measures.dax](measures.dax). Percent measures are shown as numbers (e.g. 20.94 means 20.94 %).", "",
             "## All data (no slicers)", "", "| Measure | Expected value |", "|---|---:|"]
    lines += [f"| {k} | {_fmt(k, v)} |" for k, v in m.items()]
    lines += ["", "## By year (date slicer = one year)", "", "| Measure | " + " | ".join(str(c) for c in yearly.columns) + " |",
              "|---|" + "---:|" * len(yearly.columns)]
    for name, row in yearly.iterrows():
        lines.append(f"| {name} | " + " | ".join(_fmt(name, v) for v in row) + " |")
    lines += ["", "Notes:",
              "- *Lifetime* measures (Buying Customers, Repeat Customer Rate, Avg Customer Lifetime Revenue, Active Customers) ignore the date slicer by design.",
              "- Inventory measures describe the **current** stock snapshot and also ignore the date slicer.",
              "- *Total Customers* by year counts customers with at least one completed order in that year, so the yearly values do not add up to the all-data value.", ""]
    text = "\n".join(lines)
    OUT.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    print(write_markdown(all_data(), by_year()))

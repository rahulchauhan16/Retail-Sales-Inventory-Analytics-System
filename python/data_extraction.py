"""Read the analytical views into pandas DataFrames.

All heavy relational work (joins, GST maths, RFM scores, stock health rules) already happens in PostgreSQL,
in database/views.sql. This module only pulls the results out; the analysis modules explore them.
"""
import pandas as pd

from database_connection import get_engine

# view name -> short description (also used by the validation and export scripts)
VIEWS = {
    "vw_monthly_sales": "one row per month: orders, revenue, profit, refunds",
    "vw_product_performance": "one row per product: sales, margin, returns, stock, ABC class",
    "vw_customer_summary": "one row per customer: value, RFM scores and segment (materialized)",
    "vw_inventory_health": "one row per store + product: stock level and health status",
    "vw_store_performance": "one row per store: revenue, AOV, repeat rate, returns, stock value",
    "vw_category_performance": "one row per category and year: revenue, margin, growth, returns",
    "vw_supplier_performance": "one row per supplier: spend, on-time %, fill rate",
    "vw_return_analysis": "one row per returned line: reason, store, category, refund",
    "vw_orders": "one row per order (all statuses)",
    "vw_sales_lines": "one row per sold order line (completed orders)",
}


def get_view(name: str, engine=None) -> pd.DataFrame:
    """Return a whole view as a DataFrame. Only known view names are accepted (keeps SQL injection out of f-strings)."""
    if name not in VIEWS:
        raise ValueError(f"Unknown view '{name}'. Known views: {', '.join(VIEWS)}")
    return pd.read_sql(f"SELECT * FROM {name}", engine or get_engine())


def get_query(sql: str, engine=None, params: dict | None = None) -> pd.DataFrame:
    """Run a read-only SELECT (used for the few shapes that no view provides, e.g. cohort activity)."""
    from sqlalchemy import text
    with (engine or get_engine()).connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def extract_core(engine=None) -> dict[str, pd.DataFrame]:
    """Load the small/medium views used by nearly every analysis (skips the two 50k+ row fact views)."""
    engine = engine or get_engine()
    names = ["vw_monthly_sales", "vw_product_performance", "vw_customer_summary", "vw_inventory_health",
             "vw_store_performance", "vw_category_performance", "vw_supplier_performance", "vw_return_analysis"]
    return {n: get_view(n, engine) for n in names}


if __name__ == "__main__":
    data = extract_core()
    for view, df in data.items():
        print(f"{view:<26}{len(df):>8,} rows x {df.shape[1]:>2} columns")

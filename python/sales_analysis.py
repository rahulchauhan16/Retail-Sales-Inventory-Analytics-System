"""Sales analysis in pandas: trend, growth, seasonality, channel mix, stores, categories, order-value distribution.

Run from the project root:   python python/sales_analysis.py
Everything is computed from the SQL views; nothing here re-implements a join or the GST arithmetic.
"""
import pandas as pd

from data_extraction import get_view
from kpis import growth_table, yearly_summary

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def seasonality_index(monthly: pd.DataFrame) -> pd.DataFrame:
    """Average revenue of each calendar month relative to its own year's monthly average (100 = typical month).

    Dividing by the year's mean removes the growth trend, so what is left is the seasonal pattern.
    """
    m = monthly.copy()
    m["vs_year_avg"] = m["net_revenue"] / m.groupby("year")["net_revenue"].transform("mean")
    out = m.groupby("month_number", as_index=False)["vs_year_avg"].mean()
    out["seasonality_index"] = (100 * out["vs_year_avg"]).round(1)
    out["month"] = out["month_number"].map(lambda n: MONTH_NAMES[n - 1])
    return out[["month_number", "month", "seasonality_index"]]


def channel_mix(monthly: pd.DataFrame) -> pd.DataFrame:
    """Online share of completed orders by year (order counts; revenue split by channel lives in queries/02, Q25)."""
    y = monthly.groupby("year", as_index=False).agg(orders=("orders", "sum"), online_orders=("online_orders", "sum"))
    y["online_share_pct"] = 100 * y["online_orders"] / y["orders"]
    return y


def category_table(category_perf: pd.DataFrame) -> pd.DataFrame:
    """Latest-year category revenue with growth, sorted by revenue."""
    latest = category_perf["year"].max()
    t = category_perf[category_perf["year"] == latest].sort_values("net_revenue", ascending=False)
    return t[["category_name", "net_revenue", "share_of_year_revenue_pct", "margin_pct", "yoy_growth_pct"]].reset_index(drop=True)


def order_value_distribution(orders: pd.DataFrame) -> dict:
    """Order-value summary for completed orders: mean vs median and percentiles (order values are right-skewed)."""
    v = orders.loc[orders["order_status"] == "COMPLETED", "total_amount"].astype(float)
    q = v.quantile([0.25, 0.5, 0.75, 0.9, 0.99])
    return {"mean": v.mean(), "median": q[0.5], "p25": q[0.25], "p75": q[0.75], "p90": q[0.9], "p99": q[0.99], "max": v.max(),
            "iqr_fence": q[0.75] + 1.5 * (q[0.75] - q[0.25])}


def weekday_pattern(orders: pd.DataFrame) -> pd.DataFrame:
    done = orders[orders["order_status"] == "COMPLETED"].copy()
    done["weekday"] = pd.to_datetime(done["order_date"]).dt.day_name()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    t = done.groupby("weekday").agg(orders=("order_id", "count"), avg_order_value=("total_amount", "mean")).reindex(order)
    return t.reset_index()


def main() -> None:
    pd.set_option("display.width", 200, "display.max_columns", 20, "display.float_format", "{:,.1f}".format)
    monthly, cats = get_view("vw_monthly_sales"), get_view("vw_category_performance")
    orders, stores = get_view("vw_orders"), get_view("vw_store_performance")

    print("== Yearly summary ==")
    print(yearly_summary(monthly).to_string(index=False))
    print("\n== Last 6 months (growth) ==")
    print(growth_table(monthly).tail(6).to_string(index=False))
    print("\n== Seasonality index (100 = typical month of the year) ==")
    print(seasonality_index(monthly).to_string(index=False))
    print("\n== Online share of orders ==")
    print(channel_mix(monthly).to_string(index=False))
    print("\n== Category revenue, latest year ==")
    print(category_table(cats).to_string(index=False))
    print("\n== Store ranking ==")
    print(stores.sort_values("revenue_rank")[["store_name", "net_revenue", "avg_order_value", "revenue_per_month_index_vs_stores"]].to_string(index=False))
    print("\n== Order value distribution (INR, GST-inclusive) ==")
    for k, v in order_value_distribution(orders).items():
        print(f"  {k:<10}{v:>12,.0f}")


if __name__ == "__main__":
    main()

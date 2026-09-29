"""Customer analysis in pandas: segments, RFM, activity status, cohorts, concentration, lifetime value.

Run from the project root:   python python/customer_analysis.py
The RFM scores and labels come from vw_customer_summary (thresholds documented in docs/07_customer_analytics.md).
"""
import pandas as pd

from data_extraction import get_query, get_view

RFM_ORDER = ["Champions", "Loyal Customers", "Potential Loyalists", "At Risk", "Lost Customers"]
STATUS_ORDER = ["Active (last 90 days)", "Inactive (91-365 days)", "Lost (over 365 days)", "Never purchased"]


def segment_summary(customers: pd.DataFrame) -> pd.DataFrame:
    """Buyers, revenue and lifetime value (average net revenue per buyer) by commercial segment."""
    buyers = customers[customers["orders"] > 0]
    t = buyers.groupby("segment").agg(customers=("customer_id", "count"), orders=("orders", "sum"), net_revenue=("net_revenue", "sum"),
                                      avg_lifetime_revenue=("net_revenue", "mean"), avg_lifetime_profit=("gross_profit", "mean"))
    t["revenue_share_pct"] = 100 * t["net_revenue"] / t["net_revenue"].sum()
    return t.sort_values("net_revenue", ascending=False).reset_index()


def rfm_summary(customers: pd.DataFrame) -> pd.DataFrame:
    buyers = customers[customers["orders"] > 0]
    t = buyers.groupby("rfm_segment").agg(customers=("customer_id", "count"), net_revenue=("net_revenue", "sum"),
                                          avg_recency_days=("recency_days", "mean"), avg_orders=("orders", "mean"))
    t["customer_share_pct"] = 100 * t["customers"] / t["customers"].sum()
    t["revenue_share_pct"] = 100 * t["net_revenue"] / t["net_revenue"].sum()
    return t.reindex(RFM_ORDER).reset_index()


def activity_status(customers: pd.DataFrame) -> pd.DataFrame:
    t = customers.groupby("activity_status").size().rename("customers").reindex(STATUS_ORDER).reset_index()
    t["share_pct"] = 100 * t["customers"] / t["customers"].sum()
    return t


def repeat_rate(customers: pd.DataFrame) -> dict:
    buyers = customers[customers["orders"] > 0]
    return {"buying_customers": len(buyers), "repeat_customers": int((buyers["orders"] >= 2).sum()),
            "repeat_customer_rate_pct": 100 * float((buyers["orders"] >= 2).mean())}


def frequency_bands(customers: pd.DataFrame) -> pd.DataFrame:
    buyers = customers[customers["orders"] > 0].copy()
    buyers["frequency_band"] = pd.cut(buyers["orders"], bins=[0, 1, 3, 6, 12, 10_000],
                                      labels=["1 order", "2-3 orders", "4-6 orders", "7-12 orders", "13+ orders"])
    t = buyers.groupby("frequency_band", observed=True).agg(customers=("customer_id", "count"), net_revenue=("net_revenue", "sum"))
    t["customer_share_pct"] = 100 * t["customers"] / t["customers"].sum()
    t["revenue_share_pct"] = 100 * t["net_revenue"] / t["net_revenue"].sum()
    return t.reset_index()


def concentration(customers: pd.DataFrame) -> pd.DataFrame:
    """Share of revenue held by each decile of buyers (decile 10 = top 10 % by revenue)."""
    buyers = customers[customers["orders"] > 0].sort_values("net_revenue")
    buyers = buyers.assign(decile=pd.qcut(buyers["net_revenue"].rank(method="first"), 10, labels=range(1, 11)))
    t = buyers.groupby("decile", observed=True)["net_revenue"].sum().to_frame()
    t["revenue_share_pct"] = 100 * t["net_revenue"] / t["net_revenue"].sum()
    return t.sort_index(ascending=False).reset_index()


def cohort_retention(max_month: int = 6) -> pd.DataFrame:
    """Percentage of each first-purchase-month cohort that buys again 1..max_month months later.

    Uses the order-level view because activity by month is not in the customer summary. Only cohorts with the full
    follow-up window (the last max_month months are excluded) are returned.
    """
    orders = get_query("SELECT customer_id, order_month FROM vw_orders WHERE order_status = 'COMPLETED' GROUP BY customer_id, order_month")
    orders["order_month"] = pd.to_datetime(orders["order_month"])
    first = orders.groupby("customer_id")["order_month"].min().rename("cohort")
    orders = orders.join(first, on="customer_id")
    orders["month_index"] = ((orders["order_month"].dt.year - orders["cohort"].dt.year) * 12
                             + orders["order_month"].dt.month - orders["cohort"].dt.month)
    grid = orders.pivot_table(index="cohort", columns="month_index", values="customer_id", aggfunc="nunique")
    retention = grid.div(grid[0], axis=0) * 100
    last_full = orders["order_month"].max() - pd.DateOffset(months=max_month)
    retention = retention.loc[retention.index <= last_full, list(range(0, max_month + 1))]
    retention.insert(0, "cohort_size", grid[0].loc[retention.index].astype(int))
    return retention.reset_index()


def top_customers(customers: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    cols = ["customer_id", "customer_name", "segment", "orders", "net_revenue", "avg_order_value", "last_order_date", "rfm_segment"]
    return customers.sort_values("net_revenue", ascending=False).head(n)[cols].reset_index(drop=True)


def main() -> None:
    pd.set_option("display.width", 200, "display.max_columns", 20, "display.float_format", "{:,.1f}".format)
    customers = get_view("vw_customer_summary")
    print("== Repeat customers ==");             print(repeat_rate(customers))
    print("\n== Segments (buyers) ==");           print(segment_summary(customers).to_string(index=False))
    print("\n== RFM segments ==");                print(rfm_summary(customers).to_string(index=False))
    print("\n== Activity status ==");             print(activity_status(customers).to_string(index=False))
    print("\n== Purchase frequency ==");          print(frequency_bands(customers).to_string(index=False))
    print("\n== Revenue concentration by decile ==");  print(concentration(customers).to_string(index=False))
    print("\n== Cohort retention (first 6 cohorts) ==");  print(cohort_retention().head(6).to_string(index=False))
    print("\n== Top 10 customers ==");            print(top_customers(customers).to_string(index=False))


if __name__ == "__main__":
    main()

"""Headline KPI calculations in pandas.

The SQL views hold the row-level logic; these functions turn view DataFrames into the documented KPIs.
tests/test_python_analytics.py checks every value here against the independent SQL query in
queries/11_business_questions.sql (Q401), so Python, SQL and Power BI cannot drift apart.

Definitions (also in docs/08_powerbi_dashboard.md):
    Net revenue          = sum of order lines / (1 + GST rate)            -> vw_monthly_sales.net_revenue
    Gross profit         = net revenue - quantity * unit_cost (cost snapshot at sale time)
    Gross margin %       = gross profit / net revenue * 100
    Average order value  = GST-inclusive sales / completed orders
    Order return rate    = completed orders with at least one return / completed orders * 100
    Repeat customer rate = buyers with 2+ completed orders / buyers with 1+ completed orders * 100
    Inventory value      = quantity on hand * unit cost (at cost, ex-GST)
    Inventory turnover   = cost of goods sold in the last 12 months / current inventory value (ending-inventory approximation)
    Customer lifetime value (to date) = average net revenue per buying customer (historical, not a forecast)
"""
import pandas as pd


def headline_kpis(monthly: pd.DataFrame, customers: pd.DataFrame, inventory: pd.DataFrame, orders: pd.DataFrame) -> dict:
    """Compute the executive KPIs.

    monthly   : vw_monthly_sales
    customers : vw_customer_summary
    inventory : vw_inventory_health
    orders    : vw_orders (all statuses; needs order_status, has_return)
    """
    completed_orders = int(monthly["orders"].sum())
    net_revenue = float(monthly["net_revenue"].sum())
    gross_profit = float(monthly["gross_profit"].sum())
    buyers = customers[customers["orders"] > 0]
    done = orders[orders["order_status"] == "COMPLETED"]
    last_12m_cogs = float(monthly.sort_values("month").tail(12)["cogs"].sum())
    inventory_value = float(inventory["inventory_value"].sum())
    return {
        "net_revenue": round(net_revenue, 0),
        "gross_profit": round(gross_profit, 0),
        "gross_margin_pct": round(100 * gross_profit / net_revenue, 2),
        "completed_orders": completed_orders,
        "cancelled_orders": int((orders["order_status"] == "CANCELLED").sum()),
        "buying_customers": int(len(buyers)),
        "avg_order_value": round(float(monthly["gross_sales_incl_gst"].sum()) / completed_orders, 0),
        "repeat_customer_rate_pct": round(100 * float((buyers["orders"] >= 2).mean()), 1),
        "order_return_rate_pct": round(100 * float(done["has_return"].mean()), 2),
        "inventory_value_at_cost": round(inventory_value, 0),
        "inventory_turnover_12m": round(last_12m_cogs / inventory_value, 2),
        "avg_customer_lifetime_revenue": round(float(buyers["net_revenue"].mean()), 0),
    }


def growth_table(monthly: pd.DataFrame) -> pd.DataFrame:
    """Monthly revenue with month-over-month %, year-over-year % and a 3-month moving average."""
    m = monthly.sort_values("month").reset_index(drop=True)[["month", "net_revenue", "orders", "gross_profit"]].copy()
    m["mom_growth_pct"] = m["net_revenue"].pct_change() * 100
    m["yoy_growth_pct"] = m["net_revenue"].pct_change(12) * 100
    m["moving_avg_3m"] = m["net_revenue"].rolling(3).mean()
    m["running_total"] = m["net_revenue"].cumsum()
    return m


def yearly_summary(monthly: pd.DataFrame) -> pd.DataFrame:
    """Net revenue, profit, orders and growth per calendar year."""
    y = monthly.groupby("year", as_index=False).agg(orders=("orders", "sum"), net_revenue=("net_revenue", "sum"),
                                                     gross_profit=("gross_profit", "sum"))
    y["margin_pct"] = 100 * y["gross_profit"] / y["net_revenue"]
    y["yoy_growth_pct"] = y["net_revenue"].pct_change() * 100
    return y


def pareto(values: pd.Series, a_cut: float = 80.0, b_cut: float = 95.0) -> pd.DataFrame:
    """ABC classification of any non-negative series (project convention: A = first 80 %, B = next 15 %, C = last 5 %)."""
    s = values[values > 0].sort_values(ascending=False)
    share = 100 * s / s.sum()
    cum = share.cumsum()
    klass = pd.cut(cum - share, bins=[-1, a_cut, b_cut, 101], labels=["A", "B", "C"], right=False)
    return pd.DataFrame({"value": s, "share_pct": share, "cumulative_pct": cum, "abc_class": klass})

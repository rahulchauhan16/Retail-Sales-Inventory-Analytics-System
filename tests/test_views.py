"""Views must exist, be non-empty, reconcile with the base tables and agree with each other."""
import pytest
from sqlalchemy import text

VIEWS = ["vw_asof", "vw_category_canonical", "vw_sales_lines", "vw_orders", "vw_monthly_sales", "vw_product_performance",
         "vw_customer_summary", "vw_inventory_health", "vw_store_performance", "vw_category_performance",
         "vw_supplier_performance", "vw_return_analysis"]


def scalar(conn, sql):
    return conn.execute(text(sql)).scalar()


@pytest.mark.parametrize("view", VIEWS)
def test_view_exists_and_has_rows(conn, view):
    assert scalar(conn, f"SELECT count(*) FROM {view}") > 0


def close(a, b, tol=1.0):
    return abs(float(a) - float(b)) <= tol


def test_net_revenue_agrees_across_views(conn):
    """One revenue number, however you slice it. Tolerance covers per-line vs per-order GST rounding."""
    base = scalar(conn, "SELECT SUM(total_amount - gst_amount) FROM sales_orders WHERE order_status = 'COMPLETED'")
    lines = scalar(conn, "SELECT SUM(net_revenue) FROM vw_sales_lines")
    monthly = scalar(conn, "SELECT SUM(net_revenue) FROM vw_monthly_sales")
    stores = scalar(conn, "SELECT SUM(net_revenue) FROM vw_store_performance")
    products = scalar(conn, "SELECT SUM(net_revenue) FROM vw_product_performance")
    categories = scalar(conn, "SELECT SUM(net_revenue) FROM vw_category_performance")
    customers = scalar(conn, "SELECT SUM(net_revenue) FROM vw_customer_summary")
    assert close(base, lines, 500)                       # 100k+ rounded lines: allow a few hundred rupees
    for name, value in dict(monthly=monthly, stores=stores, products=products, categories=categories).items():
        assert close(lines, value, 5), f"{name}: {value} vs {lines}"
    assert close(base, customers, 5), f"customers: {customers} vs {base}"


def test_gross_profit_agrees_across_views(conn):
    lines = scalar(conn, "SELECT SUM(gross_profit) FROM vw_sales_lines")
    for view in ("vw_monthly_sales", "vw_store_performance", "vw_product_performance", "vw_category_performance"):
        assert close(lines, scalar(conn, f"SELECT SUM(gross_profit) FROM {view}"), 5), view


def test_order_counts_agree(conn):
    completed = scalar(conn, "SELECT count(*) FROM sales_orders WHERE order_status = 'COMPLETED'")
    assert scalar(conn, "SELECT SUM(orders) FROM vw_monthly_sales") == completed
    assert scalar(conn, "SELECT SUM(orders) FROM vw_store_performance") == completed
    assert scalar(conn, "SELECT SUM(orders) FROM vw_customer_summary") == completed
    assert scalar(conn, "SELECT count(*) FROM vw_orders") == scalar(conn, "SELECT count(*) FROM sales_orders")


def test_monthly_sales_has_every_month_once(conn):
    months, distinct = conn.execute(text("SELECT count(*), count(DISTINCT month) FROM vw_monthly_sales")).one()
    assert months == distinct == 36


def test_units_sold_agree(conn):
    total = scalar(conn, "SELECT SUM(i.quantity) FROM sales_order_items i JOIN sales_orders o USING (order_id) WHERE o.order_status = 'COMPLETED'")
    assert scalar(conn, "SELECT SUM(units_sold) FROM vw_product_performance") == total
    assert scalar(conn, "SELECT SUM(units_sold) FROM vw_monthly_sales") == total


def test_customer_summary_covers_every_customer_once(conn):
    assert scalar(conn, "SELECT count(*) FROM vw_customer_summary") == scalar(conn, "SELECT count(*) FROM customers")
    assert scalar(conn, "SELECT count(*) - count(DISTINCT customer_id) FROM vw_customer_summary") == 0


def test_rfm_segments_and_activity_status_are_complete(conn):
    valid = {"Champions", "Loyal Customers", "Potential Loyalists", "At Risk", "Lost Customers"}
    got = set(conn.execute(text("SELECT DISTINCT rfm_segment FROM vw_customer_summary WHERE rfm_segment IS NOT NULL")).scalars())
    assert got == valid
    assert scalar(conn, "SELECT count(*) FROM vw_customer_summary WHERE orders = 0 AND rfm_segment IS NOT NULL") == 0
    assert scalar(conn, "SELECT count(*) FROM vw_customer_summary WHERE orders > 0 AND rfm_segment IS NULL") == 0
    never = scalar(conn, "SELECT count(*) FROM vw_customer_summary WHERE activity_status = 'Never purchased'")
    assert never == scalar(conn, "SELECT count(*) FROM vw_customer_summary WHERE orders = 0")


def test_repeat_customer_rate_matches_direct_query(conn):
    direct = scalar(conn, """SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE n >= 2) / COUNT(*), 2)
                             FROM (SELECT COUNT(*) AS n FROM sales_orders WHERE order_status = 'COMPLETED' GROUP BY customer_id) t""")
    from_view = scalar(conn, """SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE is_repeat_customer) / COUNT(*) FILTER (WHERE orders > 0), 2)
                                FROM vw_customer_summary""")
    assert direct == from_view


def test_inventory_health_covers_every_position_with_valid_status(conn):
    assert scalar(conn, "SELECT count(*) FROM vw_inventory_health") == scalar(conn, "SELECT count(*) FROM inventory")
    statuses = set(conn.execute(text("SELECT DISTINCT health_status FROM vw_inventory_health")).scalars())
    assert statuses <= {"OUT_OF_STOCK", "LOW_STOCK", "HEALTHY", "OVERSTOCKED", "DEAD_STOCK"}
    assert len(statuses) == 5, statuses                  # the dataset is meant to contain all five situations
    assert scalar(conn, "SELECT count(*) FROM vw_inventory_health WHERE health_status = 'OUT_OF_STOCK' AND quantity_on_hand <> 0") == 0


def test_inventory_value_agrees(conn):
    direct = scalar(conn, "SELECT SUM(i.quantity_on_hand * p.unit_cost) FROM inventory i JOIN products p USING (product_id)")
    assert close(direct, scalar(conn, "SELECT SUM(inventory_value) FROM vw_inventory_health"), 5)
    assert close(direct, scalar(conn, "SELECT SUM(inventory_value) FROM vw_product_performance"), 5)
    assert close(direct, scalar(conn, "SELECT SUM(inventory_value) FROM vw_store_performance"), 5)


def test_abc_classes_and_product_classes(conn):
    classes = set(conn.execute(text("SELECT DISTINCT abc_class FROM vw_product_performance")).scalars())
    assert classes == {"A", "B", "C", "No sales"}
    a_share = scalar(conn, "SELECT SUM(revenue_share_pct) FROM vw_product_performance WHERE abc_class = 'A'")
    assert 79 <= float(a_share) <= 81.5
    assert scalar(conn, "SELECT count(*) FROM vw_product_performance WHERE abc_class = 'No sales' AND units_sold > 0") == 0


def test_return_view_matches_returns_table(conn):
    assert close(scalar(conn, "SELECT SUM(refund_amount) FROM vw_return_analysis"), scalar(conn, "SELECT SUM(refund_amount) FROM returns"), 1)
    assert scalar(conn, "SELECT count(*) FROM vw_return_analysis") == scalar(conn, "SELECT count(*) FROM return_items")


def test_supplier_view_totals(conn):
    assert scalar(conn, "SELECT count(*) FROM vw_supplier_performance") == scalar(conn, "SELECT count(*) FROM suppliers")
    assert scalar(conn, "SELECT SUM(total_pos) FROM vw_supplier_performance") == scalar(conn, "SELECT count(*) FROM purchases")


def test_category_names_are_canonical(conn):
    names = set(conn.execute(text("SELECT DISTINCT category_name FROM vw_category_performance")).scalars())
    lowered = [n.lower() for n in names]
    assert len(lowered) == len(set(lowered)), "case-variant categories were not merged"


# ------------------------------------------------------------------ indexes
def test_expected_indexes_exist(conn):
    names = set(conn.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")).scalars())
    expected = {"idx_orders_customer", "idx_orders_date", "idx_items_product", "idx_payments_order", "idx_returns_order",
                "idx_return_items_order_item", "idx_inventory_product", "idx_invtxn_store_product_date",
                "idx_purchases_open_expected", "idx_customers_email_lower"}
    assert expected <= names


def test_planner_uses_the_customer_index_for_a_selective_lookup(conn):
    plan = "\n".join(conn.execute(text("EXPLAIN SELECT * FROM sales_orders WHERE customer_id = 4104")).scalars())
    assert "idx_orders_customer" in plan, plan

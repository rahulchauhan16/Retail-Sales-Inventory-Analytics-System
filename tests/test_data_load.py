"""Checks that the data loaded into PostgreSQL meets the project's volume targets."""
import pytest
from sqlalchemy import text

# table -> minimum expected rows (project targets from the requirements)
MIN_ROWS = {
    "customers": 5000, "products": 500, "categories": 15, "suppliers": 50, "stores": 10, "employees": 50,
    "sales_orders": 50000, "sales_order_items": 100000, "payments": 50000, "inventory": 5000,
    "inventory_transactions": 50000, "purchases": 5000, "returns": 2000, "promotions": 20,
}


@pytest.mark.parametrize("table,minimum", MIN_ROWS.items())
def test_row_count_meets_target(conn, table, minimum):
    count = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
    assert count >= minimum, f"{table} has {count}, expected >= {minimum}"


def test_data_covers_two_to_three_years(conn):
    lo, hi = conn.execute(text("SELECT min(order_date), max(order_date) FROM sales_orders")).one()
    assert 2.5 <= (hi - lo).days / 365.25 <= 3.1


def test_identity_sequences_are_synced(conn):
    """After a COPY load with explicit IDs, a plain INSERT must not collide with existing IDs."""
    conn.execute(text("INSERT INTO suppliers (supplier_name) VALUES ('sequence test')"))
    new_id, max_before = conn.execute(text(
        "SELECT (SELECT max(supplier_id) FROM suppliers WHERE supplier_name = 'sequence test'), "
        "(SELECT max(supplier_id) FROM suppliers WHERE supplier_name <> 'sequence test')")).one()
    assert new_id > max_before


def test_calendar_covers_data_window(conn):
    missing = conn.execute(text(
        "SELECT count(*) FROM sales_orders o LEFT JOIN dim_date d ON d.date_key = o.order_date::date "
        "WHERE d.date_key IS NULL")).scalar()
    assert missing == 0


def test_no_orphans_in_main_relationships(conn):
    """Foreign keys guarantee this; the test documents it with explicit anti-joins."""
    checks = {
        "order_items -> orders": "SELECT count(*) FROM sales_order_items i LEFT JOIN sales_orders o USING (order_id) WHERE o.order_id IS NULL",
        "orders -> customers": "SELECT count(*) FROM sales_orders o LEFT JOIN customers c USING (customer_id) WHERE c.customer_id IS NULL",
        "return_items -> order_items": "SELECT count(*) FROM return_items r LEFT JOIN sales_order_items i USING (order_item_id) WHERE i.order_item_id IS NULL",
        "inventory -> products": "SELECT count(*) FROM inventory i LEFT JOIN products p USING (product_id) WHERE p.product_id IS NULL",
    }
    for name, sql in checks.items():
        assert conn.execute(text(sql)).scalar() == 0, name

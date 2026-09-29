"""Proves that the schema rejects invalid data (PK/FK/UNIQUE/CHECK/NOT NULL)."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

EXPECTED_TABLES = {
    "customers", "customer_segments", "products", "categories", "suppliers", "stores",
    "employees", "sales_orders", "sales_order_items", "payments", "inventory",
    "inventory_transactions", "purchases", "purchase_items", "returns", "return_items",
    "promotions", "product_promotions", "dim_date",
}


def _fails(conn, sql, params=None):
    """Return the PostgreSQL error class name raised by a statement (inside a savepoint)."""
    sp = conn.begin_nested()
    with pytest.raises(DBAPIError) as exc:
        conn.execute(text(sql), params or {})
    sp.rollback()
    return type(exc.value.orig).__name__


def test_all_tables_exist(conn):
    rows = conn.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )).scalars().all()
    assert EXPECTED_TABLES <= set(rows)


def test_every_table_has_primary_key(conn):
    missing = conn.execute(text("""
        SELECT t.table_name FROM information_schema.tables t
        LEFT JOIN information_schema.table_constraints c
          ON c.table_name = t.table_name AND c.table_schema = t.table_schema
         AND c.constraint_type = 'PRIMARY KEY'
        WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE' AND c.constraint_name IS NULL
    """)).scalars().all()
    assert missing == []


def test_foreign_key_rejects_orphan(conn):
    assert _fails(conn, "INSERT INTO products (sku, product_name, category_id, unit_cost, unit_price) "
                        "VALUES ('X1', 'Orphan', 99999, 1, 2)") == "ForeignKeyViolation"


def test_negative_price_rejected(conn):
    assert _fails(conn, "INSERT INTO products (sku, product_name, unit_cost, unit_price) "
                        "VALUES ('X2', 'Neg', 1, -5)") == "CheckViolation"


def test_invalid_gst_rate_rejected(conn):
    assert _fails(conn, "INSERT INTO products (sku, product_name, unit_cost, unit_price, gst_rate) "
                        "VALUES ('X3', 'Bad GST', 1, 2, 13)") == "CheckViolation"


def test_unique_sku(conn):
    conn.execute(text("INSERT INTO products (sku, product_name, unit_cost, unit_price) VALUES ('U1','a',1,2)"))
    assert _fails(conn, "INSERT INTO products (sku, product_name, unit_cost, unit_price) "
                        "VALUES ('U1','b',1,2)") == "UniqueViolation"


def test_not_null_enforced(conn):
    assert _fails(conn, "INSERT INTO stores (store_code, store_name, city, state, region, opened_date) "
                        "VALUES ('S1', NULL, 'Pune', 'MH', 'West', '2020-01-01')") == "NotNullViolation"


def test_invalid_region_rejected(conn):
    assert _fails(conn, "INSERT INTO stores (store_code, store_name, city, state, region, opened_date) "
                        "VALUES ('S2', 'x', 'Pune', 'MH', 'Mars', '2020-01-01')") == "CheckViolation"


def test_promo_end_before_start_rejected(conn):
    assert _fails(conn, "INSERT INTO promotions (promo_code, promo_name, discount_type, discount_value, "
                        "start_date, end_date) VALUES ('P1','x','PERCENT',10,'2024-02-01','2024-01-01')"
                  ) == "CheckViolation"


def test_percent_promo_over_90_rejected(conn):
    assert _fails(conn, "INSERT INTO promotions (promo_code, promo_name, discount_type, discount_value, "
                        "start_date, end_date) VALUES ('P2','x','PERCENT',95,'2024-01-01','2024-02-01')"
                  ) == "CheckViolation"


def test_inventory_negative_stock_and_reserved_rules(conn):
    conn.execute(text("INSERT INTO stores (store_code, store_name, city, state, region, opened_date) "
                      "VALUES ('T1','t','Pune','MH','West','2020-01-01')"))
    conn.execute(text("INSERT INTO products (sku, product_name, unit_cost, unit_price) VALUES ('T-P','p',1,2)"))
    ids = "(SELECT store_id FROM stores WHERE store_code='T1'), (SELECT product_id FROM products WHERE sku='T-P')"
    assert _fails(conn, f"INSERT INTO inventory (store_id, product_id, quantity_on_hand) "
                        f"VALUES ({ids}, -1)") == "CheckViolation"
    assert _fails(conn, f"INSERT INTO inventory (store_id, product_id, quantity_on_hand, reserved_quantity) "
                        f"VALUES ({ids}, 5, 9)") == "CheckViolation"


def test_zero_quantity_line_rejected(conn):
    assert _fails(conn, "INSERT INTO sales_order_items (order_id, product_id, quantity, unit_price, "
                        "unit_cost, line_total) VALUES (1, 1, 0, 10, 5, 0)") in ("CheckViolation", "ForeignKeyViolation")


def test_updated_at_trigger(conn):
    conn.execute(text("INSERT INTO suppliers (supplier_name) VALUES ('Trigger Test')"))
    conn.execute(text("UPDATE suppliers SET updated_at = '2000-01-01' WHERE supplier_name='Trigger Test'"))
    conn.execute(text("UPDATE suppliers SET city='Pune' WHERE supplier_name='Trigger Test'"))
    year = conn.execute(text(
        "SELECT EXTRACT(year FROM updated_at) FROM suppliers WHERE supplier_name='Trigger Test'")).scalar()
    assert year >= 2024

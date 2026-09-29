"""Business-rule integrity of the loaded data (beyond what foreign keys can express)."""
import pytest
from sqlalchemy import text


def scalar(conn, sql):
    return conn.execute(text(sql)).scalar()


# ------------------------------------------------------------------ sales
def test_line_total_equals_qty_x_price_minus_discount(conn):
    assert scalar(conn, """SELECT count(*) FROM sales_order_items
                           WHERE abs(line_total - (quantity * unit_price - discount_amount)) > 0.01""") == 0


def test_order_header_matches_its_lines(conn):
    bad = scalar(conn, """
        SELECT count(*) FROM sales_orders o
        JOIN (SELECT order_id, sum(quantity * unit_price) AS gross, sum(discount_amount) AS disc,
                     sum(line_total) AS net
              FROM sales_order_items GROUP BY order_id) i USING (order_id)
        WHERE abs(o.subtotal - i.gross) > 0.05 OR abs(o.discount_amount - i.disc) > 0.05
           OR abs(o.total_amount - i.net) > 0.05 OR abs(o.total_amount - (o.subtotal - o.discount_amount)) > 0.05""")
    assert bad == 0


def test_every_order_has_at_least_one_line(conn):
    assert scalar(conn, """SELECT count(*) FROM sales_orders o
                           WHERE NOT EXISTS (SELECT 1 FROM sales_order_items i WHERE i.order_id = o.order_id)""") == 0


def test_gst_is_a_fraction_of_total(conn):
    assert scalar(conn, "SELECT count(*) FROM sales_orders WHERE gst_amount > total_amount") == 0


def test_orders_happen_after_customer_registration_and_store_opening(conn):
    assert scalar(conn, """SELECT count(*) FROM sales_orders o JOIN customers c USING (customer_id)
                           WHERE o.order_date::date < c.registration_date""") == 0
    assert scalar(conn, """SELECT count(*) FROM sales_orders o JOIN stores s USING (store_id)
                           WHERE o.order_date::date < s.opened_date""") == 0


def test_order_employee_belongs_to_order_store(conn):
    assert scalar(conn, """SELECT count(*) FROM sales_orders o JOIN employees e USING (employee_id)
                           WHERE e.store_id <> o.store_id""") == 0


def test_online_orders_use_the_hub_and_have_no_employee(conn):
    assert scalar(conn, """SELECT count(*) FROM sales_orders o JOIN stores s USING (store_id)
                           WHERE (o.channel = 'ONLINE') <> (s.store_type = 'ONLINE_WAREHOUSE')""") == 0
    assert scalar(conn, "SELECT count(*) FROM sales_orders WHERE channel = 'ONLINE' AND employee_id IS NOT NULL") == 0


def test_promotions_only_applied_inside_their_window_to_eligible_products(conn):
    assert scalar(conn, """SELECT count(*) FROM sales_order_items i
                           JOIN sales_orders o USING (order_id) JOIN promotions p USING (promotion_id)
                           WHERE o.order_date::date NOT BETWEEN p.start_date AND p.end_date""") == 0
    assert scalar(conn, """SELECT count(*) FROM sales_order_items i
                           WHERE i.promotion_id IS NOT NULL AND NOT EXISTS (
                               SELECT 1 FROM product_promotions pp
                               WHERE pp.promotion_id = i.promotion_id AND pp.product_id = i.product_id)""") == 0


def test_price_snapshot_is_positive_margin_on_most_lines(conn):
    """Selling price net of GST should exceed cost on the vast majority of lines."""
    share = scalar(conn, """SELECT avg((i.unit_price / (1 + p.gst_rate / 100) > i.unit_cost)::int)
                            FROM sales_order_items i JOIN products p USING (product_id)""")
    assert share > 0.98


# ------------------------------------------------------------------ payments
def test_successful_payment_equals_order_total(conn):
    assert scalar(conn, """
        SELECT count(*) FROM sales_orders o
        JOIN (SELECT order_id, sum(amount) AS paid FROM payments WHERE payment_status = 'SUCCESS'
              GROUP BY order_id) p USING (order_id)
        WHERE abs(o.total_amount - p.paid) > 0.01""") == 0


def test_payment_status_is_consistent_with_order_status(conn):
    assert scalar(conn, """SELECT count(*) FROM payments p JOIN sales_orders o USING (order_id)
                           WHERE o.order_status = 'CANCELLED' AND p.payment_status <> 'REFUNDED'""") == 0
    assert scalar(conn, """SELECT count(*) FROM payments p JOIN sales_orders o USING (order_id)
                           WHERE o.order_status = 'COMPLETED' AND p.payment_status = 'REFUNDED'""") == 0


def test_cash_only_in_store(conn):
    assert scalar(conn, """SELECT count(*) FROM payments p JOIN sales_orders o USING (order_id)
                           WHERE p.payment_method = 'CASH' AND o.channel = 'ONLINE'""") == 0


# ------------------------------------------------------------------ returns
def test_returned_quantity_never_exceeds_sold_quantity(conn):
    assert scalar(conn, """SELECT count(*) FROM sales_order_items i
                           JOIN (SELECT order_item_id, sum(quantity) AS q FROM return_items GROUP BY order_item_id) r
                             USING (order_item_id)
                           WHERE r.q > i.quantity""") == 0


def test_returns_only_on_completed_orders_and_after_order_date(conn):
    assert scalar(conn, """SELECT count(*) FROM returns r JOIN sales_orders o USING (order_id)
                           WHERE o.order_status <> 'COMPLETED' OR r.return_date <= o.order_date""") == 0


def test_return_header_refund_equals_sum_of_items(conn):
    assert scalar(conn, """SELECT count(*) FROM returns r
                           JOIN (SELECT return_id, sum(refund_amount) AS s FROM return_items GROUP BY return_id) i
                             USING (return_id)
                           WHERE abs(r.refund_amount - i.s) > 0.05""") == 0


def test_return_items_belong_to_the_returns_order(conn):
    assert scalar(conn, """SELECT count(*) FROM return_items ri
                           JOIN returns r USING (return_id) JOIN sales_order_items i USING (order_item_id)
                           WHERE i.order_id <> r.order_id""") == 0


# ------------------------------------------------------------------ inventory
def test_ledger_never_goes_negative(conn):
    """Running balance per store+product (ordered by time) must never drop below zero."""
    assert scalar(conn, """
        SELECT count(*) FROM (
            SELECT sum(quantity_change) OVER (PARTITION BY store_id, product_id
                                              ORDER BY transaction_date, transaction_id) AS running
            FROM inventory_transactions) t
        WHERE running < 0""") == 0


def test_ledger_reconciles_to_stock_except_planted_mismatches(conn):
    """~1.2% of inventory rows were deliberately altered; everything else must reconcile exactly."""
    total, mismatched = conn.execute(text("""
        SELECT count(*), count(*) FILTER (WHERE i.quantity_on_hand <> COALESCE(l.qty, 0))
        FROM inventory i
        LEFT JOIN (SELECT store_id, product_id, sum(quantity_change) AS qty
                   FROM inventory_transactions GROUP BY 1, 2) l USING (store_id, product_id)""")).one()
    assert 0.005 <= mismatched / total <= 0.02, f"{mismatched}/{total}"


def test_ledger_rows_all_have_an_inventory_row(conn):
    assert scalar(conn, """SELECT count(*) FROM inventory_transactions t
                           LEFT JOIN inventory i USING (store_id, product_id) WHERE i.inventory_id IS NULL""") == 0


def test_sale_ledger_matches_completed_order_lines(conn):
    lines, sold = conn.execute(text("""
        SELECT (SELECT sum(quantity) FROM sales_order_items i JOIN sales_orders o USING (order_id)
                WHERE o.order_status = 'COMPLETED'),
               (SELECT -sum(quantity_change) FROM inventory_transactions WHERE transaction_type = 'SALE')""")).one()
    assert lines == sold


def test_sale_ledger_references_real_orders(conn):
    assert scalar(conn, """SELECT count(*) FROM inventory_transactions t
                           LEFT JOIN sales_orders o ON o.order_id = t.reference_id
                           WHERE t.transaction_type = 'SALE' AND (t.reference_type <> 'SALES_ORDER' OR o.order_id IS NULL)""") == 0


def test_cancelled_orders_do_not_move_stock(conn):
    assert scalar(conn, """SELECT count(*) FROM inventory_transactions t
                           JOIN sales_orders o ON o.order_id = t.reference_id
                           WHERE t.transaction_type = 'SALE' AND o.order_status = 'CANCELLED'""") == 0


def test_received_purchase_quantities_match_ledger(conn):
    received, ledger = conn.execute(text("""
        SELECT (SELECT sum(quantity_received) FROM purchase_items),
               (SELECT sum(quantity_change) FROM inventory_transactions WHERE transaction_type = 'PURCHASE')""")).one()
    assert received == ledger


def test_reserved_never_exceeds_on_hand(conn):
    assert scalar(conn, "SELECT count(*) FROM inventory WHERE reserved_quantity > quantity_on_hand") == 0


# ------------------------------------------------------------------ purchases
def test_purchase_total_equals_sum_of_items(conn):
    assert scalar(conn, """SELECT count(*) FROM purchases p
                           JOIN (SELECT purchase_id, sum(quantity_ordered * unit_cost) AS s FROM purchase_items
                                 GROUP BY purchase_id) i USING (purchase_id)
                           WHERE abs(p.total_amount - i.s) > 0.05""") == 0


def test_purchase_status_matches_received_date(conn):
    assert scalar(conn, """SELECT count(*) FROM purchases
                           WHERE (status = 'RECEIVED') <> (received_date IS NOT NULL)""") == 0
    assert scalar(conn, """SELECT count(*) FROM purchase_items i JOIN purchases p USING (purchase_id)
                           WHERE p.status = 'ORDERED' AND i.quantity_received <> 0""") == 0


# ------------------------------------------------------------------ planted data-quality scenarios
@pytest.mark.parametrize("name,sql", {
    "duplicate-like customers": """SELECT count(*) FROM (SELECT lower(email) FROM customers WHERE email IS NOT NULL
                                   GROUP BY 1 HAVING count(*) > 1) t""",
    "invalid e-mail format": "SELECT count(*) FROM customers WHERE email IS NOT NULL AND email !~ '^[^@\\s]+@[^@\\s]+\\.[a-z]{2,}$'",
    "NULL e-mail": "SELECT count(*) FROM customers WHERE email IS NULL",
    "invalid phone": "SELECT count(*) FROM customers WHERE phone IS NOT NULL AND regexp_replace(phone, '[^0-9]', '', 'g') !~ '^(91)?[6-9][0-9]{9}$'",
    "products without category": "SELECT count(*) FROM products WHERE category_id IS NULL",
    "products without supplier": "SELECT count(*) FROM products WHERE supplier_id IS NULL",
    "case-variant categories": """SELECT count(*) FROM (SELECT lower(category_name) FROM categories
                                  GROUP BY 1 HAVING count(*) > 1) t""",
    "duplicate-like products": """SELECT count(*) FROM (SELECT lower(trim(product_name)) FROM products
                                  GROUP BY 1 HAVING count(*) > 1) t""",
    "inactive products": "SELECT count(*) FROM products WHERE NOT is_active",
    "cancelled orders": "SELECT count(*) FROM sales_orders WHERE order_status = 'CANCELLED'",
    "completed orders without payment": """SELECT count(*) FROM sales_orders o WHERE order_status = 'COMPLETED'
                                            AND NOT EXISTS (SELECT 1 FROM payments p WHERE p.order_id = o.order_id)""",
    "unusually large quantities": "SELECT count(*) FROM sales_order_items WHERE quantity >= 25",
    "zero stock rows": "SELECT count(*) FROM inventory WHERE quantity_on_hand = 0",
    "products never sold": """SELECT count(*) FROM products p WHERE NOT EXISTS (
                               SELECT 1 FROM sales_order_items i WHERE i.product_id = p.product_id)""",
    "implausible birth dates": "SELECT count(*) FROM customers WHERE date_of_birth < '1920-01-01' OR date_of_birth > current_date",
    "suppliers missing contact info": "SELECT count(*) FROM suppliers WHERE contact_email IS NULL OR contact_phone IS NULL OR gstin IS NULL",
}.items(), ids=lambda v: v if isinstance(v, str) and len(v) < 40 else None)
def test_planted_quality_issue_is_present(conn, name, sql):
    assert scalar(conn, sql) > 0, f"expected the '{name}' scenario to exist in the data"

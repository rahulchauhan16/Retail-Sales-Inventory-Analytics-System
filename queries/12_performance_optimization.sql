-- =============================================================================
-- 12_performance_optimization.sql : EXPLAIN ANALYZE workload used to judge the indexes in database/indexes.sql
--
-- HOW TO USE
--   * Run any statement here in psql / DBeaver to see the plan. EXPLAIN ANALYZE really EXECUTES the query.
--   * scripts/benchmark_indexes.py runs every statement in this file twice - with the indexes dropped, then created -
--     and writes the MEASURED numbers to docs/benchmark_results.md. No number in the docs is typed by hand.
--
-- HOW TO READ A PLAN
--   Seq Scan          reads the whole table                 Index Scan / Index Only Scan   walks an index
--   Bitmap Index Scan finds many matching rows via an index, then fetches the table pages once
--   'Execution Time'  is measured on THIS machine; compare before vs after on the same machine, not against other machines.
--   An index is not always used: for queries that read most of a table the planner correctly prefers a Seq Scan (see Q511).
-- =============================================================================

-- Q501 | One customer's order history
-- Expectation: the filter matches ~10 of 57k rows, so an index on customer_id should replace a full scan.
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, order_date, total_amount FROM sales_orders
WHERE customer_id = 4104 AND order_status = 'COMPLETED' ORDER BY order_date;

-- Q502 | Revenue in one month (date range)
-- Expectation: a one-month range is ~3% of the table; a range index on order_date can help, but the planner decides.
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*), SUM(total_amount - gst_amount) FROM sales_orders
WHERE order_date >= TIMESTAMP '2025-10-01' AND order_date < TIMESTAMP '2025-11-01' AND order_status = 'COMPLETED';

-- Q503 | All sales lines of one product
-- Expectation: UNIQUE (order_id, product_id) cannot serve a product_id-only filter, so this needs idx_items_product.
EXPLAIN (ANALYZE, BUFFERS)
SELECT SUM(quantity), SUM(line_total) FROM sales_order_items WHERE product_id = 13;

-- Q504 | Correlated subquery per row (from Q108)
-- Expectation: the subquery runs once per outer row; without an index on customer_id each run scans sales_orders.
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.order_id, o.total_amount FROM sales_orders o
WHERE o.order_status = 'COMPLETED' AND o.total_amount > 100000
  AND o.total_amount > 3 * (SELECT AVG(o2.total_amount) FROM sales_orders o2
                            WHERE o2.customer_id = o.customer_id AND o2.order_status = 'COMPLETED');

-- Q505 | Returned quantity per product (join on return_items.order_item_id)
-- Expectation: return_items has a composite unique key that starts with return_id, so a join on order_item_id benefits from idx_return_items_order_item.
EXPLAIN (ANALYZE, BUFFERS)
SELECT i.product_id, SUM(ri.quantity) FROM sales_order_items i
JOIN return_items ri ON ri.order_item_id = i.order_item_id WHERE i.product_id = 13 GROUP BY i.product_id;

-- Q506 | Ledger for one store + product in date order
-- Expectation: composite index (store_id, product_id, transaction_date) satisfies both the filter and the ORDER BY.
EXPLAIN (ANALYZE, BUFFERS)
SELECT transaction_date, transaction_type, quantity_change FROM inventory_transactions
WHERE store_id = 3 AND product_id = 13 ORDER BY transaction_date;

-- Q507 | Completed orders with no payment (anti-join, from DQ21)
-- Expectation: NOT EXISTS probes payments by order_id for each order; idx_payments_order makes each probe cheap, but the planner may
--              still choose a hash anti-join that reads both tables once. Check which one it picks.
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*) FROM sales_orders o
WHERE o.order_status = 'COMPLETED' AND NOT EXISTS (SELECT 1 FROM payments p WHERE p.order_id = o.order_id);

-- Q508 | Open purchase orders ordered by due date
-- Expectation: only ~3 percent of POs are open, so a PARTIAL index containing just those rows is tiny and fast.
EXPLAIN (ANALYZE, BUFFERS)
SELECT purchase_id, supplier_id, expected_date FROM purchases WHERE status = 'ORDERED' ORDER BY expected_date;

-- Q509 | Case-insensitive e-mail lookup
-- Expectation: WHERE LOWER(email) = ... cannot use a plain index on email; an expression index on LOWER(email) can.
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, email FROM customers WHERE LOWER(email) = 'abhishek.patil187@example.com';

-- Q510 | One store, one quarter
-- Expectation: composite (store_id, order_date) serves both conditions.
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*), SUM(total_amount) FROM sales_orders
WHERE store_id = 3 AND order_date >= TIMESTAMP '2025-07-01' AND order_date < TIMESTAMP '2025-10-01';

-- Q511 | Full-table aggregation (monthly revenue) - an index should NOT help
-- Expectation: every completed order is read, so a Seq Scan is the right plan. This proves indexes are not a cure-all.
EXPLAIN (ANALYZE, BUFFERS)
SELECT DATE_TRUNC('month', order_date) AS month, SUM(total_amount - gst_amount) FROM sales_orders
WHERE order_status = 'COMPLETED' GROUP BY 1 ORDER BY 1;

-- Q512 | Stock of one product across stores
-- Expectation: UNIQUE (store_id, product_id) cannot serve a product_id-only filter; idx_inventory_product should.
EXPLAIN (ANALYZE, BUFFERS)
SELECT SUM(quantity_on_hand) FROM inventory WHERE product_id = 13;

-- Q513 | Products of one category
-- Expectation: none - products has only 636 rows, so this is deliberately NOT indexed. The workload keeps it to show a scan of a tiny table is already fast.
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, product_name FROM products WHERE category_id = 1;

-- Q514 | Returns of one specific order
-- Expectation: a selective lookup (about 1 of 3,000 rows) is where idx_returns_order helps; a whole-table semi-join would not need it.
EXPLAIN (ANALYZE, BUFFERS)
SELECT return_id, return_date, refund_amount FROM returns WHERE order_id = 20000;

-- Q515 | Payments of one specific order
-- Expectation: a selective lookup by order_id (order detail screens, refund checks) is what idx_payments_order is for.
EXPLAIN (ANALYZE, BUFFERS)
SELECT payment_id, payment_method, amount, payment_status FROM payments WHERE order_id = 20000;

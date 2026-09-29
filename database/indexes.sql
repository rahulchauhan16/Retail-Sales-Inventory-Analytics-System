-- =============================================================================
-- Secondary indexes. Primary keys and UNIQUE constraints already create indexes, so those are NOT repeated here:
--   sales_order_items(order_id, product_id)   inventory(store_id, product_id)   purchase_items(purchase_id, product_id)
--   return_items(return_id, order_item_id)    product_promotions(promotion_id, product_id)
-- A composite index only helps queries that filter on its LEFT-most columns, which is why product_id lookups on those
-- tables still need their own index below.
--
-- Rules followed:
--   * index foreign-key columns that are joined or filtered on large tables (a FK does NOT create an index in PostgreSQL)
--   * index date columns that are used for range filters
--   * skip tiny tables (stores, employees, categories, suppliers): a sequential scan is already cheap
--   * every index has a cost (disk space + slower INSERT/UPDATE), so each one below is tested in
--     queries/12_performance_optimization.sql and the results are in docs/10_performance_optimization.md
-- Re-runnable: uses IF NOT EXISTS.
-- =============================================================================

-- Orders: look up one customer's history; filter by date range (also serves store + date queries, see note at the end)
CREATE INDEX IF NOT EXISTS idx_orders_customer         ON sales_orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_date             ON sales_orders (order_date);

-- Order lines: the UNIQUE (order_id, product_id) covers joins from orders; product lookups need their own index
CREATE INDEX IF NOT EXISTS idx_items_product           ON sales_order_items (product_id);

-- Payments and returns: joined to orders through order_id
CREATE INDEX IF NOT EXISTS idx_payments_order          ON payments (order_id);
CREATE INDEX IF NOT EXISTS idx_returns_order           ON returns (order_id);
CREATE INDEX IF NOT EXISTS idx_return_items_order_item ON return_items (order_item_id);

-- Inventory: the UNIQUE (store_id, product_id) covers store lookups; product lookups need their own index
CREATE INDEX IF NOT EXISTS idx_inventory_product       ON inventory (product_id);

-- Ledger: reconciliation and running balances always work per store + product in date order
CREATE INDEX IF NOT EXISTS idx_invtxn_store_product_date ON inventory_transactions (store_id, product_id, transaction_date);

-- Procurement: partial index, only the small set of open POs is indexed
CREATE INDEX IF NOT EXISTS idx_purchases_open_expected ON purchases (expected_date) WHERE status = 'ORDERED';

-- Customers: case-insensitive e-mail lookup and duplicate detection (expression index)
CREATE INDEX IF NOT EXISTS idx_customers_email_lower   ON customers (LOWER(email));

ANALYZE;

-- NOT indexed on purpose (kept out because a measurement or the table size does not justify the write cost):
--   products(category_id), products(supplier_id)   636 rows: a sequential scan takes ~0.1 ms (tested as Q513)
--   purchases(supplier_id), purchase_items(product_id), product_promotions(product_id)
--                                                   only used by whole-table aggregations, which scan everything anyway
--   sales_orders(store_id, order_date)              tested: with idx_orders_date present the planner ignores it, and alone it saves only ~0.4 ms
--                                                   on a 0.7 ms query - not worth 1.8 MB and slower inserts (a redundant index)

-- =============================================================================
-- Analytical views: the single, documented definition of every KPI.
-- Python (python/*.py) and Power BI read these views instead of re-implementing SQL logic.
--
-- Conventions (same as the queries/ folder):
--   * Sales = COMPLETED orders only.  Prices are GST-inclusive.
--   * net_revenue = line_total / (1 + gst_rate / 100)      gross_profit = net_revenue - quantity * unit_cost
--   * "as of" date = last order date in the data (vw_asof).
--   * Health classes, RFM cut-offs, ABC splits etc. are PROJECT ASSUMPTIONS (see docs/06 and docs/07).
-- Re-runnable: drops and recreates everything in dependency order.
-- =============================================================================

DROP VIEW IF EXISTS vw_return_analysis        CASCADE;
DROP VIEW IF EXISTS vw_supplier_performance   CASCADE;
DROP VIEW IF EXISTS vw_category_performance   CASCADE;
DROP VIEW IF EXISTS vw_store_performance      CASCADE;
DROP VIEW IF EXISTS vw_inventory_health       CASCADE;
DROP MATERIALIZED VIEW IF EXISTS vw_customer_summary CASCADE;
DROP VIEW IF EXISTS vw_product_performance    CASCADE;
DROP VIEW IF EXISTS vw_monthly_sales          CASCADE;
DROP VIEW IF EXISTS vw_orders                 CASCADE;
DROP VIEW IF EXISTS vw_sales_lines            CASCADE;
DROP VIEW IF EXISTS vw_category_canonical     CASCADE;
DROP VIEW IF EXISTS vw_asof                   CASCADE;

-- ---- helper: data window ----------------------------------------------------
CREATE VIEW vw_asof AS
SELECT MIN(order_date)::date AS first_order_date, MAX(order_date)::date AS asof_date FROM sales_orders;

-- ---- helper: canonical category (merges names that differ only by capitalisation) ----
-- 'FOOTWEAR' and 'Footwear' share the smallest category_id among names equal ignoring case.
CREATE VIEW vw_category_canonical AS
SELECT c.category_id,
       MIN(c.category_id) OVER (PARTITION BY LOWER(c.category_name))                          AS canonical_id,
       FIRST_VALUE(c.category_name) OVER (PARTITION BY LOWER(c.category_name) ORDER BY c.category_id) AS canonical_name,
       parent.category_name                                                                   AS parent_category
FROM categories c
LEFT JOIN categories parent ON parent.category_id = c.parent_category_id;

-- ---- fact: one row per sold order line (completed orders only) ----------------
CREATE VIEW vw_sales_lines AS
SELECT o.order_id, i.order_item_id, o.order_date, o.order_date::date AS order_day,
       DATE_TRUNC('month', o.order_date)::date AS order_month, EXTRACT(YEAR FROM o.order_date)::int AS order_year,
       o.store_id, o.customer_id, o.channel, o.employee_id,
       i.product_id, COALESCE(cc.canonical_id, 0) AS category_id, COALESCE(cc.canonical_name, '(no category)') AS category_name,
       i.promotion_id, i.quantity, i.unit_price, i.unit_cost, i.discount_amount,
       i.quantity * i.unit_price                                    AS gross_amount,
       i.line_total                                                 AS line_total_incl_gst,
       i.line_total / (1 + p.gst_rate / 100.0)                      AS net_revenue,
       i.quantity * i.unit_cost                                     AS cogs,
       i.line_total / (1 + p.gst_rate / 100.0) - i.quantity * i.unit_cost AS gross_profit
FROM sales_order_items i
JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
JOIN products p     ON p.product_id = i.product_id
LEFT JOIN vw_category_canonical cc ON cc.category_id = p.category_id;

-- ---- fact: one row per order, ALL statuses (for order counts and cancellation rate) ----
CREATE VIEW vw_orders AS
SELECT o.order_id, o.order_number, o.order_date, o.order_date::date AS order_day,
       DATE_TRUNC('month', o.order_date)::date AS order_month, o.customer_id, o.store_id, s.store_name, o.channel,
       o.order_status, o.subtotal, o.discount_amount, o.gst_amount, o.total_amount,
       o.total_amount - o.gst_amount AS net_amount,
       EXISTS (SELECT 1 FROM returns r WHERE r.order_id = o.order_id) AS has_return,
       COALESCE(sg.segment_name, '(no segment)') AS customer_segment
FROM sales_orders o
JOIN stores s ON s.store_id = o.store_id
JOIN customers c ON c.customer_id = o.customer_id
LEFT JOIN customer_segments sg ON sg.segment_id = c.segment_id;

-- ---- 1. monthly sales -------------------------------------------------------------
CREATE VIEW vw_monthly_sales AS
WITH months AS (
    SELECT DISTINCT year_month, DATE_TRUNC('month', date_key)::date AS month
    FROM dim_date, vw_asof WHERE date_key BETWEEN DATE_TRUNC('month', first_order_date) AND asof_date
), ord AS (
    SELECT order_month AS month, COUNT(*) AS orders, COUNT(DISTINCT customer_id) AS active_customers,
           SUM(total_amount) AS gross_sales_incl_gst, SUM(gst_amount) AS gst_collected, SUM(net_amount) AS net_revenue_orders,
           COUNT(*) FILTER (WHERE channel = 'ONLINE') AS online_orders
    FROM vw_orders WHERE order_status = 'COMPLETED' GROUP BY order_month
), cancelled AS (
    SELECT order_month AS month, COUNT(*) AS cancelled_orders FROM vw_orders WHERE order_status = 'CANCELLED' GROUP BY order_month
), lines AS (
    SELECT order_month AS month, SUM(quantity) AS units_sold, SUM(net_revenue) AS net_revenue, SUM(cogs) AS cogs,
           SUM(gross_profit) AS gross_profit, SUM(discount_amount) AS discounts
    FROM vw_sales_lines GROUP BY order_month
), refunds AS (
    SELECT DATE_TRUNC('month', r.return_date)::date AS month, SUM(ri.refund_amount / (1 + p.gst_rate / 100.0)) AS refunded_net
    FROM returns r JOIN return_items ri ON ri.return_id = r.return_id
    JOIN sales_order_items i ON i.order_item_id = ri.order_item_id JOIN products p ON p.product_id = i.product_id
    GROUP BY 1
)
SELECT m.month, EXTRACT(YEAR FROM m.month)::int AS year, EXTRACT(MONTH FROM m.month)::int AS month_number, m.year_month,
       COALESCE(o.orders, 0) AS orders, COALESCE(c.cancelled_orders, 0) AS cancelled_orders, COALESCE(o.active_customers, 0) AS active_customers,
       COALESCE(l.units_sold, 0) AS units_sold, ROUND(COALESCE(o.gross_sales_incl_gst, 0), 2) AS gross_sales_incl_gst,
       ROUND(COALESCE(l.net_revenue, 0), 2) AS net_revenue, ROUND(COALESCE(l.cogs, 0), 2) AS cogs,
       ROUND(COALESCE(l.gross_profit, 0), 2) AS gross_profit,
       ROUND(100.0 * l.gross_profit / NULLIF(l.net_revenue, 0), 2) AS gross_margin_pct,
       ROUND(o.gross_sales_incl_gst / NULLIF(o.orders, 0), 2) AS avg_order_value,
       ROUND(COALESCE(l.discounts, 0), 2) AS discounts, ROUND(COALESCE(r.refunded_net, 0), 2) AS refunded_net,
       COALESCE(o.online_orders, 0) AS online_orders
FROM months m
LEFT JOIN ord o ON o.month = m.month LEFT JOIN cancelled c ON c.month = m.month
LEFT JOIN lines l ON l.month = m.month LEFT JOIN refunds r ON r.month = m.month;

-- ---- 2. product performance (one row per product, including never-sold products) ----
CREATE VIEW vw_product_performance AS
WITH asof AS (SELECT asof_date AS d FROM vw_asof),
sales AS (
    SELECT s.product_id, COUNT(DISTINCT s.order_id) AS orders, SUM(s.quantity) AS units_sold, SUM(s.net_revenue) AS net_revenue,
           SUM(s.gross_profit) AS gross_profit, MIN(s.order_day) AS first_sale_date, MAX(s.order_day) AS last_sale_date,
           SUM(s.quantity) FILTER (WHERE s.order_day > asof.d - 90) AS units_90d,
           SUM(s.net_revenue) FILTER (WHERE s.order_day > asof.d - 365) AS revenue_12m,
           SUM(s.cogs) FILTER (WHERE s.order_day > asof.d - 365) AS cogs_12m
    FROM vw_sales_lines s CROSS JOIN asof GROUP BY s.product_id
), ret AS (
    SELECT i.product_id, SUM(ri.quantity) AS units_returned
    FROM return_items ri JOIN sales_order_items i ON i.order_item_id = ri.order_item_id GROUP BY i.product_id
), stock AS (
    SELECT inv.product_id, SUM(inv.quantity_on_hand) AS units_in_stock, SUM(inv.quantity_on_hand * p.unit_cost) AS inventory_value
    FROM inventory inv JOIN products p ON p.product_id = inv.product_id GROUP BY inv.product_id
), base AS (
    SELECT p.product_id, p.sku, p.product_name, COALESCE(p.brand, '(brand missing)') AS brand,
           COALESCE(cc.canonical_name, '(no category)') AS category, COALESCE(su.supplier_name, '(supplier missing)') AS supplier,
           p.is_active, p.unit_price, p.unit_cost, p.launch_date,
           COALESCE(s.orders, 0) AS orders, COALESCE(s.units_sold, 0) AS units_sold, COALESCE(s.net_revenue, 0) AS net_revenue,
           COALESCE(s.gross_profit, 0) AS gross_profit, s.first_sale_date, s.last_sale_date,
           COALESCE(s.units_90d, 0) AS units_90d, COALESCE(s.revenue_12m, 0) AS revenue_12m, COALESCE(s.cogs_12m, 0) AS cogs_12m,
           COALESCE(r.units_returned, 0) AS units_returned,
           COALESCE(st.units_in_stock, 0) AS units_in_stock, COALESCE(st.inventory_value, 0) AS inventory_value
    FROM products p
    LEFT JOIN vw_category_canonical cc ON cc.category_id = p.category_id
    LEFT JOIN suppliers su ON su.supplier_id = p.supplier_id
    LEFT JOIN sales s ON s.product_id = p.product_id
    LEFT JOIN ret r ON r.product_id = p.product_id
    LEFT JOIN stock st ON st.product_id = p.product_id
), scored AS (
    SELECT b.*,
           100.0 * SUM(net_revenue) OVER (ORDER BY net_revenue DESC, product_id) / NULLIF(SUM(net_revenue) OVER (), 0) AS cumulative_revenue_pct,
           100.0 * net_revenue / NULLIF(SUM(net_revenue) OVER (), 0) AS revenue_share_pct,
           CASE WHEN units_in_stock > 0 THEN NTILE(5) OVER (PARTITION BY (units_in_stock > 0) ORDER BY revenue_12m) END AS revenue_quintile
    FROM base b
)
SELECT product_id, sku, product_name, brand, category, supplier, is_active, unit_price, unit_cost, launch_date,
       orders, units_sold, ROUND(net_revenue, 2) AS net_revenue, ROUND(gross_profit, 2) AS gross_profit,
       ROUND(100.0 * gross_profit / NULLIF(net_revenue, 0), 2) AS margin_pct,
       units_returned, ROUND(100.0 * units_returned / NULLIF(units_sold, 0), 2) AS return_rate_pct,
       first_sale_date, last_sale_date, units_90d, ROUND(units_90d / 90.0, 3) AS sales_velocity_per_day,
       units_in_stock, ROUND(inventory_value, 2) AS inventory_value,
       ROUND(units_in_stock / NULLIF(units_90d / 90.0, 0), 1) AS days_of_cover,
       ROUND(cogs_12m / NULLIF(inventory_value, 0), 2) AS inventory_turnover_12m,
       RANK() OVER (ORDER BY net_revenue DESC) AS revenue_rank,
       ROUND(revenue_share_pct, 3) AS revenue_share_pct, ROUND(cumulative_revenue_pct, 2) AS cumulative_revenue_pct,
       CASE WHEN net_revenue = 0 THEN 'No sales'
            WHEN cumulative_revenue_pct - revenue_share_pct < 80 THEN 'A' WHEN cumulative_revenue_pct - revenue_share_pct < 95 THEN 'B'
            ELSE 'C' END AS abc_class,
       CASE WHEN units_in_stock = 0 THEN NULL
            WHEN revenue_quintile = 5 AND units_90d > 0 AND units_in_stock / (units_90d / 90.0) < 30 THEN 'High Revenue / Low Stock'
            WHEN revenue_quintile = 5 AND units_90d > 0 AND units_in_stock / (units_90d / 90.0) BETWEEN 30 AND 180 THEN 'High Revenue / Healthy Stock'
            WHEN revenue_quintile <= 2 AND (units_90d = 0 OR units_in_stock / (units_90d / 90.0) > 180) THEN 'Low Revenue / High Stock'
            WHEN revenue_quintile <= 2 AND units_90d > 0 AND units_in_stock / (units_90d / 90.0) < 30 THEN 'Low Revenue / Low Stock'
            ELSE 'Other' END AS product_class
FROM scored;

-- ---- 3. customer summary (MATERIALIZED: RFM over every customer is the heaviest view) ----
-- Refresh after loading new data:  REFRESH MATERIALIZED VIEW CONCURRENTLY vw_customer_summary;
CREATE MATERIALIZED VIEW vw_customer_summary AS
WITH asof AS (SELECT asof_date AS d FROM vw_asof),
agg AS (
    SELECT o.customer_id, COUNT(*) AS orders, SUM(o.total_amount - o.gst_amount) AS net_revenue, AVG(o.total_amount) AS avg_order_value,
           MIN(o.order_date)::date AS first_order_date, MAX(o.order_date)::date AS last_order_date
    FROM sales_orders o WHERE o.order_status = 'COMPLETED' GROUP BY o.customer_id
), profit AS (
    SELECT customer_id, SUM(gross_profit) AS gross_profit FROM vw_sales_lines GROUP BY customer_id
), scored AS (
    SELECT c.customer_id, a.orders, a.net_revenue, a.avg_order_value, a.first_order_date, a.last_order_date,
           (SELECT d FROM asof) - a.last_order_date AS recency_days,
           CASE WHEN a.orders IS NULL THEN NULL
                WHEN (SELECT d FROM asof) - a.last_order_date <= 30 THEN 5 WHEN (SELECT d FROM asof) - a.last_order_date <= 90 THEN 4
                WHEN (SELECT d FROM asof) - a.last_order_date <= 180 THEN 3 WHEN (SELECT d FROM asof) - a.last_order_date <= 365 THEN 2 ELSE 1 END AS r_score,
           CASE WHEN a.orders IS NULL THEN NULL WHEN a.orders >= 13 THEN 5 WHEN a.orders >= 7 THEN 4 WHEN a.orders >= 4 THEN 3
                WHEN a.orders >= 2 THEN 2 ELSE 1 END AS f_score
    FROM customers c LEFT JOIN agg a ON a.customer_id = c.customer_id
), monetary AS (
    SELECT customer_id, NTILE(5) OVER (ORDER BY net_revenue) AS m_score FROM agg
)
SELECT c.customer_id, INITCAP(TRIM(c.first_name)) || ' ' || INITCAP(TRIM(COALESCE(c.last_name, ''))) AS customer_name,
       c.email, c.city, c.state, COALESCE(sg.segment_name, '(no segment)') AS segment, c.registration_date, c.is_active,
       COALESCE(s.orders, 0) AS orders, ROUND(COALESCE(s.net_revenue, 0), 2) AS net_revenue,
       ROUND(COALESCE(pf.gross_profit, 0), 2) AS gross_profit, ROUND(s.avg_order_value, 2) AS avg_order_value,
       s.first_order_date, s.last_order_date, DATE_TRUNC('month', s.first_order_date)::date AS cohort_month,
       s.recency_days, s.r_score, s.f_score, m.m_score,
       COALESCE(s.orders, 0) >= 2 AS is_repeat_customer,
       s.last_order_date - s.first_order_date AS active_span_days,
       CASE WHEN s.orders IS NULL THEN 'Never purchased' WHEN s.recency_days <= 90 THEN 'Active (last 90 days)'
            WHEN s.recency_days <= 365 THEN 'Inactive (91-365 days)' ELSE 'Lost (over 365 days)' END AS activity_status,
       CASE WHEN s.orders IS NULL THEN NULL
            WHEN s.r_score >= 4 AND s.f_score >= 4 THEN 'Champions' WHEN s.r_score >= 3 AND s.f_score >= 3 THEN 'Loyal Customers'
            WHEN s.r_score >= 3 AND s.f_score <= 2 THEN 'Potential Loyalists' WHEN s.r_score <= 2 AND s.f_score >= 3 THEN 'At Risk'
            ELSE 'Lost Customers' END AS rfm_segment
FROM customers c
LEFT JOIN customer_segments sg ON sg.segment_id = c.segment_id
LEFT JOIN scored s ON s.customer_id = c.customer_id
LEFT JOIN monetary m ON m.customer_id = c.customer_id
LEFT JOIN profit pf ON pf.customer_id = c.customer_id;
CREATE UNIQUE INDEX uq_vw_customer_summary ON vw_customer_summary (customer_id);

-- ---- 4. inventory health (one row per store + product) -----------------------------
-- Rules (first match wins): OUT_OF_STOCK, DEAD_STOCK (no sale at that store in 365 days), LOW_STOCK (<= reorder level),
-- OVERSTOCKED (> max level or > 180 days of cover), HEALTHY.
CREATE VIEW vw_inventory_health AS
WITH asof AS (SELECT asof_date AS d FROM vw_asof),
demand AS (
    SELECT s.store_id, s.product_id,
           SUM(s.quantity) FILTER (WHERE s.order_day > asof.d - 90)  AS units_90d,
           SUM(s.quantity) AS units_365d
    FROM vw_sales_lines s CROSS JOIN asof WHERE s.order_day > asof.d - 365 GROUP BY s.store_id, s.product_id
), inbound AS (
    SELECT pu.store_id, pi.product_id, SUM(pi.quantity_ordered) AS inbound_qty
    FROM purchase_items pi JOIN purchases pu ON pu.purchase_id = pi.purchase_id AND pu.status = 'ORDERED'
    GROUP BY pu.store_id, pi.product_id
)
SELECT inv.inventory_id, inv.store_id, st.store_name, inv.product_id, p.product_name, COALESCE(cc.canonical_name, '(no category)') AS category,
       COALESCE(su.supplier_name, '(supplier missing)') AS supplier,
       inv.quantity_on_hand, inv.reserved_quantity, inv.quantity_on_hand - inv.reserved_quantity AS available_quantity,
       inv.reorder_level, inv.max_stock_level, p.unit_cost, ROUND(inv.quantity_on_hand * p.unit_cost, 2) AS inventory_value,
       COALESCE(d.units_90d, 0) AS units_sold_90d, COALESCE(d.units_365d, 0) AS units_sold_365d,
       ROUND(COALESCE(d.units_90d, 0) / 90.0, 3) AS avg_daily_demand,
       ROUND(inv.quantity_on_hand / NULLIF(COALESCE(d.units_90d, 0) / 90.0, 0), 1) AS days_of_cover,
       inv.last_restocked_date, asof.d - inv.last_restocked_date AS days_since_restock,
       COALESCE(ib.inbound_qty, 0) AS inbound_quantity,
       GREATEST(inv.max_stock_level - inv.quantity_on_hand - COALESCE(ib.inbound_qty, 0), 0) AS suggested_order_qty,
       CASE WHEN inv.quantity_on_hand = 0 THEN 'OUT_OF_STOCK'
            WHEN COALESCE(d.units_365d, 0) = 0 THEN 'DEAD_STOCK'
            WHEN inv.quantity_on_hand <= inv.reorder_level THEN 'LOW_STOCK'
            WHEN inv.quantity_on_hand > inv.max_stock_level
              OR inv.quantity_on_hand / (COALESCE(d.units_90d, 0) / 90.0 + 0.000001) > 180 THEN 'OVERSTOCKED'
            ELSE 'HEALTHY' END AS health_status
FROM inventory inv
CROSS JOIN asof
JOIN stores st ON st.store_id = inv.store_id
JOIN products p ON p.product_id = inv.product_id
LEFT JOIN vw_category_canonical cc ON cc.category_id = p.category_id
LEFT JOIN suppliers su ON su.supplier_id = p.supplier_id
LEFT JOIN demand d ON d.store_id = inv.store_id AND d.product_id = inv.product_id
LEFT JOIN inbound ib ON ib.store_id = inv.store_id AND ib.product_id = inv.product_id;

-- ---- 5. store performance -------------------------------------------------------------
CREATE VIEW vw_store_performance AS
WITH bounds AS (SELECT first_order_date AS start_d, asof_date AS end_d FROM vw_asof),
o AS (
    SELECT store_id, COUNT(*) AS orders, COUNT(DISTINCT customer_id) AS customers, SUM(net_amount) AS net_revenue,
           AVG(total_amount) AS avg_order_value,
           SUM(net_amount) FILTER (WHERE EXTRACT(YEAR FROM order_day) = 2024) AS rev_2024,
           SUM(net_amount) FILTER (WHERE EXTRACT(YEAR FROM order_day) = 2025) AS rev_2025,
           COUNT(*) FILTER (WHERE has_return) AS returned_orders
    FROM vw_orders WHERE order_status = 'COMPLETED' GROUP BY store_id
), u AS (SELECT store_id, SUM(quantity) AS units, SUM(gross_profit) AS gross_profit FROM vw_sales_lines GROUP BY store_id),
rp AS (
    SELECT store_id, COUNT(*) FILTER (WHERE n >= 2) AS repeat_customers, COUNT(*) AS customers
    FROM (SELECT store_id, customer_id, COUNT(*) AS n FROM vw_orders WHERE order_status = 'COMPLETED' GROUP BY 1, 2) t GROUP BY store_id
), iv AS (
    SELECT inv.store_id, SUM(inv.quantity_on_hand * p.unit_cost) AS inventory_value
    FROM inventory inv JOIN products p ON p.product_id = inv.product_id GROUP BY inv.store_id
), calc AS (
    SELECT s.store_id, s.store_code, s.store_name, s.store_type, s.city, s.state, s.region, s.opened_date,
           o.orders, u.units, o.customers, o.net_revenue, u.gross_profit, o.avg_order_value,
           100.0 * rp.repeat_customers / rp.customers AS repeat_customer_rate_pct,
           100.0 * o.returned_orders / o.orders AS return_rate_pct, iv.inventory_value,
           GREATEST((b.end_d - GREATEST(s.opened_date, b.start_d)) / 30.44, 1) AS months_open,
           100.0 * (o.rev_2025 / NULLIF(o.rev_2024, 0) - 1) AS growth_2025_pct
    FROM stores s CROSS JOIN bounds b JOIN o ON o.store_id = s.store_id JOIN u ON u.store_id = s.store_id
    JOIN rp ON rp.store_id = s.store_id JOIN iv ON iv.store_id = s.store_id
)
SELECT store_id, store_code, store_name, store_type, city, state, region, opened_date, orders, units, customers,
       ROUND(net_revenue, 2) AS net_revenue, ROUND(gross_profit, 2) AS gross_profit, ROUND(avg_order_value, 2) AS avg_order_value,
       ROUND(repeat_customer_rate_pct, 2) AS repeat_customer_rate_pct, ROUND(return_rate_pct, 2) AS return_rate_pct,
       ROUND(inventory_value, 2) AS inventory_value, ROUND(months_open, 1) AS months_open,
       ROUND(net_revenue / months_open, 2) AS revenue_per_month,
       ROUND(100.0 * (net_revenue / months_open) / NULLIF(AVG(net_revenue / months_open) FILTER (WHERE store_type = 'STORE') OVER (), 0), 1) AS revenue_per_month_index_vs_stores,
       CASE WHEN opened_date < DATE '2024-01-01' THEN ROUND(growth_2025_pct, 2) END AS growth_2025_vs_2024_pct,
       RANK() OVER (ORDER BY net_revenue DESC) AS revenue_rank,
       ROUND(100.0 * net_revenue / SUM(net_revenue) OVER (), 2) AS revenue_share_pct
FROM calc;

-- ---- 6. category performance (category x year) -----------------------------------------
CREATE VIEW vw_category_performance AS
WITH s AS (
    SELECT category_id, category_name, order_year, SUM(quantity) AS units_sold, SUM(net_revenue) AS net_revenue,
           SUM(gross_profit) AS gross_profit, COUNT(DISTINCT order_id) AS orders
    FROM vw_sales_lines GROUP BY category_id, category_name, order_year
), r AS (
    SELECT l.category_id, l.order_year, SUM(ri.quantity) AS units_returned
    FROM return_items ri JOIN vw_sales_lines l ON l.order_item_id = ri.order_item_id GROUP BY l.category_id, l.order_year
)
SELECT s.category_id, s.category_name, s.order_year AS year, s.orders, s.units_sold, ROUND(s.net_revenue, 2) AS net_revenue,
       ROUND(s.gross_profit, 2) AS gross_profit, ROUND(100.0 * s.gross_profit / NULLIF(s.net_revenue, 0), 2) AS margin_pct,
       COALESCE(r.units_returned, 0) AS units_returned, ROUND(100.0 * COALESCE(r.units_returned, 0) / NULLIF(s.units_sold, 0), 2) AS unit_return_rate_pct,
       ROUND(100.0 * (s.net_revenue / NULLIF(LAG(s.net_revenue) OVER (PARTITION BY s.category_id ORDER BY s.order_year), 0) - 1), 2) AS yoy_growth_pct,
       ROUND(100.0 * s.net_revenue / SUM(s.net_revenue) OVER (PARTITION BY s.order_year), 2) AS share_of_year_revenue_pct
FROM s LEFT JOIN r ON r.category_id = s.category_id AND r.order_year = s.order_year;

-- ---- 7. supplier performance ---------------------------------------------------------------
CREATE VIEW vw_supplier_performance AS
WITH asof AS (SELECT asof_date AS d FROM vw_asof),
po AS (
    SELECT pu.supplier_id, COUNT(*) AS total_pos, COUNT(*) FILTER (WHERE pu.status = 'RECEIVED') AS received_pos,
           COUNT(*) FILTER (WHERE pu.status = 'RECEIVED' AND pu.received_date <= pu.expected_date) AS on_time_pos,
           AVG(pu.received_date - pu.expected_date) FILTER (WHERE pu.status = 'RECEIVED') AS avg_days_vs_expected,
           AVG(pu.received_date - pu.order_date) FILTER (WHERE pu.status = 'RECEIVED') AS actual_lead_days,
           COUNT(*) FILTER (WHERE pu.status = 'ORDERED') AS open_pos,
           COUNT(*) FILTER (WHERE pu.status = 'ORDERED' AND pu.expected_date < (SELECT d FROM asof)) AS overdue_pos,
           SUM(pu.total_amount) AS spend
    FROM purchases pu GROUP BY pu.supplier_id
), fill AS (
    SELECT pu.supplier_id, SUM(pi.quantity_ordered) AS ordered, SUM(pi.quantity_received) AS received
    FROM purchase_items pi JOIN purchases pu ON pu.purchase_id = pi.purchase_id AND pu.status = 'RECEIVED' GROUP BY pu.supplier_id
), prod AS (
    SELECT p.supplier_id, COUNT(DISTINCT p.product_id) AS products, SUM(pp.net_revenue) AS net_revenue
    FROM products p JOIN vw_product_performance pp ON pp.product_id = p.product_id WHERE p.supplier_id IS NOT NULL GROUP BY p.supplier_id
)
SELECT su.supplier_id, su.supplier_name, su.city, su.state, su.is_active, su.lead_time_days AS promised_lead_days,
       COALESCE(prod.products, 0) AS products, ROUND(COALESCE(prod.net_revenue, 0), 2) AS net_revenue_of_products,
       COALESCE(po.total_pos, 0) AS total_pos, COALESCE(po.received_pos, 0) AS received_pos, ROUND(COALESCE(po.spend, 0), 2) AS purchase_spend,
       ROUND(100.0 * po.on_time_pos / NULLIF(po.received_pos, 0), 2) AS on_time_pct,
       ROUND(po.avg_days_vs_expected, 2) AS avg_days_vs_expected, ROUND(po.actual_lead_days, 2) AS actual_lead_days,
       ROUND(po.actual_lead_days - su.lead_time_days, 2) AS lead_time_gap_days,
       ROUND(100.0 * f.received / NULLIF(f.ordered, 0), 2) AS fill_rate_pct,
       COALESCE(po.open_pos, 0) AS open_pos, COALESCE(po.overdue_pos, 0) AS overdue_pos,
       (su.contact_email IS NULL OR su.contact_phone IS NULL OR su.gstin IS NULL) AS missing_contact_info
FROM suppliers su
LEFT JOIN po ON po.supplier_id = su.supplier_id LEFT JOIN fill f ON f.supplier_id = su.supplier_id LEFT JOIN prod ON prod.supplier_id = su.supplier_id;

-- ---- 8. return analysis (one row per returned line) -----------------------------------------
CREATE VIEW vw_return_analysis AS
SELECT ri.return_item_id, r.return_id, r.return_date, r.return_date::date AS return_day,
       DATE_TRUNC('month', r.return_date)::date AS return_month,
       r.order_id, o.order_date, o.order_date::date AS order_day, ROUND(EXTRACT(EPOCH FROM (r.return_date - o.order_date)) / 86400.0, 1) AS days_to_return,
       r.return_reason, o.store_id, s.store_name, o.channel, COALESCE(sg.segment_name, '(no segment)') AS customer_segment,
       i.product_id, p.product_name, COALESCE(cc.canonical_name, '(no category)') AS category,
       ri.quantity AS units_returned, i.quantity AS units_in_line, ri.refund_amount,
       ROUND(ri.refund_amount / (1 + p.gst_rate / 100.0), 2) AS refund_net_of_gst,
       ROUND(ri.quantity * i.unit_cost, 2) AS cost_value, ri.restocked
FROM return_items ri
JOIN returns r ON r.return_id = ri.return_id
JOIN sales_orders o ON o.order_id = r.order_id
JOIN sales_order_items i ON i.order_item_id = ri.order_item_id
JOIN products p ON p.product_id = i.product_id
JOIN stores s ON s.store_id = o.store_id
JOIN customers c ON c.customer_id = o.customer_id
LEFT JOIN customer_segments sg ON sg.segment_id = c.segment_id
LEFT JOIN vw_category_canonical cc ON cc.category_id = p.category_id;

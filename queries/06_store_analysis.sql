-- =============================================================================
-- 06_store_analysis.sql : store scorecards, rankings, growth, employees
-- Note: the 'Online Fulfilment Hub' is a warehouse store_id that fulfils all ONLINE orders.
-- =============================================================================

-- Q72 | Store performance scorecard
-- Business question: How does each store perform on revenue, orders, basket, customers, loyalty, returns and stock?
-- Approach: build one CTE per measure at store level and join them, so each measure is aggregated at the right grain first.
-- Concepts: multiple CTEs, aggregating before joining (avoids double counting), COUNT(DISTINCT), HAVING inside a CTE.
-- Why it works: revenue is per order, repeat customers per store+customer, returns per order, inventory per store+product.
--               Mixing those grains in one join would multiply rows and inflate totals.
WITH order_stats AS (
    SELECT store_id, COUNT(*) AS orders, COUNT(DISTINCT customer_id) AS customers,
           SUM(total_amount - gst_amount) AS net_revenue, AVG(total_amount) AS aov
    FROM sales_orders WHERE order_status = 'COMPLETED' GROUP BY store_id
), unit_stats AS (
    SELECT o.store_id, SUM(i.quantity) AS units
    FROM sales_order_items i JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    GROUP BY o.store_id
), repeat_stats AS (
    SELECT store_id, COUNT(*) FILTER (WHERE n >= 2) AS repeat_customers, COUNT(*) AS customers
    FROM (SELECT store_id, customer_id, COUNT(*) AS n FROM sales_orders WHERE order_status = 'COMPLETED'
          GROUP BY store_id, customer_id) t
    GROUP BY store_id
), return_stats AS (
    SELECT o.store_id, COUNT(DISTINCT r.order_id) AS returned_orders
    FROM returns r JOIN sales_orders o ON o.order_id = r.order_id GROUP BY o.store_id
), inv_stats AS (
    SELECT inv.store_id, SUM(inv.quantity_on_hand * p.unit_cost) AS inventory_value
    FROM inventory inv JOIN products p ON p.product_id = inv.product_id GROUP BY inv.store_id
)
SELECT s.store_name, o.orders, u.units, ROUND(o.net_revenue, 0) AS net_revenue, ROUND(o.aov, 0) AS avg_order_value,
       o.customers,
       ROUND(100.0 * rp.repeat_customers / rp.customers, 1)  AS repeat_customer_rate_pct,
       ROUND(100.0 * COALESCE(rt.returned_orders, 0) / o.orders, 2) AS return_rate_pct,
       ROUND(iv.inventory_value, 0) AS inventory_value
FROM stores s
JOIN order_stats o   ON o.store_id = s.store_id
JOIN unit_stats u    ON u.store_id = s.store_id
JOIN repeat_stats rp ON rp.store_id = s.store_id
LEFT JOIN return_stats rt ON rt.store_id = s.store_id
JOIN inv_stats iv    ON iv.store_id = s.store_id
ORDER BY o.net_revenue DESC;

-- Q73 | Store ranking by month (latest 3 months)
-- Business question: How do stores rank against each other month by month?
-- Approach: monthly revenue per store, RANK() within each month, then keep the latest three months.
-- Concepts: RANK() OVER (PARTITION BY month), filtering on a window result via a CTE, subquery for the latest month.
-- Why it works: partitioning by month ranks the stores separately for every month.
WITH monthly AS (
    SELECT DATE_TRUNC('month', order_date)::date AS month, store_id, SUM(total_amount - gst_amount) AS revenue
    FROM sales_orders WHERE order_status = 'COMPLETED' GROUP BY 1, 2
), ranked AS (
    SELECT *, RANK() OVER (PARTITION BY month ORDER BY revenue DESC) AS revenue_rank FROM monthly
)
SELECT r.month, s.store_name, ROUND(r.revenue, 0) AS revenue, r.revenue_rank
FROM ranked r JOIN stores s ON s.store_id = r.store_id
WHERE r.month >= (SELECT MAX(month) FROM monthly) - INTERVAL '2 months'
ORDER BY r.month, r.revenue_rank;

-- Q74 | Store revenue growth 2025 versus 2024
-- Business question: Which stores are growing and which are shrinking?
-- Approach: yearly revenue via FILTER, restricted to stores that were open for all of 2024 so the comparison is fair.
-- Concepts: FILTER pivot, WHERE on a store attribute, growth %.
-- Why it works: stores opened during 2024 would show artificial growth because their 2024 covers only part of the year.
SELECT s.store_name, s.opened_date,
       ROUND(SUM(o.total_amount - o.gst_amount) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2024), 0) AS revenue_2024,
       ROUND(SUM(o.total_amount - o.gst_amount) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2025), 0) AS revenue_2025,
       ROUND(100.0 * (SUM(o.total_amount - o.gst_amount) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2025)
             / SUM(o.total_amount - o.gst_amount) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2024) - 1), 1) AS growth_pct
FROM sales_orders o
JOIN stores s ON s.store_id = o.store_id
WHERE o.order_status = 'COMPLETED' AND s.opened_date < DATE '2024-01-01'
GROUP BY s.store_name, s.opened_date
ORDER BY growth_pct;

-- Q75 | Revenue by region and state
-- Business question: Which regions and states contribute most?
-- Approach: GROUP BY ROLLUP gives state rows plus a subtotal per region and a grand total in one query.
-- Concepts: ROLLUP, GROUPING(), COALESCE labels, share of grand total.
-- Why it works: ROLLUP(region, state) adds subtotal rows where state is NULL and a grand total where both are NULL; GROUPING() tells them apart from real NULLs.
SELECT COALESCE(s.region, 'ALL REGIONS') AS region,
       CASE WHEN GROUPING(s.state) = 1 THEN 'subtotal' ELSE s.state END AS state,
       COUNT(*) AS orders,
       ROUND(SUM(o.total_amount - o.gst_amount), 0) AS net_revenue
FROM sales_orders o JOIN stores s ON s.store_id = o.store_id
WHERE o.order_status = 'COMPLETED'
GROUP BY ROLLUP (s.region, s.state)
ORDER BY GROUPING(s.region), s.region, GROUPING(s.state), net_revenue DESC;

-- Q76 | Revenue per operating month (identifying weaker locations)
-- Business question: Which physical stores generate less revenue per month than their peers?
-- Approach: divide revenue by the number of months the store was open inside the data window, compare with the peer average.
-- Concepts: GREATEST for the window start, date arithmetic in months, AVG() OVER () as the peer benchmark, index vs average.
-- Why it works: new stores (Lucknow, Chandigarh) have fewer months open, so total revenue alone would unfairly rank them last.
--               The peer average is a plain comparison; it is not a target and does not explain the reasons for the gap.
WITH window_bounds AS (SELECT MIN(order_date)::date AS start_d, MAX(order_date)::date AS end_d FROM sales_orders),
store_rev AS (
    SELECT s.store_id, s.store_name, s.opened_date, SUM(o.total_amount - o.gst_amount) AS revenue,
           GREATEST((w.end_d - GREATEST(s.opened_date, w.start_d)) / 30.44, 1) AS months_open
    FROM sales_orders o
    JOIN stores s ON s.store_id = o.store_id AND s.store_type = 'STORE'
    CROSS JOIN window_bounds w
    WHERE o.order_status = 'COMPLETED'
    GROUP BY s.store_id, s.store_name, s.opened_date, w.start_d, w.end_d
)
SELECT store_name, opened_date, ROUND(months_open, 1) AS months_open, ROUND(revenue, 0) AS revenue,
       ROUND(revenue / months_open, 0) AS revenue_per_month,
       ROUND(100.0 * (revenue / months_open) / AVG(revenue / months_open) OVER (), 0) AS index_vs_peer_average
FROM store_rev
ORDER BY revenue_per_month;

-- Q77 | Best salesperson in every store
-- Business question: Who sells the most at each store?
-- Approach: revenue per employee, ROW_NUMBER within store, keep 1; the store's manager is fetched with a SELF JOIN on employees.
-- Concepts: ROW_NUMBER, top-1-per-group, SELF JOIN (employee -> manager), string concatenation.
-- Why it works: employees.manager_id points to another row in the same table, so joining employees to employees names the manager.
WITH emp_sales AS (
    SELECT o.employee_id, o.store_id, COUNT(*) AS orders, SUM(o.total_amount - o.gst_amount) AS revenue,
           ROW_NUMBER() OVER (PARTITION BY o.store_id ORDER BY SUM(o.total_amount - o.gst_amount) DESC) AS rn
    FROM sales_orders o
    WHERE o.order_status = 'COMPLETED' AND o.employee_id IS NOT NULL
    GROUP BY o.employee_id, o.store_id
)
SELECT s.store_name, e.first_name || ' ' || e.last_name AS top_employee, e.job_title,
       m.first_name || ' ' || m.last_name AS reports_to, es.orders, ROUND(es.revenue, 0) AS net_revenue
FROM emp_sales es
JOIN employees e ON e.employee_id = es.employee_id
LEFT JOIN employees m ON m.employee_id = e.manager_id
JOIN stores s ON s.store_id = es.store_id
WHERE es.rn = 1
ORDER BY es.revenue DESC;

-- Q78 | Leading category of each store
-- Business question: What does each store mostly sell?
-- Approach: category revenue per store, share of the store's revenue, ROW_NUMBER to keep the leader.
-- Concepts: two window functions in one CTE (SUM OVER PARTITION for the share, ROW_NUMBER for the leader).
-- Why it works: SUM(...) OVER (PARTITION BY store) repeats the store total on every category row, making the share a simple division.
WITH store_cat AS (
    SELECT o.store_id, COALESCE(c.category_name, '(no category)') AS category,
           SUM(i.line_total / (1 + p.gst_rate / 100.0)) AS revenue
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products p ON p.product_id = i.product_id
    LEFT JOIN categories c ON c.category_id = p.category_id
    GROUP BY o.store_id, 2
), shared AS (
    SELECT *, 100.0 * revenue / SUM(revenue) OVER (PARTITION BY store_id) AS share_pct,
           ROW_NUMBER() OVER (PARTITION BY store_id ORDER BY revenue DESC) AS rn
    FROM store_cat
)
SELECT s.store_name, sh.category AS leading_category, ROUND(sh.revenue, 0) AS revenue, ROUND(sh.share_pct, 1) AS share_of_store_pct
FROM shared sh JOIN stores s ON s.store_id = sh.store_id
WHERE sh.rn = 1
ORDER BY s.store_name;

-- Q79 | Average order value: store versus company
-- Business question: Which stores have baskets above or below the company average?
-- Approach: store AOV compared with the overall AOV using a scalar subquery.
-- Concepts: scalar subquery, percentage difference, HAVING.
-- Why it works: the subquery returns a single number that can be used like a constant inside the SELECT.
SELECT s.store_name, COUNT(*) AS orders, ROUND(AVG(o.total_amount), 0) AS store_aov,
       (SELECT ROUND(AVG(total_amount), 0) FROM sales_orders WHERE order_status = 'COMPLETED') AS company_aov,
       ROUND(100.0 * (AVG(o.total_amount) / (SELECT AVG(total_amount) FROM sales_orders WHERE order_status = 'COMPLETED') - 1), 1) AS difference_pct
FROM sales_orders o JOIN stores s ON s.store_id = o.store_id
WHERE o.order_status = 'COMPLETED'
GROUP BY s.store_name
HAVING COUNT(*) > 500
ORDER BY difference_pct DESC;

-- Q80 | Revenue per employee by store
-- Business question: How productive is each store's team?
-- Approach: LEFT JOIN active employees to store revenue and divide; the hub has no salespeople on orders, so it shows NULL.
-- Concepts: LEFT JOIN, COUNT(*) FILTER, ratio, NULLIF.
-- Why it works: dividing by employees counted in a separate CTE keeps the revenue from being multiplied by the number of employees.
WITH rev AS (
    SELECT store_id, SUM(total_amount - gst_amount) AS revenue
    FROM sales_orders WHERE order_status = 'COMPLETED' GROUP BY store_id
), staff AS (
    SELECT store_id, COUNT(*) FILTER (WHERE is_active) AS active_employees FROM employees GROUP BY store_id
)
SELECT s.store_name, st.active_employees, ROUND(r.revenue, 0) AS net_revenue,
       ROUND(r.revenue / NULLIF(st.active_employees, 0), 0) AS revenue_per_active_employee
FROM stores s JOIN rev r ON r.store_id = s.store_id JOIN staff st ON st.store_id = s.store_id
ORDER BY revenue_per_active_employee DESC;

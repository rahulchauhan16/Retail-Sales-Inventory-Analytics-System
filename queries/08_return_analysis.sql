-- =============================================================================
-- 08_return_analysis.sql : how much is returned, where, and by whom
-- Return rate has three deliberate definitions (state which one you mean in an interview!):
--   order return rate = orders with at least one return / completed orders
--   unit return rate  = units returned / units sold
--   value return rate = refund value (net of GST) / net revenue
-- Reasons are recorded by staff; the data shows WHAT was returned, not WHY it really happened.
-- =============================================================================

-- Q89 | Return rate: orders, units and value
-- Business question: How much of what we sell comes back?
-- Approach: three ratios computed side by side, each from its own sub-select to keep grains separate.
-- Concepts: scalar subqueries, three rate definitions, refunds net of GST via a join to products.
-- Why it works: returned value is refund / (1 + GST) so it is comparable with net revenue.
SELECT (SELECT COUNT(*) FROM sales_orders WHERE order_status = 'COMPLETED')            AS completed_orders,
       (SELECT COUNT(DISTINCT order_id) FROM returns)                                   AS orders_with_returns,
       ROUND(100.0 * (SELECT COUNT(DISTINCT order_id) FROM returns)
             / (SELECT COUNT(*) FROM sales_orders WHERE order_status = 'COMPLETED'), 2) AS order_return_rate_pct,
       ROUND(100.0 * (SELECT SUM(quantity) FROM return_items)
             / (SELECT SUM(i.quantity) FROM sales_order_items i JOIN sales_orders o ON o.order_id = i.order_id
                WHERE o.order_status = 'COMPLETED'), 2)                                  AS unit_return_rate_pct,
       ROUND((SELECT SUM(ri.refund_amount / (1 + p.gst_rate / 100.0))
              FROM return_items ri JOIN sales_order_items i ON i.order_item_id = ri.order_item_id
              JOIN products p ON p.product_id = i.product_id), 0)                        AS returned_value_net,
       ROUND(100.0 * (SELECT SUM(ri.refund_amount / (1 + p.gst_rate / 100.0))
              FROM return_items ri JOIN sales_order_items i ON i.order_item_id = ri.order_item_id
              JOIN products p ON p.product_id = i.product_id)
             / (SELECT SUM(total_amount - gst_amount) FROM sales_orders WHERE order_status = 'COMPLETED'), 2) AS value_return_rate_pct;

-- Q90 | Return reasons
-- Business question: What reasons are recorded for returns?
-- Approach: count returns and refund value per reason with share of total.
-- Concepts: GROUP BY, window percent of total, SUM.
-- Why it works: reasons are a fixed list, so grouping gives a clean distribution. Treat it as recorded reasons, not root causes.
SELECT return_reason, COUNT(*) AS returns, ROUND(SUM(refund_amount), 0) AS refund_value,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_of_returns_pct
FROM returns
GROUP BY return_reason
ORDER BY returns DESC;

-- Q91 | Returns by category
-- Business question: Which categories are returned most often?
-- Approach: sold units and returned units are aggregated separately per category, then divided.
-- Concepts: two CTEs, canonical category via window MIN, LEFT JOIN, unit return rate.
-- Why it works: pre-aggregating each side prevents the return rows from multiplying sales rows in the join.
WITH canon AS (
    SELECT category_id, MIN(category_id) OVER (PARTITION BY LOWER(category_name)) AS canonical_id FROM categories
), sold AS (
    SELECT c.canonical_id, SUM(i.quantity) AS units_sold
    FROM sales_order_items i JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products p ON p.product_id = i.product_id JOIN canon c ON c.category_id = p.category_id
    GROUP BY c.canonical_id
), ret AS (
    SELECT c.canonical_id, SUM(ri.quantity) AS units_returned, SUM(ri.refund_amount) AS refund_value
    FROM return_items ri JOIN sales_order_items i ON i.order_item_id = ri.order_item_id
    JOIN products p ON p.product_id = i.product_id JOIN canon c ON c.category_id = p.category_id
    GROUP BY c.canonical_id
)
SELECT cat.category_name, s.units_sold, COALESCE(r.units_returned, 0) AS units_returned,
       ROUND(100.0 * COALESCE(r.units_returned, 0) / s.units_sold, 2) AS unit_return_rate_pct,
       ROUND(COALESCE(r.refund_value, 0), 0) AS refund_value
FROM sold s JOIN categories cat ON cat.category_id = s.canonical_id LEFT JOIN ret r ON r.canonical_id = s.canonical_id
ORDER BY unit_return_rate_pct DESC;

-- Q92 | Returns by store
-- Business question: Do some stores see more returns than others?
-- Approach: orders with returns divided by completed orders per store.
-- Concepts: LEFT JOIN, COUNT(DISTINCT), rate, comparison with the company rate via a window function.
-- Why it works: AVG(rate) OVER () would average store rates; instead we compare with the company-wide ratio from a scalar subquery.
SELECT s.store_name, COUNT(DISTINCT o.order_id) AS completed_orders, COUNT(DISTINCT r.order_id) AS orders_with_returns,
       ROUND(100.0 * COUNT(DISTINCT r.order_id) / COUNT(DISTINCT o.order_id), 2) AS order_return_rate_pct,
       ROUND(100.0 * (SELECT COUNT(DISTINCT order_id) FROM returns)
             / (SELECT COUNT(*) FROM sales_orders WHERE order_status = 'COMPLETED'), 2) AS company_rate_pct
FROM stores s
JOIN sales_orders o ON o.store_id = s.store_id AND o.order_status = 'COMPLETED'
LEFT JOIN returns r ON r.order_id = o.order_id
GROUP BY s.store_name
ORDER BY order_return_rate_pct DESC;

-- Q93 | Returns by customer segment
-- Business question: Which customer segments return more?
-- Approach: completed orders and returned orders per segment.
-- Concepts: LEFT JOIN through customers to segments, COALESCE label, rate.
-- Why it works: customers without a segment get their own row instead of vanishing.
SELECT COALESCE(sg.segment_name, '(no segment)') AS segment, COUNT(DISTINCT o.order_id) AS completed_orders,
       COUNT(DISTINCT r.order_id) AS orders_with_returns,
       ROUND(100.0 * COUNT(DISTINCT r.order_id) / COUNT(DISTINCT o.order_id), 2) AS order_return_rate_pct
FROM sales_orders o
JOIN customers c ON c.customer_id = o.customer_id
LEFT JOIN customer_segments sg ON sg.segment_id = c.segment_id
LEFT JOIN returns r ON r.order_id = o.order_id
WHERE o.order_status = 'COMPLETED'
GROUP BY 1
ORDER BY order_return_rate_pct DESC;

-- Q94 | Products with unusually high return rates
-- Business question: Which products are returned far more often than the rest of their category?
-- Approach: product unit return rate divided by its category's rate; keep products with 40+ units sold, 8+ units returned and at least 2.5x the category rate.
-- Concepts: window function over a group (category totals), ratio to benchmark, HAVING via CTE, minimum-volume filter.
-- Why it works: comparing with the category removes the natural difference between e.g. clothing and groceries.
--               Small samples are noisy, so the 40-unit floor is a project assumption; a flagged product needs investigation, not a conclusion.
WITH prod AS (
    SELECT p.product_id, p.product_name, COALESCE(p.category_id, 0) AS category_id,
           SUM(i.quantity) AS units_sold, COALESCE(SUM(ri.quantity), 0) AS units_returned
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products p ON p.product_id = i.product_id
    LEFT JOIN (SELECT order_item_id, SUM(quantity) AS quantity FROM return_items GROUP BY order_item_id) ri
           ON ri.order_item_id = i.order_item_id
    GROUP BY p.product_id, p.product_name, p.category_id
), rated AS (
    SELECT *, 100.0 * units_returned / units_sold AS rate_pct,
           100.0 * SUM(units_returned) OVER (PARTITION BY category_id) / SUM(units_sold) OVER (PARTITION BY category_id) AS category_rate_pct
    FROM prod
)
SELECT product_name, units_sold, units_returned, ROUND(rate_pct, 1) AS return_rate_pct,
       ROUND(category_rate_pct, 1) AS category_rate_pct, ROUND(rate_pct / NULLIF(category_rate_pct, 0), 1) AS times_category_rate
FROM rated
WHERE units_sold >= 40 AND units_returned >= 8 AND rate_pct >= 2.5 * category_rate_pct
ORDER BY times_category_rate DESC
LIMIT 15;

-- Q95 | Revenue lost to returns by month
-- Business question: How much revenue is refunded each month, and how much of that month's revenue is it?
-- Approach: refund value (net of GST) by return month, compared with net revenue of the same month.
-- Concepts: two CTEs joined by month, DATE_TRUNC, ratio.
-- Why it works: refunds are attributed to the month the return happened (cash impact), not to the original sale month.
WITH refunds AS (
    SELECT DATE_TRUNC('month', r.return_date)::date AS month, SUM(ri.refund_amount / (1 + p.gst_rate / 100.0)) AS refunded
    FROM returns r
    JOIN return_items ri ON ri.return_id = r.return_id
    JOIN sales_order_items i ON i.order_item_id = ri.order_item_id
    JOIN products p ON p.product_id = i.product_id
    GROUP BY 1
), revenue AS (
    SELECT DATE_TRUNC('month', order_date)::date AS month, SUM(total_amount - gst_amount) AS revenue
    FROM sales_orders WHERE order_status = 'COMPLETED' GROUP BY 1
)
SELECT v.month, ROUND(v.revenue, 0) AS net_revenue, ROUND(COALESCE(f.refunded, 0), 0) AS refunded_net,
       ROUND(100.0 * COALESCE(f.refunded, 0) / v.revenue, 2) AS refund_pct_of_revenue
FROM revenue v LEFT JOIN refunds f ON f.month = v.month
ORDER BY v.month;

-- Q96 | Time from purchase to return
-- Business question: How long after the purchase do customers return items?
-- Approach: difference between return_date and order_date in days, bucketed and summarised with percentiles.
-- Concepts: timestamp subtraction, EXTRACT(EPOCH), CASE buckets, PERCENTILE_CONT.
-- Why it works: subtracting timestamps yields an interval; converting epoch seconds to days makes it numeric.
WITH d AS (
    SELECT EXTRACT(EPOCH FROM (r.return_date - o.order_date)) / 86400.0 AS days_to_return
    FROM returns r JOIN sales_orders o ON o.order_id = r.order_id
)
SELECT CASE WHEN days_to_return < 3 THEN 'a) within 3 days' WHEN days_to_return < 7 THEN 'b) 3-6 days'
            WHEN days_to_return < 15 THEN 'c) 7-14 days' ELSE 'd) 15+ days' END AS return_window,
       COUNT(*) AS returns, ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_pct,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_to_return))::numeric, 1) AS median_days
FROM d
GROUP BY 1
ORDER BY 1;

-- Q97 | Restocked versus written-off returns
-- Business question: How much returned merchandise goes back on the shelf and how much is written off?
-- Approach: split return lines by the restocked flag and value them at cost.
-- Concepts: boolean grouping, join to order lines for the cost snapshot, SUM of quantity * unit_cost.
-- Why it works: returned units that are not restocked leave the business without resale - their cost is a loss.
SELECT CASE WHEN ri.restocked THEN 'Restocked (resellable)' ELSE 'Not restocked (write-off)' END AS outcome,
       COUNT(*) AS return_lines, SUM(ri.quantity) AS units,
       ROUND(SUM(ri.quantity * i.unit_cost), 0) AS cost_value,
       ROUND(100.0 * SUM(ri.quantity * i.unit_cost) / SUM(SUM(ri.quantity * i.unit_cost)) OVER (), 1) AS share_of_cost_pct
FROM return_items ri JOIN sales_order_items i ON i.order_item_id = ri.order_item_id
GROUP BY ri.restocked
ORDER BY ri.restocked DESC;

-- Q98 | Return rate by sales channel
-- Business question: Are online orders returned more often than in-store orders?
-- Approach: orders with returns divided by completed orders for each channel.
-- Concepts: LEFT JOIN, COUNT(DISTINCT), rate.
-- Why it works: same construction as the store and segment queries, grouped by channel.
SELECT o.channel, COUNT(DISTINCT o.order_id) AS completed_orders, COUNT(DISTINCT r.order_id) AS orders_with_returns,
       ROUND(100.0 * COUNT(DISTINCT r.order_id) / COUNT(DISTINCT o.order_id), 2) AS order_return_rate_pct
FROM sales_orders o LEFT JOIN returns r ON r.order_id = o.order_id
WHERE o.order_status = 'COMPLETED'
GROUP BY o.channel;

-- Q99 | Most common return reason within each category
-- Business question: For each category, what reason is recorded most often?
-- Approach: count returns by category and reason, ROW_NUMBER within the category, keep the top reason with its share.
-- Concepts: window functions (ROW_NUMBER + SUM OVER PARTITION), top-1-per-group, canonical category.
-- Why it works: the share is the top reason's count over all returns in that category.
WITH canon AS (
    SELECT category_id, MIN(category_id) OVER (PARTITION BY LOWER(category_name)) AS canonical_id FROM categories
), counted AS (
    SELECT c.canonical_id, r.return_reason, COUNT(DISTINCT r.return_id) AS returns
    FROM returns r
    JOIN return_items ri ON ri.return_id = r.return_id
    JOIN sales_order_items i ON i.order_item_id = ri.order_item_id
    JOIN products p ON p.product_id = i.product_id
    JOIN canon c ON c.category_id = p.category_id
    GROUP BY c.canonical_id, r.return_reason
), ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY canonical_id ORDER BY returns DESC) AS rn,
           SUM(returns) OVER (PARTITION BY canonical_id) AS category_returns
    FROM counted
)
SELECT cat.category_name, rk.return_reason AS most_common_reason, rk.returns,
       ROUND(100.0 * rk.returns / rk.category_returns, 1) AS share_of_category_returns_pct
FROM ranked rk JOIN categories cat ON cat.category_id = rk.canonical_id
WHERE rk.rn = 1
ORDER BY category_name;

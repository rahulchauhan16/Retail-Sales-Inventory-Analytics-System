-- =============================================================================
-- 09_advanced_sql.sql : recursion, set operations, LATERAL, gaps-and-islands, percentiles, date bucketing
-- These techniques are worth learning for interviews, but each is used here only where it fits the data.
-- =============================================================================

-- Q100 | Category hierarchy with a recursive CTE
-- Business question: How are categories organised (parent > child) and how many products sit directly under each?
-- Approach: start from root categories (no parent) and repeatedly add the children of rows already found.
-- Concepts: WITH RECURSIVE (anchor + recursive member joined by UNION ALL), depth counter, path building.
-- Why it works: the anchor returns the roots; each recursion step joins categories whose parent_category_id matches a category
--               already in the result, so the tree grows one level per step until no more children exist.
--               Recursion is justified because the depth of a hierarchy is not known in advance.
WITH RECURSIVE tree AS (
    SELECT category_id, category_name, 1 AS depth, category_name::text AS path
    FROM categories WHERE parent_category_id IS NULL
    UNION ALL
    SELECT c.category_id, c.category_name, t.depth + 1, t.path || ' > ' || c.category_name
    FROM categories c JOIN tree t ON c.parent_category_id = t.category_id
)
SELECT t.path, t.depth, COUNT(p.product_id) AS direct_products
FROM tree t LEFT JOIN products p ON p.category_id = t.category_id
GROUP BY t.path, t.depth
ORDER BY t.path;

-- Q101 | Revenue rolled up to top-level categories
-- Business question: What is the revenue of each top-level group (Electronics, Fashion, ...)?
-- Approach: the recursive CTE carries the ROOT category id down every branch, so each leaf knows its top-level ancestor.
-- Concepts: recursive CTE with a carried column, roll-up through a hierarchy, JOIN to sales.
-- Why it works: root_id is copied unchanged from parent to child rows; grouping by root_id sums all descendants together.
WITH RECURSIVE tree AS (
    SELECT category_id, category_id AS root_id FROM categories WHERE parent_category_id IS NULL
    UNION ALL
    SELECT c.category_id, t.root_id FROM categories c JOIN tree t ON c.parent_category_id = t.category_id
)
SELECT r.category_name AS top_level_category,
       ROUND(SUM(i.line_total / (1 + p.gst_rate / 100.0)), 0) AS net_revenue,
       ROUND(100.0 * SUM(i.line_total / (1 + p.gst_rate / 100.0)) / SUM(SUM(i.line_total / (1 + p.gst_rate / 100.0))) OVER (), 1) AS share_pct
FROM sales_order_items i
JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
JOIN products p ON p.product_id = i.product_id
JOIN tree t ON t.category_id = p.category_id
JOIN categories r ON r.category_id = t.root_id
GROUP BY r.category_name
ORDER BY net_revenue DESC;

-- Q102 | Employee reporting chain (recursive)
-- Business question: Who reports to whom, and how deep is the chain?
-- Approach: managers (no manager_id) are level 1; recursion adds their direct reports level by level.
-- Concepts: recursive CTE on a self-referencing table, level number, string path.
-- Why it works: same pattern as the category tree; employees.manager_id is the parent pointer.
WITH RECURSIVE org AS (
    SELECT employee_id, first_name || ' ' || last_name AS employee, store_id, 1 AS level, first_name || ' ' || last_name AS chain
    FROM employees WHERE manager_id IS NULL
    UNION ALL
    SELECT e.employee_id, e.first_name || ' ' || e.last_name, e.store_id, o.level + 1, o.chain || ' > ' || e.first_name || ' ' || e.last_name
    FROM employees e JOIN org o ON e.manager_id = o.employee_id
)
SELECT s.store_name, COUNT(*) FILTER (WHERE level = 1) AS managers, COUNT(*) FILTER (WHERE level = 2) AS direct_reports, MAX(level) AS max_depth
FROM org JOIN stores s ON s.store_id = org.store_id
GROUP BY s.store_name
ORDER BY s.store_name;

-- Q103 | FULL OUTER JOIN: categories versus categories that have sales
-- Business question: Are there categories without sales, or sales without a valid category?
-- Approach: FULL OUTER JOIN keeps unmatched rows from BOTH sides; NULLs show which side is missing.
-- Concepts: FULL OUTER JOIN, COALESCE, classifying mismatches with CASE.
-- Why it works: LEFT JOIN would show only categories without sales; FULL also exposes sales whose product has no category.
WITH cat AS (SELECT category_id, category_name FROM categories),
sold AS (
    SELECT p.category_id, SUM(i.line_total / (1 + p.gst_rate / 100.0)) AS revenue
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products p ON p.product_id = i.product_id
    GROUP BY p.category_id
)
SELECT COALESCE(cat.category_name, '(products with NO category)') AS category,
       CASE WHEN cat.category_id IS NULL THEN 'Sales without a category'
            WHEN sold.revenue IS NULL THEN 'Category without sales' ELSE 'Matched' END AS match_type,
       ROUND(sold.revenue, 0) AS revenue
FROM cat FULL OUTER JOIN sold ON sold.category_id = cat.category_id
WHERE cat.category_id IS NULL OR sold.revenue IS NULL
ORDER BY match_type, category;

-- Q104 | Set operations: customers by year of purchase
-- Business question: Of the customers who bought in 2024, how many also bought in 2025, and how many were lost?
-- Approach: build two customer sets and combine them with INTERSECT, EXCEPT and UNION.
-- Concepts: INTERSECT, EXCEPT, UNION (removes duplicates) versus UNION ALL (keeps them).
-- Why it works: set operators compare whole rows; each query returns one column of customer ids.
SELECT 'Bought in 2024 and 2025 (retained)' AS segment, COUNT(*) AS customers FROM (
    SELECT customer_id FROM sales_orders WHERE order_status = 'COMPLETED' AND EXTRACT(YEAR FROM order_date) = 2024
    INTERSECT
    SELECT customer_id FROM sales_orders WHERE order_status = 'COMPLETED' AND EXTRACT(YEAR FROM order_date) = 2025) a
UNION ALL
SELECT 'Bought in 2024 but not in 2025 (lapsed)', COUNT(*) FROM (
    SELECT customer_id FROM sales_orders WHERE order_status = 'COMPLETED' AND EXTRACT(YEAR FROM order_date) = 2024
    EXCEPT
    SELECT customer_id FROM sales_orders WHERE order_status = 'COMPLETED' AND EXTRACT(YEAR FROM order_date) = 2025) b
UNION ALL
SELECT 'Bought in 2025 but not in 2024 (new or returning)', COUNT(*) FROM (
    SELECT customer_id FROM sales_orders WHERE order_status = 'COMPLETED' AND EXTRACT(YEAR FROM order_date) = 2025
    EXCEPT
    SELECT customer_id FROM sales_orders WHERE order_status = 'COMPLETED' AND EXTRACT(YEAR FROM order_date) = 2024) c;

-- Q105 | Finding days with no sales (gap filling with generate_series)
-- Business question: On which days did the Lucknow store record no orders in December 2025?
-- Approach: generate every calendar day, LEFT JOIN the actual order counts, keep days where the join found nothing.
-- Concepts: generate_series, LEFT JOIN to a derived table, anti-join through IS NULL, date bucketing.
-- Why it works: GROUP BY on orders can only show days that HAVE orders; a generated calendar supplies the missing days.
SELECT d::date AS day, TO_CHAR(d, 'Dy') AS weekday
FROM generate_series(DATE '2025-12-01', DATE '2025-12-31', INTERVAL '1 day') AS d
LEFT JOIN (
    SELECT order_date::date AS order_day
    FROM sales_orders
    WHERE store_id = (SELECT store_id FROM stores WHERE store_code = 'LKO01') AND order_status = 'COMPLETED'
    GROUP BY 1) o ON o.order_day = d::date
WHERE o.order_day IS NULL
ORDER BY d;

-- Q106 | Longest run of consecutive trading days per store (gaps and islands)
-- Business question: What is the longest streak of consecutive days on which each store had at least one order?
-- Approach: number the distinct trading days per store; (date - row number) is constant inside a run of consecutive dates,
--           so grouping by it identifies each 'island'.
-- Concepts: ROW_NUMBER, date minus integer, GROUP BY on a derived key, top-1-per-group.
-- Why it works: if dates are consecutive the row number rises by 1 exactly as the date does, so their difference stays the same;
--               a gap in dates makes the difference jump and starts a new island.
WITH days AS (
    SELECT DISTINCT store_id, order_date::date AS d FROM sales_orders WHERE order_status = 'COMPLETED'
), islands AS (
    SELECT store_id, d, d - (ROW_NUMBER() OVER (PARTITION BY store_id ORDER BY d))::int AS island FROM days
), streaks AS (
    SELECT store_id, MIN(d) AS streak_start, MAX(d) AS streak_end, COUNT(*) AS days_in_streak FROM islands GROUP BY store_id, island
), ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY store_id ORDER BY days_in_streak DESC, streak_start) AS rn FROM streaks
)
SELECT s.store_name, r.streak_start, r.streak_end, r.days_in_streak
FROM ranked r JOIN stores s ON s.store_id = r.store_id
WHERE r.rn = 1
ORDER BY r.days_in_streak DESC;

-- Q107 | Top 3 products per store with LATERAL
-- Business question: What are each store's three best-selling products by revenue?
-- Approach: for every store row run a small sub-query that can refer to that row's store_id (LATERAL), ordered and limited to 3.
-- Concepts: CROSS JOIN LATERAL, correlated sub-query in FROM, LIMIT inside a join.
-- Why it works: a normal sub-query in FROM cannot see columns of earlier tables; LATERAL lifts that restriction, which makes
--               top-N-per-group easy to read (the alternative is ROW_NUMBER in a CTE).
SELECT s.store_name, t.product_name, ROUND(t.revenue, 0) AS net_revenue
FROM stores s
CROSS JOIN LATERAL (
    SELECT p.product_name, SUM(i.line_total / (1 + p.gst_rate / 100.0)) AS revenue
    FROM sales_orders o
    JOIN sales_order_items i ON i.order_id = o.order_id
    JOIN products p ON p.product_id = i.product_id
    WHERE o.store_id = s.store_id AND o.order_status = 'COMPLETED'
    GROUP BY p.product_name
    ORDER BY revenue DESC
    LIMIT 3
) t
ORDER BY s.store_name, t.revenue DESC;

-- Q108 | Orders far above the customer's own average (correlated subquery)
-- Business question: Which unusually large orders were more than 3x what that same customer normally spends?
-- Approach: the outer query picks large orders first; a correlated sub-query then computes that customer's average.
-- Concepts: correlated subquery (runs once per outer row), filtering the outer set first for speed.
-- Why it works: the sub-query references o.customer_id from the outer row. Because it runs per row, the cheap filter
--               (total_amount > 100000) is applied first so it executes only for a few rows.
SELECT o.order_id, o.customer_id, o.total_amount,
       (SELECT ROUND(AVG(o2.total_amount), 0) FROM sales_orders o2
        WHERE o2.customer_id = o.customer_id AND o2.order_status = 'COMPLETED') AS customer_avg_order
FROM sales_orders o
WHERE o.order_status = 'COMPLETED' AND o.total_amount > 100000
  AND o.total_amount > 3 * (SELECT AVG(o2.total_amount) FROM sales_orders o2
                            WHERE o2.customer_id = o.customer_id AND o2.order_status = 'COMPLETED')
ORDER BY o.total_amount DESC
LIMIT 10;

-- Q109 | Cross-tab: revenue by category (rows) and region (columns)
-- Business question: Which categories sell best in which regions?
-- Approach: conditional aggregation, one SUM(...) FILTER per region column.
-- Concepts: manual pivot with FILTER, share of a row total, canonical category via window MIN.
-- Why it works: PostgreSQL has no native PIVOT; FILTER-based columns are the portable way to build a matrix.
WITH canon AS (
    SELECT category_id, MIN(category_id) OVER (PARTITION BY LOWER(category_name)) AS canonical_id FROM categories
)
SELECT cat.category_name,
       ROUND(SUM(i.line_total / (1 + p.gst_rate / 100.0)) FILTER (WHERE s.region = 'North'), 0) AS north,
       ROUND(SUM(i.line_total / (1 + p.gst_rate / 100.0)) FILTER (WHERE s.region = 'South'), 0) AS south,
       ROUND(SUM(i.line_total / (1 + p.gst_rate / 100.0)) FILTER (WHERE s.region = 'East'), 0)  AS east,
       ROUND(SUM(i.line_total / (1 + p.gst_rate / 100.0)) FILTER (WHERE s.region = 'West'), 0)  AS west,
       ROUND(100.0 * SUM(i.line_total / (1 + p.gst_rate / 100.0)) FILTER (WHERE s.region = 'West')
             / SUM(i.line_total / (1 + p.gst_rate / 100.0)), 1) AS west_share_pct
FROM sales_order_items i
JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
JOIN stores s ON s.store_id = o.store_id
JOIN products p ON p.product_id = i.product_id
JOIN canon c ON c.category_id = p.category_id
JOIN categories cat ON cat.category_id = c.canonical_id
GROUP BY cat.category_name
ORDER BY cat.category_name;

-- Q110 | Order value percentiles and outliers per channel
-- Business question: What does the order-value distribution look like, and which orders are statistical outliers?
-- Approach: PERCENTILE_CONT for p50/p90/p99, then the IQR rule (Q3 + 1.5 x IQR) to count high outliers.
-- Concepts: ordered-set aggregates, interquartile range, joining stats back to the detail rows.
-- Why it works: the IQR fence is a standard, distribution-free way to call a value unusual. An outlier is not an error -
--               large orders can be perfectly valid, so this is a list to review, not to delete.
WITH stats AS (
    SELECT channel,
           PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY total_amount) AS q1,
           PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY total_amount) AS median,
           PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY total_amount) AS q3,
           PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY total_amount) AS p90,
           PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY total_amount) AS p99
    FROM sales_orders WHERE order_status = 'COMPLETED' GROUP BY channel
)
SELECT st.channel, ROUND(st.median::numeric, 0) AS median, ROUND(st.p90::numeric, 0) AS p90, ROUND(st.p99::numeric, 0) AS p99,
       ROUND((st.q3 + 1.5 * (st.q3 - st.q1))::numeric, 0) AS outlier_fence,
       COUNT(*) FILTER (WHERE o.total_amount > st.q3 + 1.5 * (st.q3 - st.q1)) AS outlier_orders,
       ROUND(100.0 * COUNT(*) FILTER (WHERE o.total_amount > st.q3 + 1.5 * (st.q3 - st.q1)) / COUNT(*), 1) AS outlier_share_pct
FROM stats st JOIN sales_orders o ON o.channel = st.channel AND o.order_status = 'COMPLETED'
GROUP BY st.channel, st.q1, st.median, st.q3, st.p90, st.p99;

-- Q111 | Weekly revenue with week-over-week change and 4-week average (last 12 weeks)
-- Business question: What is the short-term weekly trend?
-- Approach: DATE_TRUNC('week') buckets to Monday, LAG for change, AVG over a 4-row frame for the smoothed line.
-- Concepts: date bucketing by week, LAG, moving average frame, filtering the latest N weeks after windows are computed.
-- Why it works: window functions run before the outer WHERE, so the moving average of early rows still sees older weeks.
--               CAUTION: the newest week (29-31 Dec 2025) is incomplete, so its week-over-week drop is not a real decline.
WITH weekly AS (
    SELECT DATE_TRUNC('week', order_date)::date AS week_start, SUM(total_amount - gst_amount) AS revenue
    FROM sales_orders WHERE order_status = 'COMPLETED' GROUP BY 1
), calc AS (
    SELECT week_start, revenue,
           100.0 * (revenue / LAG(revenue) OVER (ORDER BY week_start) - 1) AS wow_pct,
           AVG(revenue) OVER (ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS avg_4w
    FROM weekly
)
SELECT week_start, ROUND(revenue, 0) AS revenue, ROUND(wow_pct, 1) AS wow_change_pct, ROUND(avg_4w, 0) AS moving_avg_4w
FROM calc
ORDER BY week_start DESC
LIMIT 12;

-- Q112 | Cumulative customer acquisition
-- Business question: How does the number of customers who have ever purchased grow over time?
-- Approach: count first purchases per month, then a running SUM over the months.
-- Concepts: MIN per customer, GROUP BY month, SUM() OVER (ORDER BY month).
-- Why it works: a customer's first order month is unique, so summing 'new customers' cumulatively counts each person once.
WITH first_month AS (
    SELECT customer_id, DATE_TRUNC('month', MIN(order_date))::date AS month
    FROM sales_orders WHERE order_status = 'COMPLETED' GROUP BY customer_id
)
SELECT month, COUNT(*) AS new_customers, SUM(COUNT(*)) OVER (ORDER BY month) AS cumulative_customers
FROM first_month GROUP BY month ORDER BY month;

-- Q113 | Repeat rate by the category of the first purchase (DISTINCT ON)
-- Business question: Do customers whose first purchase is in a certain category come back more often?
-- Approach: DISTINCT ON keeps one row per customer - their first order; the biggest line of that order defines the category.
-- Concepts: DISTINCT ON (PostgreSQL feature), ORDER BY to control which row is kept, join to lifetime order counts.
-- Why it works: DISTINCT ON (customer_id) returns the first row of each customer according to ORDER BY.
--               This shows an association only; it does not prove the category causes repeat buying.
WITH first_order AS (
    SELECT DISTINCT ON (customer_id) customer_id, order_id
    FROM sales_orders WHERE order_status = 'COMPLETED' ORDER BY customer_id, order_date, order_id
), first_line AS (
    SELECT DISTINCT ON (f.customer_id) f.customer_id, p.category_id
    FROM first_order f JOIN sales_order_items i ON i.order_id = f.order_id JOIN products p ON p.product_id = i.product_id
    ORDER BY f.customer_id, i.line_total DESC
), totals AS (
    SELECT customer_id, COUNT(*) AS orders FROM sales_orders WHERE order_status = 'COMPLETED' GROUP BY customer_id
)
SELECT COALESCE(c.category_name, '(no category)') AS first_purchase_category, COUNT(*) AS customers,
       ROUND(100.0 * COUNT(*) FILTER (WHERE t.orders >= 2) / COUNT(*), 1) AS repeat_rate_pct
FROM first_line fl JOIN totals t ON t.customer_id = fl.customer_id LEFT JOIN categories c ON c.category_id = fl.category_id
GROUP BY 1 HAVING COUNT(*) >= 100
ORDER BY repeat_rate_pct DESC;

-- Q114 | Reactivated customers (returning after a long silence)
-- Business question: How many customers came back after being away for more than 180 days?
-- Approach: LAG gives each order's previous order date; a gap over 180 days marks a reactivation.
-- Concepts: LAG, PARTITION BY customer, filtering on a window result through a CTE.
-- Why it works: only orders that FOLLOW a long silence pass the gap filter, so counting them counts the comebacks.
--               The 180-day threshold is a project assumption.
WITH gaps AS (
    SELECT customer_id, order_date::date AS order_day,
           order_date::date - LAG(order_date::date) OVER (PARTITION BY customer_id ORDER BY order_date) AS gap_days
    FROM sales_orders WHERE order_status = 'COMPLETED'
)
SELECT COUNT(*) AS reactivation_orders, COUNT(DISTINCT customer_id) AS reactivated_customers,
       ROUND(AVG(gap_days), 0) AS avg_silence_days, MAX(gap_days) AS longest_silence_days
FROM gaps WHERE gap_days > 180;

-- Q115 | How quickly do new customers place a second order? (LEAD)
-- Business question: What share of customers come back within 30, 60 or 90 days of their first order?
-- Approach: number each customer's orders, use LEAD to fetch the date of the NEXT order on the first order's row, measure the gap.
-- Concepts: LEAD (the mirror image of LAG), ROW_NUMBER, conditional counts, cumulative-style buckets.
-- Why it works: LEAD(order_date) looks one row ahead within the customer, so on the first order it returns the second order's date;
--               it is NULL for customers who never came back. Very recent customers have had less time to return,
--               so only customers whose first order is at least 90 days before the end of the data are counted.
WITH ordered AS (
    SELECT customer_id, order_date::date AS order_day,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS rn,
           LEAD(order_date::date) OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS next_order_day
    FROM sales_orders WHERE order_status = 'COMPLETED'
), first_orders AS (
    SELECT * FROM ordered
    WHERE rn = 1 AND order_day <= (SELECT MAX(order_date)::date FROM sales_orders) - 90
)
SELECT COUNT(*) AS customers_measured,
       ROUND(100.0 * COUNT(*) FILTER (WHERE next_order_day - order_day <= 30) / COUNT(*), 1) AS second_order_within_30d_pct,
       ROUND(100.0 * COUNT(*) FILTER (WHERE next_order_day - order_day <= 60) / COUNT(*), 1) AS second_order_within_60d_pct,
       ROUND(100.0 * COUNT(*) FILTER (WHERE next_order_day - order_day <= 90) / COUNT(*), 1) AS second_order_within_90d_pct,
       ROUND(100.0 * COUNT(*) FILTER (WHERE next_order_day IS NULL) / COUNT(*), 1) AS never_came_back_pct
FROM first_orders;

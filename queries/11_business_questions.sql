-- =============================================================================
-- 11_business_questions.sql : management-level questions that combine several analyses
-- Reading guide (used in docs/05_sql_analysis.md):
--   FACT                 = a value read straight from the data
--   CALCULATED METRIC    = a value derived by a formula (documented in the KPI glossary)
--   ANALYTICAL OBSERVATION = what the numbers appear to show
--   POSSIBLE BUSINESS ACTION = an option to investigate; the data does not prove it is right
-- Queries here return FACTS and CALCULATED METRICS only. Observations and actions are written next to the results in the docs.
-- =============================================================================

-- Q401 | Executive KPI summary
-- Business question: What are the headline numbers for the whole business?
-- Approach: one row of scalar sub-queries, each a documented KPI.
-- Concepts: scalar subqueries, KPI formulas, consistent definitions (completed orders, revenue net of GST).
-- Why it works: every KPI is defined once here, so the Python and Power BI layers can be reconciled against this row.
SELECT
    (SELECT ROUND(SUM(total_amount - gst_amount), 0) FROM sales_orders WHERE order_status = 'COMPLETED')                        AS net_revenue,
    (SELECT ROUND(SUM(i.line_total / (1 + p.gst_rate / 100.0) - i.quantity * i.unit_cost), 0)
       FROM sales_order_items i JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
       JOIN products p ON p.product_id = i.product_id)                                                                          AS gross_profit,
    (SELECT COUNT(*) FROM sales_orders WHERE order_status = 'COMPLETED')                                                        AS completed_orders,
    (SELECT COUNT(DISTINCT customer_id) FROM sales_orders WHERE order_status = 'COMPLETED')                                     AS buying_customers,
    (SELECT ROUND(AVG(total_amount), 0) FROM sales_orders WHERE order_status = 'COMPLETED')                                     AS avg_order_value,
    (SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE n >= 2) / COUNT(*), 1)
       FROM (SELECT COUNT(*) AS n FROM sales_orders WHERE order_status = 'COMPLETED' GROUP BY customer_id) t)                   AS repeat_customer_rate_pct,
    (SELECT ROUND(100.0 * COUNT(DISTINCT order_id) / (SELECT COUNT(*) FROM sales_orders WHERE order_status = 'COMPLETED'), 2)
       FROM returns)                                                                                                            AS order_return_rate_pct,
    (SELECT ROUND(SUM(inv.quantity_on_hand * p.unit_cost), 0) FROM inventory inv JOIN products p ON p.product_id = inv.product_id) AS inventory_value_at_cost;

-- Q402 | Products management should look at first
-- Business question: Among the products that generate 80 percent of revenue (Pareto class A), which show a warning sign?
-- Approach: for class-A products compute margin, 2025-vs-2024 growth, return rate and network stock cover; a CASE builds a list of flags.
-- Concepts: cumulative-share window (Pareto), CONCAT_WS to combine optional text, multiple CTEs, threshold flags.
-- Why it works: CONCAT_WS skips NULLs, so only the flags that apply are listed. The thresholds (margin below the company average,
--               revenue down more than 15 percent, return rate above 3 percent, under 30 days of cover) are project assumptions.
--               A flag means "look at this product", not "take action".
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders),
p AS (
    SELECT i.product_id,
           SUM(i.line_total / (1 + pr.gst_rate / 100.0)) AS revenue,
           SUM(i.line_total / (1 + pr.gst_rate / 100.0) - i.quantity * i.unit_cost) AS profit,
           SUM(i.line_total / (1 + pr.gst_rate / 100.0)) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2024) AS rev24,
           SUM(i.line_total / (1 + pr.gst_rate / 100.0)) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2025) AS rev25,
           SUM(i.quantity) FILTER (WHERE o.order_date::date > asof.d - 90) AS units_90d,
           SUM(i.quantity) AS units
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products pr ON pr.product_id = i.product_id
    CROSS JOIN asof
    GROUP BY i.product_id
), ranked AS (
    SELECT *, 100.0 * SUM(revenue) OVER (ORDER BY revenue DESC, product_id) / SUM(revenue) OVER () AS cum_share,
           100.0 * revenue / SUM(revenue) OVER () AS share,
           100.0 * SUM(profit) OVER () / SUM(revenue) OVER () AS company_margin
    FROM p
), stock AS (SELECT product_id, SUM(quantity_on_hand) AS on_hand FROM inventory GROUP BY product_id),
ret AS (
    SELECT i.product_id, SUM(ri.quantity) AS returned
    FROM return_items ri JOIN sales_order_items i ON i.order_item_id = ri.order_item_id GROUP BY i.product_id
)
SELECT pr.product_name, ROUND(r.revenue, 0) AS net_revenue, ROUND(100.0 * r.profit / r.revenue, 1) AS margin_pct,
       ROUND(100.0 * (r.rev25 / NULLIF(r.rev24, 0) - 1), 1) AS growth_2025_pct,
       ROUND(100.0 * COALESCE(rt.returned, 0) / r.units, 1) AS return_rate_pct,
       ROUND(COALESCE(st.on_hand, 0) / NULLIF(r.units_90d / 90.0, 0), 0) AS days_of_cover,
       CONCAT_WS('; ',
           CASE WHEN 100.0 * r.profit / r.revenue < r.company_margin THEN 'margin below company average' END,
           CASE WHEN r.rev25 < 0.85 * r.rev24 THEN 'revenue down more than 15 pct' END,
           CASE WHEN 100.0 * COALESCE(rt.returned, 0) / r.units > 3 THEN 'return rate above 3 pct' END,
           CASE WHEN COALESCE(st.on_hand, 0) / NULLIF(r.units_90d / 90.0, 0) < 30 THEN 'under 30 days of stock' END) AS flags
FROM ranked r
JOIN products pr ON pr.product_id = r.product_id
LEFT JOIN stock st ON st.product_id = r.product_id
LEFT JOIN ret rt ON rt.product_id = r.product_id
WHERE r.cum_share - r.share < 80
  AND (100.0 * r.profit / r.revenue < r.company_margin OR r.rev25 < 0.85 * r.rev24
       OR 100.0 * COALESCE(rt.returned, 0) / r.units > 3 OR COALESCE(st.on_hand, 0) / NULLIF(r.units_90d / 90.0, 0) < 30)
ORDER BY r.revenue DESC
LIMIT 20;

-- Q403 | Calculated metrics behind the operational insights
-- Business question: What are the main operational signals in the data, as numbers?
-- Approach: each row is one calculated metric produced by its own sub-query; the table is meant to be read with docs/05.
-- Concepts: UNION ALL of labelled scalar results, FILTER-based ratios, consistent definitions.
-- Why it works: keeping metrics in one table makes it easy to cite exact figures in the README and in interviews.
SELECT 'Growth' AS theme, 'Net revenue growth 2025 vs 2024 (pct)' AS metric,
       (SELECT ROUND(100.0 * (SUM(total_amount - gst_amount) FILTER (WHERE EXTRACT(YEAR FROM order_date) = 2025)
               / SUM(total_amount - gst_amount) FILTER (WHERE EXTRACT(YEAR FROM order_date) = 2024) - 1), 1)
        FROM sales_orders WHERE order_status = 'COMPLETED') AS value
UNION ALL SELECT 'Channel', 'Online share of net revenue in 2025 (pct)',
       (SELECT ROUND(100.0 * SUM(total_amount - gst_amount) FILTER (WHERE channel = 'ONLINE') / SUM(total_amount - gst_amount), 1)
        FROM sales_orders WHERE order_status = 'COMPLETED' AND EXTRACT(YEAR FROM order_date) = 2025)
UNION ALL SELECT 'Channel', 'Online share of net revenue in 2023 (pct)',
       (SELECT ROUND(100.0 * SUM(total_amount - gst_amount) FILTER (WHERE channel = 'ONLINE') / SUM(total_amount - gst_amount), 1)
        FROM sales_orders WHERE order_status = 'COMPLETED' AND EXTRACT(YEAR FROM order_date) = 2023)
UNION ALL SELECT 'Promotions', 'Gross margin on promoted lines (pct)',
       (SELECT ROUND(100.0 * SUM(i.line_total / (1 + p.gst_rate / 100.0) - i.quantity * i.unit_cost) / SUM(i.line_total / (1 + p.gst_rate / 100.0)), 1)
        FROM sales_order_items i JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
        JOIN products p ON p.product_id = i.product_id WHERE i.promotion_id IS NOT NULL)
UNION ALL SELECT 'Promotions', 'Gross margin on non-promoted lines (pct)',
       (SELECT ROUND(100.0 * SUM(i.line_total / (1 + p.gst_rate / 100.0) - i.quantity * i.unit_cost) / SUM(i.line_total / (1 + p.gst_rate / 100.0)), 1)
        FROM sales_order_items i JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
        JOIN products p ON p.product_id = i.product_id WHERE i.promotion_id IS NULL)
UNION ALL SELECT 'Customers', 'Share of revenue from the top 10 pct of buyers (pct)',
       (SELECT ROUND(100.0 * SUM(revenue) FILTER (WHERE decile = 10) / SUM(revenue), 1)
        FROM (SELECT SUM(total_amount - gst_amount) AS revenue, NTILE(10) OVER (ORDER BY SUM(total_amount - gst_amount)) AS decile
              FROM sales_orders WHERE order_status = 'COMPLETED' GROUP BY customer_id) t)
UNION ALL SELECT 'Products', 'Share of revenue from the top 20 pct of products (pct)',
       (SELECT ROUND(100.0 * SUM(revenue) FILTER (WHERE rn <= n * 0.2) / SUM(revenue), 1)
        FROM (SELECT SUM(i.line_total / (1 + p.gst_rate / 100.0)) AS revenue,
                     ROW_NUMBER() OVER (ORDER BY SUM(i.line_total / (1 + p.gst_rate / 100.0)) DESC) AS rn, COUNT(*) OVER () AS n
              FROM sales_order_items i JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
              JOIN products p ON p.product_id = i.product_id GROUP BY i.product_id) t)
UNION ALL SELECT 'Returns', 'Order return rate, online (pct)',
       (SELECT ROUND(100.0 * COUNT(DISTINCT r.order_id) / COUNT(DISTINCT o.order_id), 2)
        FROM sales_orders o LEFT JOIN returns r ON r.order_id = o.order_id WHERE o.order_status = 'COMPLETED' AND o.channel = 'ONLINE')
UNION ALL SELECT 'Returns', 'Order return rate, in-store (pct)',
       (SELECT ROUND(100.0 * COUNT(DISTINCT r.order_id) / COUNT(DISTINCT o.order_id), 2)
        FROM sales_orders o LEFT JOIN returns r ON r.order_id = o.order_id WHERE o.order_status = 'COMPLETED' AND o.channel = 'IN_STORE')
UNION ALL SELECT 'Suppliers', 'On-time delivery, all received POs (pct)',
       (SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE received_date <= expected_date) / COUNT(*), 1) FROM purchases WHERE status = 'RECEIVED')
UNION ALL SELECT 'Inventory', 'Positions at or below reorder level but not empty (pct)',
       (SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE quantity_on_hand > 0 AND quantity_on_hand <= reorder_level) / COUNT(*), 1) FROM inventory)
UNION ALL SELECT 'Inventory', 'Positions above max stock level (pct)',
       (SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE quantity_on_hand > max_stock_level) / COUNT(*), 1) FROM inventory);

-- Q404 | ABC analysis of inventory value
-- Business question: How is the money tied up in stock distributed across products?
-- Approach: value per product (all stores) at cost, cumulative share, class A = first 80 percent of value, B = next 15, C = last 5.
-- Concepts: cumulative SUM window, CASE classes, aggregate by class. This is the inventory twin of the revenue Pareto in Q52.
-- Why it works: a small group of A products holding most of the value deserves the tightest stock control.
--               The 80/15/5 split is a convention, so treat it as an assumption.
WITH product_value AS (
    SELECT inv.product_id, SUM(inv.quantity_on_hand * p.unit_cost) AS value
    FROM inventory inv JOIN products p ON p.product_id = inv.product_id GROUP BY inv.product_id HAVING SUM(inv.quantity_on_hand) > 0
), cumulative AS (
    SELECT product_id, value,
           100.0 * SUM(value) OVER (ORDER BY value DESC, product_id) / SUM(value) OVER () AS cum_share,
           100.0 * value / SUM(value) OVER () AS share
    FROM product_value
)
SELECT CASE WHEN cum_share - share < 80 THEN 'A' WHEN cum_share - share < 95 THEN 'B' ELSE 'C' END AS inventory_abc_class,
       COUNT(*) AS products, ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_of_products_pct,
       ROUND(SUM(value), 0) AS stock_value_at_cost, ROUND(100.0 * SUM(value) / SUM(SUM(value)) OVER (), 1) AS share_of_value_pct
FROM cumulative
GROUP BY 1
ORDER BY 1;

-- Q405 | Where to find the answer to each of the 50 business questions
-- Business question: Which query answers which management question?
-- Approach: a VALUES list acts as an inline lookup table (question number, question, query ids).
-- Concepts: VALUES as a table, derived table with column aliases.
-- Why it works: keeps the mapping inside the database so it can be queried and filtered like any other data.
SELECT * FROM (VALUES
 (1, 'Total revenue', 'Q03, Q401'), (2, 'Total profit', 'Q04, Q401'), (3, 'Total orders', 'Q02'), (4, 'Average order value', 'Q05'),
 (5, 'Monthly revenue', 'Q13'), (6, 'Year-over-year growth', 'Q14, Q26'), (7, 'Monthly sales growth', 'Q15'),
 (8, 'Top 10 products by revenue', 'Q16'), (9, 'Top 10 products by quantity', 'Q17'), (10, 'Top categories', 'Q18'),
 (11, 'Top stores', 'Q19, Q72'), (12, 'Revenue by city', 'Q19, Q20'), (13, 'Revenue by customer segment', 'Q37'),
 (14, 'Repeat customers', 'Q33'), (15, 'Customer lifetime value', 'Q32, Q42'), (16, 'First purchase date', 'Q32'),
 (17, 'Most recent purchase date', 'Q32, Q43'), (18, 'Customer purchase frequency', 'Q36, Q45'), (19, 'Customers with no purchases', 'Q34, Q35'),
 (20, 'Products never sold', 'Q49'), (21, 'Fast-moving products', 'Q64, Q65'), (22, 'Slow-moving products', 'Q64, Q65'),
 (23, 'Low-stock products', 'Q60, Q61'), (24, 'Out-of-stock products', 'Q60'), (25, 'Overstocked products', 'Q60, Q68'),
 (26, 'Inventory value', 'Q59'), (27, 'Inventory turnover', 'Q62'), (28, 'Stock coverage', 'Q63'), (29, 'Return rate', 'Q89, Q92-Q94'),
 (30, 'Revenue lost due to returns', 'Q95'), (31, 'Promotion performance', 'Q28'), (32, 'Discount impact', 'Q27'),
 (33, 'Store performance', 'Q72-Q80'), (34, 'Supplier performance', 'Q81-Q88'), (35, 'Category growth', 'Q50'),
 (36, 'Products with declining sales', 'Q51'), (37, 'High-revenue low-stock products', 'Q67, Q69'), (38, 'Low-revenue high-stock products', 'Q68, Q69'),
 (39, 'Best-selling product per category', 'Q48'), (40, 'Top customer per store', 'Q44'), (41, 'Monthly revenue ranking', 'Q24'),
 (42, 'Running revenue total', 'Q22'), (43, '3-month moving average', 'Q23'), (44, 'Repeat customer percentage', 'Q33'),
 (45, 'Customer segmentation', 'Q39, Q40'), (46, 'ABC inventory analysis', 'Q404'), (47, 'Pareto analysis', 'Q52'),
 (48, 'Revenue contribution by product', 'Q52, Q53'), (49, 'Sales concentration', 'Q53, Q46'), (50, 'Inventory risk analysis', 'Q71, Q60')
) AS q(question_no, business_question, query_ids)
ORDER BY question_no;

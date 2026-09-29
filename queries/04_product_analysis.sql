-- =============================================================================
-- 04_product_analysis.sql : product profitability, growth/decline, Pareto (ABC), concentration
-- Definitions: completed orders only; net revenue excludes GST; profit = net revenue - quantity * unit_cost.
-- =============================================================================

-- Q47 | Product performance scorecard (top 20 by revenue)
-- Business question: For the biggest products, what are revenue, profit, margin and return rate?
-- Approach: aggregate sales per product in one CTE and returned units per product in another, then join them.
-- Concepts: multiple CTEs, LEFT JOIN, RANK, ratio metrics, aggregating BEFORE joining to avoid double counting.
-- Why it works: joining return_items directly to order lines would multiply sales rows; pre-aggregating each side keeps one row per product.
WITH sales AS (
    SELECT i.product_id,
           SUM(i.quantity)                                                          AS units_sold,
           SUM(i.line_total / (1 + p.gst_rate / 100.0))                             AS net_revenue,
           SUM(i.line_total / (1 + p.gst_rate / 100.0) - i.quantity * i.unit_cost)  AS gross_profit
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products p ON p.product_id = i.product_id
    GROUP BY i.product_id
), returned AS (
    SELECT i.product_id, SUM(ri.quantity) AS units_returned
    FROM return_items ri
    JOIN sales_order_items i ON i.order_item_id = ri.order_item_id
    GROUP BY i.product_id
)
SELECT p.product_id, p.product_name, s.units_sold,
       ROUND(s.net_revenue, 0)                                   AS net_revenue,
       ROUND(s.gross_profit, 0)                                  AS gross_profit,
       ROUND(100.0 * s.gross_profit / s.net_revenue, 1)          AS margin_pct,
       ROUND(100.0 * COALESCE(r.units_returned, 0) / s.units_sold, 2) AS return_rate_pct,
       RANK() OVER (ORDER BY s.net_revenue DESC)                 AS revenue_rank
FROM sales s
JOIN products p ON p.product_id = s.product_id
LEFT JOIN returned r ON r.product_id = s.product_id
ORDER BY revenue_rank
LIMIT 20;

-- Q48 | Best-selling product in every category
-- Business question: What is the leading product of each category?
-- Approach: rank products by revenue inside each (case-merged) category with ROW_NUMBER and keep rank 1.
-- Concepts: window function in a subquery, PARTITION BY, top-1-per-group, canonical category via MIN() OVER.
-- Why it works: ROW_NUMBER restarts per category, so filtering rn = 1 returns exactly one product per category.
WITH canon AS (
    SELECT category_id, MIN(category_id) OVER (PARTITION BY LOWER(category_name)) AS canonical_id
    FROM categories
), product_sales AS (
    SELECT p.product_id, p.product_name, c.canonical_id AS category_id,
           SUM(i.line_total / (1 + p.gst_rate / 100.0)) AS net_revenue
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products p ON p.product_id = i.product_id
    JOIN canon c ON c.category_id = p.category_id
    GROUP BY p.product_id, p.product_name, c.canonical_id
), ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY category_id ORDER BY net_revenue DESC) AS rn,
           SUM(net_revenue) OVER (PARTITION BY category_id) AS category_revenue
    FROM product_sales
)
SELECT cat.category_name, r.product_name, ROUND(r.net_revenue, 0) AS net_revenue,
       ROUND(100.0 * r.net_revenue / r.category_revenue, 1) AS share_of_category_pct
FROM ranked r
JOIN categories cat ON cat.category_id = r.category_id
WHERE r.rn = 1
ORDER BY r.net_revenue DESC;

-- Q49 | Products that have never been sold
-- Business question: Which catalogue items have zero sales and how much stock are they holding?
-- Approach: NOT EXISTS anti-join against completed sales; LEFT JOIN inventory to value the stock at cost.
-- Concepts: NOT EXISTS, LEFT JOIN with aggregated inventory, COALESCE.
-- Why it works: NOT EXISTS stops at the first matching sale per product, so it is efficient and NULL-safe.
SELECT p.product_id, p.sku, p.product_name, p.is_active,
       COALESCE(SUM(inv.quantity_on_hand), 0)                       AS units_in_stock,
       ROUND(COALESCE(SUM(inv.quantity_on_hand * p.unit_cost), 0), 0) AS stock_value_at_cost
FROM products p
LEFT JOIN inventory inv ON inv.product_id = p.product_id
WHERE NOT EXISTS (
        SELECT 1 FROM sales_order_items i
        JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
        WHERE i.product_id = p.product_id)
GROUP BY p.product_id, p.sku, p.product_name, p.is_active
ORDER BY stock_value_at_cost DESC;

-- Q50 | Category growth by year
-- Business question: Which categories are growing and which are shrinking?
-- Approach: conditional aggregation gives one column per year; growth compares consecutive years.
-- Concepts: SUM(...) FILTER by year, NULLIF, canonical category, percentage change.
-- Why it works: a manual pivot keeps the query readable and lets the growth formula reference the yearly columns.
WITH canon AS (
    SELECT category_id, MIN(category_id) OVER (PARTITION BY LOWER(category_name)) AS canonical_id
    FROM categories
), yearly AS (
    SELECT COALESCE(cat.category_name, '(no category)') AS category,
           SUM(i.line_total / (1 + p.gst_rate / 100.0)) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2023) AS rev_2023,
           SUM(i.line_total / (1 + p.gst_rate / 100.0)) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2024) AS rev_2024,
           SUM(i.line_total / (1 + p.gst_rate / 100.0)) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2025) AS rev_2025
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products p ON p.product_id = i.product_id
    LEFT JOIN canon c ON c.category_id = p.category_id
    LEFT JOIN categories cat ON cat.category_id = c.canonical_id
    GROUP BY 1
)
SELECT category, ROUND(rev_2023, 0) AS rev_2023, ROUND(rev_2024, 0) AS rev_2024, ROUND(rev_2025, 0) AS rev_2025,
       ROUND(100.0 * (rev_2024 / NULLIF(rev_2023, 0) - 1), 1) AS growth_2024_pct,
       ROUND(100.0 * (rev_2025 / NULLIF(rev_2024, 0) - 1), 1) AS growth_2025_pct,
       CASE WHEN rev_2025 < rev_2024 AND rev_2024 < rev_2023 THEN 'Declining two years in a row'
            WHEN rev_2025 < rev_2024 THEN 'Declined in 2025' ELSE 'Growing / stable' END AS trend_flag
FROM yearly
ORDER BY growth_2025_pct;

-- Q51 | Products with declining sales (2025 versus 2024)
-- Business question: Which meaningful products lost at least 20 percent of their revenue year on year?
-- Approach: yearly revenue per product with FILTER; keep products that sold in both years with a minimum volume.
-- Concepts: FILTER, HAVING on an aggregate expression, CASE flag for discontinued products.
-- Why it works: the volume floor (30+ units in 2024) avoids flagging tiny products whose percentage swings are just noise.
SELECT p.product_id, p.product_name, p.is_active,
       ROUND(SUM(i.line_total / (1 + p.gst_rate / 100.0)) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2024), 0) AS rev_2024,
       ROUND(SUM(i.line_total / (1 + p.gst_rate / 100.0)) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2025), 0) AS rev_2025,
       ROUND(100.0 * (SUM(i.line_total) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2025)
                     / SUM(i.line_total) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2024) - 1), 1) AS change_pct
FROM sales_order_items i
JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
JOIN products p ON p.product_id = i.product_id
GROUP BY p.product_id, p.product_name, p.is_active
HAVING SUM(i.quantity) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2024) >= 30
   AND SUM(i.line_total) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2025)
       <= 0.8 * SUM(i.line_total) FILTER (WHERE EXTRACT(YEAR FROM o.order_date) = 2024)
ORDER BY change_pct
LIMIT 25;

-- Q52 | Pareto (80/20) and ABC classification of products
-- Business question: How few products deliver most of the revenue?
-- Approach: rank products by revenue, compute cumulative revenue share, then label A (first 80 percent), B (next 15), C (last 5).
-- Concepts: SUM() OVER (ORDER BY ... ), cumulative percentage, CASE, aggregate of the classified rows.
-- Why it works: the running share at a product tells what fraction of revenue is earned by that product and all better ones.
--               The 80/15/5 cut-offs are a common convention, not a law - they are project assumptions.
WITH product_rev AS (
    SELECT i.product_id, SUM(i.line_total / (1 + p.gst_rate / 100.0)) AS revenue
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products p ON p.product_id = i.product_id
    GROUP BY i.product_id
), cumulative AS (
    SELECT product_id, revenue,
           100.0 * SUM(revenue) OVER (ORDER BY revenue DESC, product_id) / SUM(revenue) OVER () AS cum_share
    FROM product_rev
), classed AS (
    SELECT *, CASE WHEN cum_share - 100.0 * revenue / SUM(revenue) OVER () < 80 THEN 'A'
                   WHEN cum_share - 100.0 * revenue / SUM(revenue) OVER () < 95 THEN 'B'
                   ELSE 'C' END AS abc_class
    FROM cumulative
)
SELECT abc_class,
       COUNT(*)                                           AS products,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_of_products_pct,
       ROUND(SUM(revenue), 0)                             AS net_revenue,
       ROUND(100.0 * SUM(revenue) / SUM(SUM(revenue)) OVER (), 1) AS share_of_revenue_pct
FROM classed
GROUP BY abc_class
ORDER BY abc_class;

-- Q53 | Sales concentration
-- Business question: How concentrated is revenue among a small number of products?
-- Approach: rank products, then sum revenue of the top 10, top 50 and top 20 percent; add the Herfindahl index (HHI).
-- Concepts: ROW_NUMBER, PERCENT_RANK-free cut-offs via COUNT, conditional SUM, sum of squared shares.
-- Why it works: HHI = sum of squared revenue shares; values near 0 mean revenue is spread widely, 1 means one product has all of it.
WITH product_rev AS (
    SELECT i.product_id, SUM(i.line_total / (1 + p.gst_rate / 100.0)) AS revenue
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products p ON p.product_id = i.product_id
    GROUP BY i.product_id
), ranked AS (
    SELECT revenue, ROW_NUMBER() OVER (ORDER BY revenue DESC) AS rn, COUNT(*) OVER () AS n,
           revenue / SUM(revenue) OVER () AS share
    FROM product_rev
)
SELECT MAX(n)                                                              AS products_sold,
       ROUND(100.0 * SUM(share) FILTER (WHERE rn <= 10), 1)                AS top_10_products_share_pct,
       ROUND(100.0 * SUM(share) FILTER (WHERE rn <= 50), 1)                AS top_50_products_share_pct,
       ROUND(100.0 * SUM(share) FILTER (WHERE rn <= n * 0.2), 1)           AS top_20pct_products_share_pct,
       ROUND(SUM(share * share)::numeric, 4)                               AS herfindahl_index
FROM ranked;

-- Q54 | Three highest-margin products in every category
-- Business question: Which products are the most profitable per rupee of revenue, category by category?
-- Approach: margin % per product with a minimum sales volume, RANK within category, keep the top 3.
-- Concepts: HAVING for a volume floor, RANK() OVER (PARTITION BY ...), top-N-per-group.
-- Why it works: RANK allows ties (two products with an identical margin share a rank), unlike ROW_NUMBER.
WITH product_margin AS (
    SELECT p.product_id, p.product_name, COALESCE(p.category_id, 0) AS category_id,
           SUM(i.quantity) AS units,
           SUM(i.line_total / (1 + p.gst_rate / 100.0) - i.quantity * i.unit_cost)
             / SUM(i.line_total / (1 + p.gst_rate / 100.0)) AS margin
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products p ON p.product_id = i.product_id
    GROUP BY p.product_id, p.product_name, p.category_id
    HAVING SUM(i.quantity) >= 50
), ranked AS (
    SELECT *, RANK() OVER (PARTITION BY category_id ORDER BY margin DESC) AS margin_rank
    FROM product_margin
)
SELECT COALESCE(c.category_name, '(no category)') AS category, r.product_name, r.units,
       ROUND(100.0 * r.margin, 1) AS margin_pct, r.margin_rank
FROM ranked r
LEFT JOIN categories c ON c.category_id = r.category_id
WHERE r.margin_rank <= 3
ORDER BY category, r.margin_rank;

-- Q55 | Performance by price band
-- Business question: Do cheap, mid-range or premium products drive revenue and profit?
-- Approach: assign the band from the product's list price, aggregate sales per band.
-- Concepts: CASE band, JOIN, ratio of sums, percent of total.
-- Why it works: bands turn a continuous price into a few comparable groups.
SELECT CASE WHEN p.unit_price < 500   THEN 'a) Under 500'
            WHEN p.unit_price < 2000  THEN 'b) 500 - 1,999'
            WHEN p.unit_price < 10000 THEN 'c) 2,000 - 9,999'
            ELSE 'd) 10,000 and above' END AS price_band,
       COUNT(DISTINCT p.product_id)                                           AS products_sold,
       SUM(i.quantity)                                                        AS units,
       ROUND(SUM(i.line_total / (1 + p.gst_rate / 100.0)), 0)                 AS net_revenue,
       ROUND(100.0 * SUM(i.line_total / (1 + p.gst_rate / 100.0)) / SUM(SUM(i.line_total / (1 + p.gst_rate / 100.0))) OVER (), 1) AS revenue_share_pct,
       ROUND(100.0 * SUM(i.line_total / (1 + p.gst_rate / 100.0) - i.quantity * i.unit_cost)
             / SUM(i.line_total / (1 + p.gst_rate / 100.0)), 1)               AS margin_pct
FROM sales_order_items i
JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
JOIN products p ON p.product_id = i.product_id
GROUP BY 1
ORDER BY 1;

-- Q56 | Products frequently bought together (SELF JOIN)
-- Business question: Which product pairs appear in the same basket most often?
-- Approach: join the order-lines table to itself on order_id; the condition a.product_id < b.product_id keeps each pair once.
-- Concepts: SELF JOIN, pair de-duplication with an inequality, HAVING, LIMIT.
-- Why it works: without the < condition each pair would appear twice (A,B and B,A) and every line would pair with itself.
--               Co-occurrence counts show association only - they do not prove one product causes the other to sell.
SELECT pa.product_name AS product_a, pb.product_name AS product_b, COUNT(*) AS orders_together
FROM sales_order_items a
JOIN sales_order_items b ON b.order_id = a.order_id AND a.product_id < b.product_id
JOIN sales_orders o ON o.order_id = a.order_id AND o.order_status = 'COMPLETED'
JOIN products pa ON pa.product_id = a.product_id
JOIN products pb ON pb.product_id = b.product_id
GROUP BY pa.product_name, pb.product_name
HAVING COUNT(*) >= 5
ORDER BY orders_together DESC
LIMIT 10;

-- Q57 | Revenue from products launched during the data window
-- Business question: How much of revenue comes from newly launched products?
-- Approach: label each product as 'Existing' or by launch year, then aggregate sales.
-- Concepts: CASE on dates, EXTRACT(YEAR), grouping on a derived label.
-- Why it works: products launched on or before the first order date existed for the whole window; later launches are 'new'.
SELECT CASE WHEN p.launch_date < DATE '2023-01-01' THEN 'Launched before 2023'
            ELSE 'Launched in ' || EXTRACT(YEAR FROM p.launch_date)::int END AS launch_group,
       COUNT(DISTINCT p.product_id)                             AS products_sold,
       ROUND(SUM(i.line_total / (1 + p.gst_rate / 100.0)), 0)   AS net_revenue,
       ROUND(100.0 * SUM(i.line_total / (1 + p.gst_rate / 100.0)) / SUM(SUM(i.line_total / (1 + p.gst_rate / 100.0))) OVER (), 1) AS revenue_share_pct
FROM sales_order_items i
JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
JOIN products p ON p.product_id = i.product_id
GROUP BY 1
ORDER BY 1;

-- Q58 | Brand performance (top 10 brands)
-- Business question: Which brands contribute the most revenue?
-- Approach: group by brand; products without a brand are labelled rather than dropped.
-- Concepts: COALESCE on a grouping key, aggregate, LIMIT.
-- Why it works: dropping NULL brands would silently understate total revenue, so they get a visible label.
SELECT COALESCE(p.brand, '(brand missing)') AS brand,
       COUNT(DISTINCT p.product_id)          AS products,
       SUM(i.quantity)                       AS units,
       ROUND(SUM(i.line_total / (1 + p.gst_rate / 100.0)), 0) AS net_revenue,
       ROUND(100.0 * SUM(i.line_total / (1 + p.gst_rate / 100.0) - i.quantity * i.unit_cost)
             / SUM(i.line_total / (1 + p.gst_rate / 100.0)), 1) AS margin_pct
FROM sales_order_items i
JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
JOIN products p ON p.product_id = i.product_id
GROUP BY 1
ORDER BY net_revenue DESC
LIMIT 10;

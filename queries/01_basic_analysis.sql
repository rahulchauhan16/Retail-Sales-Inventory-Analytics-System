-- =============================================================================
-- 01_basic_analysis.sql : foundation queries (SELECT, WHERE, GROUP BY, HAVING, JOIN, CASE)
--
-- Definitions used across ALL query files (see docs/06 and docs/08 for the KPI glossary):
--   * "Sold" / "revenue" only counts orders with order_status = 'COMPLETED'.
--   * Prices are GST-inclusive (Indian MRP). NET revenue = line_total / (1 + gst_rate/100).
--   * Profit = net revenue - quantity * unit_cost   (unit_cost is ex-GST, snapshot at sale).
--   * "As of" date = the last order date in the data (the data is a fixed synthetic window).
-- =============================================================================

-- Q01 | Row counts of every main table
-- Business question: How big is the dataset and is everything loaded?
-- Approach: one tiny SELECT per table glued together with UNION ALL.
-- Concepts: UNION ALL, literal columns, COUNT(*).
-- Why it works: UNION ALL stacks result sets that have the same column list without removing rows.
SELECT 'customers' AS table_name, COUNT(*) AS row_count FROM customers
UNION ALL SELECT 'products', COUNT(*) FROM products
UNION ALL SELECT 'sales_orders', COUNT(*) FROM sales_orders
UNION ALL SELECT 'sales_order_items', COUNT(*) FROM sales_order_items
UNION ALL SELECT 'payments', COUNT(*) FROM payments
UNION ALL SELECT 'returns', COUNT(*) FROM returns
UNION ALL SELECT 'inventory', COUNT(*) FROM inventory
UNION ALL SELECT 'inventory_transactions', COUNT(*) FROM inventory_transactions
UNION ALL SELECT 'purchases', COUNT(*) FROM purchases
ORDER BY row_count DESC;

-- Q02 | Total orders, cancelled orders and cancellation rate
-- Business question: How many orders were placed and how many were cancelled?
-- Approach: conditional aggregation, COUNT(*) FILTER (WHERE ...) counts only matching rows.
-- Concepts: FILTER clause, NULLIF to avoid divide-by-zero, ROUND.
-- Why it works: FILTER lets one scan of the table produce several counts side by side.
SELECT COUNT(*)                                            AS total_orders,
       COUNT(*) FILTER (WHERE order_status = 'COMPLETED')  AS completed_orders,
       COUNT(*) FILTER (WHERE order_status = 'CANCELLED')  AS cancelled_orders,
       ROUND(100.0 * COUNT(*) FILTER (WHERE order_status = 'CANCELLED') / NULLIF(COUNT(*), 0), 2) AS cancellation_rate_pct
FROM sales_orders;

-- Q03 | Total revenue (gross and net of GST)
-- Business question: How much revenue did the business generate?
-- Approach: sum completed order totals; net revenue = total minus the GST component stored on the order.
-- Concepts: WHERE, SUM, arithmetic on aggregates.
-- Why it works: total_amount is GST-inclusive; gst_amount is the tax portion inside it.
SELECT SUM(total_amount)                   AS gross_sales_incl_gst,
       SUM(gst_amount)                     AS gst_collected,
       SUM(total_amount - gst_amount)      AS net_revenue,
       SUM(discount_amount)                AS discounts_given
FROM sales_orders
WHERE order_status = 'COMPLETED';

-- Q04 | Total profit and gross margin %
-- Business question: How much gross profit did we make and at what margin?
-- Approach: join order lines to products for the GST rate, then subtract cost from net revenue.
-- Concepts: JOIN, expression in SUM, percentage calculation.
-- Why it works: unit_cost was snapshotted on each line, so profit uses the cost at the time of sale.
SELECT ROUND(SUM(i.line_total / (1 + p.gst_rate / 100.0)), 2)                          AS net_revenue,
       ROUND(SUM(i.quantity * i.unit_cost), 2)                                          AS cost_of_goods_sold,
       ROUND(SUM(i.line_total / (1 + p.gst_rate / 100.0) - i.quantity * i.unit_cost), 2) AS gross_profit,
       ROUND(100.0 * SUM(i.line_total / (1 + p.gst_rate / 100.0) - i.quantity * i.unit_cost)
             / SUM(i.line_total / (1 + p.gst_rate / 100.0)), 2)                         AS gross_margin_pct
FROM sales_order_items i
JOIN sales_orders o ON o.order_id = i.order_id
JOIN products p     ON p.product_id = i.product_id
WHERE o.order_status = 'COMPLETED';

-- Q05 | Average order value (AOV)
-- Business question: How much does an average completed order bring in?
-- Approach: AVG of order totals, plus median for comparison because order values are skewed.
-- Concepts: AVG, PERCENTILE_CONT (ordered-set aggregate).
-- Why it works: a large gap between mean and median signals a few very large orders pulling the mean up.
SELECT ROUND(AVG(total_amount), 2)                                        AS avg_order_value,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_amount)::numeric, 2) AS median_order_value,
       MAX(total_amount)                                                   AS largest_order
FROM sales_orders
WHERE order_status = 'COMPLETED';

-- Q06 | Customer counts: total, ever purchased, never purchased
-- Business question: How many customers do we have and how many actually bought?
-- Approach: LEFT JOIN customers to their completed orders; customers with no match have NULL order_id.
-- Concepts: LEFT JOIN, COUNT(DISTINCT), conditional counting.
-- Why it works: LEFT JOIN keeps customers without orders; COUNT(o.order_id) ignores those NULLs.
SELECT COUNT(DISTINCT c.customer_id)                                        AS total_customers,
       COUNT(DISTINCT o.customer_id)                                        AS customers_who_purchased,
       COUNT(DISTINCT c.customer_id) - COUNT(DISTINCT o.customer_id)        AS customers_never_purchased,
       COUNT(DISTINCT c.customer_id) FILTER (WHERE c.is_active)             AS flagged_active
FROM customers c
LEFT JOIN sales_orders o ON o.customer_id = c.customer_id AND o.order_status = 'COMPLETED';

-- Q07 | Orders and revenue by sales channel
-- Business question: How much comes from online versus in-store?
-- Approach: group by channel and show each channel's share of the total using a window over the groups.
-- Concepts: GROUP BY, SUM() OVER () as a grand total, percent contribution.
-- Why it works: the window function runs after GROUP BY, so SUM(SUM(x)) OVER () is the total of all groups.
SELECT channel,
       COUNT(*)                                                       AS orders,
       SUM(total_amount - gst_amount)                                 AS net_revenue,
       ROUND(100.0 * SUM(total_amount - gst_amount) / SUM(SUM(total_amount - gst_amount)) OVER (), 2) AS revenue_share_pct
FROM sales_orders
WHERE order_status = 'COMPLETED'
GROUP BY channel
ORDER BY net_revenue DESC;

-- Q08 | Products per category, including products with no category
-- Business question: How is the catalogue distributed across categories?
-- Approach: LEFT JOIN so uncategorised products are not lost; COALESCE gives them a readable label.
-- Concepts: LEFT JOIN, COALESCE, GROUP BY, HAVING.
-- Why it works: HAVING filters after grouping (here: categories with at least one product).
SELECT COALESCE(c.category_name, '(no category)') AS category,
       COUNT(*)                                    AS products,
       COUNT(*) FILTER (WHERE p.is_active)         AS active_products
FROM products p
LEFT JOIN categories c ON c.category_id = p.category_id
GROUP BY COALESCE(c.category_name, '(no category)')
HAVING COUNT(*) >= 1
ORDER BY products DESC, category;

-- Q09 | Store directory with years open
-- Business question: Which stores exist, where are they, and how long have they operated?
-- Approach: date arithmetic against the as-of date.
-- Concepts: CTE for the as-of date, AGE / EXTRACT, ORDER BY on several columns.
-- Why it works: the CTE computes the as-of date once and is cross-joined to every store row.
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders)
SELECT s.store_code, s.store_name, s.city, s.state, s.region, s.store_type, s.opened_date,
       ROUND((asof.d - s.opened_date) / 365.25, 1) AS years_open
FROM stores s
CROSS JOIN asof
ORDER BY s.region, s.opened_date;

-- Q10 | Catalogue price bands
-- Business question: How is the product range spread across price points?
-- Approach: bucket unit_price with CASE and count products and average margin in each bucket.
-- Concepts: CASE, GROUP BY on a derived column, ordering with a helper column.
-- Why it works: the sort key (band_order) keeps bands in price order instead of alphabetical order.
SELECT CASE WHEN unit_price < 500   THEN 'a) Under 500'
            WHEN unit_price < 2000  THEN 'b) 500 - 1,999'
            WHEN unit_price < 10000 THEN 'c) 2,000 - 9,999'
            ELSE                         'd) 10,000 and above' END AS price_band,
       COUNT(*)                                                     AS products,
       ROUND(AVG(100.0 * (unit_price / (1 + gst_rate / 100.0) - unit_cost)
                 / (unit_price / (1 + gst_rate / 100.0))), 1)       AS avg_list_margin_pct
FROM products
GROUP BY 1
ORDER BY 1;

-- Q11 | Orders by day of week
-- Business question: Which weekdays are busiest?
-- Approach: extract ISO day-of-week (1 = Monday) and name it.
-- Concepts: EXTRACT, TO_CHAR, date functions.
-- Why it works: ISODOW is stable and starts Monday, which is convenient for weekday-versus-weekend logic.
SELECT EXTRACT(ISODOW FROM order_date)::int  AS iso_day,
       TO_CHAR(order_date, 'Day')            AS day_name,
       COUNT(*)                              AS orders,
       ROUND(AVG(total_amount), 2)           AS avg_order_value
FROM sales_orders
WHERE order_status = 'COMPLETED'
GROUP BY 1, 2
ORDER BY 1;

-- Q12 | First and last order dates and data window length
-- Business question: What period does the data cover?
-- Approach: MIN / MAX of order_date and the span in days and months.
-- Concepts: MIN, MAX, date subtraction, AGE.
-- Why it works: subtracting two dates gives an integer number of days in PostgreSQL.
SELECT MIN(order_date)::date                      AS first_order,
       MAX(order_date)::date                      AS last_order,
       MAX(order_date)::date - MIN(order_date)::date AS days_covered,
       AGE(MAX(order_date), MIN(order_date))      AS span
FROM sales_orders;

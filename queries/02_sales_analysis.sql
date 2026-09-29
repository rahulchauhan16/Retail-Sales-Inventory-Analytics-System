-- =============================================================================
-- 02_sales_analysis.sql : revenue trends, growth, ranking, running totals, promotions
-- Definitions: see the header of 01_basic_analysis.sql (completed orders only, net revenue = ex-GST).
-- NOTE: The "sales" CTE is repeated in several queries so each one can be run on its own.
--       In database/views.sql (Phase 8) the same logic is packaged once as reusable views.
-- =============================================================================

-- Q13 | Monthly revenue trend
-- Business question: How does revenue move month by month?
-- Approach: bucket order_date to the first day of its month with DATE_TRUNC and aggregate.
-- Concepts: DATE_TRUNC, GROUP BY, COUNT, SUM, AVG.
-- Why it works: DATE_TRUNC('month', ts) maps every timestamp in a month to one value, which we group on.
SELECT DATE_TRUNC('month', order_date)::date AS month,
       COUNT(*)                              AS orders,
       SUM(total_amount - gst_amount)        AS net_revenue,
       ROUND(AVG(total_amount), 2)           AS avg_order_value
FROM sales_orders
WHERE order_status = 'COMPLETED'
GROUP BY 1
ORDER BY 1;

-- Q14 | Year-over-year revenue growth
-- Business question: Is the business growing year on year?
-- Approach: aggregate to one row per year, then LAG() to fetch the previous year's revenue on the same row.
-- Concepts: CTE, LAG window function, growth % formula (current / previous - 1).
-- Why it works: LAG(x) OVER (ORDER BY year) looks one row back in year order; the first year has no previous, so growth is NULL.
WITH yearly AS (
    SELECT EXTRACT(YEAR FROM order_date)::int AS yr,
           COUNT(*)                           AS orders,
           SUM(total_amount - gst_amount)     AS net_revenue
    FROM sales_orders
    WHERE order_status = 'COMPLETED'
    GROUP BY 1
)
SELECT yr, orders, ROUND(net_revenue, 0) AS net_revenue,
       ROUND(LAG(net_revenue) OVER (ORDER BY yr), 0)                                     AS previous_year_revenue,
       ROUND(100.0 * (net_revenue / LAG(net_revenue) OVER (ORDER BY yr) - 1), 2)         AS yoy_growth_pct
FROM yearly
ORDER BY yr;

-- Q15 | Month-over-month growth
-- Business question: Which months grew or fell versus the previous month?
-- Approach: same LAG pattern on a monthly series, with NULLIF protecting against division by zero.
-- Concepts: CTE, LAG, NULLIF, ROUND.
-- Why it works: the monthly CTE gives one ordered row per month, so LAG compares neighbouring months.
WITH monthly AS (
    SELECT DATE_TRUNC('month', order_date)::date AS month, SUM(total_amount - gst_amount) AS revenue
    FROM sales_orders
    WHERE order_status = 'COMPLETED'
    GROUP BY 1
)
SELECT month, ROUND(revenue, 0) AS revenue,
       ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
             / NULLIF(LAG(revenue) OVER (ORDER BY month), 0), 2) AS mom_growth_pct
FROM monthly
ORDER BY month;

-- Q16 | Top 10 products by revenue
-- Business question: Which products earn the most?
-- Approach: join order lines to products, aggregate net revenue and units, sort, LIMIT.
-- Concepts: multi-table JOIN, GROUP BY, ORDER BY ... DESC, LIMIT.
-- Why it works: one row per product after grouping; LIMIT 10 keeps the top of the sorted list.
SELECT p.product_id, p.product_name,
       SUM(i.quantity)                                          AS units_sold,
       ROUND(SUM(i.line_total / (1 + p.gst_rate / 100.0)), 0)   AS net_revenue
FROM sales_order_items i
JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
JOIN products p     ON p.product_id = i.product_id
GROUP BY p.product_id, p.product_name
ORDER BY net_revenue DESC
LIMIT 10;

-- Q17 | Top 10 products by quantity sold
-- Business question: Which products move the most units (volume rather than value)?
-- Approach: same as Q16 but sorted by units, with revenue per unit shown to expose cheap high-volume items.
-- Concepts: JOIN, aggregation, derived ratio.
-- Why it works: the volume ranking is very different from the revenue ranking because unit prices vary from 40 to 100,000 rupees.
SELECT p.product_id, p.product_name,
       SUM(i.quantity)                                                       AS units_sold,
       ROUND(SUM(i.line_total / (1 + p.gst_rate / 100.0)) / SUM(i.quantity), 2) AS net_revenue_per_unit
FROM sales_order_items i
JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
JOIN products p     ON p.product_id = i.product_id
GROUP BY p.product_id, p.product_name
ORDER BY units_sold DESC
LIMIT 10;

-- Q18 | Category revenue with percent contribution (case-variant categories merged)
-- Business question: Which categories perform best and what share of revenue does each hold?
-- Approach: some categories exist twice with different capitalisation (a data-quality issue). A window function assigns
--           every variant the smallest category_id among names that match ignoring case; we then group on that id.
-- Concepts: MIN() OVER (PARTITION BY ...), multiple CTEs, COALESCE, percent contribution with SUM() OVER ().
-- Why it works: PARTITION BY LOWER(name) puts 'Footwear' and 'FOOTWEAR' in one partition, so both share one canonical id.
WITH canon AS (
    SELECT category_id, MIN(category_id) OVER (PARTITION BY LOWER(category_name)) AS canonical_id
    FROM categories
), by_cat AS (
    SELECT COALESCE(cc.category_name, '(no category)') AS category,
           SUM(i.quantity)                                        AS units_sold,
           SUM(i.line_total / (1 + p.gst_rate / 100.0))           AS net_revenue
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products p     ON p.product_id = i.product_id
    LEFT JOIN canon c   ON c.category_id = p.category_id
    LEFT JOIN categories cc ON cc.category_id = c.canonical_id
    GROUP BY 1
)
SELECT category, units_sold, ROUND(net_revenue, 0) AS net_revenue,
       ROUND(100.0 * net_revenue / SUM(net_revenue) OVER (), 2)                                AS revenue_share_pct,
       ROUND(100.0 * SUM(net_revenue) OVER (ORDER BY net_revenue DESC) / SUM(net_revenue) OVER (), 2) AS cumulative_share_pct
FROM by_cat
ORDER BY net_revenue DESC;

-- Q19 | Revenue by store city and region
-- Business question: Which locations bring in the most revenue?
-- Approach: join orders to stores and group by city; the online hub is shown as its own row.
-- Concepts: JOIN, GROUP BY on several columns, RANK.
-- Why it works: the hub is a warehouse in Mumbai, so we group on store_type as well to keep it separate from the Mumbai shop.
SELECT s.city, s.region, s.store_type,
       COUNT(*)                                                                 AS orders,
       ROUND(SUM(o.total_amount - o.gst_amount), 0)                             AS net_revenue,
       RANK() OVER (ORDER BY SUM(o.total_amount - o.gst_amount) DESC)           AS revenue_rank
FROM sales_orders o
JOIN stores s ON s.store_id = o.store_id
WHERE o.order_status = 'COMPLETED'
GROUP BY s.city, s.region, s.store_type
ORDER BY revenue_rank;

-- Q20 | Revenue by customer city (top 10)
-- Business question: Where do our customers live, regardless of which store served them?
-- Approach: group on the customer's city; NULL cities are labelled explicitly.
-- Concepts: JOIN, COALESCE, LIMIT.
-- Why it works: customer city differs from store city for online orders and for customers outside store cities.
SELECT COALESCE(c.city, '(unknown)') AS customer_city,
       COUNT(DISTINCT c.customer_id) AS buying_customers,
       COUNT(*)                       AS orders,
       ROUND(SUM(o.total_amount - o.gst_amount), 0) AS net_revenue
FROM sales_orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.order_status = 'COMPLETED'
GROUP BY 1
ORDER BY net_revenue DESC
LIMIT 10;

-- Q21 | Sales by time of day
-- Business question: At what time of day do customers buy?
-- Approach: bucket the hour of order_date with CASE.
-- Concepts: EXTRACT(HOUR), CASE, conditional grouping.
-- Why it works: grouping by the CASE expression (column position 1) counts orders per named time slot.
SELECT CASE WHEN EXTRACT(HOUR FROM order_date) < 12 THEN '1) Morning (10-12)'
            WHEN EXTRACT(HOUR FROM order_date) < 16 THEN '2) Afternoon (12-16)'
            WHEN EXTRACT(HOUR FROM order_date) < 19 THEN '3) Evening (16-19)'
            ELSE '4) Night (19-22)' END AS time_slot,
       COUNT(*) AS orders,
       ROUND(SUM(total_amount - gst_amount), 0) AS net_revenue
FROM sales_orders
WHERE order_status = 'COMPLETED'
GROUP BY 1
ORDER BY 1;

-- Q22 | Running (cumulative) revenue total
-- Business question: How does revenue accumulate over time?
-- Approach: SUM() OVER (ORDER BY month) gives a running total across the monthly series.
-- Concepts: window frame default (UNBOUNDED PRECEDING to CURRENT ROW), CTE.
-- Why it works: when a window has ORDER BY and no explicit frame, PostgreSQL sums from the first row to the current row.
WITH monthly AS (
    SELECT DATE_TRUNC('month', order_date)::date AS month, SUM(total_amount - gst_amount) AS revenue
    FROM sales_orders
    WHERE order_status = 'COMPLETED'
    GROUP BY 1
)
SELECT month, ROUND(revenue, 0) AS revenue,
       ROUND(SUM(revenue) OVER (ORDER BY month), 0) AS running_total
FROM monthly
ORDER BY month;

-- Q23 | 3-month moving average of revenue
-- Business question: What is the underlying trend once month-to-month noise (and seasonality) is smoothed?
-- Approach: AVG over the current row and the two before it using an explicit ROWS frame.
-- Concepts: AVG() OVER, ROWS BETWEEN 2 PRECEDING AND CURRENT ROW, CASE to hide incomplete windows.
-- Why it works: the frame defines exactly which neighbouring rows feed each average; the first two months lack a full window so we return NULL.
WITH monthly AS (
    SELECT DATE_TRUNC('month', order_date)::date AS month, SUM(total_amount - gst_amount) AS revenue
    FROM sales_orders
    WHERE order_status = 'COMPLETED'
    GROUP BY 1
)
SELECT month, ROUND(revenue, 0) AS revenue,
       CASE WHEN ROW_NUMBER() OVER (ORDER BY month) >= 3
            THEN ROUND(AVG(revenue) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 0) END AS moving_avg_3m
FROM monthly
ORDER BY month;

-- Q24 | Monthly revenue ranking within each year
-- Business question: Which months are strongest in each year?
-- Approach: RANK() partitioned by year and ordered by revenue descending.
-- Concepts: RANK, PARTITION BY, filtering on a window result through a CTE.
-- Why it works: window functions cannot be filtered in WHERE directly, so we rank inside a CTE and filter outside it.
WITH monthly AS (
    SELECT DATE_TRUNC('month', order_date)::date AS month, SUM(total_amount - gst_amount) AS revenue
    FROM sales_orders
    WHERE order_status = 'COMPLETED'
    GROUP BY 1
), ranked AS (
    SELECT month, EXTRACT(YEAR FROM month)::int AS yr, revenue,
           RANK() OVER (PARTITION BY EXTRACT(YEAR FROM month) ORDER BY revenue DESC) AS rank_in_year
    FROM monthly
)
SELECT yr, month, ROUND(revenue, 0) AS revenue, rank_in_year
FROM ranked
WHERE rank_in_year <= 3
ORDER BY yr, rank_in_year;

-- Q25 | Online versus in-store revenue mix by year
-- Business question: Is the online channel taking a bigger share over time?
-- Approach: conditional aggregation with FILTER produces one column per channel in a single pass.
-- Concepts: FILTER, pivoting rows to columns, percent calculation.
-- Why it works: each SUM(...) FILTER adds only the rows of one channel, effectively a manual pivot table.
SELECT EXTRACT(YEAR FROM order_date)::int AS yr,
       ROUND(SUM(total_amount - gst_amount) FILTER (WHERE channel = 'IN_STORE'), 0) AS in_store_revenue,
       ROUND(SUM(total_amount - gst_amount) FILTER (WHERE channel = 'ONLINE'), 0)   AS online_revenue,
       ROUND(100.0 * SUM(total_amount - gst_amount) FILTER (WHERE channel = 'ONLINE') / SUM(total_amount - gst_amount), 2) AS online_share_pct
FROM sales_orders
WHERE order_status = 'COMPLETED'
GROUP BY 1
ORDER BY 1;

-- Q26 | Quarterly revenue with same-quarter-last-year growth
-- Business question: How does each quarter compare with the same quarter a year earlier (removes seasonality)?
-- Approach: LAG with an offset of 4 rows on a quarterly series.
-- Concepts: DATE_TRUNC('quarter'), LAG(expr, 4), CASE-free growth formula.
-- Why it works: four quarters back is the same quarter of the previous year.
WITH quarterly AS (
    SELECT DATE_TRUNC('quarter', order_date)::date AS quarter_start, SUM(total_amount - gst_amount) AS revenue
    FROM sales_orders
    WHERE order_status = 'COMPLETED'
    GROUP BY 1
)
SELECT TO_CHAR(quarter_start, 'YYYY-"Q"Q') AS quarter, ROUND(revenue, 0) AS revenue,
       ROUND(100.0 * (revenue / LAG(revenue, 4) OVER (ORDER BY quarter_start) - 1), 2) AS yoy_growth_pct
FROM quarterly
ORDER BY quarter_start;

-- Q27 | Discount impact: discounted lines versus full-price lines
-- Business question: How much discount do we give and how does it affect margin?
-- Approach: split lines into promotion / no-promotion groups with CASE and compare volume, discount depth and margin.
-- Concepts: CASE in GROUP BY, ratio of sums, JOIN to products for GST.
-- Why it works: the same measures computed for two groups make the trade-off visible: discounted lines usually have a lower margin per unit.
SELECT CASE WHEN i.promotion_id IS NULL THEN 'No promotion' ELSE 'Promotion applied' END AS line_type,
       COUNT(*)                                                                   AS order_lines,
       SUM(i.quantity)                                                            AS units,
       ROUND(100.0 * SUM(i.discount_amount) / SUM(i.quantity * i.unit_price), 2)  AS discount_depth_pct,
       ROUND(100.0 * SUM(i.line_total / (1 + p.gst_rate / 100.0) - i.quantity * i.unit_cost)
             / SUM(i.line_total / (1 + p.gst_rate / 100.0)), 2)                   AS gross_margin_pct,
       ROUND(SUM(i.discount_amount), 0)                                           AS total_discount
FROM sales_order_items i
JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
JOIN products p     ON p.product_id = i.product_id
GROUP BY 1
ORDER BY 1;

-- Q28 | Promotion performance and unit uplift
-- Business question: Which promotions worked - did promoted products sell faster while the promotion ran?
-- Approach: for each promotion compare units per day for its products DURING the window against the 28 days BEFORE it.
-- Concepts: multiple CTEs, BETWEEN on dates, ratio of daily rates, JOIN through a many-to-many table.
-- Why it works: dividing by the number of days makes windows of different length comparable.
--               CAUTION: this is a before/after comparison, not proof of cause. Seasonality (e.g. Diwali) also lifts sales.
WITH promo AS (
    SELECT promotion_id, promo_code, discount_type, discount_value, start_date, end_date,
           end_date - start_date + 1 AS promo_days
    FROM promotions
    WHERE start_date - 28 >= (SELECT MIN(order_date)::date FROM sales_orders)
      AND end_date <= (SELECT MAX(order_date)::date FROM sales_orders)
), during AS (
    SELECT pr.promotion_id, SUM(i.quantity) AS units, SUM(i.discount_amount) AS discount_given
    FROM promo pr
    JOIN product_promotions pp ON pp.promotion_id = pr.promotion_id
    JOIN sales_order_items i   ON i.product_id = pp.product_id
    JOIN sales_orders o        ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
                              AND o.order_date::date BETWEEN pr.start_date AND pr.end_date
    GROUP BY pr.promotion_id
), before AS (
    SELECT pr.promotion_id, SUM(i.quantity) AS units
    FROM promo pr
    JOIN product_promotions pp ON pp.promotion_id = pr.promotion_id
    JOIN sales_order_items i   ON i.product_id = pp.product_id
    JOIN sales_orders o        ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
                              AND o.order_date::date BETWEEN pr.start_date - 28 AND pr.start_date - 1
    GROUP BY pr.promotion_id
)
SELECT pr.promo_code, pr.discount_type, pr.discount_value, pr.promo_days,
       d.units AS units_during, b.units AS units_28d_before,
       ROUND(d.discount_given, 0) AS discount_given,
       ROUND(100.0 * ((d.units::numeric / pr.promo_days) / NULLIF(b.units::numeric / 28, 0) - 1), 1) AS daily_unit_uplift_pct
FROM promo pr
JOIN during d ON d.promotion_id = pr.promotion_id
JOIN before b ON b.promotion_id = pr.promotion_id
ORDER BY pr.start_date;

-- Q29 | Basket size: lines per order versus order value
-- Business question: Do larger baskets carry higher order values?
-- Approach: count lines per order in a subquery, bucket the count, then aggregate orders per bucket.
-- Concepts: subquery in FROM, CASE bucketing, aggregate of aggregates.
-- Why it works: the inner query gives one row per order with its line count; the outer query summarises those rows.
SELECT CASE WHEN n.lines = 1 THEN '1 item' WHEN n.lines = 2 THEN '2 items'
            WHEN n.lines <= 4 THEN '3-4 items' ELSE '5+ items' END AS basket_size,
       COUNT(*)                          AS orders,
       ROUND(AVG(o.total_amount), 2)     AS avg_order_value,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS share_of_orders_pct
FROM sales_orders o
JOIN (SELECT order_id, COUNT(*) AS lines FROM sales_order_items GROUP BY order_id) n ON n.order_id = o.order_id
WHERE o.order_status = 'COMPLETED'
GROUP BY 1
ORDER BY MIN(n.lines);

-- Q30 | Payment method mix and failure rate
-- Business question: How do customers pay, and which methods fail most?
-- Approach: count successful payments and failed attempts per method with FILTER.
-- Concepts: FILTER, share of total via window, ratio of counts.
-- Why it works: failed attempts are separate rows in payments, so the failure rate is failed / all attempts per method.
SELECT payment_method,
       COUNT(*) FILTER (WHERE payment_status = 'SUCCESS')             AS successful_payments,
       ROUND(SUM(amount) FILTER (WHERE payment_status = 'SUCCESS'), 0) AS amount_collected,
       ROUND(100.0 * COUNT(*) FILTER (WHERE payment_status = 'SUCCESS')
             / SUM(COUNT(*) FILTER (WHERE payment_status = 'SUCCESS')) OVER (), 2) AS share_of_successful_pct,
       ROUND(100.0 * COUNT(*) FILTER (WHERE payment_status = 'FAILED') / COUNT(*) FILTER (WHERE payment_status <> 'REFUNDED'), 2) AS failure_rate_pct
FROM payments
GROUP BY payment_method
ORDER BY successful_payments DESC;

-- Q31 | Best month of every year
-- Business question: What is the peak month in each year?
-- Approach: ROW_NUMBER partitioned by year, keep row number 1.
-- Concepts: ROW_NUMBER vs RANK (ROW_NUMBER never ties), top-1-per-group pattern.
-- Why it works: ROW_NUMBER numbers rows inside each year by revenue; filtering to 1 keeps exactly one row per year.
WITH monthly AS (
    SELECT DATE_TRUNC('month', order_date)::date AS month, SUM(total_amount - gst_amount) AS revenue
    FROM sales_orders
    WHERE order_status = 'COMPLETED'
    GROUP BY 1
), numbered AS (
    SELECT month, revenue, ROW_NUMBER() OVER (PARTITION BY EXTRACT(YEAR FROM month) ORDER BY revenue DESC) AS rn
    FROM monthly
)
SELECT TO_CHAR(month, 'YYYY-MM') AS best_month, ROUND(revenue, 0) AS revenue
FROM numbered
WHERE rn = 1
ORDER BY month;

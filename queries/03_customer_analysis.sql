-- =============================================================================
-- 03_customer_analysis.sql : customer value, repeat behaviour, RFM segmentation, cohorts
-- "As of" date = last order date in the data. Customer value here is HISTORICAL (past net revenue),
-- so "customer lifetime value" below means lifetime value observed to date, not a forecast.
-- =============================================================================

-- Q32 | Top 20 customers by lifetime net revenue
-- Business question: Who are the most valuable customers?
-- Approach: aggregate completed orders per customer, join customer details and segment, sort by revenue.
-- Concepts: JOIN, GROUP BY, MIN/MAX dates, INITCAP/TRIM string cleaning, LEFT JOIN for optional segment.
-- Why it works: first_name is sometimes upper-case or has trailing spaces; INITCAP(TRIM()) normalises it for display.
SELECT c.customer_id,
       INITCAP(TRIM(c.first_name)) || ' ' || INITCAP(TRIM(COALESCE(c.last_name, ''))) AS customer_name,
       COALESCE(s.segment_name, '(none)')             AS segment,
       COUNT(*)                                       AS orders,
       ROUND(SUM(o.total_amount - o.gst_amount), 0)   AS lifetime_net_revenue,
       ROUND(AVG(o.total_amount), 0)                  AS avg_order_value,
       MIN(o.order_date)::date                        AS first_purchase,
       MAX(o.order_date)::date                        AS last_purchase
FROM customers c
JOIN sales_orders o ON o.customer_id = c.customer_id AND o.order_status = 'COMPLETED'
LEFT JOIN customer_segments s ON s.segment_id = c.segment_id
GROUP BY c.customer_id, c.first_name, c.last_name, s.segment_name
ORDER BY lifetime_net_revenue DESC
LIMIT 20;

-- Q33 | Repeat customer rate
-- Business question: What percentage of buying customers purchased more than once?
-- Approach: count orders per customer in a CTE, then compare customers with 2+ orders against all buyers.
-- Concepts: CTE, COUNT(*) FILTER, ratio.
-- Why it works: the CTE has one row per buying customer, so counting its rows counts customers.
WITH per_customer AS (
    SELECT customer_id, COUNT(*) AS orders
    FROM sales_orders
    WHERE order_status = 'COMPLETED'
    GROUP BY customer_id
)
SELECT COUNT(*)                                        AS buying_customers,
       COUNT(*) FILTER (WHERE orders >= 2)             AS repeat_customers,
       COUNT(*) FILTER (WHERE orders = 1)              AS one_time_customers,
       ROUND(100.0 * COUNT(*) FILTER (WHERE orders >= 2) / COUNT(*), 2) AS repeat_customer_rate_pct
FROM per_customer;

-- Q34 | Customers who never purchased: three ways to write an anti-join
-- Business question: How many registered customers have never bought anything?
-- Approach: LEFT JOIN ... IS NULL, NOT EXISTS and NOT IN should all agree - they are shown side by side.
-- Concepts: anti-join, NOT EXISTS, NOT IN (and why NULLs make NOT IN dangerous), scalar subqueries.
-- Why it works: NOT EXISTS is usually the safest: NOT IN returns nothing if the subquery yields even one NULL.
SELECT
    (SELECT COUNT(*) FROM customers c LEFT JOIN sales_orders o
            ON o.customer_id = c.customer_id AND o.order_status = 'COMPLETED'
     WHERE o.order_id IS NULL)                                                            AS via_left_join,
    (SELECT COUNT(*) FROM customers c
     WHERE NOT EXISTS (SELECT 1 FROM sales_orders o
                       WHERE o.customer_id = c.customer_id AND o.order_status = 'COMPLETED')) AS via_not_exists,
    (SELECT COUNT(*) FROM customers
     WHERE customer_id NOT IN (SELECT customer_id FROM sales_orders WHERE order_status = 'COMPLETED')) AS via_not_in;

-- Q35 | Never-purchased customers by registration year
-- Business question: Are non-buyers mostly recent sign-ups who have not had time to buy?
-- Approach: anti-join with NOT EXISTS, then group by year of registration.
-- Concepts: NOT EXISTS, EXTRACT(YEAR), GROUP BY, window percentage.
-- Why it works: late registrants have a shorter buying window, so their share of non-buyers is expected to be higher.
SELECT EXTRACT(YEAR FROM c.registration_date)::int AS registration_year,
       COUNT(*)                                     AS never_purchased,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS share_of_non_buyers_pct
FROM customers c
WHERE NOT EXISTS (SELECT 1 FROM sales_orders o WHERE o.customer_id = c.customer_id AND o.order_status = 'COMPLETED')
GROUP BY 1
ORDER BY 1;

-- Q36 | Purchase frequency distribution
-- Business question: How many customers bought once, a few times, or very often?
-- Approach: orders per customer, bucketed with CASE, then customers and revenue per bucket.
-- Concepts: CTE, CASE bucketing, aggregate of aggregates, percent of total.
-- Why it works: frequency buckets reveal whether revenue depends on a small group of frequent buyers.
WITH per_customer AS (
    SELECT customer_id, COUNT(*) AS orders, SUM(total_amount - gst_amount) AS revenue
    FROM sales_orders
    WHERE order_status = 'COMPLETED'
    GROUP BY customer_id
)
SELECT CASE WHEN orders = 1 THEN 'a) 1 order' WHEN orders <= 3 THEN 'b) 2-3 orders'
            WHEN orders <= 6 THEN 'c) 4-6 orders' WHEN orders <= 12 THEN 'd) 7-12 orders'
            ELSE 'e) 13+ orders' END AS frequency_band,
       COUNT(*)                                          AS customers,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)  AS customer_share_pct,
       ROUND(100.0 * SUM(revenue) / SUM(SUM(revenue)) OVER (), 2) AS revenue_share_pct
FROM per_customer
GROUP BY 1
ORDER BY 1;

-- Q37 | Revenue by customer segment
-- Business question: Which customer segments generate the most revenue?
-- Approach: LEFT JOIN customers to segments (some customers have no segment), aggregate their orders.
-- Concepts: LEFT JOIN, COALESCE, revenue per customer and per order, window share.
-- Why it works: revenue per buying customer separates "big segment" from "high-value segment".
SELECT COALESCE(s.segment_name, '(no segment)') AS segment,
       COUNT(DISTINCT c.customer_id)            AS buying_customers,
       COUNT(*)                                  AS orders,
       ROUND(SUM(o.total_amount - o.gst_amount), 0) AS net_revenue,
       ROUND(100.0 * SUM(o.total_amount - o.gst_amount) / SUM(SUM(o.total_amount - o.gst_amount)) OVER (), 2) AS revenue_share_pct,
       ROUND(SUM(o.total_amount - o.gst_amount) / COUNT(DISTINCT c.customer_id), 0) AS revenue_per_customer,
       ROUND(AVG(o.total_amount), 0)             AS avg_order_value
FROM sales_orders o
JOIN customers c ON c.customer_id = o.customer_id
LEFT JOIN customer_segments s ON s.segment_id = c.segment_id
WHERE o.order_status = 'COMPLETED'
GROUP BY 1
ORDER BY net_revenue DESC;

-- Q38 | New versus returning customers per month
-- Business question: Is monthly revenue driven by new customers or by existing ones?
-- Approach: find each customer's first purchase month, then classify every monthly active customer as new or returning.
-- Concepts: MIN() OVER (PARTITION BY), DISTINCT, conditional counts.
-- Why it works: a customer is 'new' in exactly the month of their first completed order and 'returning' in later months.
WITH orders_m AS (
    SELECT customer_id, DATE_TRUNC('month', order_date)::date AS month
    FROM sales_orders
    WHERE order_status = 'COMPLETED'
), active AS (
    SELECT DISTINCT customer_id, month,
           MIN(month) OVER (PARTITION BY customer_id) AS first_month
    FROM orders_m
)
SELECT month,
       COUNT(*) FILTER (WHERE month = first_month) AS new_customers,
       COUNT(*) FILTER (WHERE month > first_month) AS returning_customers,
       COUNT(*)                                     AS active_customers,
       ROUND(100.0 * COUNT(*) FILTER (WHERE month > first_month) / COUNT(*), 1) AS returning_share_pct
FROM active
GROUP BY month
ORDER BY month;

-- Q39 | RFM scores per customer (sample: top 15 by monetary value)
-- Business question: How recently, how often and how much has each customer bought?
-- Approach: Recency = days since last purchase, Frequency = order count, Monetary = net revenue.
--           Scores 1-5 use fixed project-defined thresholds for R and F and NTILE(5) quintiles for M.
-- Concepts: CTEs, date subtraction from the as-of date, CASE scoring, NTILE window function.
-- Why it works: thresholds are ASSUMPTIONS (documented in docs/07). Fixed thresholds are used for R and F because NTILE
--               would split identical frequency values into different buckets arbitrarily.
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders),
rfm_raw AS (
    SELECT o.customer_id,
           (SELECT d FROM asof) - MAX(o.order_date)::date AS recency_days,
           COUNT(*)                                        AS frequency,
           SUM(o.total_amount - o.gst_amount)              AS monetary
    FROM sales_orders o
    WHERE o.order_status = 'COMPLETED'
    GROUP BY o.customer_id
), scored AS (
    SELECT *,
           CASE WHEN recency_days <= 30 THEN 5 WHEN recency_days <= 90 THEN 4 WHEN recency_days <= 180 THEN 3
                WHEN recency_days <= 365 THEN 2 ELSE 1 END AS r_score,
           CASE WHEN frequency >= 13 THEN 5 WHEN frequency >= 7 THEN 4 WHEN frequency >= 4 THEN 3
                WHEN frequency >= 2 THEN 2 ELSE 1 END      AS f_score,
           NTILE(5) OVER (ORDER BY monetary)                AS m_score
    FROM rfm_raw
)
SELECT customer_id, recency_days, frequency, ROUND(monetary, 0) AS monetary, r_score, f_score, m_score
FROM scored
ORDER BY monetary DESC
LIMIT 15;

-- Q40 | RFM segment summary
-- Business question: How many customers and how much revenue sit in each RFM segment?
-- Approach: reuse the scoring from Q39 and map score combinations to named segments.
-- Concepts: CASE with ordered conditions (first match wins), aggregate by label, share of total.
-- Why it works: the labels are analytical groupings based on the thresholds above - they are not facts about the customers.
--   Champions: R>=4 and F>=4 | Loyal Customers: R>=3 and F>=3 | Potential Loyalists: R>=3 and F<=2
--   At Risk: R<=2 and F>=3   | Lost Customers: R<=2 and F<=2
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders),
rfm_raw AS (
    SELECT o.customer_id,
           (SELECT d FROM asof) - MAX(o.order_date)::date AS recency_days,
           COUNT(*) AS frequency,
           SUM(o.total_amount - o.gst_amount) AS monetary
    FROM sales_orders o
    WHERE o.order_status = 'COMPLETED'
    GROUP BY o.customer_id
), scored AS (
    SELECT *,
           CASE WHEN recency_days <= 30 THEN 5 WHEN recency_days <= 90 THEN 4 WHEN recency_days <= 180 THEN 3
                WHEN recency_days <= 365 THEN 2 ELSE 1 END AS r_score,
           CASE WHEN frequency >= 13 THEN 5 WHEN frequency >= 7 THEN 4 WHEN frequency >= 4 THEN 3
                WHEN frequency >= 2 THEN 2 ELSE 1 END      AS f_score
    FROM rfm_raw
), labelled AS (
    SELECT *,
           CASE WHEN r_score >= 4 AND f_score >= 4 THEN 'Champions'
                WHEN r_score >= 3 AND f_score >= 3 THEN 'Loyal Customers'
                WHEN r_score >= 3 AND f_score <= 2 THEN 'Potential Loyalists'
                WHEN r_score <= 2 AND f_score >= 3 THEN 'At Risk'
                ELSE 'Lost Customers' END AS rfm_segment
    FROM scored
)
SELECT rfm_segment,
       COUNT(*)                                         AS customers,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS customer_share_pct,
       ROUND(SUM(monetary), 0)                          AS net_revenue,
       ROUND(100.0 * SUM(monetary) / SUM(SUM(monetary)) OVER (), 2) AS revenue_share_pct,
       ROUND(AVG(recency_days), 0)                      AS avg_recency_days,
       ROUND(AVG(frequency), 1)                         AS avg_orders
FROM labelled
GROUP BY rfm_segment
ORDER BY net_revenue DESC;

-- Q41 | Cohort retention (first-purchase month cohorts, first 6 months)
-- Business question: Of the customers acquired in a month, how many buy again in the following months?
-- Approach: cohort = month of first purchase; for each later month count cohort members who ordered.
-- Concepts: cohort analysis, month arithmetic, conditional aggregation as a pivot, DISTINCT.
-- Why it works: month_index = months between cohort month and activity month; dividing by cohort size gives retention %.
--               Only cohorts with at least 6 full months of follow-up are shown.
WITH first_order AS (
    SELECT customer_id, DATE_TRUNC('month', MIN(order_date))::date AS cohort
    FROM sales_orders
    WHERE order_status = 'COMPLETED'
    GROUP BY customer_id
), activity AS (
    SELECT DISTINCT f.cohort, o.customer_id,
           (EXTRACT(YEAR FROM o.order_date) - EXTRACT(YEAR FROM f.cohort)) * 12
           + (EXTRACT(MONTH FROM o.order_date) - EXTRACT(MONTH FROM f.cohort)) AS month_index
    FROM sales_orders o
    JOIN first_order f ON f.customer_id = o.customer_id
    WHERE o.order_status = 'COMPLETED'
)
SELECT cohort,
       COUNT(*) FILTER (WHERE month_index = 0)                                                  AS cohort_size,
       ROUND(100.0 * COUNT(*) FILTER (WHERE month_index = 1) / COUNT(*) FILTER (WHERE month_index = 0), 1) AS m1_pct,
       ROUND(100.0 * COUNT(*) FILTER (WHERE month_index = 2) / COUNT(*) FILTER (WHERE month_index = 0), 1) AS m2_pct,
       ROUND(100.0 * COUNT(*) FILTER (WHERE month_index = 3) / COUNT(*) FILTER (WHERE month_index = 0), 1) AS m3_pct,
       ROUND(100.0 * COUNT(*) FILTER (WHERE month_index = 6) / COUNT(*) FILTER (WHERE month_index = 0), 1) AS m6_pct
FROM activity
WHERE cohort <= DATE '2025-06-01'
GROUP BY cohort
ORDER BY cohort;

-- Q42 | Customer lifetime value (to date) by segment
-- Business question: How much revenue and gross profit does an average customer in each segment bring in?
-- Approach: per-customer totals in a CTE, then averages per segment; profit joins order lines for cost.
-- Concepts: two-level aggregation, AVG of per-customer sums, date span per customer.
-- Why it works: averaging per-customer sums (not per-order values) gives value per customer, which is what lifetime value means.
WITH cust AS (
    SELECT o.customer_id,
           COUNT(DISTINCT o.order_id)                                              AS orders,
           SUM(i.line_total / (1 + p.gst_rate / 100.0))                             AS net_revenue,
           SUM(i.line_total / (1 + p.gst_rate / 100.0) - i.quantity * i.unit_cost)  AS gross_profit,
           MAX(o.order_date)::date - MIN(o.order_date)::date                        AS active_span_days
    FROM sales_orders o
    JOIN sales_order_items i ON i.order_id = o.order_id
    JOIN products p ON p.product_id = i.product_id
    WHERE o.order_status = 'COMPLETED'
    GROUP BY o.customer_id
)
SELECT COALESCE(s.segment_name, '(no segment)') AS segment,
       COUNT(*)                                  AS customers,
       ROUND(AVG(orders), 1)                     AS avg_orders,
       ROUND(AVG(net_revenue), 0)                AS avg_lifetime_revenue,
       ROUND(AVG(gross_profit), 0)               AS avg_lifetime_gross_profit,
       ROUND(AVG(active_span_days), 0)           AS avg_active_span_days
FROM cust
JOIN customers c ON c.customer_id = cust.customer_id
LEFT JOIN customer_segments s ON s.segment_id = c.segment_id
GROUP BY 1
ORDER BY avg_lifetime_revenue DESC;

-- Q43 | Customer activity status as of the last data date
-- Business question: How many customers are active, slipping away, lost or never bought?
-- Approach: days since last completed order compared with fixed thresholds (an assumption: 90 / 365 days).
-- Concepts: LEFT JOIN, CASE, date arithmetic, share of total.
-- Why it works: customers with no orders get NULL for last_order and fall into the 'Never purchased' branch.
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders),
last_buy AS (
    SELECT c.customer_id, MAX(o.order_date)::date AS last_order
    FROM customers c
    LEFT JOIN sales_orders o ON o.customer_id = c.customer_id AND o.order_status = 'COMPLETED'
    GROUP BY c.customer_id
)
SELECT CASE WHEN last_order IS NULL THEN '4) Never purchased'
            WHEN asof.d - last_order <= 90  THEN '1) Active (bought in last 90 days)'
            WHEN asof.d - last_order <= 365 THEN '2) Inactive (91-365 days)'
            ELSE '3) Lost (over 365 days)' END AS customer_status,
       COUNT(*) AS customers,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS share_pct
FROM last_buy CROSS JOIN asof
GROUP BY 1
ORDER BY 1;

-- Q44 | Top customer of every store
-- Business question: Who is the best customer at each store?
-- Approach: revenue per store + customer, ROW_NUMBER within each store, keep rank 1.
-- Concepts: ROW_NUMBER() OVER (PARTITION BY store ORDER BY revenue DESC), top-N-per-group.
-- Why it works: partitioning restarts the numbering for each store, so rn = 1 is that store's leader.
WITH store_customer AS (
    SELECT o.store_id, o.customer_id, COUNT(*) AS orders, SUM(o.total_amount - o.gst_amount) AS revenue,
           ROW_NUMBER() OVER (PARTITION BY o.store_id ORDER BY SUM(o.total_amount - o.gst_amount) DESC) AS rn
    FROM sales_orders o
    WHERE o.order_status = 'COMPLETED'
    GROUP BY o.store_id, o.customer_id
)
SELECT s.store_name, sc.customer_id,
       INITCAP(TRIM(c.first_name)) || ' ' || INITCAP(TRIM(c.last_name)) AS customer_name,
       sc.orders, ROUND(sc.revenue, 0) AS net_revenue
FROM store_customer sc
JOIN stores s    ON s.store_id = sc.store_id
JOIN customers c ON c.customer_id = sc.customer_id
WHERE sc.rn = 1
ORDER BY net_revenue DESC;

-- Q45 | Average days between purchases of repeat customers
-- Business question: How long do repeat customers wait between orders?
-- Approach: LAG(order_date) per customer gives the previous order date; the difference is the gap.
-- Concepts: LAG with PARTITION BY, date subtraction, percentile of gaps.
-- Why it works: the first order of each customer has no previous order, so its gap is NULL and is ignored by AVG.
WITH gaps AS (
    SELECT customer_id,
           order_date::date - LAG(order_date::date) OVER (PARTITION BY customer_id ORDER BY order_date) AS gap_days
    FROM sales_orders
    WHERE order_status = 'COMPLETED'
)
SELECT COUNT(gap_days)                                                   AS repeat_orders_measured,
       ROUND(AVG(gap_days), 1)                                           AS avg_gap_days,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY gap_days)             AS median_gap_days,
       PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY gap_days)             AS p90_gap_days
FROM gaps;

-- Q46 | Customer revenue concentration by decile
-- Business question: How dependent is revenue on the best customers?
-- Approach: NTILE(10) ranks buying customers into deciles by revenue; sum revenue per decile.
-- Concepts: NTILE, aggregate over a window result, percent contribution.
-- Why it works: decile 10 is the top 10% of buyers; its revenue share is a direct measure of concentration.
WITH per_customer AS (
    SELECT customer_id, SUM(total_amount - gst_amount) AS revenue
    FROM sales_orders
    WHERE order_status = 'COMPLETED'
    GROUP BY customer_id
), deciles AS (
    SELECT customer_id, revenue, NTILE(10) OVER (ORDER BY revenue) AS decile
    FROM per_customer
)
SELECT decile, COUNT(*) AS customers, ROUND(SUM(revenue), 0) AS net_revenue,
       ROUND(100.0 * SUM(revenue) / SUM(SUM(revenue)) OVER (), 2) AS revenue_share_pct,
       ROUND(100.0 * SUM(SUM(revenue)) OVER (ORDER BY decile DESC) / SUM(SUM(revenue)) OVER (), 2) AS cumulative_share_from_top_pct
FROM deciles
GROUP BY decile
ORDER BY decile DESC;

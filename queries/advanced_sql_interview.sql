-- =============================================================================
-- advanced_sql_interview.sql : classic SQL interview problems, solved on this project's data
-- Each problem: the question as an interviewer would ask it, the technique, and the trap to mention.
-- =============================================================================

-- Q201 | Third-highest order value
-- Interview question: "Find the 3rd highest order value." What if several orders share the same value?
-- Technique: DENSE_RANK() gives the third distinct value; ROW_NUMBER would give the third row even if it duplicates the second.
-- Trap: LIMIT 1 OFFSET 2 on the raw table returns the third ROW, not the third distinct VALUE. Use DISTINCT or DENSE_RANK.
SELECT total_amount AS third_highest_distinct_value
FROM (SELECT total_amount, DENSE_RANK() OVER (ORDER BY total_amount DESC) AS dr
      FROM sales_orders WHERE order_status = 'COMPLETED') t
WHERE dr = 3
LIMIT 1;

-- Q202 | Find duplicate customers and mark which row to keep
-- Interview question: "Identify duplicate records and keep only the earliest one."
-- Technique: ROW_NUMBER() partitioned by the duplicate key; rn = 1 is the survivor, rn > 1 are the duplicates to remove.
-- Trap: define 'duplicate' first. Here it is the same e-mail ignoring case and spaces. This is a SELECT - never DELETE before checking.
WITH numbered AS (
    SELECT customer_id, first_name, email, registration_date,
           ROW_NUMBER() OVER (PARTITION BY LOWER(TRIM(email)) ORDER BY registration_date, customer_id) AS rn
    FROM customers WHERE email IS NOT NULL
)
SELECT customer_id, first_name, email, registration_date, 'duplicate - candidate to merge' AS action
FROM numbered WHERE rn > 1
ORDER BY email
LIMIT 10;

-- Q203 | Customers who bought from ALL of several categories (relational division)
-- Interview question: "Find customers who purchased from every one of these three categories: Mobiles, Grocery, Footwear."
-- Technique: filter to the three categories, GROUP BY customer, HAVING COUNT(DISTINCT category) = 3.
-- Trap: HAVING COUNT(*) = 3 is wrong because a customer can buy in one category many times. Count DISTINCT categories.
SELECT o.customer_id, COUNT(DISTINCT p.category_id) AS categories_bought, ROUND(SUM(i.line_total), 0) AS total_spend
FROM sales_orders o
JOIN sales_order_items i ON i.order_id = o.order_id
JOIN products p ON p.product_id = i.product_id
JOIN categories c ON c.category_id = p.category_id
WHERE o.order_status = 'COMPLETED' AND c.category_name IN ('Mobiles & Accessories', 'Grocery & Staples', 'Footwear')
GROUP BY o.customer_id
HAVING COUNT(DISTINCT p.category_id) = 3
ORDER BY total_spend DESC
LIMIT 10;

-- Q204 | Customers who bought in three consecutive months
-- Interview question: "Which customers purchased in at least 3 consecutive months?"
-- Technique: gaps and islands on months: month_number minus ROW_NUMBER is constant inside a consecutive run.
-- Trap: use DISTINCT months first, or a customer with two orders in one month breaks the row-number arithmetic.
WITH months AS (
    SELECT DISTINCT customer_id,
           EXTRACT(YEAR FROM order_date)::int * 12 + EXTRACT(MONTH FROM order_date)::int AS month_no
    FROM sales_orders WHERE order_status = 'COMPLETED'
), islands AS (
    SELECT customer_id, month_no, month_no - ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY month_no) AS island FROM months
)
SELECT COUNT(DISTINCT customer_id) AS customers_with_3_consecutive_months
FROM (SELECT customer_id, island FROM islands GROUP BY customer_id, island HAVING COUNT(*) >= 3) t;

-- Q205 | Year-to-date revenue that resets every year
-- Interview question: "Show a running total that restarts each January."
-- Technique: SUM() OVER (PARTITION BY year ORDER BY month) - PARTITION BY is what resets the total.
-- Trap: without PARTITION BY the total keeps accumulating across years.
WITH monthly AS (
    SELECT DATE_TRUNC('month', order_date)::date AS month, SUM(total_amount - gst_amount) AS revenue
    FROM sales_orders WHERE order_status = 'COMPLETED' GROUP BY 1
)
SELECT month, ROUND(revenue, 0) AS revenue,
       ROUND(SUM(revenue) OVER (PARTITION BY EXTRACT(YEAR FROM month) ORDER BY month), 0) AS ytd_revenue
FROM monthly
WHERE EXTRACT(YEAR FROM month) = 2025
ORDER BY month;

-- Q206 | Median versus mean order value per store
-- Interview question: "Why might the average be misleading, and how do you get the median in SQL?"
-- Technique: PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ...) is PostgreSQL's median; compare with AVG.
-- Trap: order values are right-skewed (a few huge orders), so the mean sits well above the median.
SELECT s.store_name, ROUND(AVG(o.total_amount), 0) AS mean_order_value,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY o.total_amount))::numeric, 0) AS median_order_value
FROM sales_orders o JOIN stores s ON s.store_id = o.store_id
WHERE o.order_status = 'COMPLETED'
GROUP BY s.store_name
ORDER BY mean_order_value DESC;

-- Q207 | Top 3 products per category, keeping ties
-- Interview question: "Top 3 products per category - what happens on ties?"
-- Technique: DENSE_RANK() includes every product that ties for a rank; ROW_NUMBER would cut ties arbitrarily; RANK skips numbers after ties.
-- Trap: name the difference between ROW_NUMBER, RANK and DENSE_RANK - it is asked very often.
WITH ranked AS (
    SELECT p.category_id, p.product_name, SUM(i.quantity) AS units,
           DENSE_RANK() OVER (PARTITION BY p.category_id ORDER BY SUM(i.quantity) DESC) AS dr
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products p ON p.product_id = i.product_id
    WHERE p.category_id BETWEEN 1 AND 3
    GROUP BY p.category_id, p.product_name
)
SELECT c.category_name, r.product_name, r.units, r.dr
FROM ranked r JOIN categories c ON c.category_id = r.category_id
WHERE r.dr <= 3
ORDER BY c.category_name, r.dr;

-- Q208 | Customers whose last three order values kept rising
-- Interview question: "Find customers whose spending increased on each of their last three orders."
-- Technique: ROW_NUMBER newest-first, keep rn <= 3, then LAG/LEAD or conditional aggregation to compare consecutive values.
-- Trap: compare values in a defined order - always ORDER BY inside the window.
WITH last3 AS (
    SELECT customer_id, total_amount,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date DESC, order_id DESC) AS rn
    FROM sales_orders WHERE order_status = 'COMPLETED'
), pivoted AS (
    SELECT customer_id,
           MAX(total_amount) FILTER (WHERE rn = 1) AS latest,
           MAX(total_amount) FILTER (WHERE rn = 2) AS previous,
           MAX(total_amount) FILTER (WHERE rn = 3) AS before_that
    FROM last3 WHERE rn <= 3 GROUP BY customer_id
)
SELECT COUNT(*) FILTER (WHERE latest > previous AND previous > before_that) AS customers_rising_three_orders,
       COUNT(*) FILTER (WHERE before_that IS NOT NULL)                         AS customers_with_three_orders
FROM pivoted;

-- Q209 | Employees hired before their manager (SELF JOIN)
-- Interview question: "List employees who joined earlier than their own manager."
-- Technique: join employees to itself: e is the employee, m is the manager (m.employee_id = e.manager_id).
-- Trap: give the two copies of the table different aliases and pick the right columns from each.
-- Note: 0 rows is the correct answer here - in this data every manager was hired before their team.
SELECT e.first_name || ' ' || e.last_name AS employee, e.hire_date AS employee_hired,
       m.first_name || ' ' || m.last_name AS manager,  m.hire_date AS manager_hired
FROM employees e JOIN employees m ON m.employee_id = e.manager_id
WHERE e.hire_date < m.hire_date
ORDER BY e.hire_date
LIMIT 10;

-- Q210 | Products priced above their category average
-- Interview question: "List products more expensive than the average of their own category."
-- Technique: the window AVG() OVER (PARTITION BY category) is shown. A correlated subquery or a join to a grouped average gives the same answer.
-- Trap: knowing all three and when each is clearest. The window version reads best and scans the table once.
SELECT COUNT(*) AS via_window_function FROM (
    SELECT unit_price, AVG(unit_price) OVER (PARTITION BY category_id) AS cat_avg
    FROM products WHERE category_id IS NOT NULL) t
WHERE unit_price > cat_avg;

-- Q211 | The NOT IN trap with NULLs
-- Interview question: "Why does NOT IN sometimes return no rows at all?"
-- Technique: if the sub-query returns even ONE NULL, 'x NOT IN (..., NULL)' is never TRUE, so no rows survive.
-- Trap: products.category_id contains NULLs, so the NOT IN version below returns 0 rows while NOT EXISTS returns the true answer.
SELECT (SELECT COUNT(*) FROM categories WHERE category_id NOT IN (SELECT category_id FROM products)) AS not_in_result,
       (SELECT COUNT(*) FROM categories c WHERE NOT EXISTS (SELECT 1 FROM products p WHERE p.category_id = c.category_id)) AS not_exists_result;

-- Q212 | Month-over-month change with readable labels
-- Interview question: "Label each month as growth, decline or flat versus the previous month and count each label."
-- Technique: LAG for the previous month, CASE for the label, then aggregate the labels.
-- Trap: the first month has no previous month (LAG returns NULL) - decide how to label it instead of ignoring it.
WITH monthly AS (
    SELECT DATE_TRUNC('month', order_date)::date AS month, SUM(total_amount - gst_amount) AS revenue
    FROM sales_orders WHERE order_status = 'COMPLETED' GROUP BY 1
), labelled AS (
    SELECT month, CASE WHEN LAG(revenue) OVER (ORDER BY month) IS NULL THEN 'first month'
                       WHEN revenue > 1.02 * LAG(revenue) OVER (ORDER BY month) THEN 'growth (more than +2 pct)'
                       WHEN revenue < 0.98 * LAG(revenue) OVER (ORDER BY month) THEN 'decline (more than -2 pct)'
                       ELSE 'flat (within 2 pct)' END AS movement
    FROM monthly
)
SELECT movement, COUNT(*) AS months FROM labelled GROUP BY movement ORDER BY months DESC;

-- Q213 | Products bought by every store (double NOT EXISTS)
-- Interview question: "Which products have been sold in EVERY physical store?"
-- Technique: relational division with NOT EXISTS: there is no store for which this product has no sale.
-- Trap: this is the classic 'for all' pattern - read it as 'there does not exist a store without a sale of this product'.
SELECT COUNT(*) AS products_sold_in_every_store FROM products p
WHERE NOT EXISTS (
    SELECT 1 FROM stores s
    WHERE s.store_type = 'STORE' AND NOT EXISTS (
        SELECT 1 FROM sales_order_items i JOIN sales_orders o ON o.order_id = i.order_id
        WHERE i.product_id = p.product_id AND o.store_id = s.store_id AND o.order_status = 'COMPLETED'));

-- Q214 | Share of each store in its region (window percent within a group)
-- Interview question: "For every store show its share of its region's revenue."
-- Technique: SUM() OVER (PARTITION BY region) provides the regional total on every row without collapsing rows.
-- Trap: a window function keeps row detail; GROUP BY would lose the store rows.
SELECT s.region, s.store_name, ROUND(SUM(o.total_amount - o.gst_amount), 0) AS revenue,
       ROUND(100.0 * SUM(o.total_amount - o.gst_amount) / SUM(SUM(o.total_amount - o.gst_amount)) OVER (PARTITION BY s.region), 1) AS share_of_region_pct
FROM sales_orders o JOIN stores s ON s.store_id = o.store_id
WHERE o.order_status = 'COMPLETED'
GROUP BY s.region, s.store_name
ORDER BY s.region, revenue DESC;

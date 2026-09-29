-- =============================================================================
-- 07_supplier_analysis.sql : procurement spend, delivery reliability, dependency
-- Delivery metrics use RECEIVED purchase orders only (open orders have no received date yet).
-- "On time" = received_date <= expected_date, where expected_date = order date + the supplier's promised lead time.
-- =============================================================================

-- Q81 | Supplier purchase spend
-- Business question: How much do we buy from each supplier?
-- Approach: join suppliers to purchases and purchase lines, sum ordered value and quantities.
-- Concepts: JOIN, SUM of an expression, COUNT(DISTINCT), percent of total spend.
-- Why it works: spend = quantity ordered * unit cost on each line; distinct PO counting avoids counting a PO once per line.
SELECT su.supplier_name, COUNT(DISTINCT pu.purchase_id) AS purchase_orders, SUM(pi.quantity_ordered) AS units_ordered,
       ROUND(SUM(pi.quantity_ordered * pi.unit_cost), 0) AS spend,
       ROUND(100.0 * SUM(pi.quantity_ordered * pi.unit_cost) / SUM(SUM(pi.quantity_ordered * pi.unit_cost)) OVER (), 2) AS share_of_spend_pct
FROM suppliers su
JOIN purchases pu ON pu.supplier_id = su.supplier_id
JOIN purchase_items pi ON pi.purchase_id = pu.purchase_id
GROUP BY su.supplier_name
ORDER BY spend DESC
LIMIT 15;

-- Q82 | Supplier on-time delivery and average delay
-- Business question: Which suppliers deliver late?
-- Approach: for received POs compare received_date with expected_date; count on-time with FILTER; average the delay in days.
-- Concepts: date subtraction, FILTER, HAVING to require enough POs for a fair rate.
-- Why it works: a supplier with only a handful of POs could look perfect or terrible by chance, so we require 30+ POs.
SELECT su.supplier_name, su.lead_time_days AS promised_lead_days,
       COUNT(*) AS received_pos,
       ROUND(100.0 * COUNT(*) FILTER (WHERE pu.received_date <= pu.expected_date) / COUNT(*), 1) AS on_time_pct,
       ROUND(AVG(pu.received_date - pu.expected_date), 1) AS avg_days_vs_expected,
       MAX(pu.received_date - pu.expected_date) AS worst_delay_days
FROM purchases pu JOIN suppliers su ON su.supplier_id = pu.supplier_id
WHERE pu.status = 'RECEIVED'
GROUP BY su.supplier_id, su.supplier_name, su.lead_time_days
HAVING COUNT(*) >= 30
ORDER BY on_time_pct
LIMIT 15;

-- Q83 | Supplier fill rate
-- Business question: Do suppliers deliver the full quantity we order?
-- Approach: received quantity divided by ordered quantity on received purchase orders.
-- Concepts: ratio of sums (not average of ratios), JOIN, HAVING.
-- Why it works: the ratio of totals weights big orders correctly; averaging per-line ratios would overweight tiny orders.
SELECT su.supplier_name, SUM(pi.quantity_ordered) AS ordered, SUM(pi.quantity_received) AS received,
       ROUND(100.0 * SUM(pi.quantity_received) / SUM(pi.quantity_ordered), 2) AS fill_rate_pct,
       COUNT(*) FILTER (WHERE pi.quantity_received < pi.quantity_ordered) AS short_shipped_lines
FROM purchase_items pi
JOIN purchases pu ON pu.purchase_id = pi.purchase_id AND pu.status = 'RECEIVED'
JOIN suppliers su ON su.supplier_id = pu.supplier_id
GROUP BY su.supplier_name
HAVING SUM(pi.quantity_ordered) >= 200
ORDER BY fill_rate_pct
LIMIT 15;

-- Q84 | Actual versus promised supplier lead time
-- Business question: Are the lead times stored on the supplier record realistic?
-- Approach: average actual days from order to receipt compared with the promised lead_time_days.
-- Concepts: date subtraction, AVG, difference column, CASE flag.
-- Why it works: a large positive gap means planning with the promised number would cause stock-outs (reorder points too low).
SELECT su.supplier_name, su.lead_time_days AS promised_days,
       ROUND(AVG(pu.received_date - pu.order_date), 1) AS actual_avg_days,
       ROUND(AVG(pu.received_date - pu.order_date) - su.lead_time_days, 1) AS gap_days,
       CASE WHEN AVG(pu.received_date - pu.order_date) - su.lead_time_days > 2 THEN 'Slower than promised'
            WHEN AVG(pu.received_date - pu.order_date) - su.lead_time_days < -2 THEN 'Faster than promised'
            ELSE 'In line' END AS assessment
FROM suppliers su JOIN purchases pu ON pu.supplier_id = su.supplier_id AND pu.status = 'RECEIVED'
GROUP BY su.supplier_id, su.supplier_name, su.lead_time_days
HAVING COUNT(*) >= 30
ORDER BY gap_days DESC
LIMIT 15;

-- Q85 | Revenue dependency on suppliers
-- Business question: How much of our sales depends on each supplier's products?
-- Approach: sales joined through products.supplier_id; products with no supplier are kept as their own row.
-- Concepts: LEFT JOIN, COALESCE, window share, cumulative share.
-- Why it works: products with a NULL supplier would disappear in an inner join, hiding revenue that has no supplier record.
SELECT COALESCE(su.supplier_name, '(supplier missing on product)') AS supplier,
       COUNT(DISTINCT p.product_id) AS products_sold,
       ROUND(SUM(i.line_total / (1 + p.gst_rate / 100.0)), 0) AS net_revenue,
       ROUND(100.0 * SUM(i.line_total / (1 + p.gst_rate / 100.0)) / SUM(SUM(i.line_total / (1 + p.gst_rate / 100.0))) OVER (), 2) AS revenue_share_pct
FROM sales_order_items i
JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
JOIN products p ON p.product_id = i.product_id
LEFT JOIN suppliers su ON su.supplier_id = p.supplier_id
GROUP BY 1
ORDER BY net_revenue DESC
LIMIT 12;

-- Q86 | Suppliers without products, and inactive suppliers still being ordered from
-- Business question: Is our supplier master data consistent with what we actually buy?
-- Approach: two anti-join style checks combined with UNION ALL and labelled.
-- Concepts: LEFT JOIN ... IS NULL, EXISTS, UNION ALL with a label column.
-- Why it works: each half answers one data-consistency question; the label tells the reader which.
SELECT 'No products linked' AS finding, su.supplier_name
FROM suppliers su LEFT JOIN products p ON p.supplier_id = su.supplier_id
WHERE p.product_id IS NULL
UNION ALL
SELECT 'Inactive but has purchase orders', su.supplier_name
FROM suppliers su
WHERE NOT su.is_active AND EXISTS (SELECT 1 FROM purchases pu WHERE pu.supplier_id = su.supplier_id)
ORDER BY 1, 2;

-- Q87 | Open purchase orders and overdue orders
-- Business question: Which ordered but not yet received POs are overdue?
-- Approach: status ORDERED with expected_date before the as-of date is overdue.
-- Concepts: CTE for the as-of date, CASE, date subtraction, GROUP BY supplier.
-- Why it works: expected_date is order date + promised lead time, so past-due open POs are already later than promised.
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders)
SELECT su.supplier_name, COUNT(*) AS open_pos,
       COUNT(*) FILTER (WHERE pu.expected_date < asof.d) AS overdue_pos,
       MAX(asof.d - pu.expected_date) AS max_days_overdue,
       ROUND(SUM(pu.total_amount), 0) AS open_value
FROM purchases pu JOIN suppliers su ON su.supplier_id = pu.supplier_id CROSS JOIN asof
WHERE pu.status = 'ORDERED'
GROUP BY su.supplier_name
ORDER BY overdue_pos DESC, open_value DESC
LIMIT 15;

-- Q88 | Supplier scorecard ranking (composite)
-- Business question: Which suppliers look strongest and weakest overall on delivery reliability?
-- Approach: PERCENT_RANK for on-time %, fill rate and lead-time gap, averaged into one score (1.0 = best).
-- Concepts: PERCENT_RANK, multiple CTEs, composite score, ORDER BY on the score.
-- Why it works: percent ranks put three different units on the same 0-1 scale. The equal weighting is an assumption -
--               a real team would choose weights that match its priorities.
WITH po AS (
    SELECT pu.supplier_id, COUNT(*) AS pos,
           100.0 * COUNT(*) FILTER (WHERE pu.received_date <= pu.expected_date) / COUNT(*) AS on_time_pct,
           AVG(pu.received_date - pu.order_date) AS actual_days
    FROM purchases pu WHERE pu.status = 'RECEIVED' GROUP BY pu.supplier_id HAVING COUNT(*) >= 30
), fill AS (
    SELECT pu.supplier_id, 100.0 * SUM(pi.quantity_received) / SUM(pi.quantity_ordered) AS fill_rate_pct
    FROM purchase_items pi JOIN purchases pu ON pu.purchase_id = pi.purchase_id AND pu.status = 'RECEIVED'
    GROUP BY pu.supplier_id
), scored AS (
    SELECT su.supplier_name, po.pos, po.on_time_pct, f.fill_rate_pct, po.actual_days - su.lead_time_days AS gap_days,
           (PERCENT_RANK() OVER (ORDER BY po.on_time_pct)
          + PERCENT_RANK() OVER (ORDER BY f.fill_rate_pct)
          + PERCENT_RANK() OVER (ORDER BY -(po.actual_days - su.lead_time_days))) / 3 AS score
    FROM po JOIN fill f ON f.supplier_id = po.supplier_id JOIN suppliers su ON su.supplier_id = po.supplier_id
)
SELECT supplier_name, pos AS received_pos, ROUND(on_time_pct, 1) AS on_time_pct, ROUND(fill_rate_pct, 1) AS fill_rate_pct,
       ROUND(gap_days, 1) AS lead_time_gap_days, ROUND(score::numeric, 2) AS composite_score,
       RANK() OVER (ORDER BY score DESC) AS overall_rank
FROM scored
ORDER BY overall_rank
LIMIT 10;

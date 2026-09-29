-- =============================================================================
-- 10_data_quality_checks.sql : find the problems in the data before trusting any analysis
--
-- Two kinds of checks:
--   * CONSTRAINT-BACKED (negative price, zero quantity, orphan rows, invalid dates ...): the database already blocks them,
--     so the expected result is 0. Running the check proves the rule holds.
--   * REAL-WORLD ISSUES (duplicates, NULLs, bad formats, ledger mismatch ...): the schema allows them on purpose,
--     because real source systems contain them. These checks find them.
-- Nothing here changes data. Cleaning decisions (merge, fix, exclude) are documented in docs/09_data_quality.md.
-- =============================================================================

-- Q301 | Data-quality scorecard (one row per check)
-- Business question: How healthy is the data overall, and which issues need attention first?
-- Approach: each check is a small sub-query returning an issue count; UNION ALL stacks them, an outer query adds rate and status.
-- Concepts: UNION ALL of scalar subqueries, regex operators (!~), window ROW_NUMBER for duplicates, anti-joins with NOT EXISTS.
-- Why it works: every row has the same columns, so the result reads like a checklist. status = PASS only when issue_count = 0.
WITH checks AS (
    SELECT 'DQ01' AS check_id, 'customers' AS table_name, 'Duplicate-like customers (same e-mail ignoring case/spaces)' AS check_name, 'Medium' AS severity,
           (SELECT COUNT(*) FROM (SELECT ROW_NUMBER() OVER (PARTITION BY LOWER(TRIM(email)) ORDER BY customer_id) AS rn
                                  FROM customers WHERE email IS NOT NULL) t WHERE rn > 1) AS issue_count,
           (SELECT COUNT(*) FROM customers) AS total_rows
    UNION ALL SELECT 'DQ02', 'customers', 'NULL e-mail', 'Low',
           (SELECT COUNT(*) FROM customers WHERE email IS NULL), (SELECT COUNT(*) FROM customers)
    UNION ALL SELECT 'DQ03', 'customers', 'NULL phone', 'Low',
           (SELECT COUNT(*) FROM customers WHERE phone IS NULL), (SELECT COUNT(*) FROM customers)
    UNION ALL SELECT 'DQ04', 'customers', 'Invalid e-mail format', 'Medium',
           (SELECT COUNT(*) FROM customers WHERE email IS NOT NULL
                   AND (email !~ '^[^@[:space:]]+@[^@[:space:]]+[.][A-Za-z]{2,}$' OR POSITION('..' IN email) > 0)),
           (SELECT COUNT(*) FROM customers WHERE email IS NOT NULL)
    UNION ALL SELECT 'DQ05', 'customers', 'Invalid phone number (not a 10-digit Indian mobile)', 'Medium',
           (SELECT COUNT(*) FROM customers WHERE phone IS NOT NULL
                   AND REGEXP_REPLACE(phone, '[^0-9]', '', 'g') !~ '^(91)?[6-9][0-9]{9}$'),
           (SELECT COUNT(*) FROM customers WHERE phone IS NOT NULL)
    UNION ALL SELECT 'DQ06', 'customers', 'Implausible date of birth (before 1920 or in the future)', 'Medium',
           (SELECT COUNT(*) FROM customers WHERE date_of_birth < DATE '1920-01-01' OR date_of_birth > CURRENT_DATE),
           (SELECT COUNT(date_of_birth) FROM customers)
    UNION ALL SELECT 'DQ07', 'customers', 'Inconsistent name capitalisation or trailing spaces', 'Low',
           (SELECT COUNT(*) FROM customers WHERE first_name = UPPER(first_name) OR first_name = LOWER(first_name)
                   OR first_name <> TRIM(first_name) OR last_name <> TRIM(last_name)),
           (SELECT COUNT(*) FROM customers)
    UNION ALL SELECT 'DQ08', 'customers', 'Missing city', 'Low',
           (SELECT COUNT(*) FROM customers WHERE city IS NULL), (SELECT COUNT(*) FROM customers)
    UNION ALL SELECT 'DQ09', 'customers', 'No customer segment assigned', 'Low',
           (SELECT COUNT(*) FROM customers WHERE segment_id IS NULL), (SELECT COUNT(*) FROM customers)
    UNION ALL SELECT 'DQ10', 'products', 'Duplicate-like products (same name ignoring case/spaces)', 'Medium',
           (SELECT COUNT(*) FROM (SELECT ROW_NUMBER() OVER (PARTITION BY LOWER(TRIM(product_name)) ORDER BY product_id) AS rn
                                  FROM products) t WHERE rn > 1),
           (SELECT COUNT(*) FROM products)
    UNION ALL SELECT 'DQ11', 'products', 'Products without a category', 'High',
           (SELECT COUNT(*) FROM products WHERE category_id IS NULL), (SELECT COUNT(*) FROM products)
    UNION ALL SELECT 'DQ12', 'products', 'Products without a supplier', 'High',
           (SELECT COUNT(*) FROM products WHERE supplier_id IS NULL), (SELECT COUNT(*) FROM products)
    UNION ALL SELECT 'DQ13', 'products', 'Products without a brand', 'Low',
           (SELECT COUNT(*) FROM products WHERE brand IS NULL), (SELECT COUNT(*) FROM products)
    UNION ALL SELECT 'DQ14', 'categories', 'Category names that differ only by capitalisation', 'High',
           (SELECT COUNT(*) FROM (SELECT ROW_NUMBER() OVER (PARTITION BY LOWER(category_name) ORDER BY category_id) AS rn
                                  FROM categories) t WHERE rn > 1),
           (SELECT COUNT(*) FROM categories)
    UNION ALL SELECT 'DQ15', 'products', 'Negative or zero price / cost (blocked by CHECK)', 'High',
           (SELECT COUNT(*) FROM products WHERE unit_price <= 0 OR unit_cost < 0), (SELECT COUNT(*) FROM products)
    UNION ALL SELECT 'DQ16', 'sales_order_items', 'Quantity zero or negative (blocked by CHECK)', 'High',
           (SELECT COUNT(*) FROM sales_order_items WHERE quantity <= 0), (SELECT COUNT(*) FROM sales_order_items)
    UNION ALL SELECT 'DQ17', 'sales_order_items', 'Unusually large quantity (25 or more units on one line)', 'Medium',
           (SELECT COUNT(*) FROM sales_order_items WHERE quantity >= 25), (SELECT COUNT(*) FROM sales_order_items)
    UNION ALL SELECT 'DQ18', 'sales_orders', 'Order header total differs from the sum of its lines', 'High',
           (SELECT COUNT(*) FROM sales_orders o JOIN (SELECT order_id, SUM(line_total) AS s FROM sales_order_items GROUP BY order_id) i
                   ON i.order_id = o.order_id WHERE ABS(o.total_amount - i.s) > 0.05),
           (SELECT COUNT(*) FROM sales_orders)
    UNION ALL SELECT 'DQ19', 'multiple', 'Orphan records (child rows without a parent)', 'High',
           (SELECT (SELECT COUNT(*) FROM sales_order_items i WHERE NOT EXISTS (SELECT 1 FROM sales_orders o WHERE o.order_id = i.order_id))
                 + (SELECT COUNT(*) FROM payments p WHERE NOT EXISTS (SELECT 1 FROM sales_orders o WHERE o.order_id = p.order_id))
                 + (SELECT COUNT(*) FROM returns r WHERE NOT EXISTS (SELECT 1 FROM sales_orders o WHERE o.order_id = r.order_id))
                 + (SELECT COUNT(*) FROM inventory v WHERE NOT EXISTS (SELECT 1 FROM products p WHERE p.product_id = v.product_id))),
           (SELECT COUNT(*) FROM sales_order_items) + (SELECT COUNT(*) FROM payments) + (SELECT COUNT(*) FROM returns) + (SELECT COUNT(*) FROM inventory)
    UNION ALL SELECT 'DQ20', 'multiple', 'Impossible date order (order before registration, return before order, PO received before ordered)', 'High',
           (SELECT (SELECT COUNT(*) FROM sales_orders o JOIN customers c USING (customer_id) WHERE o.order_date::date < c.registration_date)
                 + (SELECT COUNT(*) FROM returns r JOIN sales_orders o USING (order_id) WHERE r.return_date < o.order_date)
                 + (SELECT COUNT(*) FROM purchases WHERE received_date < order_date)),
           (SELECT COUNT(*) FROM sales_orders) + (SELECT COUNT(*) FROM returns) + (SELECT COUNT(*) FROM purchases)
    UNION ALL SELECT 'DQ21', 'sales_orders', 'Completed orders with no payment record', 'High',
           (SELECT COUNT(*) FROM sales_orders o WHERE order_status = 'COMPLETED' AND NOT EXISTS (SELECT 1 FROM payments p WHERE p.order_id = o.order_id)),
           (SELECT COUNT(*) FROM sales_orders WHERE order_status = 'COMPLETED')
    UNION ALL SELECT 'DQ22', 'sales_orders', 'Completed orders where successful payments differ from the order total', 'High',
           (SELECT COUNT(*) FROM sales_orders o JOIN (SELECT order_id, SUM(amount) AS paid FROM payments WHERE payment_status = 'SUCCESS' GROUP BY order_id) p
                   ON p.order_id = o.order_id WHERE o.order_status = 'COMPLETED' AND ABS(o.total_amount - p.paid) > 0.01),
           (SELECT COUNT(*) FROM sales_orders WHERE order_status = 'COMPLETED')
    UNION ALL SELECT 'DQ23', 'inventory', 'Stock on hand differs from the sum of the inventory ledger', 'High',
           (SELECT COUNT(*) FROM inventory i LEFT JOIN (SELECT store_id, product_id, SUM(quantity_change) AS qty FROM inventory_transactions GROUP BY 1, 2) l
                   USING (store_id, product_id) WHERE i.quantity_on_hand <> COALESCE(l.qty, 0)),
           (SELECT COUNT(*) FROM inventory)
    UNION ALL SELECT 'DQ24', 'inventory', 'Positions with zero stock on hand', 'Info',
           (SELECT COUNT(*) FROM inventory WHERE quantity_on_hand = 0), (SELECT COUNT(*) FROM inventory)
    UNION ALL SELECT 'DQ25', 'products', 'Inactive products that still hold stock', 'Medium',
           (SELECT COUNT(DISTINCT p.product_id) FROM products p JOIN inventory i USING (product_id) WHERE NOT p.is_active AND i.quantity_on_hand > 0),
           (SELECT COUNT(*) FROM products WHERE NOT is_active)
    UNION ALL SELECT 'DQ26', 'customers', 'Customers flagged inactive who ordered in the last 90 days', 'Medium',
           (SELECT COUNT(DISTINCT c.customer_id) FROM customers c JOIN sales_orders o USING (customer_id)
            WHERE NOT c.is_active AND o.order_date > (SELECT MAX(order_date) FROM sales_orders) - INTERVAL '90 days'),
           (SELECT COUNT(*) FROM customers WHERE NOT is_active)
    UNION ALL SELECT 'DQ27', 'suppliers', 'Suppliers missing e-mail, phone or GSTIN', 'Medium',
           (SELECT COUNT(*) FROM suppliers WHERE contact_email IS NULL OR contact_phone IS NULL OR gstin IS NULL), (SELECT COUNT(*) FROM suppliers)
    UNION ALL SELECT 'DQ28', 'products', 'Products never sold', 'Info',
           (SELECT COUNT(*) FROM products p WHERE NOT EXISTS (SELECT 1 FROM sales_order_items i WHERE i.product_id = p.product_id)), (SELECT COUNT(*) FROM products)
    UNION ALL SELECT 'DQ29', 'sales_orders', 'Cancelled orders (kept in the data, excluded from KPIs)', 'Info',
           (SELECT COUNT(*) FROM sales_orders WHERE order_status = 'CANCELLED'), (SELECT COUNT(*) FROM sales_orders)
    UNION ALL SELECT 'DQ30', 'inventory_transactions', 'Cancelled orders that moved stock (must be none)', 'High',
           (SELECT COUNT(*) FROM inventory_transactions t JOIN sales_orders o ON o.order_id = t.reference_id
            WHERE t.transaction_type = 'SALE' AND o.order_status = 'CANCELLED'),
           (SELECT COUNT(*) FROM inventory_transactions WHERE transaction_type = 'SALE')
)
SELECT check_id, table_name, check_name, severity, issue_count, total_rows,
       ROUND(100.0 * issue_count / NULLIF(total_rows, 0), 2) AS issue_pct,
       CASE WHEN issue_count = 0 THEN 'PASS' WHEN severity = 'Info' THEN 'INFO' ELSE 'ATTENTION' END AS status
FROM checks
ORDER BY check_id;

-- Q302 | Duplicate customer groups (detail)
-- Business question: Which customer records look like the same person?
-- Approach: group by normalised e-mail and list all IDs with STRING_AGG.
-- Concepts: STRING_AGG, HAVING COUNT(*) > 1, normalising keys with LOWER/TRIM.
-- Why it works: rows sharing a normalised e-mail are candidates; a human should confirm before merging (two family members can share an e-mail).
SELECT LOWER(TRIM(email)) AS normalised_email, COUNT(*) AS records,
       STRING_AGG(customer_id::text, ', ' ORDER BY customer_id) AS customer_ids,
       STRING_AGG(first_name, ' | ' ORDER BY customer_id) AS name_variants
FROM customers WHERE email IS NOT NULL
GROUP BY LOWER(TRIM(email))
HAVING COUNT(*) > 1
ORDER BY records DESC, normalised_email
LIMIT 10;

-- Q303 | Duplicate-like products (detail)
-- Business question: Which product rows repeat the same item under different SKUs?
-- Approach: SELF JOIN on the normalised name with a.product_id < b.product_id so each pair appears once.
-- Concepts: SELF JOIN, pair de-duplication, string normalisation.
-- Why it works: the inequality removes mirrored pairs and self-matches.
SELECT a.product_id AS product_a, a.sku AS sku_a, b.product_id AS product_b, b.sku AS sku_b, a.product_name AS name_a, b.product_name AS name_b
FROM products a JOIN products b ON LOWER(TRIM(a.product_name)) = LOWER(TRIM(b.product_name)) AND a.product_id < b.product_id
ORDER BY a.product_id;

-- Q304 | NULL profile of the customers table
-- Business question: How complete is each customer column?
-- Approach: COUNT(*) minus COUNT(column) gives NULLs per column; UNION ALL turns columns into rows.
-- Concepts: COUNT(col) ignores NULLs, UNION ALL, unpivoting columns to rows manually.
-- Why it works: COUNT(*) counts rows, COUNT(email) counts non-NULL e-mails, so the difference is the NULL count.
SELECT 'email' AS column_name, COUNT(*) - COUNT(email) AS null_count, ROUND(100.0 * (COUNT(*) - COUNT(email)) / COUNT(*), 2) AS null_pct FROM customers
UNION ALL SELECT 'phone', COUNT(*) - COUNT(phone), ROUND(100.0 * (COUNT(*) - COUNT(phone)) / COUNT(*), 2) FROM customers
UNION ALL SELECT 'gender', COUNT(*) - COUNT(gender), ROUND(100.0 * (COUNT(*) - COUNT(gender)) / COUNT(*), 2) FROM customers
UNION ALL SELECT 'date_of_birth', COUNT(*) - COUNT(date_of_birth), ROUND(100.0 * (COUNT(*) - COUNT(date_of_birth)) / COUNT(*), 2) FROM customers
UNION ALL SELECT 'city', COUNT(*) - COUNT(city), ROUND(100.0 * (COUNT(*) - COUNT(city)) / COUNT(*), 2) FROM customers
UNION ALL SELECT 'segment_id', COUNT(*) - COUNT(segment_id), ROUND(100.0 * (COUNT(*) - COUNT(segment_id)) / COUNT(*), 2) FROM customers
ORDER BY null_pct DESC;

-- Q305 | Invalid e-mail and phone samples
-- Business question: What do the bad contact details look like?
-- Approach: apply the same regex rules as the scorecard and show a few examples of each.
-- Concepts: regular expressions in PostgreSQL (!~), UNION ALL of two limited samples.
-- Why it works: seeing real examples tells you whether to fix them automatically or ask the customer.
(SELECT 'invalid e-mail' AS issue, customer_id, email AS value FROM customers
 WHERE email IS NOT NULL AND (email !~ '^[^@[:space:]]+@[^@[:space:]]+[.][A-Za-z]{2,}$' OR POSITION('..' IN email) > 0)
 ORDER BY customer_id LIMIT 6)
UNION ALL
(SELECT 'invalid phone', customer_id, phone FROM customers
 WHERE phone IS NOT NULL AND REGEXP_REPLACE(phone, '[^0-9]', '', 'g') !~ '^(91)?[6-9][0-9]{9}$'
 ORDER BY customer_id LIMIT 6);

-- Q306 | Inventory positions where stock does not match the ledger
-- Business question: Where is the recorded stock different from what the movement history says it should be?
-- Approach: compare inventory.quantity_on_hand with the sum of quantity_change per store+product; show the biggest differences.
-- Concepts: LEFT JOIN to an aggregated ledger, COALESCE, ABS, ordering by size of the difference.
-- Why it works: the ledger is the audit trail of every movement, so any difference means an unrecorded movement or an entry error.
SELECT s.store_name, p.product_name, i.quantity_on_hand AS recorded_stock, COALESCE(l.qty, 0) AS ledger_stock,
       i.quantity_on_hand - COALESCE(l.qty, 0) AS difference
FROM inventory i
LEFT JOIN (SELECT store_id, product_id, SUM(quantity_change) AS qty FROM inventory_transactions GROUP BY 1, 2) l
       ON l.store_id = i.store_id AND l.product_id = i.product_id
JOIN stores s ON s.store_id = i.store_id
JOIN products p ON p.product_id = i.product_id
WHERE i.quantity_on_hand <> COALESCE(l.qty, 0)
ORDER BY ABS(i.quantity_on_hand - COALESCE(l.qty, 0)) DESC, s.store_name
LIMIT 15;

-- Q307 | Extreme order-line quantities
-- Business question: Which order lines have unusually high quantities and might be data-entry errors or genuine bulk buys?
-- Approach: show lines with 25+ units alongside the product's typical quantity per line.
-- Concepts: window AVG over the product, ratio to the typical value, ordering.
-- Why it works: comparing with the product's own average avoids flagging products that are normally bought in bulk (like staples).
SELECT i.order_item_id, o.order_id, p.product_name, i.quantity,
       ROUND(AVG(i.quantity) OVER (PARTITION BY i.product_id), 1) AS avg_qty_for_product,
       ROUND(i.line_total, 0) AS line_total, o.order_status
FROM sales_order_items i
JOIN sales_orders o ON o.order_id = i.order_id
JOIN products p ON p.product_id = i.product_id
ORDER BY i.quantity DESC
LIMIT 10;

-- Q308 | Completed orders without a payment record
-- Business question: Which completed orders have no payment on file (revenue that may not have been collected or recorded)?
-- Approach: LEFT JOIN payments and keep rows where no payment matched.
-- Concepts: anti-join with LEFT JOIN ... IS NULL, grouping by store.
-- Why it works: unmatched orders have NULL on the payments side. A high concentration in one store could point to a process problem.
SELECT s.store_name, COUNT(*) AS orders_without_payment, ROUND(SUM(o.total_amount), 0) AS order_value
FROM sales_orders o
JOIN stores s ON s.store_id = o.store_id
LEFT JOIN payments p ON p.order_id = o.order_id
WHERE o.order_status = 'COMPLETED' AND p.payment_id IS NULL
GROUP BY s.store_name
ORDER BY orders_without_payment DESC;

-- Q309 | Category names that differ only by capitalisation
-- Business question: Which category names are duplicates once case is ignored, and how many products sit under each variant?
-- Approach: group by LOWER(name), list the variants and product counts.
-- Concepts: STRING_AGG, LOWER, LEFT JOIN, HAVING.
-- Why it works: every group with more than one row is a duplicate in business terms, even though the UNIQUE constraint (case-sensitive) allows it.
SELECT LOWER(c.category_name) AS normalised_name,
       STRING_AGG(c.category_name || ' (id ' || c.category_id || ', ' || COALESCE(pc.products, 0) || ' products)', ' ; ' ORDER BY c.category_id) AS variants
FROM categories c
LEFT JOIN (SELECT category_id, COUNT(*) AS products FROM products GROUP BY category_id) pc ON pc.category_id = c.category_id
GROUP BY LOWER(c.category_name)
HAVING COUNT(*) > 1;

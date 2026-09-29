-- =============================================================================
-- 05_inventory_analysis.sql : stock levels, health classification, turnover, cover, aging, risk
--
-- PROJECT ASSUMPTIONS (not universal rules - documented in docs/06_inventory_metrics.md):
--   * As-of date = last order date. Demand windows are counted back from it.
--   * units_90d  = units sold at that store in the last 90 days (completed orders).
--   * Days of cover = quantity_on_hand / (units_90d / 90).  NULL when there was no demand.
--   * Inventory health status per store+product, first matching rule wins:
--       OUT_OF_STOCK : quantity_on_hand = 0
--       DEAD_STOCK   : stock on hand but no sale at that store in the last 365 days
--       LOW_STOCK    : quantity_on_hand <= reorder_level
--       OVERSTOCKED  : quantity_on_hand > max_stock_level  OR  days of cover > 180
--       HEALTHY      : everything else
--   * Inventory value = quantity_on_hand * unit_cost (current standard cost, ex-GST).
-- =============================================================================

-- Q59 | Inventory position by store
-- Business question: How much stock does each location hold and what is it worth?
-- Approach: join inventory to products, sum units and value; show available stock (on hand minus reserved).
-- Concepts: JOIN, SUM of an expression, derived columns, ORDER BY.
-- Why it works: value at cost = units * unit_cost; value at selling price uses price net of GST for comparability with revenue.
SELECT s.store_name,
       SUM(i.quantity_on_hand)                                                  AS units_on_hand,
       SUM(i.reserved_quantity)                                                 AS units_reserved,
       SUM(i.quantity_on_hand - i.reserved_quantity)                            AS units_available,
       ROUND(SUM(i.quantity_on_hand * p.unit_cost), 0)                          AS value_at_cost,
       ROUND(SUM(i.quantity_on_hand * p.unit_price / (1 + p.gst_rate / 100.0)), 0) AS value_at_net_price,
       COUNT(*)                                                                 AS stocked_products
FROM inventory i
JOIN products p ON p.product_id = i.product_id
JOIN stores s   ON s.store_id = i.store_id
GROUP BY s.store_name
ORDER BY value_at_cost DESC;

-- Q60 | Inventory health classification summary
-- Business question: How many store-product positions are out of stock, low, healthy, overstocked or dead?
-- Approach: compute recent demand per store+product, apply the ordered CASE rules above, then summarise per status.
-- Concepts: CTEs, FILTER inside aggregates, LEFT JOIN, CASE with priority, percent of total.
-- Why it works: CASE evaluates top-down and stops at the first match, so the rule order encodes the priority.
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders),
demand AS (
    SELECT o.store_id, i.product_id,
           SUM(i.quantity) FILTER (WHERE o.order_date::date > asof.d - 90)  AS units_90d,
           SUM(i.quantity) FILTER (WHERE o.order_date::date > asof.d - 365) AS units_365d
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    CROSS JOIN asof
    WHERE o.order_date::date > asof.d - 365
    GROUP BY o.store_id, i.product_id
), health AS (
    SELECT inv.store_id, inv.product_id, inv.quantity_on_hand, p.unit_cost,
           CASE WHEN inv.quantity_on_hand = 0                                        THEN 'OUT_OF_STOCK'
                WHEN COALESCE(d.units_365d, 0) = 0                                   THEN 'DEAD_STOCK'
                WHEN inv.quantity_on_hand <= inv.reorder_level                       THEN 'LOW_STOCK'
                WHEN inv.quantity_on_hand > inv.max_stock_level
                  OR inv.quantity_on_hand / (COALESCE(d.units_90d, 0) / 90.0 + 0.000001) > 180 THEN 'OVERSTOCKED'
                ELSE 'HEALTHY' END AS status
    FROM inventory inv
    JOIN products p ON p.product_id = inv.product_id
    LEFT JOIN demand d ON d.store_id = inv.store_id AND d.product_id = inv.product_id
)
SELECT status,
       COUNT(*)                                             AS store_product_positions,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)   AS share_of_positions_pct,
       SUM(quantity_on_hand)                                AS units,
       ROUND(SUM(quantity_on_hand * unit_cost), 0)          AS value_at_cost,
       ROUND(100.0 * SUM(quantity_on_hand * unit_cost) / SUM(SUM(quantity_on_hand * unit_cost)) OVER (), 1) AS share_of_value_pct
FROM health
GROUP BY status
ORDER BY CASE status WHEN 'OUT_OF_STOCK' THEN 1 WHEN 'LOW_STOCK' THEN 2 WHEN 'HEALTHY' THEN 3
                     WHEN 'OVERSTOCKED' THEN 4 ELSE 5 END;

-- Q61 | Replenishment list: sellers that are out of stock or below reorder level
-- Business question: Which store-product positions need re-ordering now, and how much?
-- Approach: positions at or below reorder level that sold in the last 90 days; inbound quantity on open POs is netted off.
-- Concepts: correlated scalar subquery for inbound stock, GREATEST, ordering by demand.
-- Why it works: suggested quantity = max_stock_level - on_hand - inbound, floored at 0. Sorting by daily demand puts the
--               positions that will run out soonest first.
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders),
demand AS (
    SELECT o.store_id, i.product_id, SUM(i.quantity) AS units_90d
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    CROSS JOIN asof
    WHERE o.order_date::date > asof.d - 90
    GROUP BY o.store_id, i.product_id
)
SELECT s.store_name, p.product_name, inv.quantity_on_hand, inv.reorder_level, inv.max_stock_level,
       ROUND(d.units_90d / 90.0, 2) AS avg_daily_demand,
       COALESCE((SELECT SUM(pi.quantity_ordered)
                 FROM purchase_items pi JOIN purchases pu ON pu.purchase_id = pi.purchase_id
                 WHERE pu.status = 'ORDERED' AND pu.store_id = inv.store_id AND pi.product_id = inv.product_id), 0) AS inbound_on_open_pos,
       GREATEST(inv.max_stock_level - inv.quantity_on_hand - COALESCE((SELECT SUM(pi.quantity_ordered)
                 FROM purchase_items pi JOIN purchases pu ON pu.purchase_id = pi.purchase_id
                 WHERE pu.status = 'ORDERED' AND pu.store_id = inv.store_id AND pi.product_id = inv.product_id), 0), 0) AS suggested_order_qty
FROM inventory inv
JOIN demand d   ON d.store_id = inv.store_id AND d.product_id = inv.product_id
JOIN products p ON p.product_id = inv.product_id
JOIN stores s   ON s.store_id = inv.store_id
WHERE inv.quantity_on_hand <= inv.reorder_level
ORDER BY d.units_90d DESC
LIMIT 25;

-- Q62 | Inventory turnover and days of inventory by category
-- Business question: How quickly does stock convert into sales, category by category?
-- Approach: turnover = cost of goods sold in the last 365 days / current inventory value at cost.
--           Days of inventory = 365 / turnover.
-- Concepts: two CTEs joined on category, canonical category via window MIN, NULLIF, ratio metrics.
-- Why it works: this is a simplified turnover using ENDING inventory (a full version would average opening and closing stock).
--               Treat it as an approximation and compare categories with each other rather than against outside benchmarks.
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders),
canon AS (
    SELECT category_id, MIN(category_id) OVER (PARTITION BY LOWER(category_name)) AS canonical_id FROM categories
), cogs AS (
    SELECT c.canonical_id, SUM(i.quantity * i.unit_cost) AS cogs_12m
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products p ON p.product_id = i.product_id
    JOIN canon c ON c.category_id = p.category_id
    CROSS JOIN asof
    WHERE o.order_date::date > asof.d - 365
    GROUP BY c.canonical_id
), stock AS (
    SELECT c.canonical_id, SUM(inv.quantity_on_hand * p.unit_cost) AS inventory_value
    FROM inventory inv
    JOIN products p ON p.product_id = inv.product_id
    JOIN canon c ON c.category_id = p.category_id
    GROUP BY c.canonical_id
)
SELECT cat.category_name,
       ROUND(cogs.cogs_12m, 0)                              AS cogs_last_12m,
       ROUND(stock.inventory_value, 0)                      AS inventory_value,
       ROUND(cogs.cogs_12m / NULLIF(stock.inventory_value, 0), 2)              AS inventory_turnover,
       ROUND(365 * stock.inventory_value / NULLIF(cogs.cogs_12m, 0), 0)        AS days_of_inventory
FROM cogs
JOIN stock ON stock.canonical_id = cogs.canonical_id
JOIN categories cat ON cat.category_id = cogs.canonical_id
ORDER BY inventory_turnover DESC;

-- Q63 | Stock coverage: how many days will current stock last?
-- Business question: Across positions with recent demand, how long will stock last at the current sales rate?
-- Approach: days of cover = on hand / average daily demand of the last 90 days, bucketed with CASE.
-- Concepts: CASE bucketing on a computed ratio, JOIN to aggregated demand, percent of total.
-- Why it works: only positions with demand can have a finite cover. Zero-demand positions are reported separately in Q60 (DEAD_STOCK).
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders),
demand AS (
    SELECT o.store_id, i.product_id, SUM(i.quantity) / 90.0 AS daily_demand
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    CROSS JOIN asof
    WHERE o.order_date::date > asof.d - 90
    GROUP BY o.store_id, i.product_id
), cover AS (
    SELECT inv.quantity_on_hand / d.daily_demand AS days_cover, inv.quantity_on_hand * p.unit_cost AS value
    FROM inventory inv
    JOIN demand d ON d.store_id = inv.store_id AND d.product_id = inv.product_id
    JOIN products p ON p.product_id = inv.product_id
)
SELECT CASE WHEN days_cover < 7 THEN 'a) under 7 days' WHEN days_cover < 30 THEN 'b) 7-29 days'
            WHEN days_cover < 90 THEN 'c) 30-89 days' WHEN days_cover < 180 THEN 'd) 90-179 days'
            ELSE 'e) 180+ days' END AS stock_cover,
       COUNT(*) AS positions,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_pct,
       ROUND(SUM(value), 0) AS value_at_cost
FROM cover
GROUP BY 1
ORDER BY 1;

-- Q64 | Fast-moving and slow-moving product summary
-- Business question: Which products move fast, which move slowly, and which do not move at all?
-- Approach: units sold in the last 90 days per product (all stores); PERCENT_RANK among products that have stock decides the class.
-- Concepts: PERCENT_RANK window function, CASE, LEFT JOIN, aggregated inventory value.
-- Why it works: fast = top quarter by units, slow = bottom quarter of those that sold, non-moving = stock but zero sales.
--               The quartile cut-offs are project assumptions.
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders),
sold AS (
    SELECT i.product_id, SUM(i.quantity) AS units_90d
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    CROSS JOIN asof
    WHERE o.order_date::date > asof.d - 90
    GROUP BY i.product_id
), stocked AS (
    SELECT p.product_id, COALESCE(s.units_90d, 0) AS units_90d, SUM(inv.quantity_on_hand * p.unit_cost) AS value
    FROM inventory inv
    JOIN products p ON p.product_id = inv.product_id
    LEFT JOIN sold s ON s.product_id = p.product_id
    GROUP BY p.product_id, s.units_90d
    HAVING SUM(inv.quantity_on_hand) > 0
), ranked AS (
    SELECT *, PERCENT_RANK() OVER (PARTITION BY (units_90d > 0) ORDER BY units_90d) AS pr FROM stocked
)
SELECT CASE WHEN units_90d = 0 THEN 'NON_MOVING' WHEN pr >= 0.75 THEN 'FAST_MOVING'
            WHEN pr <= 0.25 THEN 'SLOW_MOVING' ELSE 'MEDIUM' END AS movement_class,
       COUNT(*) AS products, SUM(units_90d) AS units_sold_90d, ROUND(SUM(value), 0) AS stock_value_at_cost
FROM ranked
GROUP BY 1
ORDER BY MIN(pr) FILTER (WHERE units_90d > 0) DESC NULLS LAST;

-- Q65 | Top 10 fastest and slowest sellers (with stock)
-- Business question: Which specific products are the fastest and slowest movers right now?
-- Approach: two ordered, limited sub-selects combined with UNION ALL.
-- Concepts: UNION ALL of parenthesised SELECT ... ORDER BY ... LIMIT blocks, literal label column.
-- Why it works: parentheses let each half carry its own ORDER BY/LIMIT; the outer query then sorts by the label.
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders),
sold AS (
    SELECT i.product_id, SUM(i.quantity) AS units_90d
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    CROSS JOIN asof
    WHERE o.order_date::date > asof.d - 90
    GROUP BY i.product_id
), stocked AS (
    SELECT p.product_id, p.product_name, COALESCE(s.units_90d, 0) AS units_90d, SUM(inv.quantity_on_hand) AS units_in_stock
    FROM inventory inv
    JOIN products p ON p.product_id = inv.product_id
    LEFT JOIN sold s ON s.product_id = p.product_id
    GROUP BY p.product_id, p.product_name, s.units_90d
    HAVING SUM(inv.quantity_on_hand) > 0
)
(SELECT 'FASTEST' AS list, product_name, units_90d, units_in_stock FROM stocked ORDER BY units_90d DESC LIMIT 10)
UNION ALL
(SELECT 'SLOWEST (sold at least 1)', product_name, units_90d, units_in_stock FROM stocked WHERE units_90d > 0 ORDER BY units_90d, units_in_stock DESC LIMIT 10)
ORDER BY 1 DESC, 3 DESC;

-- Q66 | Inventory aging by days since last restock
-- Business question: How old is the stock we are holding?
-- Approach: days between the as-of date and last_restocked_date, bucketed; value at cost per bucket.
-- Concepts: date subtraction, CASE, aggregation, percent of total value.
-- Why it works: last_restocked_date is a proxy for age (it does not track individual batches), so this is an approximation.
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders)
SELECT CASE WHEN asof.d - inv.last_restocked_date <= 30  THEN 'a) 0-30 days'
            WHEN asof.d - inv.last_restocked_date <= 90  THEN 'b) 31-90 days'
            WHEN asof.d - inv.last_restocked_date <= 180 THEN 'c) 91-180 days'
            WHEN asof.d - inv.last_restocked_date <= 365 THEN 'd) 181-365 days'
            ELSE 'e) over 365 days' END AS stock_age,
       COUNT(*) AS positions,
       SUM(inv.quantity_on_hand) AS units,
       ROUND(SUM(inv.quantity_on_hand * p.unit_cost), 0) AS value_at_cost,
       ROUND(100.0 * SUM(inv.quantity_on_hand * p.unit_cost) / SUM(SUM(inv.quantity_on_hand * p.unit_cost)) OVER (), 1) AS share_of_value_pct
FROM inventory inv
JOIN products p ON p.product_id = inv.product_id
CROSS JOIN asof
WHERE inv.quantity_on_hand > 0
GROUP BY 1
ORDER BY 1;

-- Q67 | High-revenue products with low stock
-- Business question: Which top-selling products are close to running out across the network?
-- Approach: rank products into revenue quintiles (last 12 months); keep quintile 5 with less than 30 days of cover.
-- Concepts: NTILE(5), aggregated stock, CTEs, division with NULLIF, ordering by urgency.
-- Why it works: cover is computed on network totals (all stores), so a product can still be short in individual stores.
--               Quintile and 30-day thresholds are project assumptions.
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders),
sales12 AS (
    SELECT i.product_id, SUM(i.line_total / (1 + p.gst_rate / 100.0)) AS revenue_12m,
           SUM(i.quantity) FILTER (WHERE o.order_date::date > asof.d - 90) AS units_90d
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products p ON p.product_id = i.product_id
    CROSS JOIN asof
    WHERE o.order_date::date > asof.d - 365
    GROUP BY i.product_id
), stock AS (
    SELECT product_id, SUM(quantity_on_hand) AS units_in_stock FROM inventory GROUP BY product_id
), scored AS (
    SELECT p.product_id, p.product_name, COALESCE(s.revenue_12m, 0) AS revenue_12m, COALESCE(s.units_90d, 0) AS units_90d,
           COALESCE(st.units_in_stock, 0) AS units_in_stock,
           NTILE(5) OVER (ORDER BY COALESCE(s.revenue_12m, 0)) AS revenue_quintile
    FROM products p
    LEFT JOIN sales12 s ON s.product_id = p.product_id
    LEFT JOIN stock st ON st.product_id = p.product_id
)
SELECT product_name, ROUND(revenue_12m, 0) AS revenue_12m, units_90d, units_in_stock,
       ROUND(units_in_stock / NULLIF(units_90d / 90.0, 0), 1) AS days_of_cover
FROM scored
WHERE revenue_quintile = 5 AND units_90d > 0 AND units_in_stock / (units_90d / 90.0) < 30
ORDER BY days_of_cover, revenue_12m DESC
LIMIT 20;

-- Q68 | Low-revenue products with high stock
-- Business question: Which weak sellers are tying up the most money in stock?
-- Approach: revenue quintile 1-2 (last 12 months) that hold more than 180 days of cover or have sold nothing in 90 days.
-- Concepts: NTILE, OR condition with NULL-safe cover logic, ordering by capital tied up.
-- Why it works: ordering by stock value at cost surfaces where the largest amount of capital is locked in slow items.
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders),
sales12 AS (
    SELECT i.product_id, SUM(i.line_total / (1 + p.gst_rate / 100.0)) AS revenue_12m,
           SUM(i.quantity) FILTER (WHERE o.order_date::date > asof.d - 90) AS units_90d
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products p ON p.product_id = i.product_id
    CROSS JOIN asof
    WHERE o.order_date::date > asof.d - 365
    GROUP BY i.product_id
), stock AS (
    SELECT inv.product_id, SUM(inv.quantity_on_hand) AS units_in_stock, SUM(inv.quantity_on_hand * p.unit_cost) AS value
    FROM inventory inv JOIN products p ON p.product_id = inv.product_id
    GROUP BY inv.product_id
), scored AS (
    SELECT p.product_id, p.product_name, COALESCE(s.revenue_12m, 0) AS revenue_12m, COALESCE(s.units_90d, 0) AS units_90d,
           st.units_in_stock, st.value,
           NTILE(5) OVER (ORDER BY COALESCE(s.revenue_12m, 0)) AS revenue_quintile
    FROM products p
    LEFT JOIN sales12 s ON s.product_id = p.product_id
    JOIN stock st ON st.product_id = p.product_id
    WHERE st.units_in_stock > 0
)
SELECT product_name, ROUND(revenue_12m, 0) AS revenue_12m, units_90d, units_in_stock, ROUND(value, 0) AS stock_value_at_cost,
       ROUND(units_in_stock / NULLIF(units_90d / 90.0, 0), 0) AS days_of_cover
FROM scored
WHERE revenue_quintile <= 2 AND (units_90d = 0 OR units_in_stock / (units_90d / 90.0) > 180)
ORDER BY value DESC
LIMIT 20;

-- Q69 | Product classification matrix: revenue tier versus stock tier
-- Business question: Which products are in each of the four revenue/stock situations that management cares about?
-- Approach: revenue tier from quintile (High = top quintile, Low = bottom two); stock tier from network days of cover.
-- Concepts: NTILE, nested CASE, GROUP BY on derived classes, aggregate value.
-- Why it works: the cells are defined only by the thresholds below (assumptions): Low stock = under 30 days of cover,
--               High stock = over 180 days or no recent sales.
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders),
sales12 AS (
    SELECT i.product_id, SUM(i.line_total / (1 + p.gst_rate / 100.0)) AS revenue_12m,
           SUM(i.quantity) FILTER (WHERE o.order_date::date > asof.d - 90) AS units_90d
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    JOIN products p ON p.product_id = i.product_id
    CROSS JOIN asof
    WHERE o.order_date::date > asof.d - 365
    GROUP BY i.product_id
), stock AS (
    SELECT inv.product_id, SUM(inv.quantity_on_hand) AS units_in_stock, SUM(inv.quantity_on_hand * p.unit_cost) AS value
    FROM inventory inv JOIN products p ON p.product_id = inv.product_id
    GROUP BY inv.product_id
), scored AS (
    SELECT p.product_id, COALESCE(s.revenue_12m, 0) AS revenue_12m, COALESCE(s.units_90d, 0) AS units_90d,
           st.units_in_stock, st.value,
           NTILE(5) OVER (ORDER BY COALESCE(s.revenue_12m, 0)) AS q
    FROM products p
    LEFT JOIN sales12 s ON s.product_id = p.product_id
    JOIN stock st ON st.product_id = p.product_id
)
SELECT CASE WHEN q = 5 AND units_90d > 0 AND units_in_stock / (units_90d / 90.0) < 30               THEN 'High Revenue / Low Stock'
            WHEN q = 5 AND units_90d > 0 AND units_in_stock / (units_90d / 90.0) BETWEEN 30 AND 180 THEN 'High Revenue / Healthy Stock'
            WHEN q <= 2 AND (units_90d = 0 OR units_in_stock / (units_90d / 90.0) > 180)             THEN 'Low Revenue / High Stock'
            WHEN q <= 2 AND units_90d > 0 AND units_in_stock / (units_90d / 90.0) < 30               THEN 'Low Revenue / Low Stock'
            ELSE 'Other' END AS product_class,
       COUNT(*) AS products, ROUND(SUM(revenue_12m), 0) AS revenue_12m, ROUND(SUM(value), 0) AS stock_value_at_cost
FROM scored
GROUP BY 1
ORDER BY 1;

-- Q70 | Monthly stock movements by transaction type
-- Business question: How do purchases, sales, returns and adjustments move stock month by month?
-- Approach: conditional aggregation over the inventory ledger, one column per movement type.
-- Concepts: FILTER pivot, DATE_TRUNC, signed quantities, net change.
-- Why it works: quantity_change is positive when stock is added and negative when removed, so the row sum is the net movement.
SELECT DATE_TRUNC('month', transaction_date)::date AS month,
       SUM(quantity_change) FILTER (WHERE transaction_type = 'PURCHASE')   AS purchased,
       -SUM(quantity_change) FILTER (WHERE transaction_type = 'SALE')       AS sold,
       SUM(quantity_change) FILTER (WHERE transaction_type = 'RETURN')     AS returned_to_stock,
       SUM(quantity_change) FILTER (WHERE transaction_type = 'ADJUSTMENT') AS adjustments,
       SUM(quantity_change) FILTER (WHERE transaction_type <> 'OPENING')   AS net_change
FROM inventory_transactions
GROUP BY 1
ORDER BY 1;

-- Q71 | Inventory risk by store: stock-out risk versus capital tied up
-- Business question: Which stores carry the most stock-out risk and the most surplus stock?
-- Approach: classify each position (same rules as Q60) and pivot statuses into columns per store with FILTER.
-- Concepts: CTEs, FILTER pivot, share calculations, two kinds of risk on one row.
-- Why it works: stock-out risk = OUT_OF_STOCK + LOW_STOCK positions; surplus = OVERSTOCKED + DEAD_STOCK value at cost.
WITH asof AS (SELECT MAX(order_date)::date AS d FROM sales_orders),
demand AS (
    SELECT o.store_id, i.product_id,
           SUM(i.quantity) FILTER (WHERE o.order_date::date > asof.d - 90)  AS units_90d,
           SUM(i.quantity) FILTER (WHERE o.order_date::date > asof.d - 365) AS units_365d
    FROM sales_order_items i
    JOIN sales_orders o ON o.order_id = i.order_id AND o.order_status = 'COMPLETED'
    CROSS JOIN asof
    WHERE o.order_date::date > asof.d - 365
    GROUP BY o.store_id, i.product_id
), health AS (
    SELECT inv.store_id, inv.quantity_on_hand * p.unit_cost AS value,
           CASE WHEN inv.quantity_on_hand = 0                                        THEN 'OUT_OF_STOCK'
                WHEN COALESCE(d.units_365d, 0) = 0                                   THEN 'DEAD_STOCK'
                WHEN inv.quantity_on_hand <= inv.reorder_level                       THEN 'LOW_STOCK'
                WHEN inv.quantity_on_hand > inv.max_stock_level
                  OR inv.quantity_on_hand / (COALESCE(d.units_90d, 0) / 90.0 + 0.000001) > 180 THEN 'OVERSTOCKED'
                ELSE 'HEALTHY' END AS status
    FROM inventory inv
    JOIN products p ON p.product_id = inv.product_id
    LEFT JOIN demand d ON d.store_id = inv.store_id AND d.product_id = inv.product_id
)
SELECT s.store_name,
       COUNT(*)                                                                    AS positions,
       COUNT(*) FILTER (WHERE status IN ('OUT_OF_STOCK', 'LOW_STOCK'))             AS stock_out_risk_positions,
       ROUND(100.0 * COUNT(*) FILTER (WHERE status IN ('OUT_OF_STOCK', 'LOW_STOCK')) / COUNT(*), 1) AS stock_out_risk_pct,
       ROUND(SUM(value) FILTER (WHERE status IN ('OVERSTOCKED', 'DEAD_STOCK')), 0) AS surplus_value_at_cost,
       ROUND(100.0 * SUM(value) FILTER (WHERE status IN ('OVERSTOCKED', 'DEAD_STOCK')) / SUM(value), 1) AS surplus_share_of_store_value_pct
FROM health h
JOIN stores s ON s.store_id = h.store_id
GROUP BY s.store_name
ORDER BY surplus_value_at_cost DESC;

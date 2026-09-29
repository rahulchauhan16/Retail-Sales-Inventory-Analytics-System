# 06. Inventory metrics

Every formula below is implemented in `database/views.sql` (`vw_inventory_health`, `vw_product_performance`) and re-checked in queries Q59-Q71, Q404.
**Thresholds are project assumptions, not industry standards.** A real retailer would tune them per category and season.

## Inputs stored in the database

| Field (table `inventory`) | Meaning |
|---|---|
| `quantity_on_hand` | units physically in stock |
| `reserved_quantity` | units promised to pending orders (never more than on hand) |
| `reorder_level` | stock at or below which a re-order is triggered |
| `max_stock_level` | order-up-to quantity |
| `last_restocked_date` | last receipt date |

**How `reorder_level` and `max_stock_level` were set (be ready to say this):** the data generator computes each store-product's average daily demand from its own sales,
then sets `reorder_level = demand x (supplier lead time + 9 days)` (with a small floor by price band) and `max_stock_level = reorder_level + about 6 weeks of demand` (at least 3x the reorder level). About 10 % of fast movers are
deliberately under-provisioned so that stock-outs occur. This is a simple reorder-point policy, **not** a statistical safety-stock model.

## Formulas

| Metric | Formula | Where |
|---|---|---|
| Current stock | `quantity_on_hand` | `vw_inventory_health` |
| Available stock | `quantity_on_hand - reserved_quantity` | `vw_inventory_health.available_quantity` |
| Inventory value | `quantity_on_hand x products.unit_cost` (current cost, ex-GST) | Q59; measure `[Inventory Value]` |
| Average daily demand | units sold at the store in the last 90 days / 90 | `avg_daily_demand` |
| Days of cover (stock coverage) | `quantity_on_hand / average daily demand`; blank when there was no demand | Q63; `days_of_cover` |
| Inventory turnover | COGS of the last 12 months / current inventory value | Q62; `[Inventory Turnover]` |
| Days of inventory | 365 / turnover | `[Days of Inventory]` |
| Suggested order quantity | `max(max_stock_level - quantity_on_hand - inbound quantity on open POs, 0)` | Q61; `suggested_order_qty` |
| Stock age | as-of date - `last_restocked_date` | Q66; `days_since_restock` |
| Supplier lead time (actual) | `received_date - order_date`, averaged per supplier, compared with the promised `lead_time_days` | Q84 |

**Turnover caveat:** the textbook formula divides COGS by *average* inventory over the period. Only the *current* stock is stored as a snapshot, so this project uses ending inventory.
Compare categories with each other; do not compare the absolute number with an outside benchmark.

**Safety stock:** not modelled as a separate quantity. `reorder_level` plays that role in this dataset. A future improvement is `safety stock = z x demand standard deviation x sqrt(lead time)`.

## Health classification (five classes)

Applied per **store + product position**, first matching rule wins:

| Order | Class | Rule |
|:-:|---|---|
| 1 | `OUT_OF_STOCK` | `quantity_on_hand = 0` |
| 2 | `DEAD_STOCK` | stock on hand but **no sale at that store in the last 365 days** |
| 3 | `LOW_STOCK` | `quantity_on_hand <= reorder_level` |
| 4 | `OVERSTOCKED` | `quantity_on_hand > max_stock_level` **or** more than 180 days of cover |
| 5 | `HEALTHY` | everything else |

Why this order: an empty shelf is the most urgent; stock that never sells should not be reported as "low" and re-ordered; overstock is judged only for items that still sell.

**Sensitivity of a threshold (an honest example):** with a 180-day dead-stock window, 63 % of stock value was classed dead; with 365 days it was 52 %. The choice moves the headline, which is why it is
written down here and can be changed in one place (`vw_inventory_health`).

Result on this dataset (5,690 positions): out of stock 77, low 358, healthy 1,643, overstocked 2,272, dead 1,340. Dead stock is 51.9 % and overstock 35.9 % of stock value (Q60).

## Product classes (revenue versus stock)

Products are ranked into revenue quintiles over the last 12 months (`NTILE(5)`), and stock is measured as network days of cover (all stores combined):

| Class | Rule |
|---|---|
| High Revenue / Low Stock | top revenue quintile, sold in the last 90 days, under 30 days of cover |
| High Revenue / Healthy Stock | top quintile, 30 to 180 days of cover |
| Low Revenue / High Stock | bottom two quintiles, and either no sales in 90 days or more than 180 days of cover |
| Low Revenue / Low Stock | bottom two quintiles, sold recently, under 30 days of cover |
| Other | anything else |

Result (Q69): 95 High Revenue / Healthy, 5 High Revenue / Low Stock, 231 Low Revenue / High Stock (INR 2.73 crore of stock against INR 22.7 lakh of 12-month revenue), 305 Other.

## Fast, slow and non-moving

Among products with stock, using units sold in the last 90 days: **non-moving** = no sales; among products that sold, **fast** = top quarter (`PERCENT_RANK >= 0.75`), **slow** = bottom quarter (`<= 0.25`), the rest medium (Q64, Q65).

## ABC on value

Products sorted by revenue (Q52) or by stock value (Q404); class A = the first 80 % of the cumulative total, B = the next 15 %, C = the last 5 %. The 80/15/5 split is a convention.
Result on revenue: 216 class-A products (about 35 % of products sold) give 80.1 % of net revenue.

## Known limitations

- The ledger and snapshot are synthetic; about 1.2 % of positions (68) intentionally do not reconcile (data-quality scenario).
- Demand is measured per store over short windows; many store-product pairs sell only a few units a year, so the 365-day dead-stock window is used.
- Inventory value uses current standard cost, not FIFO or weighted-average cost.
- Stock transfers between stores are not modelled, so "surplus in one store, shortage in another" cannot be fixed inside this data.

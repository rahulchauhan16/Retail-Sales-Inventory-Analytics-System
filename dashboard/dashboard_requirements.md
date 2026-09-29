# Dashboard requirements: Retail Sales & Inventory Analytics

## 1. Purpose and audience

| Audience | Question they bring | Page |
|---|---|---|
| Head of retail / management | "How is the business doing and where should I look?" | 1 Executive Overview |
| Sales / merchandising | "What sells, where, and how fast is it growing?" | 2 Sales Analysis |
| CRM / marketing | "Who are our customers, are they coming back?" | 3 Customer Analytics |
| Supply chain / store operations | "What is short, what is surplus, what should we order?" | 4 Inventory Analytics |
| Category managers / quality | "What is profitable, what comes back, and why (as recorded)?" | 5 Product & Returns |

Design principle: **the first thing on every page is the answer** (the KPI row); charts explain it; tables give the detail behind it.

## 2. KPI definitions (one meaning each)

| KPI | Formula | Measure | Note |
|---|---|---|---|
| **Revenue** (net revenue) | sum over completed order lines of `line_total / (1 + GST rate)` | `[Net Revenue]` | excludes GST because GST belongs to the government; line total is after discount |
| **Gross sales incl. GST** | sum of completed order totals | `[Order Sales incl GST]` | what customers paid |
| **Profit** (gross profit) | net revenue - quantity x unit cost (cost at time of sale) | `[Gross Profit]` | before store running costs, so it is *gross* profit |
| **Gross margin %** | gross profit / net revenue | `[Gross Margin %]` | |
| **Average order value** | gross sales incl. GST / completed orders | `[Average Order Value]` | GST-inclusive because that is the basket the customer sees |
| **Return rate** (order) | completed orders with at least one return / completed orders | `[Order Return Rate]` | unit and value versions: `[Unit Return Rate]`, `[Refund % of Net Revenue]` |
| **Inventory value** | quantity on hand x unit cost | `[Inventory Value]` | at cost, current snapshot |
| **Inventory turnover** | COGS of the last 12 months of data / inventory value | `[Inventory Turnover]` | ending-inventory approximation; compare categories with each other |
| **Customer lifetime value (to date)** | net revenue per buying customer | `[Avg Customer Lifetime Revenue]` | historical, not a forecast |
| **Repeat customer rate** | buyers with 2+ completed orders / buyers with 1+ | `[Repeat Customer Rate]` | lifetime, ignores the date slicer |
| **Stock-out risk %** | (out-of-stock + low-stock positions) / positions | `[Stock-out Risk %]` | health classes are project assumptions (see docs/06) |

Segment names (Champions ... Lost Customers) and inventory classes are **analytical labels built from thresholds defined in this project**, not facts.

## 3. Global rules

- Canvas 1280 x 720, theme [retail_theme.json](retail_theme.json), Segoe UI, ink colours for text.
- **One measure, one hue (blue).** Two series: blue and orange with a legend. Green / amber / red only for inventory status, always with a label.
- No dual-axis charts. No pie charts (use sorted bars). No 3D.
- Every chart has a title that says what it shows *and* the unit (e.g. "Net revenue by category, INR").
- **Slicers, synced on every page:** Year (`dim_date[year]`), Region (`dim_store[region]`), Channel (`dim_channel[channel]`, the shared 2-row dimension that filters all facts),
  Category (`dim_product[category]`).
  - The category slicer filters line-based measures only (see the model notes in powerbi_setup.md); order-level cards ignore it, which is stated in the page footer.
- Cards show the **period label** (`[Period Label]`) in the subtitle.
- Accessibility: alt text on every visual; do not rely on colour alone (status bars carry labels); minimum text 10 pt.
- Footer on each page: "Source: PostgreSQL views (vw_*). Synthetic data. GST-exclusive unless stated."

---

## Page 1: Executive Overview

**Purpose:** headline health of the business in ten seconds.

```
+--------------------------------------------------------------------------------+
| Title                                      [Year] [Region] [Category]  period  |
+--------+--------+--------+---------+---------+--------+-----------+-------------+
|Revenue | Profit | Orders |Customers|   AOV   |Return %|Inventory  |             |
+--------+--------+--------+---------+---------+--------+-----------+-------------+
|  Monthly revenue trend (line + 3M avg)         |  Revenue by category (bar)      |
+------------------------------------------------+----------------------------------+
|  Revenue by store (bar)                        |  Top 10 products (bar)           |
+------------------------------------------------+----------------------------------+
```

| Visual | Type | Fields | Notes |
|---|---|---|---|
| KPI: Total Revenue | Card | `[Net Revenue]` | subtitle `[Net Revenue YoY %]` vs prior year |
| KPI: Total Profit | Card | `[Gross Profit]` | subtitle `[Gross Margin %]` |
| KPI: Total Orders | Card | `[Completed Orders]` | subtitle `[Cancelled Orders]` cancelled |
| KPI: Total Customers | Card | `[Total Customers]` | customers who bought in the period |
| KPI: Average Order Value | Card | `[Average Order Value]` | |
| KPI: Return Rate | Card | `[Order Return Rate]` | |
| KPI: Inventory Value | Card | `[Inventory Value]` | current snapshot; label it "as of last data date" |
| Monthly revenue trend | Line chart | X `dim_date[year_month]`; Y `[Net Revenue]`, `[Net Revenue 3M Avg]` | legend on; peak month labelled |
| Revenue by category | Clustered bar (horizontal) | Y `dim_product[category]`; X `[Net Revenue]` | sorted descending; data labels |
| Revenue by store | Clustered bar (horizontal) | Y `dim_store[store_name]`; X `[Net Revenue]` | |
| Top 10 products | Clustered bar (horizontal) | Y `dim_product[product_name]`; X `[Net Revenue]` | visual filter: Top N = 10 by `[Net Revenue]` |

## Page 2: Sales Analysis

**Purpose:** where revenue comes from, how it moves, and how fast it grows.

| Visual | Type | Fields | Notes |
|---|---|---|---|
| Monthly / weekly toggle | Line chart + bookmark toggle | `dim_date[year_month]` or `dim_date[year]` + `dim_date[week_of_year]`; `[Net Revenue]` | two bookmarks: Monthly, Weekly |
| Revenue growth | Clustered column | X `dim_date[year_month]`; Y `[Net Revenue YoY %]` | show only months with a prior year; blue positive / same blue for negative with axis at 0 (no red/green) |
| Running total | Area/line | `[Net Revenue Running Total]` by month | |
| Category performance | Table | `dim_product[category]`, `[Net Revenue]`, `[Gross Margin %]`, `[Units Sold]`, `[Net Revenue YoY %]` | conditional data bars on revenue only |
| Product performance | Table | product, `[Net Revenue]`, `[Units Sold]`, `[Gross Margin %]`, `dim_product[abc_class]` | sorted by revenue; Top N 25 |
| Store performance | Clustered bar + table | store, `[Net Revenue]`, `[Average Order Value]` | |
| Sales quantity | Card + column | `[Units Sold]` by month | |
| Channel mix | 100 % stacked column or two-series line | `dim_date[year]`, `dim_channel[channel]`, `[Completed Orders]` | legend on; blue = In-store, orange = Online |
| Discount impact | Card pair | `[Discount Given]`, `[Gross Margin %]` split by `fact_sales_lines[promotion_id]` blank / not blank | create a `Promoted?` column in Power Query |

Slicers on this page: Year, Month, Region, Category, Channel.

## Page 3: Customer Analytics

**Purpose:** who buys, whether they return, and where value sits.

| Visual | Type | Fields | Notes |
|---|---|---|---|
| New vs repeat customers | Stacked column | X `dim_date[year_month]`; Y `[New Customers]`, `[Returning Customers]` | legend on |
| Customer segments (RFM) | Clustered column | X `dim_customer[rfm_segment]`; Y share of customers and share of revenue | as in `docs/images/06_customer_segments.png`; needs two measures: customers count and `SUM(dim_customer[net_revenue])`, each as % of column total |
| Commercial segments | Clustered bar | `dim_customer[segment]`, `[Avg Customer Lifetime Revenue]` | |
| Customer lifetime value | Card + histogram | `[Avg Customer Lifetime Revenue]`; bins of `dim_customer[net_revenue]` | |
| Top customers | Table | `customer_name`, `segment`, `orders`, `net_revenue`, `last_order_date`, `rfm_segment` | Top N 15 by `net_revenue` |
| Purchase frequency | Column | bins of `dim_customer[orders]` (1, 2-3, 4-6, 7-12, 13+) | create a `Frequency band` column |
| Activity status | Bar | `dim_customer[activity_status]` count | |
| KPI cards | Cards | `[Repeat Customer Rate]`, `[Buying Customers (lifetime)]`, `[Active Customers (90d)]`, `[Purchase Frequency]` | label lifetime cards "all time" |

Slicers: Segment, RFM segment, Region (date slicer affects only period measures; lifetime cards ignore it and say so).

## Page 4: Inventory Analytics

**Purpose:** what is short, what is surplus, what to reorder. Snapshot page: the date slicer does not apply to stock measures.

| Visual | Type | Fields | Notes |
|---|---|---|---|
| Inventory value | Card | `[Inventory Value]` | |
| Stock status | Horizontal bar | `fact_inventory_health[health_status]`, `[Stock Positions]` | status colours: OUT red, LOW orange-red, HEALTHY green, OVERSTOCKED amber, DEAD grey; each bar labelled with count |
| Value by status | Bar | health_status, `[Inventory Value]` | |
| Low-stock products | Table | store, product, `quantity_on_hand`, `reorder_level`, `avg_daily_demand`, `inbound_quantity`, `suggested_order_qty` | filter `health_status` = LOW_STOCK; sort by demand |
| Out-of-stock products | Table | store, product, `units_sold_365d` | filter `health_status` = OUT_OF_STOCK |
| Fast-moving products | Bar | product, `units_sold_90d` | Top N 10 |
| Slow-moving products | Bar | product, `units_sold_90d` | Bottom N: products with stock and sales > 0 |
| Inventory turnover | Bar | `dim_product[category]`, `[Inventory Turnover]` | sorted; state "12-month COGS / current stock" in the subtitle |
| Stock aging | Column | bins of `days_since_restock` | create bins 0-30, 31-90, 91-180, 181-365, 365+ |
| Store risk | Table/matrix | store, `[Stock-out Risk %]`, `[Surplus Share of Value]`, `[Inventory Value]` | |
| Product class | Matrix | `dim_product[product_class]`, count, `[Inventory Value]` | High Revenue / Low Stock etc. |
| KPI cards | Cards | `[Stock-out Risk %]`, `[Surplus Share of Value]`, `[Days of Inventory]`, `[Suggested Order Qty]` | |

Slicers: Region/Store, Category, Health status.

## Page 5: Product & Returns

**Purpose:** which products are profitable, which come back, and the recorded reasons.

| Visual | Type | Fields | Notes |
|---|---|---|---|
| Product profitability | Scatter | X `[Net Revenue]`, Y `[Gross Margin %]`, size `[Units Sold]`, details `dim_product[product_name]` | one hue; no more than one series colour |
| Return rate | Card + bar | `[Order Return Rate]`, `[Unit Return Rate]` by category | bar shows unit return rate, reference line at overall |
| Return reasons | Horizontal bar | `fact_returns[return_reason]`, count of `return_item_id` | label: recorded reason, not root cause |
| Category returns | Bar | `fact_returns[category]`, `[Units Returned]` and `[Unit Return Rate]` | |
| High-return products | Table | product, units sold, units returned, return rate | filter `units_sold` >= 40 and `units_returned` >= 8; include category rate for context |
| Refund trend | Line | `[Refunded Net of GST (by return date)]` by month | |
| Write-offs | Card | `[Write-off Cost]` | cost of returned items not restocked |
| Returns by channel / segment | Bars | `[Order Return Rate]` by `dim_channel[channel]` and by `fact_orders[customer_segment]` | segment comes from `fact_orders`, because `fact_returns` cannot be filtered by `dim_customer` |

Slicers: Year, Category, Channel, Store.

---

## 4. Acceptance checklist

- [ ] All cards match [expected_kpis.md](expected_kpis.md) with no slicers, and the 2024 column with Year = 2024.
- [ ] Every visual has a title with unit, and alt text.
- [ ] No dual axes, pies or rainbow palettes; status colours used only for status.
- [ ] Slicers synced across pages; a "Reset filters" bookmark exists.
- [ ] Lifetime and snapshot measures are labelled as such.
- [ ] Footer states the data is synthetic and revenue is GST-exclusive.
- [ ] Screenshots of all five pages saved in `screenshots/` (placeholders are listed in `screenshots/README.md`).

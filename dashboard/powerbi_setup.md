# Power BI setup guide

This guide takes you from an empty Power BI Desktop to the five-page dashboard specified in [dashboard_requirements.md](dashboard_requirements.md).

> **Why no `.pbix` file is committed:** a `.pbix` is a binary that cannot be generated or diffed from code. Everything that *defines* the dashboard is
> in this repository instead: the SQL views, the star-schema exports, [measures.dax](measures.dax), the [theme](retail_theme.json), the page
> specification and the [expected values](expected_kpis.md) to test against. Build the report once (about 60-90 minutes), then save your `.pbix`
> outside the repository or add screenshots to [../screenshots/](../screenshots/).

**You need:** Power BI Desktop (free, Windows), and this project's database running (`docker compose up -d`, then `python scripts/load_data.py`).

---------------------------------------------------------------------------------------------------------------------------------------------

## 1. Choose a data route

| Route | Best for | Steps |
|---|---|---|
| **A. CSV files** (simplest) | first attempt, no database access from Power BI | run `python python/export_dashboard_data.py`, then *Get data > Text/CSV* for each file in `dashboard/exported_data/` |
| **B. PostgreSQL connector** | the "real" setup: a refreshable model | *Get data > PostgreSQL database* (below) |

Both routes give the **same 13 tables** with the same column names, so the model, measures and pages are identical.

### Route B: connect to PostgreSQL

1. **Create a read-only login** (least privilege; Power BI never needs to write):
   ```powershell
   Get-Content database/powerbi_readonly.sql | docker exec -i retail_pg psql -U retail_user -d retail_analytics -v pw="YourPasswordHere"
   ```
   Re-run this after every `python scripts/load_data.py`, because rebuilding the views removes their grants.
2. In Power BI Desktop: **Home > Get data > PostgreSQL database**.
   - Server: `localhost:5432`  - Database: `retail_analytics`  - Data Connectivity mode: **Import**
3. Credentials tab **Database**: user `powerbi_reader`, the password from step 1.
4. If Power BI asks for the **Npgsql** provider, install Npgsql 4.0.x (choose *Npgsql GAC Installation*) and restart Power BI. Recent Desktop versions bundle it.
5. Select these objects and click **Transform data** (each maps to a CSV name; the name in the model should be the CSV name):

| Model table name | PostgreSQL object | Grain |
|---|---|---|
| `fact_sales_lines` | `vw_sales_lines` | one sold order line (completed orders) |
| `fact_orders` | `vw_orders` | one order, all statuses |
| `fact_returns` | `vw_return_analysis` | one returned order line |
| `fact_inventory_health` | `vw_inventory_health` | one store + product stock position (current snapshot) |
| `dim_date` | `dim_date` | one calendar day (filter to the data window, see 2) |
| `dim_store` | `stores` | one store |
| `dim_product` | `vw_product_performance` | one product |
| `dim_customer` | `vw_customer_summary` | one customer |
| `dim_category` | `vw_category_canonical` | category lookup (optional) |
| `agg_monthly_sales` | `vw_monthly_sales` | one month (optional: cross-check only) |
| `agg_store_performance` | `vw_store_performance` | one store (optional) |
| `agg_category_performance` | `vw_category_performance` | category by year (optional) |
| `agg_supplier_performance` | `vw_supplier_performance` | one supplier (used on page 4/5 tables) |

Only the first nine plus `agg_supplier_performance` are needed for the pages; the other `agg_` tables are handy for cross-checking a visual against a
pre-computed number.

---------------------------------------------------------------------------------------------------------------------------------------------

## 2. Power Query clean-up (Transform data)

| Table | Step | Why |
|---|---|---|
| `dim_date` | keep rows where `date_key` is between 2023-01-01 and 2025-12-31 (route B only) | the table also covers 2021-2026 for promotion dates |
| all tables | set `*_date`, `*_day`, `*_month`, `date_key`, `cohort_month`, `launch_date`, `opened_date`, `first_order_date`, `last_order_date`, `last_restocked_date` to type **Date** | time intelligence needs real dates |
| `fact_orders`, `fact_sales_lines`, `fact_returns` | keep `order_date` / `return_date` as **Date/Time**; the `*_day` columns are the Date columns used in relationships | avoids time-of-day breaking joins |
| `fact_orders`, `dim_customer`, `fact_returns` | booleans `has_return`, `is_repeat_customer`, `is_active`, `restocked` type **True/False** | measures compare with `TRUE()` / `FALSE()` |
| `dim_customer` | remove `email` | not needed on a dashboard (data is synthetic, but this is the habit to build) |
| numeric columns | percentages such as `margin_pct` stay as decimal numbers (20.9 means 20.9 %) | they are already scaled to 0-100 |

Close & Apply.

---------------------------------------------------------------------------------------------------------------------------------------------

## 3. Data model (star schema)

```
                       dim_date
          (date_key)  /   |    \  \
                     /    |     \  \  (inactive: dim_customer[cohort_month], fact_returns[return_day])
      fact_sales_lines  fact_orders  fact_returns
            |  \          |  \          |  \
            |   \         |   dim_store dim_store...
       dim_product  dim_store   dim_customer
                                        (fact_inventory_health -> dim_store, dim_product)
```

Create these relationships in *Model view*. All are **many-to-one, single direction** (dimension filters fact):

| From (many) | To (one) | Active | Note |
|---|---|:-:|---|
| `fact_sales_lines[order_day]` | `dim_date[date_key]` | yes | |
| `fact_orders[order_day]` | `dim_date[date_key]` | yes | |
| `fact_returns[order_day]` | `dim_date[date_key]` | yes | returns are attributed to the **sale** period, so rates line up with sales |
| `fact_returns[return_day]` | `dim_date[date_key]` | **no** | used by `Refunded Net of GST (by return date)` through `USERELATIONSHIP` |
| `dim_customer[cohort_month]` | `dim_date[date_key]` | **no** | used by `New Customers` through `USERELATIONSHIP` |
| `fact_sales_lines[channel]` | `dim_channel[channel]` | yes | `dim_channel` = 2-row table you create with *Enter data*: `IN_STORE`, `ONLINE` (one Channel slicer then filters every fact) |
| `fact_orders[channel]` | `dim_channel[channel]` | yes | |
| `fact_returns[channel]` | `dim_channel[channel]` | yes | |
| `fact_sales_lines[store_id]` | `dim_store[store_id]` | yes | |
| `fact_orders[store_id]` | `dim_store[store_id]` | yes | |
| `fact_returns[store_id]` | `dim_store[store_id]` | yes | |
| `fact_inventory_health[store_id]` | `dim_store[store_id]` | yes | |
| `fact_sales_lines[product_id]` | `dim_product[product_id]` | yes | |
| `fact_returns[product_id]` | `dim_product[product_id]` | yes | |
| `fact_inventory_health[product_id]` | `dim_product[product_id]` | yes | |
| `fact_sales_lines[customer_id]` | `dim_customer[customer_id]` | yes | |
| `fact_orders[customer_id]` | `dim_customer[customer_id]` | yes | |

Deliberately **not** created:
- `fact_sales_lines[order_id]` to `fact_orders[order_id]`: it would create two filter paths from `dim_store` to the lines (ambiguous). Order-level
  measures (orders, AOV) therefore read `fact_orders`; line-level measures read `fact_sales_lines`.
- a relationship from `dim_category`: category is filtered through `dim_product[category]` (already merged for case variants).
- `agg_*` tables: stand-alone, used only for cross-checks and the supplier table.

**Two more things to know:**
- `fact_returns` has no `customer_id`, so `dim_customer[segment]` does **not** filter it. On page 5 use `fact_returns[customer_segment]` for segment cuts.
- `fact_inventory_health` has no date; the Year slicer does not affect stock measures (that is intended and labelled on page 4).

**Consequence to remember:** product and category slicers filter the *line-based* measures (Net Revenue, Units Sold, Gross Profit) but not the
order-level ones (Completed Orders, Average Order Value), because one order can contain many categories. When slicing by category use
`Orders (line basis)`.

After creating relationships:
1. **Mark `dim_date` as date table** (Table tools > Mark as date table > `date_key`).
2. Hide the technical columns in the fact tables (`*_id`, `order_day`, `return_day`) and hide the fact tables' raw amount columns once the measures exist.
3. Sort `dim_date[month_name]` by `dim_date[month]`; sort `day_name` by `day_of_week`.
4. Create a date hierarchy: `year > quarter > month_name`.

---------------------------------------------------------------------------------------------------------------------------------------------

## 4. Measures

1. **Home > Enter data**, create an empty table named `_Measures`.
2. Open [measures.dax](measures.dax). For each block, choose **New measure** and paste it (the text before `=` is the measure name).
3. Set formats:

| Measures | Format |
|---|---|
| Net Revenue, Gross Profit, COGS, Discount Given, Order Sales incl GST, Average Order Value, Inventory Value, Refunded Net of GST, Write-off Cost | Currency, 0 decimals, symbol ₹ |
| Gross Margin %, Cancellation Rate, Order Return Rate, Unit Return Rate, Repeat Customer Rate, Online Order Share, Refund % of Net Revenue, Surplus Share of Value, Stock-out Risk %, Class A Revenue Share, *YoY / MoM %* | Percentage, 1 decimal |
| Purchase Frequency, Inventory Turnover | Decimal, 2 places |
| everything else | Whole number, thousands separator |

For Indian digit grouping (12,34,567) set Windows *Region > Additional settings* to English (India); Power BI follows the OS.

The 3-month average and running total use `REMOVEFILTERS(dim_date)` so they can look back across a year slicer. The 12-month COGS window is anchored to the last date in the data, not
to today.

---------------------------------------------------------------------------------------------------------------------------------------------

## 5. Theme and canvas

- **View > Themes > Browse for themes** and choose [retail_theme.json](retail_theme.json). It applies the validated colour palette:
  blue for single-measure magnitude, orange as the second series, and the reserved green / amber / red only for status.
- **View > Page view > Actual size** and set each page to **16:9** (1280 x 720).
- Use one font family (Segoe UI) and the ink colours from the theme for text; never colour text with a series colour.

---------------------------------------------------------------------------------------------------------------------------------------------

## 6. Build the pages

Follow [dashboard_requirements.md](dashboard_requirements.md), page by page. Recommended order (each step adds a testable piece):

1. Page 1 *Executive Overview*: cards first, and **stop to validate** them against [expected_kpis.md](expected_kpis.md).
2. Add the `dim_date` slicer (year, month) and check the *By year* values.
3. Pages 2-5. **Sync slicers** (View > Sync slicers) for Date, Store region and Channel across all pages.
4. Add page navigation buttons and bookmarks for "Reset filters".

## 7. Validate before you screenshot

| Test | Expected |
|---|---|
| No slicers: every card equals the *All data* column of [expected_kpis.md](expected_kpis.md) | exact to rounding |
| Date slicer = 2024: Net Revenue, Completed Orders, Average Order Value, Order Return Rate equal the 2024 column | exact to rounding |
| Sum of the *Net Revenue by Store* bars equals the Net Revenue card | yes |
| Sum of the *Net Revenue by Category* bars equals the Net Revenue card | yes (includes the `(no category)` bar) |
| Health status counts add up to Stock Positions | yes |

If a number differs, compare with the SQL view of the same name first (`SELECT * FROM vw_monthly_sales`); the views are the source of truth.

## 8. Publishing and refresh (optional)

- Route A: replace the CSVs by re-running `python python/export_dashboard_data.py` and press **Refresh**.
- Route B: press **Refresh**; if the data was rebuilt, re-run `database/powerbi_readonly.sql` first.
- Publishing to Power BI Service and scheduled refresh need a data gateway for a local database; they are outside the scope of this project.

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Ambiguous path" when creating a relationship | the two facts were linked, or two active paths exist | keep only the relationships in the table above |
| All measures show the same value in a visual | missing relationship or wrong column type (text instead of Date/Number) | check *Model view* and column data types |
| `New Customers` is blank | inactive relationship missing | create `dim_customer[cohort_month] -> dim_date[date_key]` and leave it inactive |
| Time-intelligence measures return blank | `dim_date` not marked as date table, or gaps in dates | mark it; import all days of 2023-2025 |
| `permission denied for view ...` | views were rebuilt after the grants | re-run `database/powerbi_readonly.sql` |
| Cannot connect | container stopped | `docker compose up -d`, then test with `python python/database_connection.py` |

# 08. Power BI dashboard

> **Status, stated plainly:** the dashboard is **fully specified and lint-tested, but the `.pbix` file is not in the repository** (it is a binary that cannot be generated from code).
> The SQL views, exports, DAX measures, theme, model design, page specifications and expected values are all committed, so the report can be built in about 60-90 minutes and
> verified number by number. If you build it, put screenshots in `screenshots/`.

All detail lives in the `dashboard/` folder; this page is the map.

| Document | Content |
|---|---|
| [powerbi_setup.md](../dashboard/powerbi_setup.md) | connect (CSV or PostgreSQL), Power Query steps, star schema and every relationship, formats, theme, validation, troubleshooting |
| [dashboard_requirements.md](../dashboard/dashboard_requirements.md) | audience, KPI definitions, global rules, the five pages visual by visual, acceptance checklist |
| [measures.dax](../dashboard/measures.dax) | 55 measures ready to paste |
| [expected_kpis.md](../dashboard/expected_kpis.md) | what each measure must show (all data and by year) |
| [retail_theme.json](../dashboard/retail_theme.json) | theme using the validated palette |
| [../database/powerbi_readonly.sql](../database/powerbi_readonly.sql) | read-only login for the connection |

## Data sources

PostgreSQL views (route B) or CSV exports (route A) produce the same tables:

| Role | Tables |
|---|---|
| Facts | `fact_sales_lines` (107,694 sold lines from completed orders), `fact_orders`, `fact_returns`, `fact_inventory_health` |
| Dimensions | `dim_date`, `dim_store`, `dim_product`, `dim_customer`, `dim_channel` (2 rows you create) |
| Aggregates (optional) | `agg_monthly_sales`, `agg_store_performance`, `agg_category_performance`, `agg_supplier_performance` |

## Data model

Star schema, all relationships many-to-one with single-direction filtering from dimension to fact. Facts are deliberately **not** linked to each other (that would create ambiguous paths). Two inactive relationships
(`dim_customer[cohort_month]` and `fact_returns[return_day]` to `dim_date`) are activated inside measures with `USERELATIONSHIP`. The full relationship table is in the setup guide.

## KPI definitions

| KPI | Formula | Measure |
|---|---|---|
| Revenue | sum of `line_total / (1 + GST rate)` over completed order lines | `[Net Revenue]` |
| Profit | net revenue - quantity x unit cost at time of sale | `[Gross Profit]` |
| Gross margin % | gross profit / net revenue | `[Gross Margin %]` |
| Average order value | GST-inclusive completed order sales / completed orders | `[Average Order Value]` |
| Return rate | completed orders with a return / completed orders (unit and value variants exist) | `[Order Return Rate]` |
| Inventory value | quantity on hand x unit cost | `[Inventory Value]` |
| Inventory turnover | COGS of the last 12 months / inventory value | `[Inventory Turnover]` |
| Customer lifetime value (to date) | net revenue per buying customer | `[Avg Customer Lifetime Revenue]` |
| Repeat customer rate | buyers with 2+ orders / buyers | `[Repeat Customer Rate]` |

Values on this dataset (no filters): net revenue INR 15.25 crore, gross profit INR 3.56 crore (23.37 %), 54,260 completed orders, 7,074 buying customers, AOV INR 3,202,
order return rate 5.22 %, inventory INR 6.27 crore, turnover 0.68, repeat rate 83.42 %.

## Pages

| # | Page | Purpose | Main visuals |
|:-:|---|---|---|
| 1 | Executive Overview | health of the business in ten seconds | 7 KPI cards, monthly revenue trend with 3-month average, revenue by category and store, top 10 products |
| 2 | Sales Analysis | where revenue comes from and how it grows | monthly/weekly trend, YoY growth, running total, category / product / store tables, channel mix, discount impact |
| 3 | Customer Analytics | who buys and comes back | new vs returning, RFM segments, lifetime value, top customers, frequency, activity status |
| 4 | Inventory Analytics | short, surplus, reorder | stock status bars, low and out-of-stock tables, fast and slow movers, turnover by category, aging, store risk |
| 5 | Product & Returns | profitable and returned products | profitability scatter, return rates, reasons, category returns, high-return products, refunds |

Slicers synced across pages: Year, Region, Channel (through the shared `dim_channel`), Category. Lifetime and stock measures ignore the date slicer and are labelled.

## Design principles

One hue per measure (blue), a second series in orange with a legend, green / amber / red **only** for stock status and always with a text label, no dual axes, no pies, direct labels rather than a number on every point,
text in ink colours. The eight Python charts in `docs/images/` follow the same rules.

## How the specification was validated without Power BI

`tests/test_powerbi_assets.py` checks that every `table[column]` in the DAX exists in the real exported schema, every measure reference is defined, parentheses balance, every measure named in the
documents exists, the committed expected values still equal the database, and the theme is valid. What it cannot check is the DAX *evaluation*: that is what the expected-values file is for.

## Common interview questions about this page

*Why a star schema? Why no relationship between the fact tables? What is an inactive relationship? Why does the category slicer not change the order count? Why is AOV GST-inclusive while revenue is not?*
Answers are in [11_interview_questions.md](11_interview_questions.md).

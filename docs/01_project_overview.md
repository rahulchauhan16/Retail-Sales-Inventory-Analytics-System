# 01. Project overview

## What this project is

A small but realistic analytics system for a fictional Indian retailer (11 stores across 11 cities plus an online fulfilment hub).
It takes the data a retailer really has (orders, payments, returns, stock movements, suppliers, promotions) and turns it into answers
for management: how much we sell, who buys, what is short or surplus, what comes back, and where to look first.

It is a **portfolio project**: the data is synthetic, but it is built to behave like real retail data, including its problems.
All names, brands, suppliers and e-mail addresses are invented (e-mails use the reserved `example.*` domains).

## The business problem

A retail manager has ten questions and no single place to answer them:

1. How is revenue trending, and what is seasonal?
2. Which products, categories and stores carry the business?
3. Who are the valuable customers, and who is drifting away?
4. Which products are about to run out, and which are piling up unsold?
5. How much money is tied up in stock, and how fast does it turn over?
6. What gets returned, and how much does it cost?
7. Do promotions pay for themselves?
8. Which suppliers deliver late or short?
9. Is the data itself trustworthy?
10. What should management look at first?

## What was built

```
Python generator (seeded)          PostgreSQL 16                              Consumers
------------------------          -------------------------------------      -----------------------
simulates demand, stock,   -->    19 tables (normalised, constraints)   -->   160 SQL statements
reorders, returns, and             12 analytical views (1 materialized)       Python: 4 analysis modules,
planted data-quality issues        10 justified indexes                        8 charts, 4 notebooks
CSV files                          read-only role for Power BI                Power BI: model, 55 measures,
                                                                              5-page specification
```

| Layer | What | Where |
|---|---|---|
| Data | ~57k orders, 112k order lines, 145k stock movements over 3 years | `scripts/generate_data.py` |
| Database | schema, constraints, views, indexes | `database/` |
| SQL | 143 analytical queries + 17 `EXPLAIN ANALYZE` scenarios (incl. a 30-check data-quality scorecard) | `queries/` |
| Python | extraction, validation, KPIs, analysis, charts, dashboard export | `python/` |
| Dashboard | Power BI guide, page specs, DAX, theme, expected values | `dashboard/` |
| Quality | 300+ automated tests (schema, load, integrity, SQL, views, Python, Power BI assets) | `tests/` |

## Dataset at a glance (exact counts from the database)

| Table | Rows | | Table | Rows |
|---|---:|---|---|---:|
| customers | 9,120 | | inventory | 5,690 |
| products | 636 | | inventory_transactions | 144,464 |
| categories | 23 | | purchases | 23,626 |
| suppliers | 55 | | purchase_items | 29,261 |
| stores | 12 | | returns | 2,835 |
| employees | 62 | | return_items | 2,901 |
| sales_orders | 56,575 | | promotions | 25 |
| sales_order_items | 112,512 | | product_promotions | 2,135 |
| payments | 57,918 | | customer_segments | 4 |

Period: 1 January 2023 to 31 December 2025. Of the orders, 54,260 are completed and 2,315 cancelled.

## How the data was made (and why that matters)

Independent random rows produce meaningless analytics, so the generator **simulates the business**:

- demand is generated month by month with festive seasonality (October and November peak), yearly growth, category trends, customer churn
  and store openings;
- stock levels fall with every sale; when stock reaches its reorder level a purchase order is raised, arrives after the supplier's lead time
  (sometimes late, sometimes short), and refills the store;
- a sale that cannot be filled from stock is lost, so stock-outs are real (about 7 % of demand lines);
- returns come from completed orders only, at category-specific rates, and restocked or written off;
- the stock ledger is built from these events, so it reconciles to stock on hand, **except for 1.2 % of rows that were deliberately altered** to test the
  reconciliation check.

Everything is reproducible: `python scripts/generate_data.py` with the default seed always gives the same dataset.

**Honest limits of synthetic data:** the patterns (seasonality, the Pareto shape, category trends) were designed in, so finding them proves the
analysis works, not that a real retailer behaves this way. Some properties are unusual, for example 83 % of buyers are repeat customers and inventory
turns over only about 0.7 times a year. The documents state these openly wherever they matter.

## Technology

PostgreSQL 16 (Docker) - SQL (CTEs, window functions, recursive CTEs, LATERAL, set operations) - Python 3 with pandas, NumPy, SQLAlchemy, psycopg2,
matplotlib, seaborn - Jupyter - Power BI (specified and documented) - pytest - Git.
No technology is included that is not used.

## How to navigate the repository

| If you want to ... | Open |
|---|---|
| run it | [README.md](../README.md) |
| see the business questions | [02_business_requirements.md](02_business_requirements.md) |
| understand the schema | [03_database_design.md](03_database_design.md), [04_data_dictionary.md](04_data_dictionary.md), [database/erd.md](../database/erd.md) |
| read the SQL and its findings | [05_sql_analysis.md](05_sql_analysis.md) |
| see the definitions | [06_inventory_metrics.md](06_inventory_metrics.md), [07_customer_analytics.md](07_customer_analytics.md) |
| build the dashboard | [08_powerbi_dashboard.md](08_powerbi_dashboard.md), [../dashboard/powerbi_setup.md](../dashboard/powerbi_setup.md) |
| see data quality and performance work | [09_data_quality.md](09_data_quality.md), [10_performance_optimization.md](10_performance_optimization.md) |
| prepare for interviews | [11_interview_questions.md](11_interview_questions.md), [12_project_walkthrough.md](12_project_walkthrough.md), [project_resume_bullets.md](project_resume_bullets.md) |

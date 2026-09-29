# Resume bullets

Written for: **you** to copy into a resume. Every bullet describes something implemented and tested in this repository. Numbers come from the project's own outputs; keep the wording as it is or make it *more* conservative.

## Five ATS-friendly bullets

**Retail Sales & Inventory Analytics System** | PostgreSQL, SQL, Python (pandas, SQLAlchemy, matplotlib), Power BI, Git | *personal project*

1. Designed a 19-table normalised PostgreSQL schema (primary/foreign keys, UNIQUE, CHECK constraints, triggers) and a seeded Python simulation that generated 3 years of synthetic retail data: 56K orders, 112K order lines and 144K stock movements, with a stock ledger that reconciles to inventory.
2. Wrote 143 analytical SQL queries using CTEs, window functions (LAG, RANK, NTILE), recursive CTEs, LATERAL joins and cohort/RFM analysis, and built 12 reusable views (one materialized) that define each KPI once for SQL, Python and Power BI.
3. Built a 30-check data-quality scorecard in SQL that detected duplicate customers, invalid contact details, missing categories and suppliers, orders without payments and 68 stock positions that did not match the ledger, and documented the treatment of each issue.
4. Benchmarked queries with EXPLAIN ANALYZE and added 10 justified indexes, speeding selective lookups by roughly 2x to several hundred times on a 57K-order dataset (largest gains on the 144K-row stock ledger), and rewrote a correlated subquery to run about 4x faster than even the indexed version; identical-plan timing gaps were recorded as noise, not speed-ups.
5. Developed pandas/SQLAlchemy analysis modules, 8 charts and 4 executed notebooks; wrote 300+ pytest tests that reconcile KPIs across SQL, Python and expected Power BI values; specified a 5-page Power BI dashboard (star schema, 55 DAX measures, theme).

### Why these numbers are safe to say

| Claim | Source in the repo |
|---|---|
| 19 tables | `database/schema.sql` |
| 56K orders / 112K lines / 144K movements | exact counts in `docs/01_project_overview.md` |
| 143 queries | `tests/test_sql_queries.py` asserts the count |
| 12 views, 10 indexes | `database/views.sql`, `database/indexes.sql` (tests check both) |
| 30-check scorecard, 68 mismatches | `queries/10_data_quality_checks.sql` Q301, Q306 |
| 2x to several hundred times | repeated benchmark runs; the full range of scenarios is in `docs/10_performance_optimization.md` (hardware-dependent, warm cache) |
| rewritten subquery about 4x faster than the indexed version | Q504 with its index about 149 ms vs the rewrite Q517 about 36 ms; without any index 322 ms vs 32 ms; equal results proven by a test |
| 300+ tests | `python -m pytest tests -q` |
| Power BI | *specified*, with lint tests. The bullet says "specified" on purpose |

## If you build the Power BI report

Replace the end of bullet 5 with: "...and built a 5-page Power BI dashboard (star schema, 55 DAX measures) whose KPIs reconcile to the SQL views." Add screenshots to `screenshots/` first.

## Shorter versions (for a one-page resume)

- Built an end-to-end retail analytics project in PostgreSQL and Python: 19-table schema, 143 SQL queries (window functions, CTEs, cohorts, RFM), 12 KPI views, 30 data-quality checks and 300+ automated tests.
- Optimised SQL with EXPLAIN ANALYZE: 10 measured indexes and a query rewrite that outperformed indexing; documented where indexes did not help.

## What not to write

- "Increased sales by X %" or any business outcome: the data is synthetic.
- "Production", "deployed", "real-time", "machine learning", "forecasting": none of these were built.
- A precise speed-up without the qualifier "on a laptop with a 57K-order dataset".
- "Built a Power BI dashboard" unless you have built it.

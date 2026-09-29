# 02. Business requirements

## Stakeholders

| Stakeholder | Decisions they make | Needs |
|---|---|---|
| Head of retail | where to invest, which stores to fix | revenue, profit, growth, store ranking |
| Merchandising / category managers | what to range, promote, drop | product and category performance, margin, promotion results |
| Supply chain / inventory planners | what to order, how much | stock health, cover, replenishment list, supplier reliability |
| CRM / marketing | who to retain or win back | customer value, repeat rate, RFM segments, cohorts |
| Finance | how much cash is tied up or lost | inventory value, turnover, refunds, discounts |
| Data owner | can we trust the numbers | data-quality checks, reconciliation |

## Requirements and where each is met

Every requirement below is answered by a named query, view or chart. The full 50-question map is in `queries/11_business_questions.sql` (Q405).

| Area | Business question | Answered by |
|---|---|---|
| Sales | total revenue, profit, orders, AOV | Q03, Q04, Q02, Q05, Q401 |
| Sales | monthly / yearly trend, YoY and MoM growth | Q13, Q14, Q15, Q26; view `vw_monthly_sales` |
| Sales | top products, categories, stores, cities | Q16, Q17, Q18, Q19, Q20 |
| Sales | running total, 3-month moving average, ranking | Q22, Q23, Q24 |
| Sales | promotions and discount impact | Q27, Q28 |
| Customers | repeat rate, lifetime value, frequency | Q33, Q42, Q36, Q45 |
| Customers | segments, RFM, cohorts, top customer per store | Q37, Q39, Q40, Q41, Q44 |
| Customers | customers without purchases | Q34, Q35 |
| Inventory | current stock and value | Q59 |
| Inventory | low, out-of-stock, overstocked, dead stock | Q60, Q61, Q68 |
| Inventory | turnover, cover, aging, fast and slow movers | Q62, Q63, Q66, Q64, Q65 |
| Inventory | high sales / low stock and low sales / high stock | Q67, Q68, Q69 |
| Inventory | ABC and risk | Q404, Q71 |
| Stores | performance, ranking, growth, weak locations | Q72-Q80 |
| Suppliers | spend, on-time delivery, fill rate, lead time | Q81-Q88 |
| Returns | return rate, reasons, categories, stores, high-return products | Q89-Q99 |
| Products | margin, ABC/Pareto, declining products, concentration | Q47-Q58 |
| Data quality | duplicates, NULLs, invalid formats, ledger mismatch, missing payments | Q301-Q309 |
| Management | which products need attention first | Q402, Q69 |

## Reporting principle: separate facts from opinions

The brief asks for no unsupported recommendations. Every finding in `docs/05_sql_analysis.md` therefore carries four labels:

| Label | Meaning | Example |
|---|---|---|
| **Fact** | a value read from the data | 2,315 orders were cancelled |
| **Calculated metric** | a value from a documented formula | order return rate 5.22 % |
| **Analytical observation** | what the numbers appear to show | online orders return more often than in-store orders |
| **Possible business action** | an option to investigate, never a conclusion | review the packaging and description quality of online orders |

## Definitions and assumptions

- **Sales** are completed orders only; cancelled orders are kept in the data but excluded from KPIs.
- **Revenue** is net of GST (`line_total / (1 + GST rate)`); GST-inclusive figures are always labelled.
- **Profit** is gross profit: net revenue minus cost of goods at the time of sale. Store running costs are not in the data.
- **As-of date** is 31 December 2025, the last order date.
- **Thresholds** (RFM cut-offs, stock health rules, ABC split, 30-day cover) are **project assumptions**, documented next to their use, and are not industry standards.
- **Customer lifetime value** here is the value observed so far (historical), not a prediction.

## Out of scope

Forecasting and machine learning, store running costs, staff payroll, real-time data, multi-currency, and publishing to Power BI Service.
They are listed under "Future improvements" in the README.

## Non-functional requirements

| Requirement | How it is met |
|---|---|
| Reproducible | seeded generator, one-command rebuild (`python scripts/load_data.py`) |
| Trustworthy | 300+ automated tests; every KPI reconciled across SQL, views, Python and expected Power BI values |
| Secure | no secrets in Git (`.env` ignored), read-only database login for Power BI |
| Explainable | every query has business question, approach, concepts and rationale in comments |
| Fast enough | 10 justified indexes, measured with `EXPLAIN ANALYZE` (see doc 10) |

# 11. Interview questions based on this project

Answers are short on purpose: say the idea in one or two sentences, then point to the query or file that proves it. Query IDs (Q33 ...) refer to `queries/`.
Where the honest answer includes a weakness, the weakness is stated, because interviewers respect that.

**Contents:** SQL (12) - Database (9) - Data analyst (9) - Power BI (8) - Python (8) - Business (8) - Project (10) = 64 questions.

---

## SQL questions

**1. What is the difference between `ROW_NUMBER`, `RANK` and `DENSE_RANK`?**
`ROW_NUMBER` gives every row a unique number even when values tie. `RANK` gives ties the same number and skips the next ones (1, 1, 3). `DENSE_RANK` gives ties the same number without skipping (1, 1, 2).
I used `ROW_NUMBER` for "best product per category" (Q48) because I needed exactly one row, and `DENSE_RANK` for "top 3 including ties" (interview file Q207).

**2. How do you calculate month-over-month growth?**
Aggregate to one row per month, then `LAG(revenue) OVER (ORDER BY month)` fetches last month's value on the same row, and growth = `(revenue - previous) / previous`. `NULLIF` avoids dividing by zero (Q15). Year-over-year is the same with `LAG(revenue, 12)` or, quarterly, `LAG(revenue, 4)` (Q26).

**3. How do you write a running total and a 3-month moving average?**
Running total: `SUM(revenue) OVER (ORDER BY month)` (Q22). Moving average: `AVG(revenue) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)` (Q23). I return NULL for the first two months because their window is incomplete.

**4. `WHERE` versus `HAVING`?**
`WHERE` filters rows before grouping; `HAVING` filters groups after aggregation. Example: `HAVING COUNT(*) >= 30` keeps suppliers with enough purchase orders for a fair on-time rate (Q82).

**5. `NOT IN` or `NOT EXISTS`? Why?**
`NOT EXISTS`. If the subquery returns even one NULL, `NOT IN` returns no rows at all. My data proves it: `products.category_id` has NULLs, so `NOT IN` finds 0 unused categories while `NOT EXISTS` finds 5 (Q211). Q34 shows three anti-join styles agreeing on customers who never bought.

**6. How do you find and remove duplicates?**
Define "duplicate" first (here: same e-mail ignoring case and spaces), then `ROW_NUMBER() OVER (PARTITION BY LOWER(TRIM(email)) ORDER BY registration_date)`; row 1 is kept, rows above 1 are duplicates (Q202). I only SELECT them: deleting before a human confirms is unsafe, since two family members can share an e-mail.

**7. What is a CTE and when do you use one?**
A named temporary result (`WITH x AS (...)`) that makes a query readable and reusable within it. I use them to build a query in steps (aggregate, then rank, then filter). A recursive CTE (Q100) walks a hierarchy such as the category tree.

**8. When is a recursive CTE justified?**
When the depth of the structure is unknown: category parent/child and employee reporting lines (Q100-Q102). It has an anchor query (roots) and a recursive part that adds children until none are left. I did not use recursion for anything a normal join can do.

**9. How do you get the median in PostgreSQL?**
`PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_amount)` (Q05, Q206). It matters here because the mean order value (INR 3,202) is much higher than the median (INR 1,812): a few large orders lift the mean.

**10. What is a `LATERAL` join?**
A subquery in `FROM` that can refer to columns of tables before it, so it runs once per row. I used it for "top 3 products per store" (Q107): for each store row, a small ordered `LIMIT 3` query.

**11. How do you find gaps or streaks in dates?**
"Gaps and islands": number the distinct days with `ROW_NUMBER`, subtract the number from the date; consecutive days give the same result, so grouping by it finds each streak (Q106, and consecutive months in Q204).

**12. Why is `SELECT` with a function on an indexed column slow, and how do you fix it?**
`WHERE LOWER(email) = 'x'` cannot use a plain index on `email`. Create an expression index on `LOWER(email)` (Q509: about 100x faster) or filter with a range instead of `DATE_TRUNC` on a date column.

---

## Database questions

**13. Explain the main relationships in your schema.**
Customer to orders is one-to-many; an order has many lines; orders and products are many-to-many, resolved by `sales_order_items`. Products and stores are many-to-many through `inventory`. Promotions and products are many-to-many through `product_promotions`. Categories and employees have self-references. The ERD is in `database/erd.md`.

**14. Why split orders into a header and lines?**
An order has many products. Storing one row per product avoids repeating order data and gives clean product-level analysis. It also keeps totals consistent: a test proves every order header equals the sum of its lines.

**15. Why store price and cost on the order line?**
Prices change. A snapshot at the time of sale means history is never rewritten, and profit uses the cost that applied then. Without it, last year's revenue would change whenever today's price changes.

**16. Which constraints did you use, and what do they catch?**
Primary keys, foreign keys, UNIQUE, NOT NULL, CHECK and DEFAULT. Examples: `CHECK (quantity > 0)`, `CHECK (end_date >= start_date)`, `reserved_quantity <= quantity_on_hand`. A test suite tries to insert bad rows and expects PostgreSQL to reject each one.

**17. Why did you deliberately *not* constrain some things?**
Real source systems allow duplicate customers, bad e-mails and missing categories. I left those loose (no unique e-mail, nullable category) so the data-quality queries have real problems to find. The rule: block what is impossible, detect what is merely messy.

**18. What indexes did you create and how did you decide?**
Ten, each justified by `EXPLAIN ANALYZE`: foreign keys used for single-record lookups, the order date, the ledger key (store, product, date), a partial index on open purchase orders, and an expression index on `LOWER(email)`. I removed indexes I could not justify, for example one that the planner ignored (doc 10).

**19. Does a foreign key create an index in PostgreSQL?**
No. The referenced primary key is indexed, but the referencing column is not. If you look up or join by it, add an index. Also a composite key like `UNIQUE (order_id, product_id)` only serves queries that filter on its left-most column.

**20. What is normalisation and did you go too far?**
Removing repeated data by putting facts in one place (3NF). I stopped where it stayed practical: GST rate sits on the product (simple) although a real system would keep a rate history. Analytical views then denormalise on purpose for reporting.

**21. What is a view, and what is a materialized view? Which did you use?**
A view stores a query; a materialized view stores its result and must be refreshed. Twelve views define the KPIs; only `vw_customer_summary` is materialized because RFM over every customer is the most expensive calculation.

**22. What is a transaction and where did you use one?**
A group of statements that succeeds or fails together. The loader loads all 18 tables, the views and the indexes in one transaction, so a failure leaves no half-loaded database. Tests also run inside transactions that are rolled back so they never change data.

**23. What is the stock ledger and why keep it?**
`inventory_transactions` records every movement (opening, purchase, sale, return, adjustment). Summed per store and product it must equal stock on hand. It gives an audit trail, and a check finds the 68 positions that were altered without a matching entry.

---

## Data analyst questions

**24. How did you define revenue, and why net of GST?**
Net revenue = line total / (1 + GST rate). GST is collected on behalf of the government, so it is not the business's revenue. Average order value is GST-inclusive because it describes what the customer pays. I state both wherever they appear.

**25. How do you check that a number is right?**
Compute it by two independent routes and compare. Total revenue comes from order headers, from order lines, from three views and from Python; tests assert they agree to within rounding. Discrepancy found once is worth a lot: I caught a wrong "best month" claim in my own write-up this way.

**26. What is RFM and how did you implement it?**
Recency (days since last order), Frequency (orders), Monetary (revenue). I used fixed thresholds for recency and frequency and quintiles for monetary, then named segments (Champions ... Lost) by rules. I state that the labels and thresholds are my assumptions, not facts.

**27. What is cohort analysis?**
Group customers by the month of their first purchase and follow how many buy again in later months (Q41). It separates "acquiring new customers" from "keeping them". In my data the January 2023 cohort returned at 44 % in month 1; later cohorts around 29-36 %.

**28. What is a Pareto or ABC analysis?**
Rank items by contribution and cumulate the share: class A is the first 80 % of revenue, B the next 15 %, C the last 5 %. Here 216 products (35 %) give 80 % of net revenue, and the top 20 % of products give about 66 %. The 80/15/5 split is a convention.

**29. How do you handle missing or dirty data?**
Detect, count, decide, document. NULL categories are shown as "(no category)" instead of being dropped (dropping would understate revenue); case-variant categories are merged in one view; cancelled orders are excluded from KPIs; duplicates are flagged but not merged. The table of treatments is in doc 09.

**30. What is the difference between a fact and an insight?**
A fact is a value from the data. A calculated metric comes from a formula. An observation interprets the numbers. A possible action is an option to test. I keep the four apart in doc 05 so I never present an opinion as a fact.

**31. How would you tell whether a promotion worked?**
Compare against a control, not just before and after. My before/after comparison (Q28) shows summer promotions +60 to +87 % in daily units, but summer appliances sell more in summer anyway, so the number cannot prove a promotion caused it. Promoted lines also earn 11.0 % margin versus 24.2 % on full-price lines, so extra volume must cover that.

**32. The mean and median order values differ a lot. What do you report?**
Both, and say why: the distribution is right-skewed. Mean INR 3,202, median INR 1,812. For "typical order" use the median; for revenue planning the mean.

---

## Power BI questions

**33. What data model did you design?**
A star schema: fact tables (sales lines, orders, returns, inventory snapshot) around dimensions (date, store, product, customer, channel). Relationships are many-to-one with single-direction filtering. The full table is in `dashboard/powerbi_setup.md`. (State honestly that the report is specified and lint-tested; if you built it, say so.)

**34. Why not link the fact tables to each other?**
Linking order lines to orders would give two filter paths from the store dimension to the lines (ambiguous). Instead each fact has its own path from the dimensions, and measures read the right fact. The trade-off: category slicers do not change the order count.

**35. What is an inactive relationship?**
A relationship that exists but is not used by default. `USERELATIONSHIP` turns it on inside a measure. I used it for "new customers" (customer first-purchase month to the date table) and for refunds by return date.

**36. Row context versus filter context?**
Row context is "the current row" (calculated columns, iterators). Filter context is the set of filters from slicers, visuals and `CALCULATE`. `CALCULATE` changes the filter context, which is how "last 12 months COGS" or "revenue for prior year" work.

**37. How did you calculate the 3-month moving average and running total?**
With `CALCULATE` plus `REMOVEFILTERS(dim_date)` and a date condition, so the window can reach back across a year slicer. The measures are in `dashboard/measures.dax`.

**38. Import or DirectQuery?**
Import: the data is small (tens of MB), it is much faster, and it supports all DAX. DirectQuery would suit very large or real-time data, at the cost of speed and some features.

**39. How do you make a dashboard trustworthy?**
Define each KPI once (in views), test the measures against known values (`expected_kpis.md`: with no slicer every card must equal the listed value), label snapshot and lifetime measures, and keep colours meaningful (status colours only for status).

**40. Why avoid dual-axis charts and pie charts?**
Two scales on one chart invite false visual correlation; sorted bars compare values more accurately than pie slices. Two measures of different scale get two charts.

---

## Python questions

**41. Why use both SQL and Python?**
SQL for relational work (joins, GST, RFM, stock rules) close to the data; Python for exploration, statistics and charts. The analysis modules read the SQL views and do not repeat the join logic, so there is one definition of each KPI.

**42. How do you connect to PostgreSQL safely?**
SQLAlchemy engine built from environment variables (`.env`, ignored by Git). No password in code. `.env.example` documents the variables.

**43. How did you test the Python code?**
`pytest`: the pandas KPI functions must equal the independent SQL query Q401 for revenue, profit, orders, customers, AOV, repeat rate, return rate and inventory value; charts must be created; the dashboard export must have the right files and totals; notebooks must contain no error output.

**44. What does `data_validation.py` check?**
30 checks on the views: expected columns, unique keys, value ranges, valid categories, and reconciliation of revenue, profit, units, orders and inventory value across views and against the base tables. It exits with a non-zero code on failure, so it can gate a pipeline.

**45. How did you calculate growth and moving averages in pandas?**
`pct_change()` for month-over-month and `pct_change(12)` for year-over-year on a month-sorted frame; `rolling(3).mean()` for the moving average; `cumsum()` for the running total (`python/kpis.py`).

**46. How do you avoid double counting when combining tables in pandas?**
Aggregate each table to the grain you will join on before merging, then merge one-to-one. The same rule applies in SQL (Q47, Q72).

**47. How did you build the charts, and how did you check them?**
matplotlib and seaborn with one blue hue for one measure, a second colour only for a second series with a legend, direct labels and recessive gridlines. I looked at every image: this caught clipped axis labels that no automated check would find.

**48. What is the difference between `apply`, vectorised operations and loops in pandas?**
Vectorised operations run in optimised compiled code and are fastest; `apply` runs Python per row and is slower; explicit loops are slowest. I used vectorised operations and pushed heavy work into SQL.

---

## Business questions

**49. Which products should management focus on?**
Q402 lists class-A products (the 80 % of revenue) with a warning sign: margin below the company average, revenue down more than 15 %, return rate above 3 %, or under 30 days of stock. For example, Compex Laptop Pro (5.7 % margin, revenue down 39 %). A flag means "look", not "act".

**50. Which categories are declining?**
Books & Stationery (-10.0 % then -25.4 %), Furniture & Decor (-5.3 % then -19.9 %) and Kids' Wear (-0.1 % then -15.1 %) fell two years in a row; Laptops & Computers fell 18 % in 2025 after growing 9 %. Footwear's +112 % is a single new product, so I do not call it a trend.

**51. Which stores are weak?**
Measured as revenue per month open versus the store average: Lucknow 46 %, Chandigarh 47 %, Jaipur 64 %. Lucknow also holds INR 63 lakh of stock, 96 % of it surplus. Before acting I would study local demand; a new store may still be ramping (though Chandigarh has been open 31 months).

**52. How much stock is a problem?**
Of INR 6.27 crore of stock at cost, dead stock (no sale at the store in 365 days) is 51.9 % and overstock 35.9 %. Turnover is 0.68 a year (about 535 days). The rules are my assumptions; with a 180-day window dead stock would be 63 %. That sensitivity is written down.

**53. Which products have high sales but low stock?**
Five products are in the top revenue quintile with under 30 days of cover, such as Golden Grain Pure Ghee 1L (15.6 days) and Annadata Pure Ghee 1L Pack of 2 (18.6 days) (Q67, Q69). Meanwhile 231 slow products hold INR 2.73 crore of stock, so allocation, not total stock, looks like the issue.

**54. What are the returns telling you?**
Order return rate 5.22 %, value return rate 2.56 % of net revenue. Online 6.94 % vs in-store 4.91 %. Footwear and apparel have the highest unit return rates and "size issue" is the top recorded reason. I say "recorded reason": the data does not prove why customers returned things.

**55. Are the suppliers reliable?**
52.4 % of purchase orders arrive on or before the expected date and fill rates are about 98 % or higher even for the weakest suppliers, so lateness is frequent but small (about 2 days at worst averages). Because reorder points use the promised lead time, a steady two-day gap erodes the safety margin.

**56. What would you do with a limited budget?**
Fix data first (missing categories and suppliers, duplicate customers), then use the ranked lists: replenish the short fast movers, stop re-ordering dead stock, and test a win-back offer on the "At Risk" segment against a control group.

---

## Project questions

**57. Give me the two-minute overview.** See [12_project_walkthrough.md](12_project_walkthrough.md).

**58. Why synthetic data, and how did you make it realistic?**
Real retail data with returns, stock ledgers and suppliers is not public. I wrote a seeded simulation of the business process: demand with seasonality, stock falling with sales, reorders arriving after supplier lead times, lost sales on stock-outs, returns and payments. I also planted known data-quality problems so the checks have something to find.

**59. What are the limits of the data?**
The patterns were designed in, so finding them shows the method works, not that a real retailer behaves this way. Some properties are unusual: 83 % repeat customers, and inventory that turns over only 0.68 times. I state these in the docs and in the README.

**60. What was the hardest problem?**
Making the numbers agree. Examples: a benchmark that ran in one rolled-back transaction so my indexes never persisted; a "best month" sentence that was wrong for 2023; unrealistic overstock (544 unsold laptops) that I found by reading query results. Each was found by a test or by looking at the output, and fixed.

**61. How did you make sure nothing is faked?**
Every figure in the docs comes from a query, the generator, or the benchmark script. Benchmarks record measured times, mark identical plans as "noise", and the docs give ranges across runs. Tests pin the counts quoted in the documents.

**62. What would you improve with more time?**
Real safety-stock and forecasting models; stock transfers between stores; customer de-duplication with a matching score; a built and published Power BI report with scheduled refresh; incremental loading instead of full rebuild; row-level security.

**63. How did you organise the work?**
In phases with a check after each: requirements, structure, schema, data generation, load, validation, queries, views and indexes, SQL validation, Python, dashboard, documentation, README, audit. One Git commit per phase.

**64. What did you learn?**
Verify by reading results, not only by running tests; state definitions before computing; a number is trusted only when two routes agree; indexes are a tool, not a habit; and being explicit about assumptions makes an analysis more credible.

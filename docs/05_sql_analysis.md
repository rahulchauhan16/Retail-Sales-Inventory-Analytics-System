# 05. SQL analysis

## How the SQL is organised

143 analytical queries + 17 `EXPLAIN ANALYZE` scenarios, in 13 files under `queries/`. Every query starts with a header:

```sql
-- Q33 | Repeat customer rate
-- Business question: ...        what management wants to know
-- Approach: ...                 how the SQL answers it
-- Concepts: ...                 SQL features demonstrated
-- Why it works: ...             the reasoning (and any trap)
```

| File | Queries | Topic | Techniques worth knowing |
|---|---:|---|---|
| `01_basic_analysis.sql` | 12 | totals, revenue, profit, AOV, counts | `FILTER`, `UNION ALL`, `CASE`, `PERCENTILE_CONT`, date functions |
| `02_sales_analysis.sql` | 19 | trend, growth, ranking, promotions | `LAG`, `RANK`, `ROW_NUMBER`, running total, `ROWS BETWEEN` moving average, conditional aggregation |
| `03_customer_analysis.sql` | 15 | value, repeat rate, RFM, cohorts | `NTILE`, anti-joins (`NOT EXISTS` vs `NOT IN`), cohort maths, `LAG` for gaps |
| `04_product_analysis.sql` | 12 | margin, Pareto/ABC, decline, co-purchase | cumulative-share window, `SELF JOIN`, top-N per group |
| `05_inventory_analysis.sql` | 13 | health, turnover, cover, aging, risk | multi-CTE classification, correlated subquery, `PERCENT_RANK` |
| `06_store_analysis.sql` | 9 | scorecards, ranking, weak locations | aggregate-then-join, `ROLLUP` + `GROUPING`, self join |
| `07_supplier_analysis.sql` | 8 | spend, on-time, fill rate, scorecard | date arithmetic, ratio of sums, composite `PERCENT_RANK` score |
| `08_return_analysis.sql` | 11 | return rates (3 definitions), reasons | pre-aggregation to avoid double counting, benchmark vs category |
| `09_advanced_sql.sql` | 16 | recursion, sets, LATERAL, islands, percentiles | `WITH RECURSIVE`, `FULL OUTER JOIN`, `INTERSECT`/`EXCEPT`, `LATERAL`, gap filling, `LEAD`, `DISTINCT ON` |
| `advanced_sql_interview.sql` | 14 | classic interview problems | Nth highest, dedupe, relational division, consecutive months, the `NOT IN` trap |
| `10_data_quality_checks.sql` | 9 | 30-check scorecard + drill-downs | regex, `STRING_AGG`, orphan and reconciliation checks |
| `11_business_questions.sql` | 5 | KPI summary, focus list, 50-question map | composed KPIs |
| `12_performance_optimization.sql` | 17 | `EXPLAIN ANALYZE` workload | see doc 10 |

Run any file with `python scripts/run_query_file.py queries/02_sales_analysis.sql --show 5`; the automated tests (`tests/test_sql_queries.py`) execute every statement and cross-check the totals.

### Definitions used by every query

Sales = completed orders. Net revenue = `line_total / (1 + GST rate)`. Gross profit = net revenue - `quantity x unit_cost` (cost at time of sale).
As-of date = 31 Dec 2025. Full definitions: [dashboard_requirements.md](../dashboard/dashboard_requirements.md).

---

## Findings

Each finding has four layers so that facts are never mixed with opinion.
Figures are from the seed-42 dataset; the query that produces each is named. **These are observations about synthetic data**; several patterns were designed into the generator, so the value here
is showing the method, not discovering truths about a real retailer.

### 1. Revenue growth is positive but slowing
| Layer | Statement |
|---|---|
| Fact | Net revenue was INR 4.54 crore (2023), 5.09 crore (2024) and 5.62 crore (2025). |
| Calculated metric | Year-over-year growth: +12.05 % (2024), +10.42 % (2025). Q14. |
| Observation | Growth continues but at a lower rate in the latest year. |
| Possible action | Break growth into new customers, repeat purchases and price: the data has all three (Q38, Q33, `vw_monthly_sales`). |

### 2. Strong festive seasonality
| Layer | Statement |
|---|---|
| Calculated metric | Seasonality index (100 = a typical month of the year): October 141.6, November 130.7, December 114.8, January 74.2, February 74.1. |
| Fact | The best month was November in 2023 (INR 53.4 lakh) and October in 2024 (INR 60.1 lakh) and 2025 (INR 68.7 lakh); October and November are always in the top two (Q24, Q31). |
| Observation | The peak sits in October-November every year, and it is getting taller in absolute terms. |
| Possible action | Time stock build-up and promotions ahead of September; check that reorder levels are raised before the peak (the data does not show whether they were). |

### 3. Growth comes from online and newer stores, not from the largest older stores
| Layer | Statement |
|---|---|
| Fact | The online hub's revenue grew 34.4 % in 2025 vs 2024, Jaipur 39.2 %; Bengaluru (-2.4 %), Hyderabad (-1.6 %), Delhi (-1.4 %) and Mumbai (+0.5 %) were flat or down. Q74. |
| Calculated metric | Online share of completed orders: 10.9 % (2023), 15.3 % (2024), 20.0 % (2025). Online share of net revenue: 14.5 % (2023), 23.5 % (2025). Q403. |
| Observation | The company's growth is coming from the online channel and from stores still ramping up. |
| Possible action | Check whether online sales replace store sales in the same cities. The data cannot show this, because online orders are not linked to a "home store" visit. |

### 4. Category mix: leaders and decliners
| Layer | Statement |
|---|---|
| Fact | 2025 revenue share: Mobiles & Accessories 14.8 %, Women's Clothing 11.0 %, Grocery 10.8 %, Men's Clothing 10.6 %. |
| Calculated metric | Books & Stationery fell in both 2024 (-10.0 %) and 2025 (-25.4 %); Furniture & Decor -5.3 % then -19.9 %; Kids' Wear -0.1 % then -15.1 %; Laptops & Computers +9.3 % then -18.0 %. Q50. |
| Observation | Three categories declined two years in a row. Footwear's +112 % in 2025 is one product: "Pacer Ankle Boots UK 6", launched March 2025, accounts for INR 15.3 lakh of Footwear's INR 22 lakh increase. |
| Possible action | For decliners, look at range, price and stock availability before deciding to shrink the category. Do not read Footwear's jump as a category trend. |

### 5. Revenue is concentrated
| Layer | Statement |
|---|---|
| Calculated metric | The top 20 % of products give 65.6 % of net revenue; 216 class-A products (35 % of products sold) give 80.1 % (Q52, Q53). The top 10 % of buyers give 46.1 % of revenue (Q46). |
| Observation | Both product and customer revenue follow a Pareto-like pattern; the Herfindahl index (0.007) shows no single product dominates. |
| Possible action | Prioritise availability and quality for class-A products; protect the top-decile customers (see finding 8). |

### 6. Promotions cost margin, and their effect varies widely
| Layer | Statement |
|---|---|
| Fact | 5,308 order lines carried a promotion; total discount was INR 24.3 lakh. |
| Calculated metric | Discount depth on promoted lines 18.9 %; gross margin on promoted lines 11.0 % vs 24.2 % on full-price lines (Q27). Daily unit uplift versus the 28 days before: Summer promotions +60 % to +87 %, Diwali +7 % to +14 %, some year-end, Republic Day and clearance promotions -1 % to -20 % (Q28). |
| Observation | Promoted lines earn less than half the margin. Uplift is uneven, and the before/after method cannot separate a promotion from the season (summer appliances sell more in summer anyway). |
| Possible action | Test promotions against a comparison group (a holdout store or product set) before scaling; check that extra volume covers the lost margin. |

### 7. Customers: high repeat rate, but a large dormant group
| Layer | Statement |
|---|---|
| Fact | 7,074 of 9,120 registered customers bought (77.6 %); 2,046 (22.4 %) never did. |
| Calculated metric | Repeat customer rate 83.4 % of buyers. Second order within 30 / 60 / 90 days of the first: 33.3 % / 49.3 % / 60.1 %; 12.0 % never came back (Q115). |
| Observation | Once a customer buys twice they mostly keep buying; the 90 days after first purchase are where most of the second orders happen. The unusually high repeat rate is a property of the synthetic data. |
| Possible action | Focus onboarding messages on the first 30-60 days after a first purchase. |

### 8. RFM: value sits with a few groups, and "At Risk" holds real revenue
| Layer | Statement |
|---|---|
| Calculated metric | Champions: 23.0 % of buyers, 54.0 % of revenue. At Risk: 18.5 % of buyers, 19.3 % of revenue, average 447 days since last order. Lost Customers: 19.0 % of buyers, 4.7 % of revenue (Q40). |
| Observation | About a fifth of historical revenue comes from customers who have not bought for more than a year. Segment names are analytical labels based on project thresholds, not facts about people. |
| Possible action | Trial a win-back offer on the At Risk group and compare with a control group. |

### 9. Inventory: most of the stock value is not moving
| Layer | Statement |
|---|---|
| Fact | Stock at cost is INR 6.27 crore. Of 5,690 store-product positions: 77 out of stock, 358 low, 1,643 healthy, 2,272 overstocked, 1,340 dead stock (Q60). |
| Calculated metric | Dead stock is 51.9 % and overstock 35.9 % of stock value (87.8 % together). Inventory turnover 0.68 (about 535 days of stock). Turnover by category ranges from 6.5 (Grocery) and 5.0 (Beverages) down to 0.1 (TV & Audio, Furniture). Q62. |
| Observation | Fast-selling low-value categories turn quickly, while expensive categories hold years of stock. The classification rules and the synthetic stock policy are assumptions (doc 06), so the exact percentages depend on them. |
| Possible action | Review which premium items each store should range at all; stop re-ordering dead-stock positions; move surplus between stores if transfers are possible (transfers are not modelled). |

### 10. Some best-selling products are short while many slow products hold most of the stock
| Layer | Statement |
|---|---|
| Fact | Five high-revenue products have under 30 days of stock, including Golden Grain Pure Ghee 1L (15.6 days) and Annadata Pure Ghee 1L Pack of 2 (18.6 days). Q67. |
| Calculated metric | 231 low-revenue products hold INR 2.73 crore of stock while earning INR 22.7 lakh of revenue in the last 12 months (Q69). |
| Observation | Stock-outs on fast movers and surplus on slow ones can occur together, which points to allocation rather than total quantity. |
| Possible action | Raise reorder levels for the short fast-movers; review the slow group's ranging. |

### 11. Weak locations
| Layer | Statement |
|---|---|
| Calculated metric | Revenue per month open, as % of the store average: Lucknow 46 %, Chandigarh 47 %, Jaipur 64 %; Mumbai 158 %, Delhi 152 %, Bengaluru 141 % (Q76). |
| Fact | Lucknow (opened March 2024) holds INR 63.4 lakh of stock, 96 % of it surplus (Q71). |
| Observation | Three stores earn about half or less than the average store per month, even Chandigarh after 31 months. The weakest store carries the most surplus stock. |
| Possible action | Study local demand before changing anything; align stock with what the store actually sells. |

### 12. Suppliers deliver late half the time, but only slightly
| Layer | Statement |
|---|---|
| Calculated metric | 52.4 % of received purchase orders arrived on or before the expected date; the weakest suppliers are at 41-42 % (Q82, Q403). Fill rate is high even for the weakest suppliers with 200+ units ordered (lowest 98.0 %, Q83). Average lateness for the weakest is about 1.5-2.2 days (Q82, Q84). |
| Observation | Lateness is frequent but small. Reorder levels are based on promised lead times, so a consistent gap of a couple of days erodes the safety margin. |
| Possible action | Update lead-time assumptions with actual averages; review the ranked scorecard (Q88). |

### 13. Returns: modest overall, higher online and in apparel
| Layer | Statement |
|---|---|
| Calculated metric | Order return rate 5.22 % (2,835 of 54,260); unit return rate 1.62 %; refunds INR 39.0 lakh net of GST = 2.56 % of net revenue; write-off cost INR 7.8 lakh (Q89, Q95, Q97). Online 6.94 % vs in-store 4.91 % (Q98). Unit return rates: Footwear 5.59 %, Women's 4.89 %, Men's 4.00 % (Q91). |
| Fact | Recorded reasons: size issue 24.9 %, changed mind 19.9 %, defective 17.8 %, not as described 16.3 % (Q90). |
| Observation | Apparel and footwear have the highest unit return rates, and size issue is the most frequent recorded reason. The data shows the recorded reason, not why customers really returned. |
| Possible action | Test better size guidance on high-return items; compare online packaging and description quality with in-store. |

### 14. The data has known quality problems, and the checks find them
Covered in [09_data_quality.md](09_data_quality.md): 30 checks, of which 8 constraint-backed checks return 0 and 13 planted problems are detected (for example 120 duplicate-like customers, 68 stock positions that differ from the ledger, 211 completed orders without a payment record).

### 15. Management focus list
Q402 combines margin, growth, returns and stock cover for class-A products. Examples: *Compex Laptop Pro* (5.7 % margin, revenue down 39 % in 2025) and *Techra Laptop Black* (12.9 % return rate, revenue down 48 %, 585 days of stock) are flagged. A flag means "look at this product", not "act".

---

## Reading the numbers honestly

- The dataset is synthetic; designed patterns (seasonality, category trends, Pareto) will always be "found".
- Thresholds and class boundaries are assumptions written next to each query.
- Before/after comparisons (promotions) and associations (co-purchase, first-purchase category) do not prove cause.
- Small counts (for example five products in "High Revenue / Low Stock") can change with a different threshold.

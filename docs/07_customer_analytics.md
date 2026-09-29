# 07. Customer analytics

Implemented in `vw_customer_summary` (a materialized view), queries Q32-Q46 and Q104-Q115, and `python/customer_analysis.py`.
**All segment names and thresholds below are analytical labels chosen for this project, not facts about people.**

## Basic measures

| Measure | Definition |
|---|---|
| Total customers | registered customers (9,120 rows, including 120 duplicate-like records) |
| Buying customers | customers with at least one completed order (7,074) |
| Never purchased | registered but no completed order (2,046, 22.4 %) |
| New customers (in a period) | customers whose first completed order falls in that period |
| Repeat customer | buyer with 2 or more completed orders |
| Repeat customer rate | repeat customers / buying customers = 83.4 % (5,901 of 7,074) |
| Purchase frequency | completed orders / buying customers (7.67 over three years) |
| Average order value | GST-inclusive order value: INR 3,202 (the median order is only INR 1,812, so a few large orders lift the mean) |
| Customer lifetime value (to date) | net revenue per buying customer: INR 21,562 on average |
| Recency, Frequency, Monetary | days since last order; number of orders; total net revenue |

Lifetime value here is **historical** (what the customer has already spent), not a predicted future value.

## Activity status (as of 31 Dec 2025)

| Status | Rule | Customers |
|---|---|---:|
| Active | last order within 90 days | 3,376 (37.0 %) |
| Inactive | 91-365 days | 2,126 (23.3 %) |
| Lost | over 365 days | 1,572 (17.2 %) |
| Never purchased | no completed order | 2,046 (22.4 %) |

The 90/365-day cut-offs are assumptions. Note the `is_active` column in `customers` is the *source system's* flag and is a different thing (data-quality check DQ26 confirms no flagged-inactive customer ordered in the last 90 days).

## RFM scoring

| Score | Recency (days since last order) | Frequency (completed orders) | Monetary |
|:-:|---|---|---|
| 5 | 30 or less | 13+ | top 20 % of buyers by net revenue |
| 4 | 31-90 | 7-12 | next 20 % |
| 3 | 91-180 | 4-6 | middle 20 % |
| 2 | 181-365 | 2-3 | next 20 % |
| 1 | over 365 | 1 | bottom 20 % |

- Recency and Frequency use fixed thresholds; Monetary uses `NTILE(5)` on net revenue. Fixed thresholds are used for frequency because `NTILE` would split identical order counts into different buckets arbitrarily.
- The monetary score is stored (`m_score`) but is **not** used to name the segment, to keep the labels easy to explain.

### Segment labels (first matching rule)

| Segment | Rule | Customers | Share of buyers | Share of net revenue | Avg days since last order |
|---|---|---:|---:|---:|---:|
| Champions | R >= 4 and F >= 4 | 1,630 | 23.0 % | 54.0 % | 34 |
| Loyal Customers | R >= 3 and F >= 3 | 1,257 | 17.8 % | 16.8 % | 82 |
| Potential Loyalists | R >= 3 and F <= 2 | 1,529 | 21.6 % | 5.3 % | 67 |
| At Risk | R <= 2 and F >= 3 | 1,311 | 18.5 % | 19.3 % | 447 |
| Lost Customers | R <= 2 and F <= 2 | 1,347 | 19.0 % | 4.7 % | 528 |

Every buying customer falls into exactly one segment (checked by tests). Read "At Risk" as: bought often in the past, but nothing for more than 180 days.

## Commercial segments (source attribute `customer_segments`)

| Segment | Buyers | Avg lifetime revenue (INR) | Share of revenue |
|---|---:|---:|---:|
| Regular | 4,327 | 19,092 | 54.2 % |
| Premium | 1,049 | 35,106 | 24.1 % |
| Corporate | 415 | 39,340 | 10.7 % |
| Student | 1,211 | 12,751 | 10.1 % |
| (none assigned) | 72 | 18,367 | 0.9 % |

Regular customers bring the most revenue in total (there are many of them); Corporate and Premium bring the most per customer.

## Cohorts

Cohort = month of first purchase (Q41, `customer_analysis.cohort_retention`). For each cohort, the percentage that buys again 1-6 months later.
The January 2023 cohort (717 customers) returns at 44 % in month 1; later cohorts sit around 29-36 %. Retention does not decay smoothly because customers in this dataset return in bursts around the festive season.

Second-order timing (Q115): of customers whose first order is at least 90 days before the end of the data, 33.3 % order again within 30 days, 49.3 % within 60, 60.1 % within 90, and 12.0 % never do.

## Concentration

Top 10 % of buyers = 46.1 % of net revenue; top 20 % = 65.1 % (Q46, `customer_analysis.concentration`).

## Limitations to state in an interview

- **Duplicates:** 120 duplicate-like customer records are counted as separate customers. Merging them would raise repeat rates slightly and lower the customer count; the effect is not measured here.
- **Synthetic behaviour:** the 83 % repeat rate and the churn pattern are properties of the generator, not of real shoppers.
- **RFM is descriptive:** it says who bought recently and often, not who will buy next.
- **Thresholds:** changing 90/365-day cut-offs or the score bands changes segment sizes; nothing here is calibrated to a real business.

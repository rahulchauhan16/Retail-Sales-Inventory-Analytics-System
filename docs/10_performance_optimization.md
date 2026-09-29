# 10. Performance optimisation

Every number here was **measured** by `scripts/benchmark_indexes.py`; none is estimated. The latest single run is written to [benchmark_results.md](benchmark_results.md) each time the script runs.
Nothing was invented: where a timing gap was noise, the report says so.

## Method

1. `queries/12_performance_optimization.sql` holds 17 scenarios, each an `EXPLAIN (ANALYZE, BUFFERS)` statement with a written **expectation** before it was measured.
2. The script drops every secondary index, runs `ANALYZE`, and runs each scenario once to warm the cache and then **11 times, taking the median**.
3. It creates the indexes from `database/indexes.sql`, runs `ANALYZE`, and measures again.
4. If the plan is identical before and after, any timing difference is labelled **noise** instead of a speed-up.

**Environment:** PostgreSQL 16 in Docker on a Windows laptop, warm cache, 40 MB of table data (about 57k orders, 112k order lines, 144k ledger rows). Use the plan types and the size of the change, not the absolute milliseconds.

## Results

Timings vary from run to run, so the table gives the **range seen over repeated runs** (I ran the benchmark several times while refining the index list).

| Scenario | Plan before -> after | Speed-up seen |
|---|---|---|
| Q501 one customer's order history | Seq Scan -> Bitmap Index Scan (`idx_orders_customer`) | about 11x to 53x |
| Q502 revenue for one month | Seq Scan -> Index Scan (`idx_orders_date`) | about 2x to 8x |
| Q503 all lines of one product | Index Scan on the wrong index -> Bitmap Index Scan (`idx_items_product`) | about 4x to 24x |
| Q505 returned quantity for one product | improves through `idx_items_product` | about 2x to 6x |
| Q506 ledger of one store + product, in date order | Seq Scan -> Bitmap Index Scan (composite index) | about 280x to 650x |
| Q508 open purchase orders (partial index, 16 kB) | Seq Scan -> Index Scan | about 11x to 25x |
| Q509 case-insensitive e-mail lookup (expression index) | Seq Scan -> Bitmap Index Scan | about 95x to 150x |
| Q510 one store, one quarter | Seq Scan -> Index Scan (`idx_orders_date`) | about 5x to 7x |
| Q512 stock of one product | Seq Scan -> Bitmap Index Scan | about 5x to 13x |
| Q514 / Q515 / Q516 one order's returns / payments, one line's returns | Seq Scan -> Index Scan | about 6x to 10x, and about 130x to 160x for payments |
| Q504 correlated subquery per large order | Seq Scan -> Seq Scan + index probes | only about 1.6x to 3.5x |
| **Q507 anti-join for orders without payment** | **Hash Anti Join on both sides, index unused** | **none: same plan** |
| **Q511 full-table monthly aggregation** | **Seq Scan both times** | **none: same plan** |
| **Q513 products of one category (636 rows)** | **Seq Scan both times; not indexed on purpose** | **none** |

Last complete run: Q504 took 322 ms before and 149 ms after the indexes; the rewritten Q517 took 32 ms before and 36 ms after (see below).

## What the results teach

**1. An index helps a *selective* lookup on a *big* table.** Finding one customer's 70 orders among 57k, or one product's ledger rows among 144k, is a large win. Reading most of a table
(Q511) or joining two whole tables (Q507) is faster with a sequential scan or a hash join, and PostgreSQL correctly ignores the index. An index that is never used still slows every insert.

**2. A composite key only helps its left-most column.** `UNIQUE (order_id, product_id)` cannot serve `WHERE product_id = 13` (Q503), and `UNIQUE (store_id, product_id)` cannot serve product-only lookups (Q512).
A foreign key does not create an index in PostgreSQL; you must add one where you look up by that column.

**3. Special index types fit special problems.** A *partial* index (`WHERE status = 'ORDERED'`, only 1.7 % of purchase orders: 407 of 23,626) is 16 kB. An *expression* index on `LOWER(email)` is required because
`WHERE LOWER(email) = ...` cannot use an index on `email`.

**4. Rewriting the query can beat an index.** Q504 runs a subquery for every large order. With `idx_orders_customer` it fell from about 322 ms to about 149 ms. The rewrite Q517 computes each customer's average **once** and joins to it:
about 32 ms, **without needing the index**, and a test proves it returns exactly the same rows. Work that scales with the number of outer rows is the thing to remove.

**5. Measurement beats intuition.** Two indexes I first created were removed after testing: `(store_id, order_date)` was ignored by the planner when `order_date` alone existed, and alone it saved about 0.4 ms on a 0.7 ms query
(1.8 MB, slower inserts). Five foreign-key indexes on tiny or full-scan-only tables (products, suppliers, purchase items, promotions) had no measured benefit and were never kept.
Also, `idx_return_items_order_item` first looked unused; a more selective scenario (Q516) showed it is used and about 6x faster, so it stayed.

**6. Small tables gain little in absolute terms.** Several wins above are in the range 0.15 ms to 0.02 ms. They are justified by growth (the same lookups on millions of rows), not by today's users. The rule used: index foreign-key and lookup columns on tables of a few thousand rows and up; skip tables of about a thousand rows or fewer.

## Final index list (10) and size

| Index | Table | Why | Size |
|---|---|---|---:|
| `idx_invtxn_store_product_date` | inventory_transactions | ledger per store + product in date order (reconciliation, running balance) | 4.4 MB |
| `idx_payments_order` | payments | payments of an order | 1.2 MB |
| `idx_orders_date` | sales_orders | date-range filters, also serves store + period | 1.2 MB |
| `idx_items_product` | sales_order_items | all sales of a product | 0.8 MB |
| `idx_orders_customer` | sales_orders | a customer's orders; correlated subqueries | 0.6 MB |
| `idx_customers_email_lower` | customers | case-insensitive lookup and duplicate detection | 0.4 MB |
| `idx_return_items_order_item` | return_items | returns of a sold line | 80 kB |
| `idx_returns_order` | returns | returns of an order | 80 kB |
| `idx_inventory_product` | inventory | stock of a product across stores | 72 kB |
| `idx_purchases_open_expected` (partial) | purchases | open POs by due date | 16 kB |

Together about 9 MB on top of 40 MB of tables.

## SQL habits that keep queries fast (all used in `queries/`)

- Aggregate each measure at its own grain **before** joining (Q47, Q72). Joining sales to returns first multiplies rows and gives wrong totals as well as slow queries.
- Filter early and put cheap filters before correlated subqueries (Q108 filters to large orders first).
- Prefer `NOT EXISTS` to `NOT IN`: it is faster to reason about and it is NULL-safe (Q34, Q211).
- Avoid wrapping an indexed column in a function; use a range instead (`order_date >= ... AND order_date < ...`, as in Q502) or create an expression index.
- Read only the columns you need; use `LIMIT` for top-N.
- Use a materialized view for the one expensive, rarely-changing calculation (`vw_customer_summary`).
- Look at the plan (`EXPLAIN ANALYZE`) before and after; keep the change only if the plan improves.

## Reproduce

```powershell
python scripts/benchmark_indexes.py --runs 11
```
It leaves the final indexes in place. A previous run's file is overwritten; timings will differ slightly on your machine, plan types should match.

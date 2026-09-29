# 09. Data quality

Real data is messy, so the synthetic data is **deliberately messy in known ways**, and SQL finds the problems. Nothing in this project silently "fixes" data:
each issue is detected, counted, and given a documented treatment.

## Two kinds of checks

| Kind | Meaning | Expected result |
|---|---|---|
| **Constraint-backed** | the database already forbids it (CHECK, FOREIGN KEY, NOT NULL) | 0 rows. Running the check proves the rule holds |
| **Real-world** | the schema allows it, as most source systems do | rows found, counted and treated |

## The scorecard (`queries/10_data_quality_checks.sql`, Q301)

30 checks in one result: `check_id`, table, description, severity, `issue_count`, `total_rows`, `issue_pct`, status (`PASS` / `ATTENTION` / `INFO`).
Results on this dataset:

### Constraint-backed (all PASS with 0 rows)

| Check | Rule proved |
|---|---|
| DQ15 | no negative or zero price or cost |
| DQ16 | no zero or negative quantity |
| DQ18 | every order header total equals the sum of its lines |
| DQ19 | no orphan rows (lines without orders, payments without orders, returns without orders, stock without products) |
| DQ20 | no impossible date order (order before customer registered, return before order, PO received before ordered) |
| DQ22 | successful payments equal the order total |
| DQ26 | no customer flagged inactive ordered in the last 90 days |
| DQ30 | no cancelled order moved stock |

### Real-world (found by query)

| Check | Issue | Found | Of | Severity |
|---|---|---:|---:|---|
| DQ01 | duplicate-like customers (same e-mail ignoring case/spaces) | 120 | 9,120 | Medium |
| DQ02 | customers with no e-mail | 305 | 9,120 | Low |
| DQ03 | customers with no phone | 352 | 9,120 | Low |
| DQ04 | invalid e-mail format | 181 | 8,815 | Medium |
| DQ05 | invalid phone number | 164 | 8,768 | Medium |
| DQ06 | implausible date of birth (1900 or in the future) | 7 | 7,756 | Medium |
| DQ07 | inconsistent name capitalisation / trailing spaces | 433 | 9,120 | Low |
| DQ08 | missing city | 96 | 9,120 | Low |
| DQ09 | no customer segment | 104 | 9,120 | Low |
| DQ10 | duplicate-like products (same name ignoring case/space) | 6 | 636 | Medium |
| DQ11 | products without a category | 8 | 636 | High |
| DQ12 | products without a supplier | 12 | 636 | High |
| DQ13 | products without a brand | 18 | 636 | Low |
| DQ14 | category names differing only by capitalisation | 2 | 23 | High |
| DQ17 | unusually large quantity (25+ units on one line) | 7 | 112,512 | Medium |
| DQ21 | completed orders with no payment record | 211 | 54,260 | High |
| DQ23 | stock on hand differs from the ledger | 68 | 5,690 | High |
| DQ25 | inactive products that still hold stock | 30 | 30 | Medium |
| DQ27 | suppliers missing e-mail, phone or GSTIN | 10 | 55 | Medium |

Information-only: DQ24 zero-stock positions (77), DQ28 products never sold (24), DQ29 cancelled orders (2,315).

Drill-down queries: duplicate customer groups (Q302), duplicate products (Q303), NULL profile (Q304), invalid contact samples (Q305), ledger mismatches (Q306), extreme quantities (Q307), orders without payment by store (Q308), case-variant categories (Q309).

## Treatment: what each issue does to the analysis

| Issue | Treatment in this project | Effect |
|---|---|---|
| Case-variant categories | merged in `vw_category_canonical` (smallest id among names equal ignoring case) | all category reports show one 'Footwear' and one 'Home Appliances' |
| Products without category | shown as `(no category)`, never dropped | INR 8.6 lakh of net revenue (0.56 %) sits under this label |
| Products without supplier / brand | shown as `(supplier missing)` / `(brand missing)` | supplier-based revenue excludes them; procurement still records the real supplier on POs |
| Cancelled orders | kept in the data, excluded from every KPI, except the cancellation rate | 2,315 orders (4.09 %) |
| Duplicate-like customers | **not merged**: counted as separate customers, flagged by DQ01 and Q302 | slightly understates repeat behaviour and overstates the customer count; not quantified |
| Invalid e-mail / phone | left as is (not used in any KPI); identified for correction | none on KPIs |
| Implausible birth dates | left as is; age is not used in any analysis | none |
| Completed orders without payment | **kept in revenue** (the order is completed) and flagged | 211 orders, INR 7.9 lakh GST-inclusive = 0.45 % of completed sales |
| Large quantities | kept as valid bulk purchases; flagged | 3 lines in completed orders, INR 47 thousand net revenue |
| Ledger mismatch | analysis uses `quantity_on_hand` (the snapshot); mismatches are listed for investigation | 68 positions, 161 units in total |
| Inactive products with stock | listed; included in inventory value | discontinued items still hold stock |

## Recommended real-world fixes (not applied, to keep the evidence)

1. Add a customer matching process (normalised e-mail + phone) and merge duplicates with an audit trail.
2. Validate e-mail and phone at entry.
3. Make `category_id` and `supplier_id` mandatory on new products.
4. Reconcile the stock ledger to the snapshot nightly and investigate differences.
5. Alert when a completed order has no successful payment after a set time.

## How the checks are tested

`tests/test_sql_queries.py` asserts that all eight constraint-backed checks return 0 and that all thirteen planted problems are found, and that the scorecard counts equal direct SQL counts.
`tests/test_data_integrity.py` (42 tests) proves the business rules that make the data internally consistent (totals, payments, returns, ledger).

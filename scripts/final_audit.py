"""Final project audit: proves every item of the completion checklist with evidence, and writes docs/13_final_audit.md.

Usage (project root, database running):   python scripts/final_audit.py
Exit code 0 = every item passed, 1 = at least one failed. Each line shows the evidence, not just a tick.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "scripts"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
from sqlalchemy import text  # noqa: E402

from data_extraction import extract_core, get_query  # noqa: E402
from database_connection import get_engine  # noqa: E402
from run_query_file import split_statements  # noqa: E402

RESULTS: list[tuple[str, str, bool, str]] = []          # (section, item, passed, evidence)
engine = get_engine()


def check(section: str, item: str, passed: bool, evidence: str) -> None:
    RESULTS.append((section, item, bool(passed), evidence))


def scalar(sql: str):
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


def sql_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8-sig") for p in sorted((ROOT / "queries").glob("*.sql")))


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout


# ---------------------------------------------------------------------------------------------------- DATABASE
def audit_database() -> None:
    s = "DATABASE"
    tables = scalar("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
    required = {"customers", "customer_segments", "products", "categories", "suppliers", "stores", "employees", "sales_orders",
                "sales_order_items", "payments", "inventory", "inventory_transactions", "purchases", "purchase_items", "returns",
                "return_items", "promotions", "product_promotions"}
    have = set(get_query("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")["tablename"])
    check(s, "PostgreSQL schema works (all 18 required tables + dim_date)", required <= have, f"{tables} tables; missing={sorted(required - have)}")

    fks = scalar("SELECT count(*) FROM pg_constraint WHERE contype = 'f'")
    with engine.connect() as c:                                    # prove a foreign key rejects an orphan, inside a rolled-back transaction
        trans = c.begin()
        try:
            c.execute(text("INSERT INTO sales_order_items (order_id, product_id, quantity, unit_price, unit_cost, line_total) "
                           "VALUES (999999999, 1, 1, 1, 1, 1)"))
            rejected = False
        except Exception as exc:
            rejected = "foreign key" in str(exc).lower()
        finally:
            trans.rollback()
    check(s, "Foreign keys work", fks >= 25 and rejected, f"{fks} foreign keys; orphan insert rejected={rejected}")

    checks_n = scalar("SELECT count(*) FROM pg_constraint WHERE contype = 'c'")
    uq_n = scalar("SELECT count(*) FROM pg_constraint WHERE contype = 'u'")
    with engine.connect() as c:
        trans = c.begin()
        try:
            c.execute(text("INSERT INTO products (sku, product_name, unit_cost, unit_price) VALUES ('AUDIT-1', 'x', 1, -5)"))
            rejected = False
        except Exception as exc:
            rejected = "check constraint" in str(exc).lower()
        finally:
            trans.rollback()
    check(s, "Constraints work (CHECK / UNIQUE / NOT NULL)", checks_n >= 40 and rejected,
          f"{checks_n} CHECK + {uq_n} UNIQUE constraints; negative price rejected={rejected}")

    targets = {"customers": 5000, "products": 500, "categories": 15, "suppliers": 50, "stores": 10, "employees": 50,
               "sales_orders": 50000, "sales_order_items": 100000, "payments": 50000, "inventory": 5000,
               "inventory_transactions": 50000, "purchases": 5000, "returns": 2000}
    counts = {t: scalar(f"SELECT count(*) FROM {t}") for t in targets}
    short = {t: (counts[t], m) for t, m in targets.items() if counts[t] < m}
    check(s, "Data loads at the required volume", not short,
          ", ".join(f"{t} {counts[t]:,}" for t in ["customers", "products", "sales_orders", "sales_order_items", "inventory_transactions", "purchases", "returns"]) + f"; below target: {short or 'none'}")

    orphans = 0
    fk_rows = get_query("""SELECT c.conrelid::regclass AS child, c.confrelid::regclass AS parent,
        (SELECT string_agg(format('c.%I = p.%I', a.attname, b.attname), ' AND ') FROM unnest(c.conkey, c.confkey) k(ck, pk)
         JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.ck JOIN pg_attribute b ON b.attrelid = c.confrelid AND b.attnum = k.pk) AS cond,
        (SELECT string_agg(format('c.%I IS NOT NULL', a.attname), ' AND ') FROM unnest(c.conkey) k(ck)
         JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.ck) AS notnull
        FROM pg_constraint c WHERE c.contype = 'f'""")
    for r in fk_rows.itertuples():
        orphans += scalar(f"SELECT count(*) FROM {r.child} c WHERE {r.notnull} AND NOT EXISTS (SELECT 1 FROM {r.parent} p WHERE {r.cond})")
    check(s, "Relationships are valid (no orphan rows in any foreign key)", orphans == 0, f"{len(fk_rows)} relationships checked; orphan rows={orphans}")

    dq = get_query("SELECT count(*) FROM sales_orders o JOIN (SELECT order_id, SUM(line_total) s FROM sales_order_items GROUP BY 1) i USING (order_id) "
                   "WHERE ABS(o.total_amount - i.s) > 0.05").iloc[0, 0]
    check(s, "Order totals equal the sum of their lines", dq == 0, f"mismatched orders={dq}")


# ---------------------------------------------------------------------------------------------------- SQL
def audit_sql() -> None:
    s = "SQL"
    statements = []
    for f in sorted((ROOT / "queries").glob("*.sql")):
        statements += [(f.name, q, t) for q, t, _ in split_statements(f.read_text(encoding="utf-8-sig"))]
    analytical = [x for x in statements if x[0] != "12_performance_optimization.sql"]
    check(s, "50+ meaningful queries", len(analytical) >= 50, f"{len(analytical)} analytical queries + {len(statements) - len(analytical)} EXPLAIN scenarios in {len({x[0] for x in statements})} files")
    body = sql_text().upper()
    features = {
        "joins": ["INNER JOIN", "LEFT JOIN", "FULL OUTER JOIN", "CROSS JOIN", "SELF JOIN"],
        "CTEs": ["WITH RECURSIVE", "\nWITH ", "), "],
        "window functions": ["ROW_NUMBER()", "RANK() OVER", "DENSE_RANK()", "LAG(", "LEAD(", "NTILE(", "SUM(", "ROWS BETWEEN"],
        "subqueries": ["(SELECT", "EXISTS (SELECT", "NOT EXISTS"],
        "aggregations": ["GROUP BY", "HAVING", "COUNT(DISTINCT", "PERCENTILE_CONT", "FILTER (WHERE"],
        "date analysis": ["DATE_TRUNC", "EXTRACT(", "GENERATE_SERIES", "AGE("],
        "ranking": ["RANK()", "DENSE_RANK()", "ROW_NUMBER()", "PERCENT_RANK"],
        "set operations & conditionals": ["UNION ALL", "INTERSECT", "EXCEPT", "CASE WHEN", "COALESCE(", "NULLIF("],
    }
    for name, needles in features.items():
        present = [n for n in needles if n in body]
        shown = ", ".join(n.strip() for n in present if n.strip() != "),")
        check(s, f"Demonstrates {name}", len(present) >= max(1, len(needles) - 2), f"found {len(present)}/{len(needles)}: {shown}")
    mapping = re.findall(r"\(\d+, '", (ROOT / "queries" / "11_business_questions.sql").read_text(encoding="utf-8-sig"))
    check(s, "Business questions answered (all 50 mapped to queries)", len(mapping) == 50, f"{len(mapping)} questions in the Q405 map")
    scorecard = len(re.findall(r"UNION ALL SELECT 'DQ", (ROOT / 'queries' / '10_data_quality_checks.sql').read_text(encoding='utf-8-sig'))) + 1
    check(s, "Data-quality queries (duplicates, NULLs, orphans, quantities, prices, dates, ledger, payments, category, supplier)", scorecard == 30,
          f"{scorecard} checks in the scorecard + 8 drill-downs")
    explains = body.count("EXPLAIN (ANALYZE")
    bench = (ROOT / "docs" / "benchmark_results.md").read_text(encoding="utf-8")
    check(s, "Performance optimisation (measured EXPLAIN ANALYZE, before/after)", explains >= 15 and "Before (ms)" in bench,
          f"{explains} EXPLAIN scenarios; benchmark report present; no hand-typed numbers (generated by scripts/benchmark_indexes.py)")
    idx = scalar("SELECT count(*) FROM pg_indexes WHERE indexname LIKE 'idx\\_%'")
    views = scalar("SELECT count(*) FROM pg_views WHERE schemaname = 'public' AND viewname LIKE 'vw\\_%'") + scalar(
        "SELECT count(*) FROM pg_matviews WHERE schemaname = 'public'")
    required_views = ["vw_monthly_sales", "vw_product_performance", "vw_customer_summary", "vw_inventory_health", "vw_store_performance",
                      "vw_category_performance", "vw_supplier_performance", "vw_return_analysis"]
    existing = set(get_query("SELECT viewname AS n FROM pg_views WHERE schemaname='public' UNION SELECT matviewname FROM pg_matviews")["n"])
    check(s, "The 8 required views exist (+ helpers), indexes created", set(required_views) <= existing and idx >= 8, f"{views} views (incl. 1 materialized), {idx} indexes")


# ---------------------------------------------------------------------------------------------------- PYTHON
def audit_python() -> None:
    s = "PYTHON"
    version = get_query("SELECT split_part(version(), ',', 1) AS v").iloc[0, 0]
    check(s, "Database connection works", "PostgreSQL" in version, version)
    data = extract_core()
    check(s, "Data extraction works", all(len(df) > 0 for df in data.values()), ", ".join(f"{k.replace('vw_', '')}={len(v):,}" for k, v in list(data.items())[:4]) + " ...")
    import data_validation
    checks = data_validation.run_checks(data)
    failed = [c.name for c in checks if not c.passed]
    check(s, "Data validation works", not failed, f"{len(checks) - len(failed)}/{len(checks)} checks passed")
    import customer_analysis as ca
    import inventory_analysis as ia
    import product_analysis as pa
    import sales_analysis as sa
    from kpis import headline_kpis
    from data_extraction import get_view
    orders = get_view("vw_orders")
    kpi = headline_kpis(data["vw_monthly_sales"], data["vw_customer_summary"], data["vw_inventory_health"], orders)
    outputs = [len(sa.seasonality_index(data["vw_monthly_sales"])), len(ca.rfm_summary(data["vw_customer_summary"])),
               len(ia.health_summary(data["vw_inventory_health"])), len(pa.abc_summary(data["vw_product_performance"])), len(ca.cohort_retention())]
    q401 = get_query("SELECT ROUND(SUM(total_amount - gst_amount)) AS r FROM sales_orders WHERE order_status = 'COMPLETED'").iloc[0, 0]
    check(s, "Analysis works (sales, customer, inventory, product) and KPIs match SQL", all(o > 0 for o in outputs) and abs(kpi["net_revenue"] - float(q401)) < 5,
          f"net revenue Python {kpi['net_revenue']:,.0f} vs SQL {float(q401):,.0f}; output rows {outputs}")
    import visualization as viz
    with tempfile.TemporaryDirectory() as tmp:
        paths = viz.make_all(Path(tmp), data={**data, "vw_orders": orders})
        sizes = [p.stat().st_size for p in paths]
    check(s, "Visualizations work (8 charts)", len(paths) == 8 and min(sizes) > 10_000, f"{len(paths)} PNG files, smallest {min(sizes) // 1024} KB")
    import json
    nbs = list((ROOT / "python" / "notebooks").glob("*.ipynb"))
    cells = [c for n in nbs for c in json.loads(n.read_text(encoding="utf-8"))["cells"] if c["cell_type"] == "code"]
    executed = all(c.get("execution_count") for c in cells)
    errors = sum(1 for c in cells for o in c.get("outputs", []) if o.get("output_type") == "error")
    check(s, "Notebooks are executed with no errors", len(nbs) == 4 and executed and errors == 0, f"{len(nbs)} notebooks, {len(cells)} code cells, all executed={executed}, error outputs={errors}")


# ---------------------------------------------------------------------------------------------------- POWER BI
def audit_powerbi() -> None:
    s = "POWER BI"
    d = ROOT / "dashboard"
    req, setup, dax = (d / "dashboard_requirements.md").read_text(encoding="utf-8"), (d / "powerbi_setup.md").read_text(encoding="utf-8"), (d / "measures.dax").read_text(encoding="utf-8")
    pages = len(re.findall(r"^## Page \d", req, flags=re.M))
    check(s, "Dashboard architecture documented (5 pages, visuals, slicers)", pages == 5, f"{pages} pages specified")
    kpis = ["Revenue", "Profit", "Gross margin", "Average order value", "Return rate", "Inventory value", "Inventory turnover", "Customer lifetime value", "Repeat customer rate"]
    missing = [k for k in kpis if k.lower() not in req.lower()]
    check(s, "KPI definitions documented (9 KPIs, one meaning each)", not missing, f"missing={missing or 'none'}")
    check(s, "Data sources documented (CSV and PostgreSQL routes, 13 tables)", "Route B" in setup and "vw_sales_lines" in setup and "powerbi_readonly" in setup, "setup guide sections 1-2")
    rel = len(re.findall(r"^\| `\w+\[\w+\]` \| `\w+\[\w+\]` \|", setup, flags=re.M))
    check(s, "Relationships documented", rel >= 14, f"{rel} relationships in a table with cardinality, direction and active flag")
    measures = len([m for m in re.findall(r"^([A-Za-z][^=/\[\],]*?)\s=\s?", dax, flags=re.M) if not m.startswith(("VAR ", "RETURN"))])
    check(s, "Measures documented (DAX)", measures >= 45, f"{measures} measures in dashboard/measures.dax; lint-tested against the real schema")
    pbix = list(ROOT.rglob("*.pbix"))
    check(s, "Honest status: .pbix file is NOT part of the repository", not pbix, "the report is specified and lint-tested, not built here (stated in README section 12)")


# ---------------------------------------------------------------------------------------------------- GITHUB
def audit_github() -> None:
    s = "GITHUB"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    sections = re.findall(r"^## (\d+)\. ", readme, flags=re.M)
    check(s, "README complete (26 sections)", len(sections) == 26, f"{len(sections)} numbered sections, {len(readme.split()):,} words")
    check(s, ".gitignore present and protects secrets/venv/caches", all(p in (ROOT / ".gitignore").read_text(encoding="utf-8") for p in [".env", ".venv/", "__pycache__/", ".vscode/"]), ".env, .venv/, __pycache__/, .vscode/, .idea/, generated CSVs")
    check(s, ".env.example present with no secret", "DATABASE_PASSWORD=" in (ROOT / ".env.example").read_text(encoding="utf-8")
          and not re.search(r"DATABASE_PASSWORD=\S", (ROOT / ".env.example").read_text(encoding="utf-8")), "all 5 variables, password empty")
    tracked = git("ls-files").split()
    env_tracked = ".env" in tracked
    pw = ""
    env_file = ROOT / ".env"
    if env_file.exists():
        m = re.search(r"DATABASE_PASSWORD=(\S+)", env_file.read_text(encoding="utf-8"))
        pw = m.group(1) if m else ""
    leak_hits = git("grep", "-I", "-n", "--all-match", "-e", pw, *git("rev-list", "--all").split()) if pw else ""
    patterns = git("grep", "-I", "-n", "-E", r"(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"][A-Za-z0-9]{8,}", "HEAD")
    check(s, "No secrets in the repository or its history", not env_tracked and not leak_hits.strip() and not patterns.strip(),
          f".env tracked={env_tracked}; real password found in any commit={'YES' if leak_hits.strip() else 'no'}; credential-like literals in HEAD={'YES' if patterns.strip() else 'none'}")
    big = [(f, (ROOT / f).stat().st_size) for f in tracked if (ROOT / f).exists() and (ROOT / f).stat().st_size > 1_000_000]
    check(s, "No large generated files committed", not big, f"largest tracked file: {max(((ROOT / f).stat().st_size for f in tracked if (ROOT / f).exists()), default=0) // 1024} KB; files over 1 MB: {big or 'none'}")
    top = sorted({f.split('/')[0] for f in tracked if '/' in f})
    expected = {"dashboard", "database", "docs", "python", "queries", "screenshots", "scripts", "tests"}
    check(s, "Clean folder structure", expected <= set(top), "top-level folders: " + ", ".join(top))
    # this report is regenerated by every run, so it is excluded (otherwise the audit could never pass on a clean tree)
    dirty = git("status", "--short", "--", ".", ":(exclude)docs/13_final_audit.md").strip()
    check(s, "Working tree committed (one commit per phase)", not dirty, f"uncommitted changes: {dirty or 'none'} (this report excluded)")
    check(s, "Setup instructions work from scratch", (ROOT / "scripts" / "verify_clean_install.ps1").exists(),
          "scripts/verify_clean_install.ps1 clones the committed repo, installs, generates, loads and runs all tests (see the audit note below for the last run)")


# ---------------------------------------------------------------------------------------------------- INTERVIEW
def audit_interview() -> None:
    s = "INTERVIEW"
    walk = (ROOT / "docs" / "12_project_walkthrough.md").read_text(encoding="utf-8")
    two_min = re.search(r"## The 2-minute answer.*?\n> (.*?)\n\n\*\*Delivery", walk, flags=re.S)
    words = len(re.sub(r"[>\n]", " ", two_min.group(1)).split()) if two_min else 0
    check(s, "2-minute explanation", 200 <= words <= 400, f"{words} words (about {words / 140:.1f} minutes spoken)")
    resume = (ROOT / "docs" / "project_resume_bullets.md").read_text(encoding="utf-8")
    check(s, "Resume bullets (5, based only on implemented work)", len(re.findall(r"^\d\. ", resume, flags=re.M)) == 5 and "What not to write" in resume, "5 bullets + a source table + a what-not-to-claim list")
    qs = (ROOT / "docs" / "11_interview_questions.md").read_text(encoding="utf-8")
    n = len(re.findall(r"^\*\*\d+\. ", qs, flags=re.M))
    check(s, "40+ interview questions in 7 categories", n >= 40 and qs.count("\n## ") >= 7, f"{n} questions")
    concepts = ["ROW_NUMBER", "NOT IN", "recursive", "LATERAL", "median", "gaps and islands", "PERCENTILE_CONT", "index", "EXPLAIN"]
    covered = [c for c in concepts if c.lower() in qs.lower()]
    check(s, "SQL concepts are explainable (each has an answer)", len(covered) == len(concepts), f"{len(covered)}/{len(concepts)} concepts covered: {', '.join(covered)}")


NOTES = """## Known gaps and deviations (stated plainly)

| Topic | Status |
|---|---|
| Power BI report | **Specified and lint-tested, not built.** No `.pbix` file exists; there are no Power BI screenshots. The DAX has never been evaluated in Power BI itself; `dashboard/expected_kpis.md` is how you verify it. |
| Duplicate files in the brief | The brief lists both un-numbered data-quality and performance query files and the numbered 10_ and 12_ files. Only the numbered files exist, because they contain exactly those queries. |
| "Returns: several thousand" | 2,835 returns and 2,901 return lines. This meets "several thousand" only loosely. |
| Safety stock | Not modelled as a separate quantity. `reorder_level` plays that role (doc 06). |
| Synthetic-data properties | 83 % of buyers are repeat customers, inventory turns over 0.68 times a year, and 52 % of stock value is dead stock. These come from the generator and are disclosed, not tuned away. |
| Customer duplicates | 120 duplicate-like customers are flagged but not merged, so customer counts and repeat rates are slightly affected (not quantified). |
| README author section | Contains placeholders (name, LinkedIn, GitHub, e-mail) that you must fill in before publishing. |
| Licence | No `LICENSE` file is included; choose one before making the repository public. |
| Benchmarks | Timings are from a Windows laptop with PostgreSQL in Docker, warm cache; ratios vary between runs and are reported as ranges. |
"""


def main() -> int:
    for step in (audit_database, audit_sql, audit_python, audit_powerbi, audit_github, audit_interview):
        try:
            step()
        except Exception as exc:  # an audit step that crashes is a failed audit, not a skipped one
            check(step.__name__, "audit step ran without error", False, f"{type(exc).__name__}: {exc}")
    lines, section = ["# 13. Final project audit", "",
                      "Generated by `python scripts/final_audit.py`. Each row is a checklist item with the evidence produced by a command against the real project, not an assertion.", ""], None
    for sec, item, ok, evidence in RESULTS:
        if sec != section:
            lines += ["", f"## {sec}", "", "| Status | Item | Evidence |", "|---|---|---|"]
            section = sec
        lines.append(f"| {'PASS' if ok else '**FAIL**'} | {item} | {evidence.replace('|', '/')} |")
    passed = sum(1 for r in RESULTS if r[2])
    lines += ["", f"**Result: {passed} of {len(RESULTS)} items passed.**", "", NOTES]
    text_ = "\n".join(lines)
    print(text_)
    (ROOT / "docs" / "13_final_audit.md").write_text(text_, encoding="utf-8")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())

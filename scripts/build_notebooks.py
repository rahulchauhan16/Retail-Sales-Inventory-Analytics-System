"""Generate and execute the Jupyter notebooks in python/notebooks/.

Usage (project root):
    python scripts/build_notebooks.py            # build + execute (needs the database running)
    python scripts/build_notebooks.py --no-run   # build only

The notebooks are deliberately thin: they call the tested modules in python/ and explain the results. All logic lives in
the modules, so the notebook, the scripts and the tests always agree.
"""
import argparse
from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

OUT = Path(__file__).resolve().parents[1] / "python" / "notebooks"

SETUP = """import sys
sys.path.insert(0, "..")            # make the modules in python/ importable from this folder
import pandas as pd
import matplotlib.pyplot as plt
import visualization as viz
from data_extraction import get_view
pd.set_option("display.width", 160, "display.max_columns", 20, "display.float_format", "{:,.1f}".format)
%matplotlib inline"""

NOTEBOOKS = {
    "01_extraction_and_validation": [
        ("md", "# 1. Connecting, extracting and validating\n\n**Goal:** load the analytical views from PostgreSQL and prove the data is trustworthy before analysing it.\n\n"
               "**Why this order?** Real analysts never start with charts. They first check that the numbers reconcile.\n\n"
               "*What to learn:* SQLAlchemy connection from environment variables (`.env`), reading a view with `pandas.read_sql`, and "
               "checking one number through two independent routes."),
        ("code", SETUP),
        ("md", "## Connection\nCredentials come from environment variables (see `.env.example`); nothing is hard-coded."),
        ("code", "from database_connection import run_query\nrun_query('SELECT version() AS postgres_version')"),
        ("md", "## What views are available?"),
        ("code", "from data_extraction import VIEWS\npd.DataFrame({'view': list(VIEWS), 'contents': list(VIEWS.values())})"),
        ("md", "## Load the core views and look at their shape"),
        ("code", "from data_extraction import extract_core\ndata = extract_core()\npd.DataFrame({v: {'rows': len(df), 'columns': df.shape[1]} for v, df in data.items()}).T"),
        ("md", "## Validation checks\n`data_validation.run_checks` reconciles revenue, profit, units, orders and inventory value **across views and against the base tables**."),
        ("code", "import data_validation\nchecks = data_validation.run_checks(data)\nreport = data_validation.report(checks)\nprint(f\"{(report.status == 'PASS').sum()} of {len(report)} checks passed\")\nreport"),
        ("md", "## Null and dtype profile of the customer view\nMissing values here are expected: customers who never bought have no order dates or RFM scores."),
        ("code", "c = data['vw_customer_summary']\npd.DataFrame({'dtype': c.dtypes.astype(str), 'nulls': c.isna().sum(), 'null_%': (100 * c.isna().mean()).round(1)})"),
        ("md", "## Headline KPIs\nDefined once in `kpis.py` and tested against the SQL query `Q401`."),
        ("code", "from kpis import headline_kpis\norders = get_view('vw_orders')\nkpis = headline_kpis(data['vw_monthly_sales'], data['vw_customer_summary'], data['vw_inventory_health'], orders)\npd.Series(kpis, name='value').to_frame()"),
    ],
    "02_sales_and_product_analysis": [
        ("md", "# 2. Sales and product analysis\n\n**Business questions:** how is revenue trending, when does it peak, which categories and products carry the business, "
               "and where is it concentrated?\n\nEvery number is read from the SQL views. Statements below are **facts or calculated metrics**; "
               "interpretation is kept separate."),
        ("code", SETUP),
        ("code", "import sales_analysis as sa, product_analysis as pa\nfrom kpis import growth_table, yearly_summary\nmonthly = get_view('vw_monthly_sales')\ncats = get_view('vw_category_performance')\nproducts = get_view('vw_product_performance')\norders = get_view('vw_orders')"),
        ("md", "## Revenue by year\n*Calculated metric:* net revenue excludes GST; growth is year over year."),
        ("code", "yearly_summary(monthly)"),
        ("md", "## Monthly trend, growth and moving average"),
        ("code", "growth_table(monthly).tail(12)"),
        ("code", "viz.monthly_revenue_trend(monthly); plt.show()"),
        ("md", "## Seasonality\nEach calendar month relative to its own year's average (100 = a typical month). Dividing by the yearly average removes the growth trend."),
        ("code", "sa.seasonality_index(monthly)"),
        ("md", "## Channel mix"),
        ("code", "sa.channel_mix(monthly)"),
        ("md", "## Categories\n*Observation to check:* Footwear shows a very large jump in 2025. The next cell shows what drives it."),
        ("code", "viz.category_revenue(cats); plt.show()\npa.category_trends(cats)"),
        ("code", "# Which products drive the Footwear increase? (a product launched in March 2025 explains most of it)\nfrom data_extraction import get_query\nf = get_query(\"\"\"SELECT product_name, order_year, SUM(net_revenue) AS revenue FROM vw_sales_lines JOIN products USING (product_id)\n                  WHERE category_name = 'Footwear' GROUP BY 1, 2\"\"\").pivot_table(index='product_name', columns='order_year', values='revenue').fillna(0)\nf['change_2025_vs_2024'] = f[2025] - f[2024]\nf.sort_values('change_2025_vs_2024', ascending=False).head(5)"),
        ("md", "## Products: top sellers, Pareto and concentration"),
        ("code", "viz.top_products(products); plt.show()\npa.abc_summary(products)"),
        ("code", "pa.concentration(products)"),
        ("md", "## High-return products\nFlagged only when a product has a meaningful volume **and** returns at 2.5x or more of its category rate. A flag is a prompt to investigate, not a conclusion."),
        ("code", "pa.high_return_products(products)"),
        ("md", "## Order-value distribution"),
        ("code", "viz.order_value_distribution(orders); plt.show()\nsa.order_value_distribution(orders)"),
    ],
    "03_customer_analysis": [
        ("md", "# 3. Customer analysis\n\n**Business questions:** who are the most valuable customers, how many come back, and which groups are drifting away?\n\n"
               "*Note:* RFM segment names are **analytical labels** built from project-defined thresholds (see `docs/07_customer_analytics.md`), not facts about the people."),
        ("code", SETUP),
        ("code", "import customer_analysis as ca\ncustomers = get_view('vw_customer_summary')"),
        ("md", "## Repeat customers"),
        ("code", "ca.repeat_rate(customers)"),
        ("md", "## Commercial segments and lifetime value (to date)"),
        ("code", "ca.segment_summary(customers)"),
        ("md", "## RFM segments\nRecency = days since last order, Frequency = number of orders, Monetary = net revenue."),
        ("code", "viz.customer_segments(customers); plt.show()\nca.rfm_summary(customers)"),
        ("md", "## Activity status"),
        ("code", "ca.activity_status(customers)"),
        ("md", "## Purchase frequency and revenue concentration"),
        ("code", "ca.frequency_bands(customers)"),
        ("code", "ca.concentration(customers)"),
        ("md", "## Cohort retention\nOf the customers who first bought in a month, the percentage who buy again 1-6 months later."),
        ("code", "import seaborn as sns\nret = ca.cohort_retention()\nfig, ax = plt.subplots(figsize=(9, 7))\nsns.heatmap(ret.set_index('cohort')[[1, 2, 3, 4, 5, 6]], annot=True, fmt='.0f', cmap='Blues', cbar_kws={'label': '% of cohort active'}, ax=ax)\nax.set_yticklabels([d.strftime('%Y-%m') for d in ret['cohort']], rotation=0)\nax.set_xlabel('Months after first purchase'); ax.set_ylabel('First-purchase month')\nplt.show()"),
        ("md", "## Top customers"),
        ("code", "ca.top_customers(customers)"),
    ],
    "04_inventory_and_returns_analysis": [
        ("md", "# 4. Inventory and returns analysis\n\n**Business questions:** which stock is short, which is surplus, and how much money is tied up? Which categories and reasons drive returns?\n\n"
               "*Health classes are project assumptions* (documented in `docs/06_inventory_metrics.md`): OUT_OF_STOCK, DEAD_STOCK (no sale at the store in 365 days), "
               "LOW_STOCK (at or below reorder level), OVERSTOCKED (above max level or more than 180 days of cover), HEALTHY."),
        ("code", SETUP),
        ("code", "import inventory_analysis as ia, product_analysis as pa\ninv = get_view('vw_inventory_health')\nproducts = get_view('vw_product_performance')\ncats = get_view('vw_category_performance')\nreturns = get_view('vw_return_analysis')"),
        ("md", "## Stock health"),
        ("code", "viz.inventory_health(inv); plt.show()\nia.health_summary(inv)"),
        ("md", "## Store risk: stock-out risk versus surplus capital"),
        ("code", "ia.store_risk(inv)"),
        ("md", "## Stock aging and cover"),
        ("code", "ia.aging(inv)"),
        ("code", "ia.coverage_bands(inv)"),
        ("md", "## Turnover by category\nSimplified: cost of goods sold in the last 12 months divided by current inventory value (ending-inventory approximation)."),
        ("code", "ia.turnover_by_category(products)"),
        ("md", "## Product classes: revenue versus stock"),
        ("code", "ia.product_classes(products)"),
        ("md", "## Replenishment list\nPositions that sold in the last 90 days and are at or below reorder level. Suggested quantity subtracts stock already on open purchase orders."),
        ("code", "ia.replenishment_list(inv, 15)"),
        ("md", "## Returns\n*Recorded* reasons only: the data shows what was recorded at the counter, not why the customer really returned the item."),
        ("code", "viz.return_rate_by_category(cats); plt.show()\npa.return_reasons(returns)"),
    ],
}


def build() -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, cells in NOTEBOOKS.items():
        nb = new_notebook(metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})
        nb.cells = [new_markdown_cell(src) if kind == "md" else new_code_cell(src) for kind, src in cells]
        path = OUT / f"{name}.ipynb"
        nbformat.write(nb, path)
        paths.append(path)
    return paths


def execute(paths: list[Path]) -> None:
    from nbclient import NotebookClient
    for path in paths:
        nb = nbformat.read(path, as_version=4)
        NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(path.parent)}}).execute()
        nbformat.write(nb, path)
        print("executed", path.name)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-run", action="store_true")
    written = build()
    if not ap.parse_args().no_run:
        execute(written)
    print(f"{len(written)} notebooks in {OUT}")

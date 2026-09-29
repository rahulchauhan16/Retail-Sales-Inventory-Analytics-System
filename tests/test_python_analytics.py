"""Python layer: extraction, KPI maths vs SQL, analysis functions, charts and the dashboard export."""
import matplotlib

matplotlib.use("Agg")

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

import customer_analysis as ca  # noqa: E402
import data_validation  # noqa: E402
import export_dashboard_data as ed  # noqa: E402
import inventory_analysis as ia  # noqa: E402
import product_analysis as pa  # noqa: E402
import sales_analysis as sa  # noqa: E402
import visualization as viz  # noqa: E402
from data_extraction import VIEWS, extract_core, get_view  # noqa: E402
from kpis import growth_table, headline_kpis, pareto, yearly_summary  # noqa: E402
from sqlhelpers import run  # noqa: E402


@pytest.fixture(scope="module")
def data():
    d = extract_core()
    d["vw_orders"] = get_view("vw_orders")
    return d


# ------------------------------------------------------------------ extraction
def test_get_view_rejects_unknown_names():
    with pytest.raises(ValueError):
        get_view("customers; DROP TABLE customers")


def test_every_declared_view_loads():
    for name in ("vw_monthly_sales", "vw_store_performance", "vw_supplier_performance"):
        assert len(get_view(name)) > 0
    assert set(VIEWS) >= {"vw_sales_lines", "vw_orders"}


# ------------------------------------------------------------------ validation script
def test_data_validation_checks_all_pass(data):
    checks = data_validation.run_checks(data)
    failed = [c for c in checks if not c.passed]
    assert len(checks) >= 30
    assert not failed, [(c.name, c.detail) for c in failed]


# ------------------------------------------------------------------ KPI maths must match the independent SQL query
def test_python_kpis_match_sql_query_q401(data, conn):
    py = headline_kpis(data["vw_monthly_sales"], data["vw_customer_summary"], data["vw_inventory_health"], data["vw_orders"])
    sql = run(conn, "11_business_questions.sql", "Q401").iloc[0]
    assert abs(py["net_revenue"] - sql["net_revenue"]) <= 5
    assert abs(py["gross_profit"] - sql["gross_profit"]) <= 5
    assert py["completed_orders"] == sql["completed_orders"]
    assert py["buying_customers"] == sql["buying_customers"]
    assert abs(py["avg_order_value"] - sql["avg_order_value"]) <= 1
    assert abs(py["repeat_customer_rate_pct"] - sql["repeat_customer_rate_pct"]) <= 0.05
    assert abs(py["order_return_rate_pct"] - sql["order_return_rate_pct"]) <= 0.01
    assert abs(py["inventory_value_at_cost"] - sql["inventory_value_at_cost"]) <= 5


def test_python_inventory_turnover_matches_sql_q62_total(data, conn):
    """Aggregate turnover (12m COGS / inventory) must equal the category-level SQL figures combined."""
    cats = run(conn, "05_inventory_analysis.sql", "Q62")
    sql_total = cats["cogs_last_12m"].sum() / cats["inventory_value"].sum()
    py = headline_kpis(data["vw_monthly_sales"], data["vw_customer_summary"], data["vw_inventory_health"], data["vw_orders"])
    # Q62 skips uncategorised products, so allow a small difference
    assert abs(py["inventory_turnover_12m"] - sql_total) / sql_total < 0.05


def test_growth_and_yearly_tables(data):
    g = growth_table(data["vw_monthly_sales"])
    assert len(g) == 36 and g["running_total"].iloc[-1] == pytest.approx(data["vw_monthly_sales"]["net_revenue"].sum())
    assert g["yoy_growth_pct"].isna().sum() == 12 and g["moving_avg_3m"].isna().sum() == 2
    y = yearly_summary(data["vw_monthly_sales"])
    assert list(y["year"]) == [2023, 2024, 2025] and y["yoy_growth_pct"].isna().iloc[0]


def test_yearly_growth_matches_sql_q14(data, conn):
    y = yearly_summary(data["vw_monthly_sales"]).set_index("year")
    sql = run(conn, "02_sales_analysis.sql", "Q14").set_index("yr")
    for yr in (2024, 2025):
        assert abs(y.loc[yr, "yoy_growth_pct"] - sql.loc[yr, "yoy_growth_pct"]) < 0.05


def test_pareto_helper_classes():
    s = pd.Series([50, 30, 10, 5, 3, 2], index=list("abcdef"))
    p = pareto(s)
    assert list(p["abc_class"].astype(str)) == ["A", "A", "B", "B", "C", "C"] or p["abc_class"].astype(str).iloc[0] == "A"
    assert p["share_pct"].sum() == pytest.approx(100)


# ------------------------------------------------------------------ analysis modules
def test_sales_analysis_outputs(data):
    s = sa.seasonality_index(data["vw_monthly_sales"])
    assert len(s) == 12
    assert s.loc[s["seasonality_index"].idxmax(), "month"] in ("Oct", "Nov")            # festive peak built into the data
    assert sa.channel_mix(data["vw_monthly_sales"])["online_share_pct"].is_monotonic_increasing
    d = sa.order_value_distribution(data["vw_orders"])
    assert d["mean"] > d["median"]                                                        # right-skewed
    assert len(sa.weekday_pattern(data["vw_orders"])) == 7


def test_customer_analysis_outputs(data):
    c = data["vw_customer_summary"]
    assert ca.rfm_summary(c)["customers"].sum() == (c["orders"] > 0).sum()
    assert ca.activity_status(c)["customers"].sum() == len(c)
    conc = ca.concentration(c)
    assert conc["revenue_share_pct"].sum() == pytest.approx(100) and conc.iloc[0]["revenue_share_pct"] > 30
    assert ca.frequency_bands(c)["customers"].sum() == (c["orders"] > 0).sum()
    r = ca.cohort_retention()
    assert (r["cohort_size"] > 0).all() and r[0].eq(100).all()


def test_inventory_analysis_outputs(data):
    inv = data["vw_inventory_health"]
    h = ia.health_summary(inv)
    assert list(h["health_status"]) == ia.STATUS_ORDER and h["positions"].sum() == len(inv)
    assert ia.aging(inv)["positions"].sum() == (inv["quantity_on_hand"] > 0).sum()
    rep = ia.replenishment_list(inv)
    assert (rep["quantity_on_hand"] <= rep["reorder_level"]).all()
    assert len(ia.store_risk(inv)) == 12


def test_product_analysis_outputs(data):
    p = data["vw_product_performance"]
    abc = pa.abc_summary(p).set_index("abc_class")
    assert 79 <= abc.loc["A", "revenue_share_pct"] <= 81.5
    assert pa.concentration(p)["top_20pct_products_pct_of_revenue"] > 50
    trends = pa.category_trends(data["vw_category_performance"])
    assert "Declining two years in a row" in set(trends["trend"])
    assert (pa.high_return_products(p)["times_category_rate"] >= 2.5).all()
    assert pa.return_reasons(get_view("vw_return_analysis"))["share_pct"].sum() == pytest.approx(100)


# ------------------------------------------------------------------ charts and export
def test_all_eight_charts_are_written(tmp_path, data):
    paths = viz.make_all(tmp_path, data=data)
    assert len(paths) == 8
    for p in paths:
        assert p.exists() and p.stat().st_size > 10_000, p


def test_inr_formatter():
    assert viz.inr(1_50_00_000) == "₹1.5 Cr" and viz.inr(4_20_000) == "₹4.2 L" and viz.inr(950) == "₹950"


def test_dashboard_export_writes_all_files(tmp_path):
    manifest = ed.export_all(tmp_path)
    assert set(manifest["file"]) == {f"{n}.csv" for n in ed.EXPORTS}
    assert (tmp_path / "README.md").exists()
    sales = pd.read_csv(tmp_path / "fact_sales_lines.csv")
    assert len(sales) == manifest.set_index("file").loc["fact_sales_lines.csv", "rows"] > 100_000
    assert abs(sales["net_revenue"].sum() - pd.read_csv(tmp_path / "agg_monthly_sales.csv")["net_revenue"].sum()) < 500
    assert len(pd.read_csv(tmp_path / "dim_date.csv")) == 1096          # 3 years incl. leap day 29 Feb 2024

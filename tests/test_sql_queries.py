"""Phase 9 - SQL validation.

1. Every statement in queries/*.sql executes without error and returns rows.
2. Headline numbers computed by independent routes (query files vs views vs base tables) must agree.
3. The data-quality scorecard behaves as designed: constraint-backed checks pass, planted problems are found.
"""
import pytest
from sqlalchemy import text

from sqlhelpers import QUERY_DIR, all_statements, run, run_sql

STATEMENTS = all_statements()
EMPTY_IS_OK = {"Q209"}          # 'employees hired before their manager' - correctly returns 0 rows on this data


def test_there_are_at_least_fifty_queries():
    analytical = [s for s in STATEMENTS if not s[0].startswith("Q5")]      # exclude the EXPLAIN workload
    assert len(analytical) >= 50
    assert len({(f, q) for f, q, _, _ in STATEMENTS}) == len(STATEMENTS), "duplicate query ids inside a file"


@pytest.mark.parametrize("filename,qid,title,sql", STATEMENTS, ids=[f"{s[0][:2]}-{s[1]}" for s in STATEMENTS])
def test_query_executes_and_returns_rows(conn, filename, qid, title, sql):
    df = run_sql(conn, sql)
    if qid not in EMPTY_IS_OK:
        assert len(df) > 0, f"{filename} {qid} '{title}' returned no rows"


def test_query_files_use_required_sql_features():
    """The project promises specific SQL skills - make sure each is really demonstrated somewhere."""
    text_all = "\n".join(p.read_text(encoding="utf-8-sig").upper() for p in QUERY_DIR.glob("*.sql"))
    for feature in ["JOIN", "LEFT JOIN", "FULL OUTER JOIN", "UNION ALL", "INTERSECT",
                    "EXCEPT", "CASE WHEN", "COALESCE(", "NULLIF(", "WITH RECURSIVE", "RANK() OVER", "DENSE_RANK()", "ROW_NUMBER()",
                    "LAG(", "LEAD(", "SUM(", "AVG(", "NTILE(", "PERCENTILE_CONT", "EXISTS", "NOT EXISTS", "LATERAL", "HAVING",
                    "DATE_TRUNC", "GENERATE_SERIES", "FILTER (WHERE", "ROWS BETWEEN", "EXPLAIN (ANALYZE"]:
        assert feature in text_all, f"feature '{feature}' is not demonstrated in queries/"
    assert "SELF JOIN" in text_all


# ------------------------------------------------------------------ cross-checks between independent routes
def test_executive_kpis_match_the_views(conn):
    kpi = run(conn, "11_business_questions.sql", "Q401").iloc[0]
    v = run_sql(conn, """SELECT (SELECT SUM(net_revenue) FROM vw_monthly_sales) AS rev,
                                (SELECT SUM(gross_profit) FROM vw_monthly_sales) AS profit,
                                (SELECT SUM(orders) FROM vw_monthly_sales) AS orders,
                                (SELECT count(*) FROM vw_customer_summary WHERE orders > 0) AS buyers,
                                (SELECT SUM(inventory_value) FROM vw_inventory_health) AS inv""").iloc[0]
    assert abs(kpi["net_revenue"] - v["rev"]) <= 5
    assert abs(kpi["gross_profit"] - v["profit"]) <= 5
    assert kpi["completed_orders"] == v["orders"]
    assert kpi["buying_customers"] == v["buyers"]
    assert abs(kpi["inventory_value_at_cost"] - v["inv"]) <= 5


def test_basic_revenue_queries_agree(conn):
    q03 = run(conn, "01_basic_analysis.sql", "Q03").iloc[0]
    yearly = run(conn, "02_sales_analysis.sql", "Q14")
    monthly = run(conn, "02_sales_analysis.sql", "Q13")
    channel = run(conn, "01_basic_analysis.sql", "Q07")
    assert abs(yearly["net_revenue"].sum() - q03["net_revenue"]) <= 3
    assert abs(monthly["net_revenue"].sum() - q03["net_revenue"]) <= 1
    assert abs(channel["net_revenue"].sum() - q03["net_revenue"]) <= 1
    assert abs(q03["gross_sales_incl_gst"] - q03["gst_collected"] - q03["net_revenue"]) <= 1


def test_running_total_ends_at_total_revenue(conn):
    running = run(conn, "02_sales_analysis.sql", "Q22")
    total = run(conn, "01_basic_analysis.sql", "Q03").iloc[0]["net_revenue"]
    assert abs(running["running_total"].iloc[-1] - total) <= 40           # each month is rounded to whole rupees


def test_share_columns_add_up_to_100(conn):
    assert abs(run(conn, "02_sales_analysis.sql", "Q18")["revenue_share_pct"].sum() - 100) < 0.2
    assert abs(run(conn, "01_basic_analysis.sql", "Q07")["revenue_share_pct"].sum() - 100) < 0.1
    assert abs(run(conn, "03_customer_analysis.sql", "Q37")["revenue_share_pct"].sum() - 100) < 0.2
    assert abs(run(conn, "03_customer_analysis.sql", "Q46")["revenue_share_pct"].sum() - 100) < 0.2
    assert abs(run(conn, "04_product_analysis.sql", "Q52")["share_of_revenue_pct"].sum() - 100) < 0.2


def test_pareto_class_a_holds_about_eighty_percent(conn):
    df = run(conn, "04_product_analysis.sql", "Q52").set_index("abc_class")
    assert 79.5 <= df.loc["A", "share_of_revenue_pct"] <= 80.5
    assert list(df.index) == ["A", "B", "C"]


def test_rfm_segments_cover_all_buyers_and_match_the_view(conn):
    seg = run(conn, "03_customer_analysis.sql", "Q40").set_index("rfm_segment")["customers"]
    buyers = run_sql(conn, "SELECT count(*) AS n FROM vw_customer_summary WHERE orders > 0").iloc[0]["n"]
    assert seg.sum() == buyers
    view = run_sql(conn, "SELECT rfm_segment, count(*) AS n FROM vw_customer_summary WHERE rfm_segment IS NOT NULL GROUP BY 1").set_index("rfm_segment")["n"]
    assert (seg.sort_index() == view.sort_index()).all()


def test_inventory_health_query_matches_view(conn):
    q = run(conn, "05_inventory_analysis.sql", "Q60").set_index("status")["store_product_positions"]
    v = run_sql(conn, "SELECT health_status, count(*) AS n FROM vw_inventory_health GROUP BY 1").set_index("health_status")["n"]
    assert (q.sort_index() == v.sort_index()).all()
    assert q.sum() == run_sql(conn, "SELECT count(*) AS n FROM inventory").iloc[0]["n"]


def test_store_scorecard_query_matches_view(conn):
    q = run(conn, "06_store_analysis.sql", "Q72").set_index("store_name")["net_revenue"]
    v = run_sql(conn, "SELECT store_name, net_revenue FROM vw_store_performance").set_index("store_name")["net_revenue"]
    assert ((q - v.reindex(q.index)).abs() <= 1).all()


def test_return_rate_definitions_are_ordered_sensibly(conn):
    r = run(conn, "08_return_analysis.sql", "Q89").iloc[0]
    assert 0 < r["value_return_rate_pct"] < r["order_return_rate_pct"] < 25
    assert r["orders_with_returns"] <= r["completed_orders"]


def test_customer_no_purchase_three_methods_agree(conn):
    r = run(conn, "03_customer_analysis.sql", "Q34").iloc[0]
    assert r["via_left_join"] == r["via_not_exists"] == r["via_not_in"]
    assert r["via_left_join"] > 0


def test_not_in_trap_is_demonstrated(conn):
    r = run(conn, "advanced_sql_interview.sql", "Q211").iloc[0]
    assert r["not_in_result"] == 0 and r["not_exists_result"] > 0


def test_question_map_lists_all_fifty_and_points_to_real_queries(conn):
    import re
    mapping = run(conn, "11_business_questions.sql", "Q405")
    assert list(mapping["question_no"]) == list(range(1, 51))
    existing = {q for _, q, _, _ in STATEMENTS}
    for ids in mapping["query_ids"]:
        for token in re.findall(r"Q\d+", ids):
            assert token in existing, f"question map refers to missing query {token}"


# ------------------------------------------------------------------ data-quality scorecard behaves as designed
CONSTRAINT_BACKED = {"DQ15", "DQ16", "DQ18", "DQ19", "DQ20", "DQ22", "DQ26", "DQ30"}
PLANTED = {"DQ01", "DQ02", "DQ04", "DQ05", "DQ06", "DQ10", "DQ11", "DQ12", "DQ14", "DQ17", "DQ21", "DQ23", "DQ27"}


def test_dq_scorecard_constraint_backed_checks_pass(conn):
    sc = run(conn, "10_data_quality_checks.sql", "Q301").set_index("check_id")
    assert len(sc) == 30
    for cid in CONSTRAINT_BACKED:
        assert sc.loc[cid, "issue_count"] == 0, f"{cid} {sc.loc[cid, 'check_name']}"
        assert sc.loc[cid, "status"] == "PASS"


def test_dq_scorecard_finds_the_planted_problems(conn):
    sc = run(conn, "10_data_quality_checks.sql", "Q301").set_index("check_id")
    for cid in PLANTED:
        assert sc.loc[cid, "issue_count"] > 0, f"{cid} {sc.loc[cid, 'check_name']} found nothing"
        assert sc.loc[cid, "status"] == "ATTENTION"


def test_dq_scorecard_counts_match_direct_sql(conn):
    sc = run(conn, "10_data_quality_checks.sql", "Q301").set_index("check_id")
    direct = conn.execute(text("SELECT count(*) FROM products WHERE category_id IS NULL")).scalar()
    assert sc.loc["DQ11", "issue_count"] == direct
    direct = conn.execute(text("SELECT count(*) FROM sales_orders o WHERE order_status='COMPLETED' "
                               "AND NOT EXISTS (SELECT 1 FROM payments p WHERE p.order_id=o.order_id)")).scalar()
    assert sc.loc["DQ21", "issue_count"] == direct
    mismatch = run(conn, "10_data_quality_checks.sql", "Q306")
    assert (mismatch["difference"] != 0).all() and sc.loc["DQ23", "issue_count"] >= len(mismatch)

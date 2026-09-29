"""Power BI cannot be run here, so these tests lint everything that defines the dashboard against the real data model.

* every  table[column]  used in dashboard/measures.dax exists in the exported schema
* every  [Measure]  referenced anywhere is defined
* every measure named in the docs and in expected_kpis.md exists
* the theme JSON is valid and uses the validated palette
"""
import json
import re
from pathlib import Path

import pytest

from export_dashboard_data import EXPORTS
from sqlhelpers import run_sql

DASH = Path(__file__).resolve().parents[1] / "dashboard"
DAX = (DASH / "measures.dax").read_text(encoding="utf-8")

# tables that exist in the Power BI model but not in the export
EXTRA_TABLES = {"dim_channel": {"channel"}}


@pytest.fixture(scope="module")
def schema(engine):
    """{table name: set of column names}, read from the database for every export."""
    out = dict(EXTRA_TABLES)
    with engine.connect() as conn:
        for name, (sql, _) in EXPORTS.items():
            out[name] = set(run_sql(conn, f"SELECT * FROM ({sql}) t LIMIT 0").columns)
    return out


def measure_definitions(text: str) -> dict[str, str]:
    """Measure name -> DAX body. A definition starts at column 0 with 'Name =' (comments start with //)."""
    blocks = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z][^=/\[\],]*?)\s=\s?(.*)$", line)          # a name never contains [ ] or a comma
        if m and not line.startswith(("//", " ", "VAR ", "RETURN")):
            current = m.group(1).strip()
            blocks[current] = m.group(2)
        elif current and not line.startswith("//"):
            blocks[current] += "\n" + line
    return blocks


MEASURES = measure_definitions(DAX)


def test_measure_file_has_enough_measures():
    assert len(MEASURES) >= 45
    for required in ["Net Revenue", "Gross Profit", "Gross Margin %", "Average Order Value", "Order Return Rate", "Inventory Value",
                     "Inventory Turnover", "Repeat Customer Rate", "Avg Customer Lifetime Revenue", "Net Revenue YoY %",
                     "Net Revenue 3M Avg", "Net Revenue Running Total", "New Customers", "Stock-out Risk %"]:
        assert required in MEASURES, required


def test_every_table_column_reference_exists(schema):
    refs = set(re.findall(r"\b(\w+)\[(\w+)\]", DAX))
    assert refs
    missing = [(t, c) for t, c in refs if t not in schema or c not in schema[t]]
    assert not missing, f"unknown table[column] in measures.dax: {missing}"


def test_every_measure_reference_is_defined():
    for name, body in MEASURES.items():
        body = re.sub(r"//.*", "", body)
        for ref in re.findall(r"(?<![\w\]])\[([^\[\]]+)\]", body):
            assert ref in MEASURES, f"measure '{name}' references undefined [{ref}]"


def test_parentheses_are_balanced_in_every_measure():
    for name, body in MEASURES.items():
        body = re.sub(r"//.*", "", body)
        body = re.sub(r'"[^"]*"', "", body)
        assert body.count("(") == body.count(")"), f"unbalanced parentheses in '{name}'"
        assert body.count("{") == body.count("}"), f"unbalanced braces in '{name}'"


def test_relationship_columns_documented_exist(schema):
    """Every  table[column]  written in the setup guide's relationship table must exist."""
    text = (DASH / "powerbi_setup.md").read_text(encoding="utf-8")
    section = text.split("## 3. Data model")[1].split("## 4. Measures")[0]
    for table, column in set(re.findall(r"`(\w+)\[(\w+)\]`", section)):
        assert table in schema and column in schema[table], f"{table}[{column}] in relationship table does not exist"


def test_measures_named_in_docs_exist():
    names = {n for n in MEASURES}
    for doc in ("dashboard_requirements.md", "powerbi_setup.md"):
        text = (DASH / doc).read_text(encoding="utf-8")
        for ref in re.findall(r"`\[([^\]`]+)\]`", text):
            assert ref in names, f"{doc} mentions measure [{ref}] which is not in measures.dax"


def test_expected_kpis_only_lists_real_measures():
    text = (DASH / "expected_kpis.md").read_text(encoding="utf-8")
    normalise = lambda s: re.sub(r"\s%$", "", s.strip())              # noqa: E731  ('Gross Margin %' <-> measure 'Gross Margin %')
    known = {normalise(n) for n in MEASURES}
    rows = re.findall(r"^\| ([^|]+?) \| [-\d,.blank ]+", text, flags=re.M)
    names = [normalise(r) for r in rows if r not in ("Measure", "---")]
    assert len(names) > 40
    unknown = [n for n in names if n not in known]
    assert not unknown, f"expected_kpis.md lists measures that are not defined: {unknown}"


def test_setup_guide_mentions_every_export_file():
    text = (DASH / "powerbi_setup.md").read_text(encoding="utf-8")
    for name in EXPORTS:
        assert f"`{name}`" in text, f"{name} is not described in powerbi_setup.md"


def test_theme_is_valid_json_with_the_validated_palette():
    theme = json.loads((DASH / "retail_theme.json").read_text(encoding="utf-8"))
    assert theme["dataColors"] == ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
    assert theme["good"] == "#0ca30c" and theme["bad"] == "#d03b3b"
    assert theme["background"] == "#fcfcfb"


def test_expected_kpis_match_current_database(schema):
    """The committed expected values must still equal what the database produces (catches stale docs)."""
    from expected_kpis import all_data
    live = all_data()
    text = (DASH / "expected_kpis.md").read_text(encoding="utf-8")
    for key in ("Net Revenue", "Gross Profit", "Completed Orders", "Inventory Value", "Total Customers"):
        shown = re.search(rf"^\| {re.escape(key)} \| ([\d,.]+) \|", text, flags=re.M).group(1).replace(",", "")
        assert abs(float(shown) - live[key]) <= 1, f"{key}: doc {shown} vs database {live[key]:,.0f}"

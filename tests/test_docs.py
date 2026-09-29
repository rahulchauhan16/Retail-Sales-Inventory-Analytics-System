"""Documentation must stay true: the data dictionary matches the database, links and cited files exist,
every cited query id exists, and the row counts quoted in the overview equal the database."""
import re
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from sqlhelpers import all_statements

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
DOCS = sorted((ROOT / "docs").glob("*.md")) + sorted((ROOT / "dashboard").glob("*.md")) + [ROOT / "database" / "erd.md"]
README = ROOT / "README.md"
DOCS.append(README)
EXPECTED_DOCS = [f"{n}.md" for n in [
    "01_project_overview", "02_business_requirements", "03_database_design", "04_data_dictionary", "05_sql_analysis",
    "06_inventory_metrics", "07_customer_analytics", "08_powerbi_dashboard", "09_data_quality", "10_performance_optimization",
    "11_interview_questions", "12_project_walkthrough", "project_resume_bullets"]]


def test_all_required_documents_exist_and_are_substantial():
    for name in EXPECTED_DOCS:
        path = ROOT / "docs" / name
        assert path.exists(), name
        assert len(path.read_text(encoding="utf-8").split()) > 300, f"{name} looks too short"


def test_data_dictionary_is_in_sync_with_the_database():
    from build_data_dictionary import build
    generated, missing = build()
    assert not missing, f"columns without a description: {missing}"
    assert (ROOT / "docs" / "04_data_dictionary.md").read_text(encoding="utf-8") == generated, \
        "docs/04_data_dictionary.md is stale: run python scripts/build_data_dictionary.py"


def test_every_table_in_the_database_is_documented(conn):
    tables = set(conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).scalars())
    dictionary = (ROOT / "docs" / "04_data_dictionary.md").read_text(encoding="utf-8")
    for table in tables:
        assert f"## {table}\n" in dictionary, f"{table} is missing from the data dictionary"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_relative_markdown_links_resolve(doc):
    text_ = doc.read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)\s]+)\)", text_):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = (doc.parent / target.split("#")[0]).resolve()
        assert path.exists(), f"{doc.name}: broken link -> {target}"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_cited_repository_files_exist(doc):
    pattern = r"`((?:queries|scripts|python|database|dashboard|docs|tests)/[\w./-]+\.(?:sql|py|md|json|dax|yml|ipynb|png))`"
    for cited in re.findall(pattern, doc.read_text(encoding="utf-8")):
        assert (ROOT / cited).exists(), f"{doc.name} cites a file that does not exist: {cited}"


def test_every_query_id_cited_in_docs_exists():
    known = {q for _, q, _, _ in all_statements()}
    for doc in DOCS:
        for qid in set(re.findall(r"\bQ\d{2,3}\b", doc.read_text(encoding="utf-8"))):
            assert qid in known, f"{doc.name} cites {qid}, which is not a query in queries/"


def test_row_counts_quoted_in_the_overview_match_the_database(conn):
    overview = (ROOT / "docs" / "01_project_overview.md").read_text(encoding="utf-8")
    pairs = re.findall(r"\| ([a-z_]+) \| ([\d,]+) \|", overview)
    assert len(pairs) >= 15
    for table, quoted in pairs:
        actual = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
        assert actual == int(quoted.replace(",", "")), f"{table}: doc says {quoted}, database has {actual:,}"


def test_interview_document_has_enough_questions_in_every_category():
    doc = (ROOT / "docs" / "11_interview_questions.md").read_text(encoding="utf-8")
    assert len(re.findall(r"^\*\*\d+\. ", doc, flags=re.M)) >= 40
    for section in ["SQL questions", "Database questions", "Data analyst questions", "Power BI questions", "Python questions",
                    "Business questions", "Project questions"]:
        assert f"## {section}" in doc, section


def test_resume_bullets_are_five_and_carry_the_honesty_notes():
    doc = (ROOT / "docs" / "project_resume_bullets.md").read_text(encoding="utf-8")
    assert len(re.findall(r"^\d\. ", doc, flags=re.M)) == 5
    assert "What not to write" in doc and "specified" in doc


def test_no_credentials_or_secrets_in_documents():
    for doc in DOCS:
        body = doc.read_text(encoding="utf-8")
        assert not re.search(r"DATABASE_PASSWORD=\S+", body), doc.name
        assert not re.search(r"(?i)password\s*[:=]\s*['\"]?[A-Za-z0-9]{12,}", body), doc.name


# ------------------------------------------------------------------ README
README_SECTIONS = ["Project overview", "Business problem", "Project objectives", "Key features", "Technology stack", "Architecture",
                   "Database schema", "Data model", "Dataset", "SQL analysis", "Python analysis", "Power BI dashboard", "Key KPIs",
                   "Business questions answered", "Data quality checks", "SQL optimization", "Project structure", "Installation",
                   "PostgreSQL setup", "Running the project", "Power BI setup", "Screenshots", "Example insights",
                   "Interview talking points", "Future improvements", "Author"]


def test_readme_has_all_26_sections_in_order():
    body = README.read_text(encoding="utf-8")
    headings = re.findall(r"^## (\d+)\. (.+)$", body, flags=re.M)
    assert [int(n) for n, _ in headings] == list(range(1, 27))
    assert [h.lower() for _, h in headings] == [s.lower() for s in README_SECTIONS]


def test_every_script_used_in_the_readme_commands_exists():
    body = README.read_text(encoding="utf-8")
    blocks = "\n".join(re.findall(r"```(?:powershell|sql)?\n(.*?)```", body, flags=re.S))
    referenced = set(re.findall(r"\b((?:scripts|python|queries|database)/[\w./-]+\.(?:py|sql|ps1))\b", blocks))
    assert len(referenced) >= 10
    for path in referenced:
        assert (ROOT / path).exists(), f"README command uses a file that does not exist: {path}"


def test_readme_setup_commands_cover_the_full_workflow():
    body = README.read_text(encoding="utf-8")
    for command in ["python -m venv .venv", "pip install -r requirements.txt", "docker compose up -d --wait",
                    "python scripts/generate_data.py", "python scripts/load_data.py", "python -m pytest tests -q"]:
        assert command in body, command


def test_readme_says_the_data_is_synthetic_and_powerbi_is_specified():
    body = README.read_text(encoding="utf-8").lower()
    assert "synthetic" in body and "specified" in body and "not in the repository" in body


def test_project_structure_lists_every_top_level_folder():
    body = README.read_text(encoding="utf-8")
    for folder in ["database/", "queries/", "python/", "scripts/", "dashboard/", "docs/", "tests/", "screenshots/"]:
        assert folder in body and (ROOT / folder).is_dir(), folder


def test_env_example_has_no_secret_and_gitignore_protects_env():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"DATABASE_PASSWORD=\s*$", example, flags=re.M)
    for key in ["DATABASE_HOST", "DATABASE_PORT", "DATABASE_NAME", "DATABASE_USER", "DATABASE_PASSWORD"]:
        assert key in example
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in [".env", ".venv/", "__pycache__/", ".vscode/", ".idea/"]:
        assert pattern in ignore, pattern
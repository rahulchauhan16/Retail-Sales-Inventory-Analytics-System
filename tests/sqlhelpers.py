"""Helpers for running the statements of a queries/*.sql file inside tests."""
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_query_file import split_statements  # noqa: E402

QUERY_DIR = ROOT / "queries"


def statements(filename):
    """Return [(query_id, title, sql_without_comments)] for one query file."""
    out = []
    for qid, title, sql in split_statements((QUERY_DIR / filename).read_text(encoding="utf-8-sig")):
        body = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--")).strip().rstrip(";")
        out.append((qid, title, body))
    return out


def all_statements():
    return [(f.name, qid, title, sql) for f in sorted(QUERY_DIR.glob("*.sql")) for qid, title, sql in statements(f.name)]


def run(conn, filename, qid):
    """Execute one statement of a query file and return its result as a DataFrame."""
    for q, _, sql in statements(filename):
        if q == qid:
            return pd.read_sql(sql, conn)
    raise KeyError(f"{qid} not found in {filename}")


def run_sql(conn, sql):
    return pd.read_sql(sql, conn)

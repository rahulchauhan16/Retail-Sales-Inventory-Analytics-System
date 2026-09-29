"""Execute every query in a .sql file separately and report rows / time / errors.

Convention used by the files in queries/: each query starts with a header comment
    -- Q07 | Title
and ends with a line finishing in ';'. Comment lines never end with ';'.

Usage (project root):
    python scripts/run_query_file.py queries/01_basic_analysis.sql
    python scripts/run_query_file.py queries/02_sales_analysis.sql --show 3      # preview 3 rows each
    python scripts/run_query_file.py queries/02_sales_analysis.sql --only Q14 --show 20
"""
import argparse
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from database_connection import get_engine  # noqa: E402

HEADER = re.compile(r"^--\s*(Q\d+)\s*\|\s*(.+)$")


def split_statements(text: str):
    """Yield (query_id, title, sql) for each statement in the file."""
    buf, qid, title = [], None, None
    for line in text.splitlines():
        m = HEADER.match(line.strip())
        if m and not any(l.strip() and not l.strip().startswith("--") for l in buf):
            qid, title = m.group(1), m.group(2)
        buf.append(line)
        if line.rstrip().endswith(";") and not line.strip().startswith("--"):
            sql = "\n".join(buf).strip()
            yield (qid or "-", title or "(untitled)", sql)
            buf, qid, title = [], None, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--show", type=int, default=0, help="print first N rows of each result")
    ap.add_argument("--only", help="run a single query id, e.g. Q14")
    ap.add_argument("--timeout-ms", type=int, default=60000)
    args = ap.parse_args()

    stmts = list(split_statements(Path(args.file).read_text(encoding="utf-8-sig")))
    engine = get_engine()
    failures = 0
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    for qid, title, sql in stmts:
        if args.only and qid != args.only:
            continue
        start = time.time()
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql(f"SET statement_timeout = {args.timeout_ms}")
                # comments are dropped: a '%' inside one would be misread as a driver placeholder
                body = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
                df = pd.read_sql(body.rstrip(";"), conn)
                conn.rollback()
            print(f"OK   {qid:<5}{len(df):>7} rows {time.time() - start:6.2f}s  {title}")
            if args.show:
                print(df.head(args.show).to_string(index=False), end="\n\n")
        except Exception as exc:  # report and keep going
            failures += 1
            print(f"FAIL {qid:<5} {title}\n     {str(exc).splitlines()[0][:300]}")
    print(f"\n{len(stmts)} statements, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

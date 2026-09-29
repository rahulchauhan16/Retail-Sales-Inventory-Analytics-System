"""Run one or more .sql files against the project database.

Usage (from project root):
    python scripts/run_sql.py database/schema.sql
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from database_connection import run_sql_file  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for file in sys.argv[1:]:
        run_sql_file(file)
        print(f"OK: {file}")

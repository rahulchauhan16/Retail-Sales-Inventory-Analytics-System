"""Create the schema, bulk-load data/generated/*.csv with COPY, then run database/seed_data.sql.

Usage (project root):
    python scripts/load_data.py            # rebuild everything (drops and recreates tables)

Tables are loaded parents-first so every foreign key is satisfied. The whole load is
one transaction: either everything loads or nothing does.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from database_connection import get_engine  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "generated"

# Parents before children (foreign-key order)
LOAD_ORDER = [
    "customer_segments", "categories", "suppliers", "stores", "employees", "customers", "products",
    "promotions", "product_promotions", "sales_orders", "sales_order_items", "payments", "returns",
    "return_items", "inventory", "inventory_transactions", "purchases", "purchase_items",
]


def main() -> None:
    missing = [t for t in LOAD_ORDER if not (DATA_DIR / f"{t}.csv").exists()]
    if missing:
        sys.exit(f"Missing CSVs {missing}. Run: python scripts/generate_data.py")

    engine = get_engine()
    raw = engine.raw_connection()
    started = time.time()
    try:
        with raw.cursor() as cur:
            print("Creating schema ...")
            cur.execute((ROOT / "database" / "schema.sql").read_text(encoding="utf-8"))
            for table in LOAD_ORDER:
                path = DATA_DIR / f"{table}.csv"
                with open(path, "r", encoding="utf-8") as fh:
                    columns = fh.readline().strip()
                    fh.seek(0)
                    cur.copy_expert(f"COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv, HEADER true)", fh)
                cur.execute(f"SELECT count(*) FROM {table}")
                print(f"  {table:<24}{cur.fetchone()[0]:>9,} rows")
            print("Running seed_data.sql (calendar + sequence sync) ...")
            cur.execute((ROOT / "database" / "seed_data.sql").read_text(encoding="utf-8"))
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()

    # ANALYZE cannot run inside a transaction block; it refreshes planner statistics.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql("ANALYZE")
    print(f"Done in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()

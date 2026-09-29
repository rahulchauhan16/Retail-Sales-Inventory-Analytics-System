"""PostgreSQL connection helpers. Credentials are read from environment variables / .env."""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine import URL

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def get_engine() -> Engine:
    """Build a SQLAlchemy engine from DATABASE_* environment variables."""
    password = os.getenv("DATABASE_PASSWORD")
    if not password:
        raise RuntimeError("DATABASE_PASSWORD is not set. Copy .env.example to .env and fill it in.")
    url = URL.create(
        "postgresql+psycopg2",
        username=os.getenv("DATABASE_USER", "retail_user"),
        password=password,
        host=os.getenv("DATABASE_HOST", "localhost"),
        port=int(os.getenv("DATABASE_PORT", "5432")),
        database=os.getenv("DATABASE_NAME", "retail_analytics"),
    )
    return create_engine(url)


def run_query(sql: str, engine: Engine | None = None, params: dict | None = None) -> pd.DataFrame:
    """Run a SELECT and return a DataFrame."""
    engine = engine or get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def run_sql_file(path: str | Path, engine: Engine | None = None) -> None:
    """Execute a multi-statement .sql file (no psql meta-commands) in one transaction."""
    engine = engine or get_engine()
    sql = Path(path).read_text(encoding="utf-8")
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute(sql)
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


if __name__ == "__main__":
    print(run_query("SELECT version() AS postgres_version").iloc[0, 0])

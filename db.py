"""Database access for both backends: SQLite by default, PostgreSQL when DATABASE_URL is set.

SQL elsewhere is written once with `?` placeholders; this module translates for PostgreSQL.
"""
import os
import sqlite3
from pathlib import Path

BASE = Path(__file__).parent
DATA_DIR = Path(os.environ.get("RADIOCALICO_DATA_DIR", BASE / "data"))
DB_PATH = DATA_DIR / "radiocalico.db"
DATABASE_URL = os.environ.get("DATABASE_URL")
BACKEND = "postgres" if DATABASE_URL else "sqlite"

if BACKEND == "postgres":
    import psycopg
    from psycopg.rows import dict_row

    IntegrityError = psycopg.IntegrityError
else:
    IntegrityError = sqlite3.IntegrityError


class Connection:
    """Context manager: commits on success, rolls back on error, always closes."""

    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, params=()):
        if BACKEND == "postgres":
            sql = sql.replace("?", "%s")
        return self.raw.execute(sql, params)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type:
            self.raw.rollback()
        else:
            self.raw.commit()
        self.raw.close()


def connect():
    if BACKEND == "postgres":
        return Connection(psycopg.connect(DATABASE_URL, row_factory=dict_row))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(DB_PATH)
    raw.row_factory = sqlite3.Row
    raw.execute("pragma foreign_keys = on")
    return Connection(raw)


def init_db():
    with connect() as conn:
        if BACKEND == "postgres":
            # Serialize concurrent starts (e.g. several replicas) around the DDL.
            conn.execute("select pg_advisory_xact_lock(4242)")
            conn.execute((BASE / "schema_postgres.sql").read_text())
        else:
            conn.raw.executescript((BASE / "schema.sql").read_text())
            cols = {r[1] for r in conn.execute("pragma table_info(tracks)")}
            for col, typ in (("album", "text"), ("duration", "real")):
                if col not in cols:
                    conn.execute(f"alter table tracks add column {col} {typ}")

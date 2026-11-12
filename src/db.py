"""SQLite helpers: connection factory, schema bootstrap, small utilities."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from . import config


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    """Canonical stored timestamp: naive UTC ISO-8601 down to the second."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 8000")
    return conn


@contextmanager
def get_conn(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def connection(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Transaction scope for code that receives an existing connection."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db(db_path: Path | str | None = None) -> None:
    sql = Path(config.SCHEMA_PATH).read_text(encoding="utf-8")
    with get_conn(db_path) as conn:
        conn.executescript(sql)


def tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


# Fully-literal statements: the table name selects a constant string, it is never
# interpolated into SQL, so no dynamic query construction exists in this module.
COUNT_STATEMENTS = {
    "users": "SELECT COUNT(*) AS n FROM users",
    "sessions": "SELECT COUNT(*) AS n FROM sessions",
    "datasets": "SELECT COUNT(*) AS n FROM datasets",
    "series": "SELECT COUNT(*) AS n FROM series",
    "points": "SELECT COUNT(*) AS n FROM points",
}


def count(conn: sqlite3.Connection, table: str) -> int:
    statement = COUNT_STATEMENTS.get(table)
    if statement is None:
        raise ValueError(f"unknown table {table!r}")
    row = conn.execute(statement).fetchone()
    return int(row["n"])

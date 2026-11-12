import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import auth, db, seed  # noqa: E402

FIXED_ANCHOR = datetime(2025, 12, 1, 0, 0, 0)


@pytest.fixture(scope="session")
def seeded_db(tmp_path_factory):
    """One fully seeded database shared by the read-only tests."""
    path = tmp_path_factory.mktemp("metricscope") / "seeded.db"
    db.init_db(path)
    with db.get_conn(path) as conn:
        seed.seed_if_empty(conn, anchor=FIXED_ANCHOR)
    return path


@pytest.fixture()
def fresh_db(tmp_path):
    """Empty schema for tests that write their own rows."""
    path = tmp_path / "fresh.db"
    db.init_db(path)
    return path


@pytest.fixture()
def demo_user_id(fresh_db):
    with db.get_conn(fresh_db) as conn:
        user_id = auth.create_user(conn, "cenius", "cenius@cenius.ai", "cenius")
        conn.commit()
        return user_id


@pytest.fixture(scope="session")
def seeded_user_id(seeded_db):
    with db.get_conn(seeded_db) as conn:
        return int(
            conn.execute("SELECT id FROM users WHERE username = ?", ("cenius",)).fetchone()["id"]
        )

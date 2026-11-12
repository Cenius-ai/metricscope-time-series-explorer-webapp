import pytest

from src import db, seed
from src.api import auth as auth_api


def test_wrong_password_is_rejected_without_creating_a_session(seeded_db):
    with db.get_conn(seeded_db) as conn:
        before = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]

    with pytest.raises(ValueError) as excinfo:
        auth_api.login("cenius", "wrong-password", db_path=seeded_db)
    assert str(excinfo.value) == auth_api.INVALID_CREDENTIALS

    with db.get_conn(seeded_db) as conn:
        after = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
    assert after == before


def test_unknown_user_uses_the_same_message(seeded_db):
    with pytest.raises(ValueError) as excinfo:
        auth_api.login("nobody-here", "cenius", db_path=seeded_db)
    assert str(excinfo.value) == auth_api.INVALID_CREDENTIALS


def test_login_session_logout_round_trip(seeded_db):
    result = auth_api.login("cenius", "cenius", db_path=seeded_db)
    token = result["token"]
    assert result["user"]["username"] == "cenius"
    assert len(token) >= 32

    assert auth_api.session(token, db_path=seeded_db)["username"] == "cenius"

    auth_api.logout(token, db_path=seeded_db)
    with pytest.raises(auth_api.Unauthorized):
        auth_api.session(token, db_path=seeded_db)
    with db.get_conn(seeded_db) as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM sessions WHERE token = ?", (token,)).fetchone()["n"] == 0


def test_email_identifier_also_authenticates(seeded_db):
    result = auth_api.login("cenius@cenius.ai", "cenius", db_path=seeded_db)
    assert result["user"]["email"] == "cenius@cenius.ai"


def test_expired_session_is_rejected_and_purged(seeded_db):
    result = auth_api.login("cenius", "cenius", db_path=seeded_db)
    token = result["token"]
    with db.get_conn(seeded_db) as conn:
        conn.execute(
            "UPDATE sessions SET expires_at = ? WHERE token = ?",
            ("2000-01-01 00:00:00", token),
        )
        conn.commit()
    with pytest.raises(auth_api.Unauthorized):
        auth_api.session(token, db_path=seeded_db)
    with db.get_conn(seeded_db) as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM sessions WHERE token = ?", (token,)).fetchone()["n"] == 0


def test_password_hash_is_pbkdf2_and_never_plaintext(seeded_db):
    with db.get_conn(seeded_db) as conn:
        row = conn.execute("SELECT password_hash, salt FROM users WHERE username = 'cenius'").fetchone()
    assert row["password_hash"] != "cenius"
    assert len(row["password_hash"]) == 64
    assert len(row["salt"]) == 32


def test_second_demo_account_from_seed_plan(seeded_db):
    result = auth_api.login("demo", "demo1234", db_path=seeded_db)
    assert result["user"]["username"] == "demo"


def test_seed_is_idempotent(seeded_db):
    with db.get_conn(seeded_db) as conn:
        before = {t: db.count(conn, t) for t in ("users", "datasets", "series", "points")}
        seed.seed_if_empty(conn)
        after = {t: db.count(conn, t) for t in ("users", "datasets", "series", "points")}
    assert before == after
    assert after["datasets"] == 3
    assert after["users"] >= 2

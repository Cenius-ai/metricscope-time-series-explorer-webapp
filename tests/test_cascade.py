from src import db
from src.api import datasets as datasets_api
from src.api import upload


def _csv(rows: int = 12) -> bytes:
    lines = ["timestamp,requests,errors"]
    for index in range(rows):
        lines.append(f"2026-04-{1 + index // 24:02d} {index % 24:02d}:00:00,{100 + index},{index % 3}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_delete_cascades_series_and_points(fresh_db, demo_user_id):
    created = upload.create(demo_user_id, "cascade.csv", _csv(), db_path=fresh_db)
    dataset_id = created["dataset_id"]

    with db.get_conn(fresh_db) as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM series WHERE dataset_id = ?", (dataset_id,)).fetchone()["n"] == 2
        assert conn.execute("SELECT COUNT(*) AS n FROM points WHERE dataset_id = ?", (dataset_id,)).fetchone()["n"] == 24

    result = datasets_api.delete(dataset_id, db_path=fresh_db)
    assert result["ok"] is True
    assert result["remaining_points"] == 0

    with db.get_conn(fresh_db) as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM datasets").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM series").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM points").fetchone()["n"] == 0


def test_delete_missing_dataset_raises(fresh_db):
    import pytest

    with pytest.raises(datasets_api.DatasetNotFound):
        datasets_api.delete(9999, db_path=fresh_db)


def test_library_rows_expose_counts(fresh_db, demo_user_id):
    upload.create(demo_user_id, "library.csv", _csv(), db_path=fresh_db)
    rows = datasets_api.list_datasets(db_path=fresh_db)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "Library"
    assert row["source_filename"] == "library.csv"
    assert row["row_count"] == 12
    assert row["dropped_row_count"] == 0
    assert row["is_seed"] is False
    assert row["series_count"] == 2
    assert row["created_at"]


def test_preview_returns_first_twenty_rows_and_skipped_count(fresh_db, demo_user_id):
    upload.create(demo_user_id, "preview.csv", _csv(rows=30), db_path=fresh_db)
    dataset_id = datasets_api.list_datasets(db_path=fresh_db)[0]["id"]
    preview = datasets_api.preview(dataset_id, db_path=fresh_db)
    assert len(preview["frame"]) == 20
    assert preview["dropped_row_count"] == 0
    assert "requests" in preview["frame"].columns


def test_foreign_keys_enforced(fresh_db):
    import sqlite3

    with db.get_conn(fresh_db) as conn:
        try:
            conn.execute(
                "INSERT INTO series (dataset_id, name) VALUES (424242, 'orphan')"
            )
        except sqlite3.IntegrityError:
            pass
        else:  # pragma: no cover
            raise AssertionError("foreign key constraint was not enforced")

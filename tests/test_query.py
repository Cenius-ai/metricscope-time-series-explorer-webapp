import pytest

from src import db, seed
from src.api import query as query_api


def _dataset_id(seeded_db, seed_key: str) -> int:
    with db.get_conn(seeded_db) as conn:
        return int(
            conn.execute("SELECT id FROM datasets WHERE seed_key = ?", (seed_key,)).fetchone()["id"]
        )


def test_series_list_returns_four_series(seeded_db):
    dataset_id = _dataset_id(seeded_db, "seed-api-latency")
    series = query_api.series_list(dataset_id, db_path=seeded_db)
    assert [s["name"] for s in series] == [
        "p50_latency_ms",
        "p95_latency_ms",
        "p99_latency_ms",
        "error_rate_pct",
    ]
    assert all(s["point_count"] == seed.WINDOW_DAYS * 24 for s in series)
    assert series[0]["unit"] == "ms"


def test_resample_and_rolling_window(seeded_db):
    dataset_id = _dataset_id(seeded_db, "seed-web-traffic")
    series = query_api.series_list(dataset_id, db_path=seeded_db)
    bounds = query_api.dataset_range(dataset_id, db_path=seeded_db)
    result = query_api.query(
        dataset_id,
        [series[0]["id"]],
        bounds[0],
        bounds[1],
        resample="6h",
        aggregation="mean",
        rolling_window=3,
        db_path=seeded_db,
    )
    frame = result["frames"][series[0]["name"]]
    assert len(frame) == seed.WINDOW_DAYS * 4
    assert frame["rolling"].isna().sum() == 2
    assert frame["rolling"].iloc[2:].notna().all()


def test_raw_resample_keeps_hourly_points(seeded_db):
    dataset_id = _dataset_id(seeded_db, "seed-cpu-fleet")
    series = query_api.series_list(dataset_id, db_path=seeded_db)
    bounds = query_api.dataset_range(dataset_id, db_path=seeded_db)
    result = query_api.query(
        dataset_id, [series[0]["id"]], bounds[0], bounds[1], db_path=seeded_db
    )
    assert len(result["frames"][series[0]["name"]]) == seed.WINDOW_DAYS * 24


def test_multiple_series_return_multiple_frames(seeded_db):
    dataset_id = _dataset_id(seeded_db, "seed-web-traffic")
    series = query_api.series_list(dataset_id, db_path=seeded_db)
    bounds = query_api.dataset_range(dataset_id, db_path=seeded_db)
    result = query_api.query(
        dataset_id,
        [series[0]["id"], series[1]["id"]],
        bounds[0],
        bounds[1],
        resample="1d",
        aggregation="max",
        db_path=seeded_db,
    )
    assert set(result["frames"]) == {series[0]["name"], series[1]["name"]}


def test_inverted_range_is_rejected(seeded_db):
    dataset_id = _dataset_id(seeded_db, "seed-web-traffic")
    series = query_api.series_list(dataset_id, db_path=seeded_db)
    bounds = query_api.dataset_range(dataset_id, db_path=seeded_db)
    with pytest.raises(query_api.QueryError):
        query_api.query(dataset_id, [series[0]["id"]], bounds[1], bounds[0], db_path=seeded_db)


def test_unknown_resample_interval_is_rejected(seeded_db):
    dataset_id = _dataset_id(seeded_db, "seed-web-traffic")
    series = query_api.series_list(dataset_id, db_path=seeded_db)
    bounds = query_api.dataset_range(dataset_id, db_path=seeded_db)
    with pytest.raises(query_api.QueryError):
        query_api.query(
            dataset_id, [series[0]["id"]], bounds[0], bounds[1], resample="7m", db_path=seeded_db
        )

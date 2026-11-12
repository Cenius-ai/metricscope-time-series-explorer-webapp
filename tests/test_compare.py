from datetime import timedelta

import pytest

from src import db
from src.api import compare as compare_api
from src.api import query as query_api


def _context(seeded_db, seed_key: str = "seed-api-latency"):
    with db.get_conn(seeded_db) as conn:
        dataset_id = int(
            conn.execute("SELECT id FROM datasets WHERE seed_key = ?", (seed_key,)).fetchone()["id"]
        )
    series = query_api.series_list(dataset_id, db_path=seeded_db)
    bounds = query_api.dataset_range(dataset_id, db_path=seeded_db)
    return dataset_id, series, bounds


def test_two_series_produce_two_summary_rows(seeded_db):
    dataset_id, series, bounds = _context(seeded_db)
    a_start, a_end, b_start, b_end = compare_api.preset_windows(bounds[1], 7)
    result = compare_api.periods(
        dataset_id,
        [series[0]["id"], series[1]["id"]],
        a_start,
        a_end,
        b_start,
        b_end,
        db_path=seeded_db,
    )
    assert [row["series"] for row in result["summary"]] == [series[0]["name"], series[1]["name"]]
    for row in result["summary"]:
        assert row["count_a"] > 0 and row["count_b"] > 0
        assert row["delta"] == pytest.approx(row["mean_b"] - row["mean_a"])
        assert row["pct_change"] == pytest.approx((row["mean_b"] - row["mean_a"]) / row["mean_a"] * 100)
    frame = result["frames"][series[0]["name"]]
    assert {"elapsed_hours", "period_a", "period_b"} <= set(frame.columns)
    assert frame["elapsed_hours"].min() == 0


def test_overlay_starts_at_hour_zero_for_both_periods(seeded_db):
    dataset_id, series, bounds = _context(seeded_db)
    a_start, a_end, b_start, b_end = compare_api.preset_windows(bounds[1], 14)
    result = compare_api.periods(
        dataset_id, [series[0]["id"]], a_start, a_end, b_start, b_end, db_path=seeded_db
    )
    frame = result["frames"][series[0]["name"]]
    assert frame["elapsed_hours"].iloc[0] == 0
    assert frame["period_a"].notna().sum() > 0
    assert frame["period_b"].notna().sum() > 0


def test_inverted_period_is_rejected(seeded_db):
    dataset_id, series, bounds = _context(seeded_db)
    a_start, a_end, b_start, b_end = compare_api.preset_windows(bounds[1], 7)
    with pytest.raises(compare_api.CompareError):
        compare_api.periods(
            dataset_id, [series[0]["id"]], a_end, a_start, b_start, b_end, db_path=seeded_db
        )


def test_overlapping_periods_are_rejected(seeded_db):
    dataset_id, series, bounds = _context(seeded_db)
    a_start, a_end, _b_start, _b_end = compare_api.preset_windows(bounds[1], 7)
    with pytest.raises(compare_api.CompareError):
        compare_api.periods(
            dataset_id,
            [series[0]["id"]],
            a_start,
            a_end,
            a_start + timedelta(days=1),
            a_end,
            db_path=seeded_db,
        )


def test_empty_selection_is_rejected(seeded_db):
    dataset_id, _series, bounds = _context(seeded_db)
    a_start, a_end, b_start, b_end = compare_api.preset_windows(bounds[1], 7)
    with pytest.raises(compare_api.CompareError):
        compare_api.periods(dataset_id, [], a_start, a_end, b_start, b_end, db_path=seeded_db)


def test_preset_windows_do_not_overlap():
    from datetime import datetime

    anchor = datetime(2026, 3, 31, 23, 0)
    a_start, a_end, b_start, b_end = compare_api.preset_windows(anchor, 7)
    assert a_end == anchor.date()
    assert (a_end - a_start).days == 6
    assert b_end == a_start - timedelta(days=1)
    assert (b_end - b_start).days == 6
    assert not (a_start <= b_end)

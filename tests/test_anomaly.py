from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src import anomaly, db, seed
from tests.conftest import FIXED_ANCHOR


def _series(seeded_db, seed_key: str, series_name: str):
    with db.get_conn(seeded_db) as conn:
        rows = conn.execute(
            "SELECT p.ts, p.value FROM points p JOIN series s ON s.id = p.series_id"
            " JOIN datasets d ON d.id = s.dataset_id"
            " WHERE d.seed_key = ? AND s.name = ? ORDER BY p.ts",
            (seed_key, series_name),
        ).fetchall()
    return [row["ts"] for row in rows], pd.Series([row["value"] for row in rows])


def test_documented_spike_is_flagged_at_default_threshold(seeded_db):
    stamps, values = _series(seeded_db, "seed-web-traffic", "page_views")
    mask = anomaly.flag_mask(values, 3.0)
    flagged = {stamps[i] for i, hit in enumerate(mask) if hit}

    documented = {
        db.iso(FIXED_ANCHOR + timedelta(days=12, hours=14)),
        db.iso(FIXED_ANCHOR + timedelta(days=37, hours=3)),
        db.iso(FIXED_ANCHOR + timedelta(days=61, hours=21)),
    }
    assert flagged, "expected the seeded spike to be flagged at z >= 3"
    assert flagged <= documented
    assert db.iso(FIXED_ANCHOR + timedelta(days=12, hours=14)) in flagged


def test_high_threshold_flags_nothing(seeded_db):
    _, values = _series(seeded_db, "seed-cpu-fleet", "worker_fleet_cpu_pct")
    assert anomaly.flag_mask(values, 3.0).sum() >= 1
    assert anomaly.flag_mask(values, 10.0).sum() == 0


def test_every_seeded_spike_sits_between_the_two_thresholds(seeded_db):
    catalogue = seed.anomaly_catalogue(FIXED_ANCHOR)
    assert len(catalogue) > 0
    for entry in catalogue:
        stamps, values = _series(seeded_db, _seed_key(entry["dataset"]), entry["series"])
        index = stamps.index(entry["timestamp"])
        score = abs(float(anomaly.zscores(values)[index]))
        assert 3.0 <= score < 10.0, f"{entry['dataset']}/{entry['series']} spike scored {score:.2f}"


def _seed_key(dataset_name: str) -> str:
    for spec in seed.SEED_DATASETS:
        if spec.name == dataset_name:
            return spec.seed_key
    raise AssertionError(f"unknown seeded dataset {dataset_name}")


def test_flat_series_has_no_anomalies():
    values = pd.Series([42.0] * 50)
    assert anomaly.flag_mask(values, 3.0).sum() == 0
    assert np.allclose(anomaly.zscores(values), 0.0)


def test_short_and_empty_series_are_safe():
    assert anomaly.flag_mask(pd.Series([1.0, 2.0]), 3.0).sum() == 0
    assert anomaly.flag_mask(pd.Series(dtype=float), 3.0).sum() == 0


def test_flag_frame_adds_columns_and_summary():
    values = [10.0] * 30 + [100.0]
    frame = pd.DataFrame({"value": values})
    flagged = anomaly.flag_frame(frame, "value", 3.0)
    assert {"z", "is_anomaly"} <= set(flagged.columns)
    summary = anomaly.summarise(flagged)
    assert summary["count"] == 1
    assert summary["peak_abs_z"] > 3.0


def test_invalid_threshold_rejected():
    with pytest.raises(ValueError):
        anomaly.flag_mask(pd.Series([1.0, 2.0, 3.0]), 0.0)


def test_seed_anchor_is_deterministic_on_a_fixed_date():
    anchor_a = seed.default_anchor(datetime(2026, 5, 12, 18, 30))
    anchor_b = seed.default_anchor(datetime(2026, 5, 12, 1, 5))
    assert anchor_a == anchor_b == datetime(2026, 2, 12)

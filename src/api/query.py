"""Series listing plus resampling / rolling-window queries."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

import pandas as pd

from .. import db

RESAMPLE_RULES = {
    "raw": None,
    "1h": "1h",
    "6h": "6h",
    "1d": "1D",
}
AGGREGATIONS = ("mean", "sum", "max")


class QueryError(ValueError):
    """Invalid query parameters (safe to show to the user)."""


def _as_bounds(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d 00:00:00")
    return str(value)


def _as_upper_bound(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d 23:59:59")
    text = str(value)
    return text if len(text) > 10 else f"{text} 23:59:59"


def series_list(dataset_id: int, db_path=None) -> list[dict[str, Any]]:
    with db.get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT s.id, s.name, s.unit, COUNT(p.id) AS point_count,"
            " MIN(p.ts) AS first_ts, MAX(p.ts) AS last_ts"
            " FROM series s LEFT JOIN points p ON p.series_id = s.id"
            " WHERE s.dataset_id = ? GROUP BY s.id ORDER BY s.id",
            (int(dataset_id),),
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "name": row["name"],
            "unit": row["unit"],
            "point_count": int(row["point_count"]),
            "first_ts": row["first_ts"],
            "last_ts": row["last_ts"],
        }
        for row in rows
    ]


def dataset_range(dataset_id: int, db_path=None) -> tuple[datetime, datetime] | None:
    with db.get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT MIN(ts) AS lo, MAX(ts) AS hi FROM points WHERE dataset_id = ?",
            (int(dataset_id),),
        ).fetchone()
    if not row or row["lo"] is None:
        return None
    return (
        datetime.strptime(row["lo"], "%Y-%m-%d %H:%M:%S"),
        datetime.strptime(row["hi"], "%Y-%m-%d %H:%M:%S"),
    )


def _load_values(
    conn, dataset_id: int, series_id: int, start: str, end: str
) -> pd.Series:
    rows = conn.execute(
        "SELECT ts, value FROM points WHERE series_id = ? AND dataset_id = ?"
        " AND ts >= ? AND ts <= ? ORDER BY ts",
        (int(series_id), int(dataset_id), start, end),
    ).fetchall()
    if not rows:
        return pd.Series(dtype=float)
    frame = pd.DataFrame(
        {"ts": [row["ts"] for row in rows], "value": [row["value"] for row in rows]}
    )
    frame["ts"] = pd.to_datetime(frame["ts"])
    return frame.set_index("ts")["value"].astype(float)


def query(
    dataset_id: int,
    series_ids: Iterable[int],
    start,
    end,
    resample: str = "raw",
    aggregation: str = "mean",
    rolling_window: int = 1,
    db_path=None,
) -> dict[str, Any]:
    """Return resampled + rolling frames for the requested series."""
    if resample not in RESAMPLE_RULES:
        raise QueryError("Unsupported resample interval.")
    if aggregation not in AGGREGATIONS:
        raise QueryError("Unsupported aggregation.")
    try:
        window = int(rolling_window)
    except (TypeError, ValueError) as exc:
        raise QueryError("Rolling window must be a whole number.") from exc
    if window < 1:
        raise QueryError("Rolling window must be at least 1 interval.")

    lower, upper = _as_bounds(start), _as_upper_bound(end)
    if lower > upper:
        raise QueryError("Start date must be on or before the end date.")

    series_ids = [int(sid) for sid in series_ids]
    if not series_ids:
        return {"frames": {}, "resample": resample, "aggregation": aggregation, "rolling_window": window}

    with db.get_conn(db_path) as conn:
        names: dict[int, str] = {}
        for series_id in series_ids:
            row = conn.execute(
                "SELECT id, name FROM series WHERE dataset_id = ? AND id = ?",
                (int(dataset_id), int(series_id)),
            ).fetchone()
            if row is not None:
                names[int(row["id"])] = row["name"]

        frames: dict[str, pd.DataFrame] = {}
        for series_id in series_ids:
            if series_id not in names:
                continue
            values = _load_values(conn, dataset_id, series_id, lower, upper)
            if values.empty:
                continue
            rule = RESAMPLE_RULES[resample]
            if rule is not None:
                values = values.resample(rule).agg(aggregation).dropna()
            rolling = values.rolling(window=window, min_periods=window).mean()
            frames[names[series_id]] = pd.DataFrame(
                {
                    "ts": values.index,
                    "value": values.to_numpy(dtype=float),
                    "rolling": rolling.to_numpy(dtype=float),
                }
            )

    return {
        "frames": frames,
        "resample": resample,
        "aggregation": aggregation,
        "rolling_window": window,
        "start": lower,
        "end": upper,
    }

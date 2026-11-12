"""Two-period comparison API: elapsed-time aligned frames and summary rows."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable

import pandas as pd

from .. import db
from .query import _as_bounds, _as_upper_bound


class CompareError(ValueError):
    """Invalid comparison windows (safe to show to the user)."""


def _parse_ts(value) -> datetime:
    text = _as_bounds(value)
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def _load_series(conn, dataset_id: int, series_id: int, lower: str, upper: str) -> pd.Series:
    rows = conn.execute(
        "SELECT ts, value FROM points WHERE series_id = ? AND dataset_id = ?"
        " AND ts >= ? AND ts <= ? ORDER BY ts",
        (int(series_id), int(dataset_id), lower, upper),
    ).fetchall()
    if not rows:
        return pd.Series(dtype=float)
    frame = pd.DataFrame(
        {"ts": [row["ts"] for row in rows], "value": [row["value"] for row in rows]}
    )
    frame["ts"] = pd.to_datetime(frame["ts"])
    return frame.set_index("ts")["value"].astype(float)


def _hourly(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    return series.resample("1h").mean().dropna()


def validate_periods(a_start, a_end, b_start, b_end) -> None:
    a_lo, a_hi = _parse_ts(a_start), _parse_ts(a_end)
    b_lo, b_hi = _parse_ts(b_start), _parse_ts(b_end)
    if a_hi < a_lo:
        raise CompareError("Period A: the end date must be on or after the start date.")
    if b_hi < b_lo:
        raise CompareError("Period B: the end date must be on or after the start date.")
    if a_lo <= b_hi and b_lo <= a_hi:
        raise CompareError("Periods A and B overlap. Choose two non-overlapping windows.")


def periods(
    dataset_id: int,
    series_ids: Iterable[int],
    a_start,
    a_end,
    b_start,
    b_end,
    db_path=None,
) -> dict[str, Any]:
    """Compare the same series across two windows, aligned on elapsed hours."""
    validate_periods(a_start, a_end, b_start, b_end)
    series_ids = [int(sid) for sid in series_ids]
    if not series_ids:
        raise CompareError("Select at least one series to compare.")

    a_lower, a_upper = _as_bounds(a_start), _as_upper_bound(a_end)
    b_lower, b_upper = _as_bounds(b_start), _as_upper_bound(b_end)
    a_origin = datetime.strptime(a_lower, "%Y-%m-%d %H:%M:%S")
    b_origin = datetime.strptime(b_lower, "%Y-%m-%d %H:%M:%S")

    with db.get_conn(db_path) as conn:
        names: dict[int, str] = {}
        for series_id in series_ids:
            row = conn.execute(
                "SELECT id, name FROM series WHERE dataset_id = ? AND id = ?",
                (int(dataset_id), int(series_id)),
            ).fetchone()
            if row is not None:
                names[int(row["id"])] = row["name"]

        summary: list[dict[str, Any]] = []
        frames: dict[str, pd.DataFrame] = {}
        for series_id in series_ids:
            if series_id not in names:
                continue
            name = names[series_id]
            raw_a = _load_series(conn, dataset_id, series_id, a_lower, a_upper)
            raw_b = _load_series(conn, dataset_id, series_id, b_lower, b_upper)
            series_a, series_b = _hourly(raw_a), _hourly(raw_b)

            mean_a = float(series_a.mean()) if not series_a.empty else float("nan")
            mean_b = float(series_b.mean()) if not series_b.empty else float("nan")
            delta = mean_b - mean_a
            if mean_a and mean_a != 0 and mean_a == mean_a and mean_b == mean_b:
                pct_change = (delta / mean_a) * 100.0
            else:
                pct_change = float("nan")

            summary.append(
                {
                    "series": name,
                    "series_id": series_id,
                    "mean_a": mean_a,
                    "mean_b": mean_b,
                    "delta": delta,
                    "pct_change": pct_change,
                    "count_a": int(len(raw_a)),
                    "count_b": int(len(raw_b)),
                }
            )

            elapsed_a = pd.Series(
                series_a.to_numpy(dtype=float),
                index=[(ts - a_origin).total_seconds() / 3600.0 for ts in series_a.index],
            ).sort_index()
            elapsed_b = pd.Series(
                series_b.to_numpy(dtype=float),
                index=[(ts - b_origin).total_seconds() / 3600.0 for ts in series_b.index],
            ).sort_index()
            frames[name] = pd.DataFrame({"elapsed_hours": elapsed_a.index, "period_a": elapsed_a.to_numpy(dtype=float)})
            frames[name] = frames[name].merge(
                pd.DataFrame(
                    {"elapsed_hours": elapsed_b.index, "period_b": elapsed_b.to_numpy(dtype=float)}
                ),
                on="elapsed_hours",
                how="outer",
            ).sort_values("elapsed_hours")

    return {
        "summary": summary,
        "frames": frames,
        "period_a": {"start": a_lower, "end": a_upper},
        "period_b": {"start": b_lower, "end": b_upper},
    }


def preset_windows(last_ts: datetime, days: int = 7) -> tuple[date, date, date, date]:
    """Last N days vs the N days before, anchored to the newest data point."""
    end = last_ts.date()
    a_start = end - timedelta(days=days - 1)
    b_end = a_start - timedelta(days=1)
    b_start = b_end - timedelta(days=days - 1)
    return a_start, end, b_start, b_end

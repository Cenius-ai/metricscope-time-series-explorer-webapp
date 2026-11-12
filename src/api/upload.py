"""Upload API: parse a CSV and commit it as a dataset with series and points."""

from __future__ import annotations

from typing import Any

from .. import db
from ..db import iso, utcnow
from ..ingest import ParsedUpload, UploadError, iter_points, parse_csv, preview_frame

__all__ = ["create", "parse_only", "UploadError"]


def parse_only(data: bytes, filename: str) -> ParsedUpload:
    """Parse without writing anything — used for the pre-commit preview."""
    return parse_csv(data, filename)


def create(user_id: int, filename: str, data: bytes, db_path=None) -> dict[str, Any]:
    """Parse and persist an upload. Raises UploadError on fatal problems."""
    parsed = parse_only(data, filename)
    with db.get_conn(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO datasets (name, source_filename, uploaded_by, row_count,"
            " dropped_row_count, is_seed, seed_key, created_at)"
            " VALUES (?, ?, ?, ?, ?, 0, NULL, ?)",
            (
                parsed.dataset_name,
                filename,
                int(user_id),
                parsed.accepted_rows,
                parsed.dropped_rows,
                iso(utcnow()),
            ),
        )
        dataset_id = int(cur.lastrowid)

        series_ids: dict[str, int] = {}
        for column in parsed.series_columns:
            series_cur = conn.execute(
                "INSERT INTO series (dataset_id, name, unit) VALUES (?, ?, NULL)",
                (dataset_id, column),
            )
            series_ids[column] = int(series_cur.lastrowid)

        points = [
            (dataset_id, series_ids[name], ts, value)
            for name, ts, value in iter_points(parsed)
        ]
        conn.executemany(
            "INSERT INTO points (dataset_id, series_id, ts, value) VALUES (?, ?, ?, ?)",
            points,
        )
        conn.commit()

    return {
        "dataset_id": dataset_id,
        "name": parsed.dataset_name,
        "row_count": parsed.accepted_rows,
        "dropped_row_count": parsed.dropped_rows,
        "series": list(parsed.series_columns),
        "point_count": len(points),
        "preview": preview_frame(parsed, limit=20),
        "skipped_summary": parsed.skipped_summary,
    }
"""Dataset library API: list, preview, delete with cascade."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .. import db

PREVIEW_ROWS = 20


class DatasetNotFound(Exception):
    """Raised when a dataset id does not exist."""


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "source_filename": row["source_filename"],
        "row_count": int(row["row_count"]),
        "dropped_row_count": int(row["dropped_row_count"]),
        "is_seed": bool(row["is_seed"]),
        "created_at": row["created_at"],
        "uploaded_by": row["uploaded_by"],
        "series_count": int(row["series_count"]) if "series_count" in row.keys() else 0,
        "point_count": int(row["point_count"]) if "point_count" in row.keys() else 0,
    }


def list_datasets(db_path=None) -> list[dict[str, Any]]:
    with db.get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT d.*,"
            " (SELECT COUNT(*) FROM series s WHERE s.dataset_id = d.id) AS series_count,"
            " (SELECT COUNT(*) FROM points p WHERE p.dataset_id = d.id) AS point_count"
            " FROM datasets d ORDER BY d.is_seed DESC, d.id ASC"
        ).fetchall()
        return [_row_to_dict(row) for row in rows]


def get_dataset(dataset_id: int, db_path=None) -> dict[str, Any]:
    with db.get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT d.*,"
            " (SELECT COUNT(*) FROM series s WHERE s.dataset_id = d.id) AS series_count,"
            " (SELECT COUNT(*) FROM points p WHERE p.dataset_id = d.id) AS point_count"
            " FROM datasets d WHERE d.id = ?",
            (int(dataset_id),),
        ).fetchone()
    if row is None:
        raise DatasetNotFound(f"Dataset {dataset_id} does not exist.")
    return _row_to_dict(row)


def preview(dataset_id: int, limit: int = PREVIEW_ROWS, db_path=None) -> dict[str, Any]:
    """First `limit` accepted rows (wide) plus the skipped-row count."""
    dataset = get_dataset(dataset_id, db_path=db_path)
    with db.get_conn(db_path) as conn:
        stamps = conn.execute(
            "SELECT DISTINCT ts FROM points WHERE dataset_id = ? ORDER BY ts LIMIT ?",
            (int(dataset_id), int(limit)),
        ).fetchall()
        if not stamps:
            return {"dataset": dataset, "frame": pd.DataFrame(), "dropped_row_count": dataset["dropped_row_count"]}
        last_stamp = stamps[-1]["ts"]
        rows = conn.execute(
            "SELECT p.ts, s.name AS series, p.value FROM points p"
            " JOIN series s ON s.id = p.series_id"
            " WHERE p.dataset_id = ? AND p.ts <= ? ORDER BY p.ts",
            (int(dataset_id), last_stamp),
        ).fetchall()
    frame = pd.DataFrame(
        [{"ts": row["ts"], "series": row["series"], "value": row["value"]} for row in rows]
    )
    wide = frame.pivot_table(index="ts", columns="series", values="value", aggfunc="first")
    wide = wide.reset_index().rename(columns={"ts": "timestamp"})
    return {
        "dataset": dataset,
        "frame": wide,
        "dropped_row_count": dataset["dropped_row_count"],
    }


def delete(dataset_id: int, db_path=None) -> dict[str, Any]:
    """Delete a dataset; series and points cascade away via foreign keys."""
    with db.get_conn(db_path) as conn:
        row = conn.execute("SELECT id FROM datasets WHERE id = ?", (int(dataset_id),)).fetchone()
        if row is None:
            raise DatasetNotFound(f"Dataset {dataset_id} does not exist.")
        points_before = conn.execute(
            "SELECT COUNT(*) AS n FROM points WHERE dataset_id = ?", (int(dataset_id),)
        ).fetchone()["n"]
        conn.execute("DELETE FROM datasets WHERE id = ?", (int(dataset_id),))
        conn.commit()
        remaining_points = conn.execute(
            "SELECT COUNT(*) AS n FROM points WHERE dataset_id = ?", (int(dataset_id),)
        ).fetchone()["n"]
    return {"ok": True, "deleted_points": int(points_before), "remaining_points": int(remaining_points)}

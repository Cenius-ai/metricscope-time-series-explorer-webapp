import pandas as pd
import pytest

from src import db
from src.api import upload
from src.ingest import (
    FILE_TOO_LARGE,
    MISSING_TIMESTAMP,
    NO_NUMERIC_SERIES,
    NO_VALID_ROWS,
    UploadError,
    dataset_name_from_filename,
    parse_csv,
)


def make_csv(rows: int = 100, bad_timestamps: int = 0) -> bytes:
    lines = ["timestamp,page_views,error_rate"]
    for index in range(rows):
        stamp = f"2026-03-{1 + index // 24:02d} {index % 24:02d}:00:00"
        if index < bad_timestamps:
            stamp = "not-a-timestamp"
        lines.append(f"{stamp},{4000 + index},{0.4 + index / 1000:.3f}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_rows_with_unparseable_timestamps_are_dropped_and_counted():
    parsed = parse_csv(make_csv(rows=100, bad_timestamps=3), "traffic.csv")
    assert parsed.accepted_rows == 97
    assert parsed.dropped_rows == 3
    assert parsed.series_columns == ["page_views", "error_rate"]
    assert parsed.dataset_name == "Traffic"


def test_upload_create_stores_only_accepted_rows(fresh_db, demo_user_id):
    result = upload.create(demo_user_id, "traffic.csv", make_csv(100, 3), db_path=fresh_db)
    assert result["row_count"] == 97
    assert result["dropped_row_count"] == 3
    assert result["point_count"] == 97 * 2

    with db.get_conn(fresh_db) as conn:
        points = conn.execute("SELECT COUNT(*) AS n FROM points").fetchone()["n"]
        series = conn.execute("SELECT COUNT(*) AS n FROM series").fetchone()["n"]
        dataset = conn.execute("SELECT row_count, dropped_row_count FROM datasets").fetchone()
    assert points == 194
    assert series == 2
    assert dataset["dropped_row_count"] == 3


def test_missing_timestamp_column_is_fatal(fresh_db, demo_user_id):
    csv = b"a,b\n1,2\n3,4\n"
    with pytest.raises(UploadError) as excinfo:
        parse_csv(csv, "no-time.csv")
    assert str(excinfo.value) == MISSING_TIMESTAMP
    with pytest.raises(UploadError):
        upload.create(demo_user_id, "no-time.csv", csv, db_path=fresh_db)
    with db.get_conn(fresh_db) as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM datasets").fetchone()["n"] == 0


def test_all_timestamps_unparseable_is_fatal():
    csv = b"timestamp,value\nnot-a-date,1\nstill-not,2\n"
    with pytest.raises(UploadError) as excinfo:
        parse_csv(csv, "bad.csv")
    assert str(excinfo.value) == NO_VALID_ROWS


def test_no_numeric_series_is_fatal():
    csv = b"timestamp,label\n2026-03-01 00:00:00,alpha\n2026-03-01 01:00:00,beta\n"
    with pytest.raises(UploadError) as excinfo:
        parse_csv(csv, "labels.csv")
    assert str(excinfo.value) == NO_NUMERIC_SERIES


def test_oversized_file_is_fatal():
    oversized = b"timestamp,value\n" + b"2026-03-01 00:00:00,1\n" * (26 * 1024 * 1024 // 22 + 1)
    assert len(oversized) > 25 * 1024 * 1024
    with pytest.raises(UploadError) as excinfo:
        parse_csv(oversized, "huge.csv")
    assert str(excinfo.value) == FILE_TOO_LARGE


def test_preview_returns_first_twenty_rows():
    from src.ingest import preview_frame

    parsed = parse_csv(make_csv(rows=40), "traffic.csv")
    preview = preview_frame(parsed, limit=20)
    assert len(preview) == 20
    assert list(preview.columns)[0] == "timestamp"
    assert isinstance(preview, pd.DataFrame)


def test_blank_cells_become_gaps_not_errors():
    csv = (
        b"timestamp,requests,errors\n"
        b"2026-03-01 00:00:00,10,1\n"
        b"2026-03-01 01:00:00,,0\n"
        b"2026-03-01 02:00:00,12,2\n"
    )
    parsed = parse_csv(csv, "gappy.csv")
    assert parsed.accepted_rows == 3
    requests = parsed.frame["requests"].tolist()
    assert requests[0] == 10
    assert pd.isna(requests[1])
    assert parsed.frame["errors"].tolist() == [1, 0, 2]


def test_row_with_no_numeric_values_is_dropped():
    csv = b"timestamp,requests\n2026-03-01 00:00:00,10\n2026-03-01 01:00:00,\n"
    parsed = parse_csv(csv, "sparse.csv")
    assert parsed.accepted_rows == 1


def test_dataset_name_from_filename_is_humanised():
    assert dataset_name_from_filename("fleet_cpu_hourly.csv") == "Fleet Cpu Hourly"

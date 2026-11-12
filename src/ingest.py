"""CSV ingestion with row-level timestamp handling.

Fatal conditions (the only reasons a whole upload is rejected):
  * file larger than the configured limit
  * no timestamp column
  * no numeric series column
  * zero rows with a parseable timestamp

Rows whose timestamp cannot be parsed are dropped and counted; cells that cannot
be coerced to a number become gaps rather than errors.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import config

TIMESTAMP_NAMES = (
    "timestamp",
    "time",
    "datetime",
    "date_time",
    "recorded_at",
    "event_time",
    "created_at",
    "ts",
    "date",
)

MISSING_TIMESTAMP = "Missing timestamp column."
NO_VALID_ROWS = "No valid rows found."
NO_NUMERIC_SERIES = "No numeric series columns found."
FILE_TOO_LARGE = f"File exceeds {config.MAX_UPLOAD_MB} MB limit."


class UploadError(ValueError):
    """Fatal upload problem; the message is safe to show to the user."""


@dataclass
class ParsedUpload:
    frame: pd.DataFrame  # DatetimeIndex named "ts"; one column per numeric series
    timestamp_column: str
    series_columns: list[str]
    accepted_rows: int
    dropped_rows: int
    dataset_name: str

    @property
    def skipped_summary(self) -> str:
        if self.dropped_rows == 0:
            return "All rows parsed cleanly."
        return f"{self.dropped_rows:,} row(s) skipped: unparseable timestamp."


def dataset_name_from_filename(filename: str) -> str:
    stem = Path(filename or "upload.csv").stem.replace("_", " ").replace("-", " ").strip()
    return (stem or "Uploaded dataset").title()


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UploadError("Could not decode the CSV file as text.")


def _find_timestamp_column(columns: list[str]) -> str | None:
    lowered = {col.strip().lower(): col for col in columns}
    for candidate in TIMESTAMP_NAMES:
        if candidate in lowered:
            return lowered[candidate]
    for name, original in lowered.items():
        if "time" in name or "date" in name or name.endswith("ts"):
            return original
    return None


def parse_csv(data: bytes, filename: str = "upload.csv") -> ParsedUpload:
    """Parse CSV bytes into a tidy wide frame of timestamped numeric series."""
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise UploadError(FILE_TOO_LARGE)
    if not data.strip():
        raise UploadError(NO_VALID_ROWS)

    text = _decode(data)
    try:
        raw = pd.read_csv(
            io.StringIO(text),
            dtype=str,
            keep_default_na=False,
            skip_blank_lines=True,
        )
    except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as exc:
        raise UploadError("Could not parse the file as CSV.") from exc

    raw.columns = [str(col).strip() for col in raw.columns]
    if raw.empty or not len(raw.columns):
        raise UploadError(NO_VALID_ROWS)

    timestamp_column = _find_timestamp_column(list(raw.columns))
    if timestamp_column is None:
        raise UploadError(MISSING_TIMESTAMP)

    stamps = pd.to_datetime(
        raw[timestamp_column].astype("string").str.strip(),
        errors="coerce",
        utc=True,
        format="mixed",
    )
    valid_mask = stamps.notna()
    dropped_rows = int((~valid_mask).sum())

    value_columns = [col for col in raw.columns if col != timestamp_column]
    numeric: dict[str, pd.Series] = {}
    for col in value_columns:
        coerced = pd.to_numeric(
            raw[col].astype("string").str.replace(",", "", regex=False).str.strip(),
            errors="coerce",
        )
        if coerced.notna().any():
            numeric[col] = coerced

    if not numeric:
        raise UploadError(NO_NUMERIC_SERIES)

    frame = pd.DataFrame(numeric)[valid_mask.to_numpy()]
    index = stamps[valid_mask].dt.tz_convert(None).dt.floor("s")
    frame.index = pd.DatetimeIndex(index, name="ts")
    frame = frame.dropna(how="all")

    if frame.empty:
        raise UploadError(NO_VALID_ROWS)

    frame = frame.sort_index()
    return ParsedUpload(
        frame=frame,
        timestamp_column=timestamp_column,
        series_columns=list(frame.columns),
        accepted_rows=int(len(frame)),
        dropped_rows=dropped_rows,
        dataset_name=dataset_name_from_filename(filename),
    )


def preview_frame(parsed: ParsedUpload, limit: int = 20) -> pd.DataFrame:
    """First `limit` accepted rows, ready for display."""
    preview = parsed.frame.head(limit).reset_index()
    preview["ts"] = preview["ts"].dt.strftime("%Y-%m-%d %H:%M")
    return preview.rename(columns={"ts": "timestamp"})


def iter_points(parsed: ParsedUpload):
    """Yield (series_name, ts_string, value) for every non-null cell."""
    frame = parsed.frame
    stamp_strings = frame.index.strftime("%Y-%m-%d %H:%M:%S")
    for column in frame.columns:
        values = frame[column]
        mask = values.notna().to_numpy()
        column_values = values.to_numpy(dtype=float)
        for position in mask.nonzero()[0]:
            yield str(column), str(stamp_strings[position]), float(column_values[position])

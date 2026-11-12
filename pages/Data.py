"""Data page: upload a CSV metric file with row-level validation and preview."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import config, ui
from src.api import datasets as datasets_api
from src.api import upload as upload_api
from src.ingest import (
    FILE_TOO_LARGE,
    MISSING_TIMESTAMP,
    NO_NUMERIC_SERIES,
    NO_VALID_ROWS,
    UploadError,
    parse_csv,
    preview_frame,
)

ui.page_config("Data · Metricscope Time-Series Explorer")

user = ui.gate(
    kicker="Data",
    heading="Upload a metric file",
    subtitle="Drop in a CSV with a timestamp column and one column per numeric series. "
    "Rows with unparseable timestamps are skipped and counted; everything else is stored locally.",
)

flash = st.session_state.pop("ms_upload_flash", None)
if flash:
    st.success(flash)
upload_error = st.session_state.pop("ms_upload_error", None)
if upload_error:
    ui.error_state("Upload rejected", upload_error)

library = datasets_api.list_datasets()

ui.stat_cards(
    [
        {
            "label": "datasets",
            "value": f"{len(library)}",
            "note": "Seeded and uploaded files in the local SQLite store.",
        },
        {
            "label": "rows stored",
            "value": ui.fmt_number(sum(ds["row_count"] for ds in library)),
            "note": "Accepted timestamp rows across every dataset.",
        },
        {
            "label": "rows skipped",
            "value": ui.fmt_number(sum(ds["dropped_row_count"] for ds in library)),
            "note": "Rows dropped for an unparseable timestamp.",
            "tone": "alert" if any(ds["dropped_row_count"] for ds in library) else "",
        },
        {
            "label": "upload limit",
            "value": str(config.MAX_UPLOAD_MB),
            "unit": "MB",
            "note": "Hard guard applied before parsing.",
        },
    ]
)

left, right = st.columns([1.35, 1], gap="large")

with left:
    with st.container(border=True):
        st.markdown("#### Choose a CSV file")
        ui.note(
            "Required: a timestamp column named timestamp, time, ts, datetime or date. "
            "Every other column that holds numbers becomes a series."
        )
        nonce = st.session_state.get("ms_upload_nonce", 0)
        uploaded = st.file_uploader(
            "CSV file",
            type=["csv"],
            key=f"ms-csv-{nonce}",
            max_upload_size=config.MAX_UPLOAD_MB,
            help="Up to 25 MB. The first 20 accepted rows are previewed before you commit.",
        )

        template = (
            "timestamp,page_views,error_rate\n"
            "2026-11-01 00:00:00,4821,0.42\n"
            "2026-11-01 01:00:00,4410,0.38\n"
            "2026-11-01 02:00:00,3980,0.35\n"
        )
        st.download_button(
            "Download a CSV template",
            data=template,
            file_name="metricscope_template.csv",
            mime="text/csv",
            type="tertiary",
        )

        if uploaded is None:
            ui.empty_state(
                "No file selected yet",
                "Pick a CSV above to see the parsed preview. The three seeded datasets are "
                "already in the Library — you do not need to upload anything to explore.",
            )

    if uploaded is not None:
        data = uploaded.getvalue()
        try:
            with st.spinner("Parsing rows and coercing numerics…"):
                parsed = parse_csv(data, uploaded.name)
        except UploadError as exc:
            ui.error_state("Upload rejected", str(exc))
        else:
            with st.container(border=True):
                st.markdown("#### Preview")
                st.markdown(
                    f"**{parsed.dataset_name}** · timestamp column "
                    f"`{parsed.timestamp_column}` · {parsed.accepted_rows:,} accepted rows · "
                    f"{len(parsed.series_columns)} series"
                )
                if parsed.dropped_rows:
                    st.warning(
                        f"{parsed.dropped_rows:,} row(s) skipped: unparseable timestamp. "
                        "They will not be stored."
                    )
                else:
                    st.success("Every row parsed cleanly.")
                st.dataframe(preview_frame(parsed, limit=20), hide_index=True)
                if st.button("Save dataset", type="primary", key="ms-save-dataset"):
                    try:
                        result = upload_api.create(user["id"], uploaded.name, data)
                    except UploadError as exc:
                        st.session_state["ms_upload_error"] = str(exc)
                        st.rerun()
                    st.session_state["ms_upload_flash"] = (
                        f"Saved “{result['name']}” — {result['row_count']:,} rows across "
                        f"{len(result['series'])} series."
                    )
                    st.session_state["ms_upload_nonce"] = nonce + 1
                    st.rerun()

with right:
    with st.container(border=True):
        st.markdown("#### Expected format")
        st.dataframe(
            pd.DataFrame(
                {
                    "timestamp": ["2026-11-01 00:00:00", "2026-11-01 01:00:00"],
                    "page_views": [4821, 4410],
                    "error_rate": [0.42, 0.38],
                }
            ),
            hide_index=True,
        )
        ui.note("Any column that parses as a number becomes a series. Blank cells become gaps.")
    with st.container(border=True):
        st.markdown("#### Fatal errors")
        for message in (FILE_TOO_LARGE, MISSING_TIMESTAMP, NO_VALID_ROWS, NO_NUMERIC_SERIES):
            st.markdown(f"- {message}")
        ui.note("Those four conditions reject the file. Everything else degrades to a skipped row.")
    with st.container(border=True):
        st.markdown("#### Recently added")
        uploaded_only = [ds for ds in library if not ds["is_seed"]]
        if not uploaded_only:
            ui.note("No uploads yet — the Library currently holds the three seeded datasets.")
        else:
            for ds in uploaded_only[:5]:
                st.markdown(
                    f"- **{ds['name']}** · {ds['row_count']:,} rows · {ui.fmt_ts(ds['created_at'])}"
                )

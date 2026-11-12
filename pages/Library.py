"""Library page: manage datasets, inspect a preview, delete with confirmation."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import ui
from src.api import datasets as datasets_api

ui.page_config("Library · Metricscope Time-Series Explorer")

ui.gate(
    kicker="Library",
    heading="Dataset library",
    subtitle="Every metric file in the local store, seeded or uploaded. Open a preview, "
    "check the row counts, or delete a dataset with its series and points.",
)

flash = st.session_state.pop("ms_library_flash", None)
if flash:
    st.success(flash)

datasets = datasets_api.list_datasets()

if not datasets:
    ui.empty_state(
        "No datasets yet",
        "Nothing is stored right now. Upload a CSV on the Data page, or restart the app / "
        "run python3 -m src.seed to restore the three seeded datasets.",
    )
    st.stop()

series_total = sum(ds["series_count"] for ds in datasets)
point_total = sum(ds["point_count"] for ds in datasets)
skipped_total = sum(ds["dropped_row_count"] for ds in datasets)

ui.stat_cards(
    [
        {"label": "datasets", "value": f"{len(datasets)}", "note": f"{series_total} series in total."},
        {
            "label": "stored points",
            "value": ui.fmt_number(point_total),
            "note": f"Values across all {series_total} series.",
        },
        {
            "label": "skipped rows",
            "value": ui.fmt_number(skipped_total),
            "note": "Rejected for an unparseable timestamp.",
            "tone": "alert" if skipped_total else "",
        },
        {
            "label": "seeded",
            "value": f"{sum(1 for ds in datasets if ds['is_seed'])}",
            "note": "Deterministic demo datasets with injected spikes.",
        },
    ]
)

table = pd.DataFrame(
    [
        {
            "Dataset": ds["name"],
            "Source file": ds["source_filename"] or "—",
            "Rows": ds["row_count"],
            "Skipped": ds["dropped_row_count"],
            "Series": ds["series_count"],
            "Origin": "seed" if ds["is_seed"] else "upload",
            "Created": ui.fmt_ts(ds["created_at"]),
        }
        for ds in datasets
    ]
)

st.dataframe(
    table,
    hide_index=True,
    column_config={
        "Rows": st.column_config.NumberColumn(format="%d"),
        "Skipped": st.column_config.NumberColumn(format="%d"),
        "Series": st.column_config.NumberColumn(format="%d"),
    },
)

left, right = st.columns([1.6, 1], gap="large")

names = {ds["id"]: ds["name"] for ds in datasets}
if st.session_state.get("ms-library-dataset") not in names:
    st.session_state["ms-library-dataset"] = datasets[0]["id"]

with left:
    with st.container(border=True):
        selected_id = st.selectbox(
            "Preview dataset",
            options=list(names),
            format_func=lambda dataset_id: names[dataset_id],
            key="ms-library-dataset",
        )
        try:
            with st.spinner("Loading preview…"):
                preview = datasets_api.preview(selected_id, limit=20)
        except datasets_api.DatasetNotFound:
            ui.error_state("Preview unavailable", "That dataset no longer exists.")
        else:
            dataset = preview["dataset"]
            ui.pill_row(
                [
                    f"{dataset['row_count']:,} rows",
                    f"{dataset['series_count']} series",
                    f"{dataset['dropped_row_count']:,} skipped",
                    "seed" if dataset["is_seed"] else "upload",
                ]
            )
            frame = preview["frame"]
            if frame.empty:
                ui.empty_state(
                    "No points stored",
                    "This dataset has no rows. Delete it and re-upload the CSV, or use a seeded dataset.",
                )
            else:
                ui.render_table(frame)
                ui.note(
                    f"First {len(frame)} rows of “{dataset['name']}”. "
                    f"{preview['dropped_row_count']:,} row(s) were skipped during parsing."
                )

with right:
    with st.container(border=True):
        st.markdown("#### Delete dataset")
        st.markdown(
            f"Deletes **{names[selected_id]}** plus its series and every stored point. "
            "This cannot be undone."
        )
        confirmed = st.checkbox(
            "I understand the series and points are deleted permanently.",
            key="ms-library-confirm",
        )
        if st.button(
            "Delete dataset",
            type="primary",
            disabled=not confirmed,
            key="ms-library-delete",
        ):
            try:
                result = datasets_api.delete(selected_id)
            except datasets_api.DatasetNotFound:
                ui.error_state("Delete failed", "That dataset no longer exists.")
            else:
                st.session_state["ms_library_flash"] = (
                    f"Deleted “{names[selected_id]}” and {result['deleted_points']:,} points."
                )
                st.session_state.pop("ms-library-confirm", None)
                st.session_state.pop("ms-library-dataset", None)
                st.rerun()
        if not confirmed:
            ui.note("Tick the confirmation box to enable the delete button.")

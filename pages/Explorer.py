"""Explorer page: multi-series plot with resampling, rolling average and z-score anomalies."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import anomaly, ui
from src.api import datasets as datasets_api
from src.api import query as query_api

ui.page_config("Explorer · Metricscope Time-Series Explorer")

ui.gate(
    kicker="Explorer",
    heading="Multi-series explorer",
    subtitle="Plot several series at once, resample the buckets, overlay a rolling average and "
    "mark every point whose z-score crosses your threshold.",
)

datasets = datasets_api.list_datasets()
if not datasets:
    ui.empty_state(
        "No datasets to explore",
        "The library is empty. Upload a CSV on the Data page, or restart the app to restore the "
        "seeded datasets.",
    )
    st.stop()

names = {ds["id"]: ds["name"] for ds in datasets}
available_ids = list(names)
if st.session_state.get("exp-dataset") not in available_ids:
    st.session_state["exp-dataset"] = available_ids[0]

picker, meta = st.columns([2, 3], vertical_alignment="bottom")
with picker:
    dataset_id = st.selectbox(
        "Dataset",
        options=available_ids,
        format_func=lambda dataset_id: names[dataset_id],
        key="exp-dataset",
    )

series = query_api.series_list(dataset_id)
if not series:
    ui.empty_state("No series in this dataset", "Upload a CSV with numeric columns to explore it.")
    st.stop()

bounds = query_api.dataset_range(dataset_id)
if bounds is None:
    ui.empty_state("No points in this dataset", "Upload a CSV with data rows to explore it.")
    st.stop()
first_day, last_day = bounds[0].date(), bounds[1].date()

series_names = [s["name"] for s in series]
series_ids = {s["name"]: s["id"] for s in series}
series_units = {s["name"]: (s["unit"] or "") for s in series}

with meta:
    ui.pill_row(
        [
            f"{len(series)} series",
            f"{ui.fmt_number(sum(s['point_count'] for s in series))} points",
            f"{first_day.strftime('%d %b')} – {last_day.strftime('%d %b %Y')}",
        ]
    )

series_key = f"exp-series-{dataset_id}"
if st.session_state.get(series_key) is None:
    st.session_state[series_key] = series_names[:2]
start_key, end_key = f"exp-start-{dataset_id}", f"exp-end-{dataset_id}"
if start_key not in st.session_state:
    st.session_state[start_key] = first_day
if end_key not in st.session_state:
    st.session_state[end_key] = last_day

with st.container(border=True):
    st.markdown("#### Window and shaping")
    c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 2], vertical_alignment="bottom")
    with c1:
        selected = st.multiselect(
            "Series",
            options=series_names,
            key=series_key,
            placeholder="Select at least one series",
        )
    with c2:
        start = st.date_input(
            "Start", key=start_key, min_value=first_day, max_value=last_day
        )
    with c3:
        end = st.date_input("End", key=end_key, min_value=first_day, max_value=last_day)
    with c4:
        resample = st.segmented_control(
            "Resample",
            options=["raw", "1h", "6h", "1d"],
            default="raw",
            key="exp-resample",
        )
    with c5:
        aggregation = st.selectbox(
            "Aggregation", options=["mean", "sum", "max"], key="exp-aggregation"
        )

    c6, c7 = st.columns([2, 3], vertical_alignment="bottom")
    with c6:
        rolling_window = st.slider(
            "Rolling window (intervals)", min_value=1, max_value=48, value=6, key="exp-rolling"
        )
    with c7:
        threshold = st.slider(
            "Anomaly z-score threshold",
            min_value=1.0,
            max_value=10.0,
            value=3.0,
            step=0.1,
            key="exp-threshold",
        )

resample = resample or "raw"

if not selected:
    ui.empty_state(
        "Select at least one series",
        "Pick one or more series above to draw the chart. Two series make the rolling overlay "
        "and anomaly flagging easier to read.",
    )
    st.stop()

try:
    result = query_api.query(
        dataset_id,
        [series_ids[name] for name in selected],
        start,
        end,
        resample=resample,
        aggregation=aggregation,
        rolling_window=rolling_window,
    )
except query_api.QueryError as exc:
    ui.error_state("Query rejected", str(exc))
    st.stop()

frames = result["frames"]
if not frames:
    ui.error_state(
        "No points in this window",
        "Nothing is stored between those dates. Widen the date range or pick another dataset.",
    )
    st.stop()

flagged_frames = {name: anomaly.flag_frame(frame, "value", threshold) for name, frame in frames.items()}
flagged_total = sum(int(frame["is_anomaly"].sum()) for frame in flagged_frames.values())
peak_z = max((float(frame["z"].abs().max()) for frame in flagged_frames.values()), default=0.0)
point_total = sum(len(frame) for frame in frames.values())

ui.stat_cards(
    [
        {
            "label": "series plotted",
            "value": f"{len(frames)}",
            "note": " · ".join(frames) if len(frames) <= 3 else f"{len(frames)} selected series",
        },
        {
            "label": "points in window",
            "value": ui.fmt_number(point_total),
            "note": f"{resample} buckets, {aggregation} aggregation.",
        },
        {
            "label": "flagged anomalies",
            "value": f"{flagged_total}",
            "note": f"|z| ≥ {threshold:.1f} over the visible window.",
            "tone": "alert" if flagged_total else "ok",
        },
        {
            "label": "peak |z|",
            "value": f"{peak_z:.2f}",
            "note": "Highest absolute z-score in the current view.",
        },
    ]
)

figure = go.Figure()
flagged_rows: list[dict] = []
rolling_visible = rolling_window > 1

for index, (name, frame) in enumerate(flagged_frames.items()):
    colour = ui.series_colour(index)
    unit = series_units.get(name) or ""
    value_label = f"{name}" + (f" ({unit})" if unit else "")
    figure.add_trace(
        go.Scatter(
            x=frame["ts"],
            y=frame["value"],
            mode="lines",
            name=value_label,
            line=dict(color=colour, width=1.4),
            opacity=0.55,
            hovertemplate="%{x|%d %b %H:%M}<br>" + f"{name} " + "%{y:,.2f}<extra></extra>",
        )
    )
    if rolling_visible:
        figure.add_trace(
            go.Scatter(
                x=frame["ts"],
                y=frame["rolling"],
                mode="lines",
                name=f"{name} · rolling {rolling_window}",
                line=dict(color=colour, width=3),
                connectgaps=False,
                hovertemplate="%{x|%d %b %H:%M}<br>"
                + f"{name} rolling "
                + "%{y:,.2f}<extra></extra>",
            )
        )
    flagged = frame[frame["is_anomaly"]]
    if not flagged.empty:
        figure.add_trace(
            go.Scatter(
                x=flagged["ts"],
                y=flagged["value"],
                mode="markers",
                name=f"{name} · anomaly",
                marker=dict(
                    color="#c9302d",
                    size=11,
                    symbol="triangle-up",
                    line=dict(color="#fdffff", width=1),
                ),
                hovertemplate="%{x|%d %b %H:%M}<br>"
                + f"{name} anomaly "
                + "%{y:,.2f}<extra></extra>",
            )
        )
        for _, row in flagged.iterrows():
            flagged_rows.append(
                {
                    "Series": name,
                    "Timestamp": ui.fmt_ts(row["ts"].strftime("%Y-%m-%d %H:%M:%S")),
                    "Value": round(float(row["value"]), 2),
                    "Z-score": round(float(row["z"]), 2),
                }
            )

ui.style_figure(figure, height=430, y_title=series_units.get(selected[0]) or None)
st.plotly_chart(figure, theme=None, config={"displayModeBar": False})

ui.note(
    f"{resample} buckets · {aggregation} aggregation · rolling window {rolling_window} intervals · "
    f"anomaly threshold |z| ≥ {threshold:.1f} · {ui.fmt_ts(result['start'])} → {ui.fmt_ts(result['end'])}"
)

if flagged_rows:
    with st.container(border=True):
        st.markdown("#### Flagged points")
        st.dataframe(
            pd.DataFrame(flagged_rows).sort_values("Z-score", key=lambda s: s.abs(), ascending=False),
            hide_index=True,
            column_config={
                "Value": st.column_config.NumberColumn(format="%.2f"),
                "Z-score": st.column_config.NumberColumn(format="%.2f"),
            },
        )
else:
    ui.empty_state(
        "No points cross the threshold",
        f"Every point in this window sits inside |z| < {threshold:.1f}. Lower the threshold or "
        "widen the date range — the seeded datasets carry documented spikes.",
    )

with st.expander("How the numbers are computed"):
    st.markdown(
        f"- **Resampling** buckets the raw hourly points into `{resample}` windows using "
        f"`{aggregation}`.\n"
        f"- **Rolling average** is the mean of the last {rolling_window} bucket(s); it needs a "
        "full window before it draws.\n"
        "- **Z-score** is `(value − mean) / std` computed per series over the visible window, so "
        "changing the date range changes which points count as anomalous.\n"
        "- Flagged points are the triangles drawn on the raw series."
    )

"""Compare page: two non-overlapping periods aligned on elapsed time."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import ui
from src.api import compare as compare_api
from src.api import datasets as datasets_api
from src.api import query as query_api

ui.page_config("Compare · Metricscope Time-Series Explorer")

ui.gate(
    kicker="Compare",
    heading="Two-period comparison",
    subtitle="Put two windows side by side on an elapsed-time axis and read the per-series "
    "delta. Presets anchor to the newest data point in the dataset.",
)

datasets = datasets_api.list_datasets()
if not datasets:
    ui.empty_state(
        "Nothing to compare yet",
        "The library is empty. Upload a CSV on the Data page, or restart the app to restore the "
        "seeded datasets.",
    )
    st.stop()

names = {ds["id"]: ds["name"] for ds in datasets}
available_ids = list(names)
if st.session_state.get("cmp-dataset") not in available_ids:
    st.session_state["cmp-dataset"] = available_ids[0]

top_left, top_right = st.columns([2, 3], vertical_alignment="bottom")
with top_left:
    dataset_id = st.selectbox(
        "Dataset",
        options=available_ids,
        format_func=lambda dataset_id: names[dataset_id],
        key="cmp-dataset",
    )

series = query_api.series_list(dataset_id)
bounds = query_api.dataset_range(dataset_id)
if not series or bounds is None:
    ui.empty_state("No series in this dataset", "Upload a CSV with numeric columns to compare.")
    st.stop()

first_day, last_day = bounds[0].date(), bounds[1].date()
series_names = [s["name"] for s in series]
series_ids = {s["name"]: s["id"] for s in series}
series_units = {s["name"]: (s["unit"] or "") for s in series}

series_key = f"cmp-series-{dataset_id}"
if not st.session_state.get(series_key):
    st.session_state[series_key] = series_names[:2]

PERIOD_KEYS = ("cmp-a-start", "cmp-a-end", "cmp-b-start", "cmp-b-end")


def _apply_preset(last_ts: datetime, days: int) -> None:
    a_start, a_end, b_start, b_end = compare_api.preset_windows(last_ts, days)
    st.session_state["cmp-a-start"] = a_start
    st.session_state["cmp-a-end"] = a_end
    st.session_state["cmp-b-start"] = b_start
    st.session_state["cmp-b-end"] = b_end


if any(key not in st.session_state for key in PERIOD_KEYS):
    _apply_preset(bounds[1], 7)
else:
    # Keep the stored windows inside this dataset's range when the dataset changes.
    for key in PERIOD_KEYS:
        value = st.session_state[key]
        if not isinstance(value, date) or value < first_day or value > last_day:
            _apply_preset(bounds[1], 7)
            break

with st.container(border=True):
    st.markdown("#### Periods")
    preset_left, preset_right, preset_note = st.columns([2, 2, 3], vertical_alignment="bottom")
    with preset_left:
        st.button(
            "Last 7 days vs prior 7",
            key="cmp-preset-7",
            on_click=_apply_preset,
            args=(bounds[1], 7),
            width="stretch",
        )
    with preset_right:
        st.button(
            "Last 30 days vs prior 30",
            key="cmp-preset-30",
            on_click=_apply_preset,
            args=(bounds[1], 30),
            width="stretch",
        )
    with preset_note:
        ui.note(f"Newest data point: {ui.fmt_ts(bounds[1].strftime('%Y-%m-%d %H:%M:%S'))}")

    row1, row2, row3, row4, row5 = st.columns([2.4, 1, 1, 1, 1], vertical_alignment="bottom")
    with row1:
        selected = st.multiselect(
            "Series",
            options=series_names,
            key=series_key,
            placeholder="Select one or more series",
        )
    with row2:
        a_start = st.date_input(
            "A start", key="cmp-a-start", min_value=first_day, max_value=last_day
        )
    with row3:
        a_end = st.date_input("A end", key="cmp-a-end", min_value=first_day, max_value=last_day)
    with row4:
        b_start = st.date_input(
            "B start", key="cmp-b-start", min_value=first_day, max_value=last_day
        )
    with row5:
        b_end = st.date_input("B end", key="cmp-b-end", min_value=first_day, max_value=last_day)

if not selected:
    ui.empty_state(
        "Choose at least one series",
        "Select one or more series above. Both periods are aligned to their own hour 0 so the "
        "shapes can be compared directly.",
    )
    st.stop()

if a_start > a_end:
    ui.error_state("Period A is inverted", "Period A: the end date must be on or after the start date.")
    st.stop()
if b_start > b_end:
    ui.error_state("Period B is inverted", "Period B: the end date must be on or after the start date.")
    st.stop()
if a_start <= b_end and b_start <= a_end:
    ui.error_state(
        "Periods overlap",
        "Windows A and B must not overlap. Shift one of the periods so the comparison stays honest.",
    )
    st.stop()

try:
    with st.spinner("Comparing periods…"):
        result = compare_api.periods(
            dataset_id,
            [series_ids[name] for name in selected],
            a_start,
            a_end,
            b_start,
            b_end,
        )
except compare_api.CompareError as exc:
    ui.error_state("Comparison rejected", str(exc))
    st.stop()

summary = result["summary"]
lead = summary[0] if summary else None
if lead:
    unit = series_units.get(lead["series"]) or ""
    ui.stat_cards(
        [
            {
                "label": f"mean A · {lead['series']}",
                "value": ui.fmt_number(lead["mean_a"], 2),
                "unit": unit,
                "note": f"{lead['count_a']:,} points in period A.",
            },
            {
                "label": f"mean B · {lead['series']}",
                "value": ui.fmt_number(lead["mean_b"], 2),
                "unit": unit,
                "note": f"{lead['count_b']:,} points in period B.",
            },
            {
                "label": "change",
                "value": ui.fmt_pct(lead["pct_change"]),
                "note": f"Δ {ui.fmt_number(lead['delta'], 2)} {unit}".strip(),
                "tone": "alert" if lead["pct_change"] < 0 else "ok",
            },
            {
                "label": "series compared",
                "value": f"{len(summary)}",
                "note": f"{a_start:%d %b} – {a_end:%d %b} vs {b_start:%d %b} – {b_end:%d %b}",
            },
        ]
    )

figure = go.Figure()
for index, row in enumerate(summary):
    frame = result["frames"].get(row["series"])
    if frame is None or frame.empty:
        continue
    colour = ui.series_colour(index)
    unit = series_units.get(row["series"]) or ""
    suffix = f" ({unit})" if unit else ""
    figure.add_trace(
        go.Scatter(
            x=frame["elapsed_hours"],
            y=frame["period_a"],
            mode="lines",
            name=f"{row['series']} · A{suffix}",
            line=dict(color=colour, width=2.4),
            hovertemplate="hour %{x:.0f}<br>period A %{y:,.2f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=frame["elapsed_hours"],
            y=frame["period_b"],
            mode="lines",
            name=f"{row['series']} · B{suffix}",
            line=dict(color=colour, width=1.6, dash="dot"),
            hovertemplate="hour %{x:.0f}<br>period B %{y:,.2f}<extra></extra>",
        )
    )

ui.style_figure(
    figure,
    height=430,
    x_title="Elapsed hours from period start",
    y_title=series_units.get(selected[0]) or None,
)
st.plotly_chart(figure, theme=None, config={"displayModeBar": False})
ui.note("Solid line = period A, dotted line = period B. Both start at hour 0 of their own window.")

with st.container(border=True):
    st.markdown("#### Per-series summary")
    summary_frame = pd.DataFrame(
        [
            {
                "Series": row["series"],
                "Mean A": round(row["mean_a"], 2) if row["mean_a"] == row["mean_a"] else None,
                "Mean B": round(row["mean_b"], 2) if row["mean_b"] == row["mean_b"] else None,
                "Delta": round(row["delta"], 2) if row["delta"] == row["delta"] else None,
                "% change": (
                    f"{row['pct_change']:+.2f}%"
                    if row["pct_change"] == row["pct_change"]
                    else "—"
                ),
                "Points A": row["count_a"],
                "Points B": row["count_b"],
            }
            for row in summary
        ]
    )
    st.dataframe(
        summary_frame,
        hide_index=True,
        column_config={
            "Mean A": st.column_config.NumberColumn(format="%.2f"),
            "Mean B": st.column_config.NumberColumn(format="%.2f"),
            "Delta": st.column_config.NumberColumn(format="%.2f"),
            "Points A": st.column_config.NumberColumn(format="%d"),
            "Points B": st.column_config.NumberColumn(format="%d"),
        },
    )
    ui.note(
        f"Period A: {ui.fmt_ts(a_start)} → {ui.fmt_ts(a_end)} · "
        f"Period B: {ui.fmt_ts(b_start)} → {ui.fmt_ts(b_end)}"
    )

with st.expander("How the comparison is aligned"):
    st.markdown(
        "- Each period is resampled to hourly means and re-indexed on hours elapsed since the "
        "period's own start, so both curves begin at hour 0.\n"
        "- `Δ` is `mean B − mean A`; `% change` is `Δ / mean A × 100`.\n"
        "- Windows must not overlap, and each period's end must be on or after its start."
    )

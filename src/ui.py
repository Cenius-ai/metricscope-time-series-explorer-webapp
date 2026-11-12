"""Shared shell, styling, auth gate and small presentation helpers."""

from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from . import config, seed
from .api import auth as auth_api

TOKEN_KEY = "ms_token"
COOKIE_NAME = "ms_token"
COOKIE_WRITTEN_KEY = "ms_cookie_written"
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
ERROR_KEY = "ms_auth_error"
BUSY_KEY = "ms_busy"

CSS_PATH = config.PROJECT_ROOT / "static" / "app.css"
FAVICON = str(config.PROJECT_ROOT / "static" / "favicon.png")


# --------------------------------------------------------------------------- #
# boot + styling
# --------------------------------------------------------------------------- #


@st.cache_resource(show_spinner=False)
def _bootstrap_cached(db_path: str) -> str:
    seed.ensure_seeded(db_path)
    return db_path


def bootstrap() -> None:
    """Create the schema and seed demo data once per server process."""
    _bootstrap_cached(str(config.DB_PATH))


@st.cache_data(show_spinner=False)
def _css_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def inject_styles() -> None:
    st.markdown(f"<style>{_css_text(str(CSS_PATH))}</style>", unsafe_allow_html=True)


def page_config(title: str) -> None:
    st.set_page_config(
        page_title=title,
        page_icon=FAVICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )


# --------------------------------------------------------------------------- #
# session + auth gate
# --------------------------------------------------------------------------- #


def _cookie_token() -> str | None:
    """Session token remembered in the browser cookie (survives a page reload)."""
    try:
        value = st.context.cookies.get(COOKIE_NAME)
    except (KeyError, AttributeError, RuntimeError):
        return None
    return value if isinstance(value, str) and TOKEN_PATTERN.match(value) else None


def _browser_cookie_script(value: str, max_age: int) -> str:
    return (
        "<script>document.cookie = "
        f"'{COOKIE_NAME}={value}; path=/; max-age={max_age}; SameSite=Lax';</script>"
    )


def remember_session(token: str) -> None:
    """Write the token to a first-party cookie once per browser session."""
    if st.session_state.get(COOKIE_WRITTEN_KEY) or not TOKEN_PATTERN.match(token):
        return
    st.session_state[COOKIE_WRITTEN_KEY] = True
    st.iframe(_browser_cookie_script(token, config.SESSION_TTL_DAYS * 86400), height=1)


def forget_session_cookie() -> None:
    st.iframe(_browser_cookie_script("", 0), height=1)


def session_token() -> str | None:
    raw = st.query_params.get("token")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    token = raw or st.session_state.get(TOKEN_KEY) or _cookie_token()
    if token:
        st.session_state[TOKEN_KEY] = token
    return token


def resolve_user() -> dict | None:
    token = session_token()
    if not token:
        return None
    try:
        return auth_api.session(token)
    except auth_api.Unauthorized:
        st.session_state.pop(TOKEN_KEY, None)
        return None


def _complete_login(identifier: str, password: str) -> None:
    if st.session_state.get(BUSY_KEY):
        return
    st.session_state[BUSY_KEY] = True
    try:
        result = auth_api.login(identifier, password)
    except ValueError:
        st.session_state[ERROR_KEY] = auth_api.INVALID_CREDENTIALS
        st.session_state[BUSY_KEY] = False
        return
    st.session_state[TOKEN_KEY] = result["token"]
    st.query_params["token"] = result["token"]
    st.session_state.pop(ERROR_KEY, None)
    st.session_state[BUSY_KEY] = False
    st.rerun()


def sign_out() -> None:
    """Delete the session row, drop the URL token and the browser cookie."""
    token = st.session_state.get(TOKEN_KEY) or session_token()
    auth_api.logout(token)
    st.session_state.pop(TOKEN_KEY, None)
    st.session_state.pop(BUSY_KEY, None)
    st.session_state.pop(ERROR_KEY, None)
    st.session_state.pop(COOKIE_WRITTEN_KEY, None)
    forget_session_cookie()
    st.query_params.clear()
    st.rerun()


def render_sign_in() -> None:
    """Sign-in card: one non-enumerating error message plus the demo hint."""
    _, center, _ = st.columns([1, 1.55, 1])
    with center:
        brand_bar()
        st.markdown(
            '<div class="ms-kicker">Sign in</div>'
            '<h1 class="ms-h1">Explore 90 days of metrics in a minute</h1>'
            '<p class="ms-sub">Metricscope is a Grafana-lite CSV explorer: pick or upload a'
            " dataset, resample it, roll it, flag z-score anomalies, and compare two"
            " periods. Everything runs locally against a seeded SQLite database.</p>",
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            st.markdown(
                '<div class="ms-demo">Demo: <code>cenius@cenius.ai</code> /'
                " <code>cenius</code><br>"
                "Both fields accept the demo username <code>cenius</code> as well.</div>",
                unsafe_allow_html=True,
            )
            with st.form("ms-sign-in", border=False):
                identifier = st.text_input(
                    "Username or email",
                    key="ms-identifier",
                    placeholder="cenius@cenius.ai",
                    autocomplete="username",
                )
                password = st.text_input(
                    "Password",
                    type="password",
                    key="ms-password",
                    placeholder="cenius",
                    autocomplete="current-password",
                )
                submitted = st.form_submit_button("Sign in", type="primary")

            if submitted:
                _complete_login(identifier, password)

            error = st.session_state.get(ERROR_KEY)
            if error:
                st.error(error)

            if st.button("Sign in with the demo account", key="ms-demo-signin"):
                _complete_login(config.DEMO_EMAIL, config.DEMO_PASSWORD)
        st.markdown(
            '<p class="ms-note">Demo accounts are for evaluation only — remove them before a'
            " production deploy.</p>",
            unsafe_allow_html=True,
        )


def gate(kicker: str, heading: str, subtitle: str) -> dict:
    """Standard page prologue: styles, seed, auth gate, brand bar, page heading."""
    bootstrap()
    inject_styles()
    user = resolve_user()
    if user is None:
        # Signing in reruns this page, so the user lands on the route they asked for.
        render_sign_in()
        st.stop()
    if session_token():
        remember_session(session_token() or "")
    brand_bar()
    page_heading(kicker, heading, subtitle, user)
    return user


# --------------------------------------------------------------------------- #
# chrome
# --------------------------------------------------------------------------- #


def brand_bar() -> None:
    st.markdown(
        '<div class="ms-bar">'
        '<span class="ms-mark" aria-hidden="true">M</span>'
        f'<span class="ms-brand">{config.APP_NAME}</span>'
        '<span class="ms-brand-tag">time-series explorer</span>'
        '<span class="ms-live"><span class="ms-live-dot" aria-hidden="true"></span>'
        "seeded 90-day window</span>"
        "</div>",
        unsafe_allow_html=True,
    )


def page_heading(kicker: str, heading: str, subtitle: str, user: dict) -> None:
    left, right = st.columns([3.2, 1], vertical_alignment="bottom")
    with left:
        st.markdown(
            f'<div class="ms-kicker">{html.escape(kicker)}</div>'
            f'<h1 class="ms-h1">{html.escape(heading)}</h1>'
            f'<p class="ms-sub">{html.escape(subtitle)}</p>',
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            f'<div class="ms-user">signed in as <strong>{html.escape(user["username"])}</strong></div>',
            unsafe_allow_html=True,
        )
        if st.button("Sign out", key="ms-sign-out", type="tertiary"):
            sign_out()


# --------------------------------------------------------------------------- #
# presentational blocks
# --------------------------------------------------------------------------- #


def stat_cards(items: list[dict]) -> None:
    """Elevation-tier cards whose label rides a flag callout (the signature move)."""
    blocks = ['<div class="ms-stats" role="list">']
    for item in items:
        tone = item.get("tone", "")
        chip_class = "ms-chip" + (f" ms-chip--{tone}" if tone in {"alert", "ok"} else "")
        unit = f'<span class="ms-stat-unit">{html.escape(str(item["unit"]))}</span>' if item.get("unit") else ""
        note = item.get("note") or ""
        blocks.append(
            '<div class="ms-stat" role="listitem">'
            '<div class="ms-flag"><span class="ms-flag-line" aria-hidden="true"></span>'
            f'<span class="{chip_class}">{html.escape(str(item["label"]))}</span></div>'
            f'<div class="ms-stat-value">{html.escape(str(item["value"]))}{unit}</div>'
            f'<div class="ms-stat-note">{html.escape(str(note))}</div>'
            "</div>"
        )
    blocks.append("</div>")
    st.markdown("".join(blocks), unsafe_allow_html=True)


def empty_state(title: str, body: str) -> None:
    st.markdown(
        f'<div class="ms-state"><h3>{html.escape(title)}</h3>'
        f"<p>{html.escape(body)}</p></div>",
        unsafe_allow_html=True,
    )


def error_state(title: str, body: str) -> None:
    st.markdown(
        f'<div class="ms-state ms-state--error"><h3>{html.escape(title)}</h3>'
        f"<p>{html.escape(body)}</p></div>",
        unsafe_allow_html=True,
    )


def note(text: str) -> None:
    st.markdown(f'<p class="ms-note">{html.escape(text)}</p>', unsafe_allow_html=True)


def pill_row(pills: list[str]) -> None:
    inner = "".join(f'<span class="ms-pill">{html.escape(p)}</span>' for p in pills)
    st.markdown(f'<div class="ms-pill-row">{inner}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# formatting
# --------------------------------------------------------------------------- #


def fmt_number(value, decimals: int = 0) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number != number or number in (float("inf"), float("-inf")):
        return "—"
    return f"{number:,.{decimals}f}"


def fmt_pct(value, decimals: int = 1) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number != number:
        return "—"
    return f"{number:+,.{decimals}f}%"


def fmt_ts(value) -> str:
    """Humanise a stored timestamp: '12 Nov 2026, 14:00 UTC'."""
    if value is None:
        return "—"
    text = str(value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.strftime("%d %b %Y, %H:%M UTC") if "%H" in fmt else parsed.strftime("%d %b %Y")
        except ValueError:
            continue
    return text


# --------------------------------------------------------------------------- #
# charts
# --------------------------------------------------------------------------- #


def style_figure(
    fig: go.Figure,
    height: int = 400,
    y_title: str | None = None,
    x_title: str | None = None,
) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=52, r=18, t=28, b=42),
        paper_bgcolor="#fdffff",
        plot_bgcolor="#fdffff",
        font=dict(family="IBM Plex Mono, monospace", size=12, color="#0b1512"),
        colorway=list(config.CHART_COLORS),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#13231f", font=dict(color="#ffffff", family="IBM Plex Mono, monospace")),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=11)),
        showlegend=True,
    )
    fig.update_xaxes(
        gridcolor="#e8efec",
        linecolor="#d9e0de",
        zeroline=False,
        tickfont=dict(size=11, color="#5a6663"),
        title_text=x_title,
    )
    fig.update_yaxes(
        gridcolor="#e8efec",
        linecolor="#d9e0de",
        zeroline=False,
        tickfont=dict(size=11, color="#5a6663"),
        title_text=y_title,
    )
    return fig


def series_colour(index: int) -> str:
    return config.CHART_COLORS[index % len(config.CHART_COLORS)]


def render_table(frame: pd.DataFrame, height: int | str = "auto") -> None:
    st.dataframe(frame, hide_index=True, height=height)

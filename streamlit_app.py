"""Metricscope Time-Series Explorer — entry point (sign in)."""

from __future__ import annotations

import streamlit as st

from src import ui

ui.page_config("Sign in · Metricscope Time-Series Explorer")
ui.bootstrap()
ui.inject_styles()

if ui.resolve_user():
    st.switch_page("pages/Explorer.py")

ui.render_sign_in()

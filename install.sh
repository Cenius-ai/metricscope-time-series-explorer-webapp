#!/usr/bin/env bash
# Metricscope Time-Series Explorer — dependency install + database seed.
# Runs unprivileged, installs only project dependencies, and EXITS.
# It never starts the web server. Works under both `sh install.sh` and
# `bash install.sh` (no bash-only features are used).

set -eu
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_INPUT=1

echo "==> Using $("$PYTHON" --version)"
echo "==> Upgrading packaging tools"
"$PYTHON" -m pip install --quiet --upgrade pip setuptools wheel

echo "==> Installing project dependencies from requirements.txt"
"$PYTHON" -m pip install --quiet -r requirements.txt

echo "==> Creating the SQLite schema and seeding demo data"
"$PYTHON" -m src.seed

echo "==> Verifying the app modules import cleanly"
"$PYTHON" -c "import streamlit, pandas, numpy, plotly, src.ui, src.seed, src.api.query"

echo
echo "Install complete."
echo "Start the app with:"
echo "  streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true"

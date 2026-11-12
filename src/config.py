"""Runtime configuration for Metricscope Time-Series Explorer.

Every value has a working default so the app boots from a fresh clone with no
.env file present.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    candidate = Path(raw).expanduser()
    return candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate).resolve()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


APP_NAME = "Metricscope"
APP_TAGLINE = "Time-Series Explorer"

DATA_DIR = _env_path("METRICSCOPE_DATA_DIR", PROJECT_ROOT / "data")
DB_PATH = _env_path("METRICSCOPE_DB_PATH", DATA_DIR / "metricscope.db")
SCHEMA_PATH = PROJECT_ROOT / "src" / "schema.sql"

MAX_UPLOAD_MB = _env_int("METRICSCOPE_MAX_UPLOAD_MB", 25)
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
SESSION_TTL_DAYS = _env_int("METRICSCOPE_SESSION_TTL_DAYS", 7)
PBKDF2_ITERATIONS = 240_000

DEMO_USERNAME = "cenius"
DEMO_EMAIL = "cenius@cenius.ai"
DEMO_PASSWORD = "cenius"

# Committed chart palette (hex only — chart libraries cannot parse oklch()).
CHART_COLORS = ("#3fbf86", "#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00")
ACCENT_HEX = CHART_COLORS[0]

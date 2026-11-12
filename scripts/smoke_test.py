"""End-to-end smoke test.

1. Proves first boot creates the schema, the demo users and three seeded
   datasets, and that a second boot does not duplicate any of it.
2. Loads the sign-in page and every multipage screen through Streamlit's
   AppTest harness and checks each renders without an exception.
3. Signs in through the real form and asserts the app leaves the sign-in wall.

Run with:  python3 scripts/smoke_test.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORKDIR = Path(tempfile.mkdtemp(prefix="metricscope-smoke-"))
os.environ["METRICSCOPE_DB_PATH"] = str(WORKDIR / "smoke.db")

from streamlit.testing.v1 import AppTest  # noqa: E402

from src import db, seed  # noqa: E402
from src.api import auth as auth_api  # noqa: E402

PAGES = {
    "Data": ("pages/Data.py", "Upload a metric file"),
    "Library": ("pages/Library.py", "Dataset library"),
    "Explorer": ("pages/Explorer.py", "Multi-series explorer"),
    "Compare": ("pages/Compare.py", "Two-period comparison"),
}


def fail(message: str) -> None:
    print(f"SMOKE FAIL: {message}")
    raise SystemExit(1)


def check_seeding() -> str:
    first = seed.ensure_seeded()
    if first["datasets"] != 3:
        fail(f"first boot created {first['datasets']} datasets, expected 3")

    with db.get_conn() as conn:
        counts = {t: db.count(conn, t) for t in ("users", "sessions", "datasets", "series", "points")}
    if counts["users"] < 2:
        fail(f"expected at least 2 demo users, found {counts['users']}")
    if counts["datasets"] != 3 or counts["series"] != 12:
        fail(f"unexpected seed shape: {counts}")

    second = seed.ensure_seeded()
    if second["datasets"] != 0 or second["points"] != 0 or second["users"] != 0:
        fail(f"second boot was not idempotent: {second}")

    with db.get_conn() as conn:
        again = {t: db.count(conn, t) for t in ("users", "datasets", "series", "points")}
    if again != {k: counts[k] for k in again}:
        fail(f"seed duplicated rows: {counts} -> {again}")

    print(f"  seed ok: {counts['datasets']} datasets, {counts['series']} series, "
          f"{counts['points']} points, {counts['users']} users")
    return first["anchor"]


def app_text(app: AppTest) -> str:
    chunks: list[str] = []
    for element in list(app.markdown) + list(app.title) + list(app.header) + list(app.subheader):
        value = getattr(element, "value", "")
        if isinstance(value, str):
            chunks.append(value)
    return "\n".join(chunks)


def check_sign_in_page() -> None:
    app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=120).run()
    if app.exception:
        fail(f"sign-in page raised: {app.exception[0].value}")
    text = app_text(app)
    if "cenius@cenius.ai" not in text or "cenius" not in text:
        fail("sign-in page is missing the demo credential hint")
    print("  sign-in page renders with the demo hint")


def check_sign_in_flow() -> str:
    app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=120).run()
    app.text_input[0].set_value("cenius")
    app.text_input[1].set_value("cenius")
    app.button[0].click()
    app.run()
    if app.exception:
        fail(f"sign-in form raised: {app.exception[0].value}")
    text = app_text(app)
    if "Multi-series explorer" not in text:
        fail("signing in did not reach the Explorer page")
    print("  sign-in form reaches the Explorer page")
    return "authed"


def check_pages(token: str) -> None:
    for name, (relative, heading) in PAGES.items():
        app = AppTest.from_file(str(ROOT / relative), default_timeout=120)
        app.session_state["ms_token"] = token
        app.run()
        if app.exception:
            fail(f"{name} page raised: {app.exception[0].value}")
        text = app_text(app)
        if heading not in text:
            fail(f"{name} page did not render its heading")
        if name in {"Explorer", "Compare"} and not app.get("plotly_chart"):
            fail(f"{name} page rendered no chart")
        print(f"  {name} page renders ({len(text)} chars of copy)")


def check_unauthorised_gate() -> None:
    app = AppTest.from_file(str(ROOT / "pages/Explorer.py"), default_timeout=120).run()
    if app.exception:
        fail(f"gated Explorer raised: {app.exception[0].value}")
    text = app_text(app)
    if "cenius@cenius.ai" not in text:
        fail("unauthenticated Explorer did not fall back to the sign-in card")
    print("  unauthenticated page access falls back to sign-in")


def main() -> int:
    print("Metricscope smoke test")
    anchor = check_seeding()
    print(f"  seed anchor: {anchor} UTC")
    check_sign_in_page()
    check_unauthorised_gate()
    check_sign_in_flow()
    token = auth_api.login("cenius", "cenius")["token"]
    check_pages(token)
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

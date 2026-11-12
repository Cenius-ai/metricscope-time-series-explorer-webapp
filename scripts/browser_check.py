"""Optional real-browser check (maintainers only).

Requires Playwright, which is NOT a project dependency:

    pip install playwright && python -m playwright install chromium
    streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=8501 &
    python3 scripts/browser_check.py

It logs in with the demo credential through the auth contract selectors, walks
every page at desktop and phone widths, and fails on console errors, horizontal
scroll, missing Plex fonts, leaked placeholder values or a broken upload.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

# Playwright is an OPTIONAL maintainer tool, not an application dependency: the
# app, the test suite and the smoke test all run without it. Install it with
#   python3 -m pip install -r requirements-dev.txt
try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - optional tooling
    sync_playwright = None

# Target origin: override with METRICSCOPE_BASE_URL for a remote or split deploy
# (e.g. METRICSCOPE_BASE_URL=https://metricscope.example.com). The localhost
# default keeps `streamlit run ...` on the default port working out of the box.
BASE = os.environ.get("METRICSCOPE_BASE_URL", "http://127.0.0.1:8501").rstrip("/")
ROOT = Path(__file__).resolve().parent.parent
CONTRACT = json.loads((ROOT / ".cenius" / "auth_contract.json").read_text())
PAGES = ["/Data", "/Library", "/Explorer", "/Compare"]
SHOTS = ROOT / "out" / "browser-shots"
SHOTS.mkdir(parents=True, exist_ok=True)

problems: list[str] = []


def probe(page) -> dict:
    return page.evaluate(
        """() => {
            const bodyText = (document.querySelector('main') || document.body).innerText;
            return {
                scrollW: document.documentElement.scrollWidth,
                innerW: window.innerWidth,
                bodyFont: getComputedStyle(document.body).fontFamily,
                plexMono: document.fonts.check('12px "IBM Plex Mono"'),
                plexSans: document.fonts.check('16px "IBM Plex Sans"'),
                h1: (document.querySelector('h1') || {}).innerText || '',
                charts: document.querySelectorAll('[data-testid="stPlotlyChart"]').length,
                tables: document.querySelectorAll('[data-testid="stDataFrame"]').length,
                leak: (bodyText.match(/\\b(nan|NaN|None|undefined|Invalid Date)\\b/) || [''])[0],
                chars: bodyText.trim().length,
            };
        }"""
    )


def main() -> int:
    if sync_playwright is None:
        print(
            "scripts/browser_check.py needs the optional Playwright tooling.\n"
            "Install it with: python3 -m pip install -r requirements-dev.txt\n"
            "                  python3 -m playwright install chromium"
        )
        return 1

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on(
            "console",
            lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None,
        )

        page.goto(BASE, wait_until="networkidle")
        page.wait_for_selector(CONTRACT["email_selector"], timeout=60000)
        page.fill(CONTRACT["email_selector"], CONTRACT["demo_email"])
        page.fill(CONTRACT["password_selector"], CONTRACT["demo_password"])
        page.click(CONTRACT["submit_selector"])
        page.wait_for_url("**/Explorer", timeout=60000)
        page.wait_for_timeout(3500)
        print("post-login url:", page.url)

        for route in PAGES + ["/"]:
            page.goto(BASE + route, wait_until="networkidle")
            page.wait_for_timeout(3000)
            info = probe(page)
            print(route, "->", page.url, json.dumps(info))
            if info["scrollW"] > info["innerW"] + 1:
                problems.append(f"{route}: horizontal scroll {info['scrollW']} > {info['innerW']}")
            if info["leak"]:
                problems.append(f"{route}: leaked placeholder {info['leak']}")
            if info["chars"] < 200:
                problems.append(f"{route}: too little visible text ({info['chars']} chars)")
            if not (info["plexMono"] and info["plexSans"]):
                problems.append(f"{route}: IBM Plex fonts not loaded ({info['bodyFont']})")
            if route in {"/Explorer", "/Compare"} and info["charts"] < 1:
                problems.append(f"{route}: no chart rendered")
            page.screenshot(path=str(SHOTS / f"{route.strip('/') or 'signin'}-1280.png"))

        # create path: upload a CSV and confirm it persists on a full reload
        page.goto(BASE + "/Data", wait_until="networkidle")
        page.wait_for_timeout(2500)
        rows = "\n".join(
            f"2026-11-{1 + i // 24:02d} {i % 24:02d}:00:00,{200 + (i * 7) % 90},{0.2 + (i % 5) / 10}"
            for i in range(72)
        )
        csv_path = Path(tempfile.mkdtemp()) / "browser_check_upload.csv"
        csv_path.write_text("timestamp,checkout_latency_ms,error_rate\n" + rows + "\n")
        page.locator('input[type="file"]').first.set_input_files(str(csv_path))
        page.wait_for_timeout(4000)
        page.get_by_role("button", name="Save dataset").click()
        page.wait_for_timeout(4000)
        if "Saved" not in page.inner_text("body"):
            problems.append("upload commit produced no success message")

        page.goto(BASE + "/Library", wait_until="networkidle")
        page.wait_for_timeout(3000)
        if "browser check upload" not in page.inner_text("body").lower():
            problems.append("uploaded dataset did not persist into the Library")
        page.screenshot(path=str(SHOTS / "library-after-upload-1280.png"))

        phone = browser.new_context(viewport={"width": 390, "height": 844})
        phone_page = phone.new_page()
        for route in PAGES:
            phone_page.goto(BASE + route, wait_until="networkidle")
            phone_page.wait_for_timeout(2500)
            metrics = phone_page.evaluate(
                "() => ({sw: document.documentElement.scrollWidth, iw: window.innerWidth})"
            )
            print("phone", route, metrics)
            if metrics["sw"] > metrics["iw"] + 1:
                problems.append(f"phone {route}: horizontal scroll {metrics['sw']} > {metrics['iw']}")
            phone_page.screenshot(path=str(SHOTS / f"{route.strip('/')}-390.png"))
        phone.close()

        if errors:
            problems.append("browser errors: " + " | ".join(sorted(set(errors))[:6]))
        browser.close()

    print("\nPROBLEMS:" if problems else "\nBROWSER OK")
    for item in problems:
        print(" -", item)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

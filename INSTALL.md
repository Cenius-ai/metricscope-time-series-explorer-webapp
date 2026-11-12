# Install

Metricscope Time-Series Explorer is a single Streamlit application with one
SQLite file. There is no database server, no Node build step and no container.

## Prerequisites

* **Python 3.11** (3.10+ works) with `pip` available as `python3 -m pip`.
* A writable project directory (the app creates `./data/metricscope.db`).
* No system packages beyond the Python toolchain — every wheel in
  `requirements.txt` is pure-Python or has a manylinux wheel.

Check your interpreter:

```bash
python3 --version    # expect Python 3.11.x
```

## 1. Install dependencies and seed the database

```bash
sh install.sh
```

The script installs the pinned dependencies from `requirements.txt`, creates the
SQLite schema, seeds the demo users and the three demo datasets, and then
**exits** — it never starts the web server. It is safe to run repeatedly.

If you prefer to do it by hand:

```bash
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -r requirements.txt
python3 -m src.seed          # create schema + seed demo data (idempotent)
```

`python3 -m src.seed` prints the seed anchor and every documented anomaly
timestamp for the database it just seeded.

## 2. Run the app

```bash
streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true
```

Open <http://localhost:8501> and sign in with **cenius@cenius.ai / cenius**
(the sign-in card shows the demo credential).

`--server.address=0.0.0.0` is required for the app to be reachable from another
host; `--server.headless=true` stops Streamlit from trying to open a browser.

The app also self-heals: if the database file is missing it is created and
seeded on the first page load, so a bare `streamlit run streamlit_app.py` works
once the dependencies are installed.

## 3. Verify

```bash
python3 -m pytest                 # unit + integration tests
python3 scripts/smoke_test.py     # seeding + all five screens, prints SMOKE OK
```

`scripts/browser_check.py` is an optional maintainer walkthrough (Playwright).
It is the only file that needs anything beyond `requirements.txt`:

```bash
python3 -m pip install -r requirements-dev.txt   # optional
python3 -m playwright install chromium           # optional
```

## Configuration

No `.env` file is needed. Copy `.env.example` to `.env` only if you want to
override a default; the shell that starts Streamlit must export those variables
(`set -a; . ./.env; set +a`).

| Variable | Default | Meaning |
| --- | --- | --- |
| `METRICSCOPE_DB_PATH` | `./data/metricscope.db` | SQLite file (relative to the project root) |
| `METRICSCOPE_SESSION_TTL_DAYS` | `7` | Session lifetime in days |
| `METRICSCOPE_MAX_UPLOAD_MB` | `25` | Upload size guard |

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `ModuleNotFoundError: streamlit` | Run `sh install.sh` first (or `python3 -m pip install -r requirements.txt`). |
| `Port 8501 is already in use` | Stop the other process or run with `--server.port=8502`. |
| Page loads but every table is empty | The database was emptied by hand: run `python3 -m src.seed`. Deleting seeded datasets is otherwise harmless — they are recreated on the next process start. |
| Sign-in says *Invalid username or password* | Use `cenius@cenius.ai` or the username `cenius`; both accept the password `cenius`. Re-run `python3 -m src.seed` if the demo user is missing. |
| Fonts look like a generic monospace | The vendored faces live in `static/fonts/` and are declared in `.streamlit/config.toml`; make sure the app is started from the project root. |

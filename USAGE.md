# Using Metricscope Time-Series Explorer

## Overview

This is **Metricscope Time-Series Explorer** — an importable library / package. This document covers the surface area you can use, with copy-pasteable examples for each entry point. For setup, see `INSTALL.md`.

## Quickstart

```python
# After `pip install this-package`:
import this_package

# Inspect the public API:
print(dir(this_package))
```

## Public API

**65** public symbols were detected at the library surface.

| Symbol | Source |
|--------|--------|
| `flag_frame` | `src/anomaly.py` |
| `flag_mask` | `src/anomaly.py` |
| `summarise` | `src/anomaly.py` |
| `zscores` | `src/anomaly.py` |
| `auth` | `src/api/__init__.py` |
| `compare` | `src/api/__init__.py` |
| `datasets` | `src/api/__init__.py` |
| `query` | `src/api/__init__.py` |
| `upload` | `src/api/__init__.py` |
| `AuthError` | `src/auth.py` |
| `authenticate` | `src/auth.py` |
| `create_session` | `src/auth.py` |
| `create_user` | `src/auth.py` |
| `hash_password` | `src/auth.py` |
| `normalise_identifier` | `src/auth.py` |
| `revoke_session` | `src/auth.py` |
| `session_user` | `src/auth.py` |
| `verify_password` | `src/auth.py` |
| `connect` | `src/db.py` |
| `connection` | `src/db.py` |
| `count` | `src/db.py` |
| `get_conn` | `src/db.py` |
| `init_db` | `src/db.py` |
| `iso` | `src/db.py` |
| `tables` | `src/db.py` |
| `utcnow` | `src/db.py` |
| `ParsedUpload` | `src/ingest.py` |
| `UploadError` | `src/ingest.py` |
| `dataset_name_from_filename` | `src/ingest.py` |
| `iter_points` | `src/ingest.py` |

_… and 35 more (truncated)._

### Import examples

```python
# After `pip install this-package`:
import this_package

# Inspect the public API:
print(dir(this_package))
```

## Worked example

1. Install: `pip install this-package` (Python) / `npm install this-package` (Node) — see the Import examples section above for the right command for your language.
2. Import + call the public surface in your own code.
3. Run your test suite to verify the integration before shipping.

## Reference

### Entry points

_No explicit entry points declared in this project's manifests._

### Surface index (auto-extracted)

| Kind | Title | Source file |
|------|-------|-------------|
| function | `flag_frame` | `src/anomaly.py` |
| function | `flag_mask` | `src/anomaly.py` |
| function | `summarise` | `src/anomaly.py` |
| function | `zscores` | `src/anomaly.py` |
| function | `auth` | `src/api/__init__.py` |
| function | `compare` | `src/api/__init__.py` |
| function | `datasets` | `src/api/__init__.py` |
| function | `query` | `src/api/__init__.py` |
| function | `upload` | `src/api/__init__.py` |
| function | `AuthError` | `src/auth.py` |
| function | `authenticate` | `src/auth.py` |
| function | `create_session` | `src/auth.py` |
| function | `create_user` | `src/auth.py` |
| function | `hash_password` | `src/auth.py` |
| function | `normalise_identifier` | `src/auth.py` |
| function | `revoke_session` | `src/auth.py` |
| function | `session_user` | `src/auth.py` |
| function | `verify_password` | `src/auth.py` |
| function | `connect` | `src/db.py` |
| function | `connection` | `src/db.py` |
| function | `count` | `src/db.py` |
| function | `get_conn` | `src/db.py` |
| function | `init_db` | `src/db.py` |
| function | `iso` | `src/db.py` |
| function | `tables` | `src/db.py` |
| function | `utcnow` | `src/db.py` |
| function | `ParsedUpload` | `src/ingest.py` |
| function | `UploadError` | `src/ingest.py` |
| function | `dataset_name_from_filename` | `src/ingest.py` |
| function | `iter_points` | `src/ingest.py` |
| function | `parse_csv` | `src/ingest.py` |
| function | `preview_frame` | `src/ingest.py` |
| function | `DatasetSpec` | `src/seed.py` |
| function | `SeriesSpec` | `src/seed.py` |
| function | `anomaly_catalogue` | `src/seed.py` |
| function | `build_series_values` | `src/seed.py` |
| function | `default_anchor` | `src/seed.py` |
| function | `ensure_seeded` | `src/seed.py` |
| function | `main` | `src/seed.py` |
| function | `seed_datasets` | `src/seed.py` |
| function | `seed_if_empty` | `src/seed.py` |
| function | `seed_users` | `src/seed.py` |
| function | `bootstrap` | `src/ui.py` |
| function | `brand_bar` | `src/ui.py` |
| function | `empty_state` | `src/ui.py` |
| function | `error_state` | `src/ui.py` |
| function | `fmt_number` | `src/ui.py` |
| function | `fmt_pct` | `src/ui.py` |
| function | `fmt_ts` | `src/ui.py` |
| function | `forget_session_cookie` | `src/ui.py` |

_… and 15 more entries (truncated)._

## Next steps

- Read [INSTALL.md](./INSTALL.md) if anything in the Quickstart didn't work.
- Inspect `.env.example` for the full list of environment variables this project understands.
- See [README.md](./README.md) for the architecture diagram + feature list.

"""Deterministic first-boot seed data with documented injected anomaly spikes.

The seed window is 90 days of hourly points ending today (UTC). Each series is
built from a fixed base level, a daily season, a weekly season, a slow trend and
seeded Gaussian noise, then a handful of documented spikes are injected at
``(day_offset, hour)`` positions measured from the start of the window.

Spike magnitude is expressed in standard deviations of that series' *pre-spike*
values (k = 4.5), so every documented spike lands at a z-score of roughly 4-5 in
its visible window: it is flagged at the default threshold of 3.0 and is not
flagged at a threshold of 10.0.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from . import config, db
from .auth import hash_password, normalise_identifier

WINDOW_DAYS = 90
SPIKE_SIGMA = 4.5

DEMO_USERS = (
    # username, email, password, label
    (config.DEMO_USERNAME, config.DEMO_EMAIL, config.DEMO_PASSWORD, "primary demo analyst"),
    ("demo", "demo@metricscope.dev", "demo1234", "secondary demo analyst"),
)


@dataclass(frozen=True)
class SeriesSpec:
    name: str
    unit: str
    base: float
    daily_amplitude: float
    peak_hour: float
    weekly: tuple[float, ...]
    noise_fraction: float
    trend: float
    decimals: int
    spikes: tuple[tuple[int, int, int], ...] = ()  # (day offset, hour, direction)
    cap: float | None = None


@dataclass(frozen=True)
class DatasetSpec:
    seed_key: str
    name: str
    source_filename: str
    series: tuple[SeriesSpec, ...]


SEED_DATASETS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        seed_key="seed-web-traffic",
        name="Web traffic - marketing site",
        source_filename="web_traffic_hourly.csv",
        series=(
            SeriesSpec(
                name="page_views",
                unit="views",
                base=4_800.0,
                daily_amplitude=0.42,
                peak_hour=14.0,
                weekly=(1.0, 1.03, 1.06, 1.07, 1.02, 0.84, 0.76),
                noise_fraction=0.07,
                trend=0.18,
                decimals=0,
                spikes=((12, 14, 1), (37, 3, 1), (61, 21, 1)),
            ),
            SeriesSpec(
                name="sessions",
                unit="sessions",
                base=1_950.0,
                daily_amplitude=0.38,
                peak_hour=13.0,
                weekly=(1.0, 1.02, 1.05, 1.06, 1.01, 0.86, 0.78),
                noise_fraction=0.08,
                trend=0.15,
                decimals=0,
                spikes=((37, 3, 1),),
            ),
            SeriesSpec(
                name="bounce_rate",
                unit="%",
                base=41.5,
                daily_amplitude=0.09,
                peak_hour=22.0,
                weekly=(1.0, 1.0, 0.99, 0.98, 1.01, 1.03, 1.04),
                noise_fraction=0.03,
                trend=-0.06,
                decimals=2,
                cap=100.0,
                spikes=((61, 21, 1),),
            ),
            SeriesSpec(
                name="cdn_hits",
                unit="hits",
                base=12_400.0,
                daily_amplitude=0.33,
                peak_hour=15.0,
                weekly=(1.0, 1.02, 1.05, 1.06, 1.0, 0.85, 0.77),
                noise_fraction=0.06,
                trend=0.22,
                decimals=0,
                spikes=((12, 14, 1),),
            ),
        ),
    ),
    DatasetSpec(
        seed_key="seed-api-latency",
        name="API latency - checkout service",
        source_filename="checkout_latency_hourly.csv",
        series=(
            SeriesSpec(
                name="p50_latency_ms",
                unit="ms",
                base=168.0,
                daily_amplitude=0.24,
                peak_hour=16.0,
                weekly=(1.0, 1.01, 1.03, 1.04, 1.06, 0.92, 0.88),
                noise_fraction=0.05,
                trend=0.09,
                decimals=1,
                spikes=((9, 16, 1),),
            ),
            SeriesSpec(
                name="p95_latency_ms",
                unit="ms",
                base=412.0,
                daily_amplitude=0.3,
                peak_hour=16.0,
                weekly=(1.0, 1.02, 1.04, 1.05, 1.08, 0.9, 0.87),
                noise_fraction=0.08,
                trend=0.12,
                decimals=1,
                spikes=((9, 16, 1), (44, 11, 1)),
            ),
            SeriesSpec(
                name="p99_latency_ms",
                unit="ms",
                base=786.0,
                daily_amplitude=0.26,
                peak_hour=17.0,
                weekly=(1.0, 1.01, 1.03, 1.04, 1.07, 0.93, 0.9),
                noise_fraction=0.12,
                trend=0.1,
                decimals=1,
                spikes=((44, 11, 1),),
            ),
            SeriesSpec(
                name="error_rate_pct",
                unit="%",
                base=0.62,
                daily_amplitude=0.2,
                peak_hour=18.0,
                weekly=(1.0, 1.0, 1.02, 1.02, 1.05, 0.95, 0.93),
                noise_fraction=0.1,
                trend=0.02,
                decimals=3,
                cap=100.0,
                spikes=((9, 16, 1),),
            ),
        ),
    ),
    DatasetSpec(
        seed_key="seed-cpu-fleet",
        name="CPU utilization - production fleet",
        source_filename="fleet_cpu_hourly.csv",
        series=(
            SeriesSpec(
                name="web_fleet_cpu_pct",
                unit="%",
                base=46.0,
                daily_amplitude=0.34,
                peak_hour=15.0,
                weekly=(1.0, 1.02, 1.05, 1.06, 1.03, 0.9, 0.86),
                noise_fraction=0.06,
                trend=0.05,
                decimals=1,
                cap=100.0,
                spikes=((21, 18, 1),),
            ),
            SeriesSpec(
                name="worker_fleet_cpu_pct",
                unit="%",
                base=61.0,
                daily_amplitude=0.22,
                peak_hour=13.0,
                weekly=(1.0, 1.01, 1.03, 1.04, 1.02, 0.94, 0.91),
                noise_fraction=0.07,
                trend=0.08,
                decimals=1,
                cap=100.0,
                spikes=((21, 18, 1), (55, 6, 1)),
            ),
            SeriesSpec(
                name="db_fleet_cpu_pct",
                unit="%",
                base=38.0,
                daily_amplitude=0.28,
                peak_hour=16.0,
                weekly=(1.0, 1.02, 1.04, 1.05, 1.04, 0.92, 0.89),
                noise_fraction=0.05,
                trend=0.03,
                decimals=1,
                cap=100.0,
                spikes=((55, 6, 1),),
            ),
            SeriesSpec(
                name="cache_fleet_cpu_pct",
                unit="%",
                base=24.0,
                daily_amplitude=0.2,
                peak_hour=14.0,
                weekly=(1.0, 1.0, 1.02, 1.02, 1.01, 0.96, 0.94),
                noise_fraction=0.09,
                trend=0.02,
                decimals=1,
                cap=100.0,
                spikes=((76, 9, -1),),
            ),
        ),
    ),
)


def default_anchor(now: datetime | None = None) -> datetime:
    """Start of the seeded window: today's UTC midnight minus (WINDOW_DAYS - 1)."""
    now = now or datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=WINDOW_DAYS - 1)


def _rng(name: str) -> np.random.RandomState:
    seed = int.from_bytes(name.encode("utf-8")[:8].ljust(8, b"\0"), "little") % (2**32)
    return np.random.RandomState(seed)


def build_series_values(spec: SeriesSpec, anchor: datetime) -> list[tuple[str, float]]:
    """Generate the hourly points for one series, including its injected spikes."""
    hours = WINDOW_DAYS * 24
    rng = _rng(spec.name)
    weekday = np.array(spec.weekly, dtype=float)

    t = np.arange(hours, dtype=float)
    hour_of_day = t % 24
    day_of_week = ((t // 24).astype(int) + anchor.weekday()) % 7
    daily = 1.0 + spec.daily_amplitude * np.sin(2 * np.pi * (hour_of_day - spec.peak_hour) / 24.0)
    trend = 1.0 + spec.trend * (t / max(hours - 1, 1))
    noise = rng.normal(0.0, spec.noise_fraction, hours)

    values = spec.base * daily * trend * weekday[day_of_week] * (1.0 + noise)

    if spec.cap is not None:
        values = np.clip(values, 0.0, spec.cap)
    else:
        values = np.clip(values, 0.0, None)

    mean = float(values.mean())
    sigma = float(values.std(ddof=0)) or 1.0
    for day, hour, direction in spec.spikes:
        index = day * 24 + hour
        if not 0 <= index < hours:
            continue
        # Aim the point at mean +/- SPIKE_SIGMA standard deviations. The target is
        # clamped to the series' physical bounds, so every documented spike stays
        # inside a z-score band of roughly 3.4 - 4.6 in its visible window.
        target = mean + direction * SPIKE_SIGMA * sigma
        if spec.cap is not None:
            target = min(target, spec.cap)
        values[index] = max(target, 0.0)

    stamps = [db.iso(anchor + timedelta(hours=int(i))) for i in range(hours)]
    return [(stamps[i], round(float(values[i]), spec.decimals)) for i in range(hours)]


def anomaly_catalogue(anchor: datetime) -> list[dict]:
    """Documented spike timestamps for the given seed anchor."""
    rows = []
    for dataset in SEED_DATASETS:
        for spec in dataset.series:
            for day, hour, direction in spec.spikes:
                ts = db.iso(anchor + timedelta(days=day, hours=hour))
                rows.append(
                    {
                        "dataset": dataset.name,
                        "series": spec.name,
                        "timestamp": ts,
                        "day_offset": day,
                        "hour_utc": hour,
                        "direction": "spike up" if direction > 0 else "drop",
                        "sigma": SPIKE_SIGMA,
                    }
                )
    return rows


def seed_users(conn: sqlite3.Connection) -> int:
    created = 0
    for username, email, password, _label in DEMO_USERS:
        email = normalise_identifier(email)
        existing = conn.execute(
            "SELECT id FROM users WHERE lower(username) = ? OR lower(email) = ?",
            (username.lower(), email),
        ).fetchone()
        if existing:
            continue
        password_hash, salt = hash_password(password)
        conn.execute(
            "INSERT INTO users (username, email, password_hash, salt, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (username, email, password_hash, salt, db.iso(db.utcnow())),
        )
        created += 1
    conn.commit()
    return created


def seed_datasets(conn: sqlite3.Connection, anchor: datetime) -> dict:
    created_datasets = 0
    created_points = 0
    for spec in SEED_DATASETS:
        existing = conn.execute(
            "SELECT id FROM datasets WHERE seed_key = ?", (spec.seed_key,)
        ).fetchone()
        if existing:
            continue
        cur = conn.execute(
            "INSERT INTO datasets (name, source_filename, uploaded_by, row_count,"
            " dropped_row_count, is_seed, seed_key, created_at)"
            " VALUES (?, ?, NULL, ?, 0, 1, ?, ?)",
            (
                spec.name,
                spec.source_filename,
                WINDOW_DAYS * 24,
                spec.seed_key,
                db.iso(anchor),
            ),
        )
        dataset_id = int(cur.lastrowid)
        for series in spec.series:
            series_cur = conn.execute(
                "INSERT INTO series (dataset_id, name, unit) VALUES (?, ?, ?)",
                (dataset_id, series.name, series.unit),
            )
            series_id = int(series_cur.lastrowid)
            points = [
                (dataset_id, series_id, ts, value)
                for ts, value in build_series_values(series, anchor)
            ]
            conn.executemany(
                "INSERT INTO points (dataset_id, series_id, ts, value) VALUES (?, ?, ?, ?)",
                points,
            )
            created_points += len(points)
        created_datasets += 1
    conn.commit()
    return {"datasets": created_datasets, "points": created_points}


def seed_if_empty(conn: sqlite3.Connection, anchor: datetime | None = None) -> dict:
    """Idempotently create the demo users and the three demo datasets."""
    anchor = anchor or default_anchor()
    users = seed_users(conn)
    data = seed_datasets(conn, anchor)
    stored = conn.execute(
        "SELECT created_at FROM datasets WHERE seed_key IS NOT NULL ORDER BY id LIMIT 1"
    ).fetchone()
    return {"users": users, **data, "anchor": stored["created_at"] if stored else db.iso(anchor)}


def ensure_seeded(db_path=None, anchor: datetime | None = None) -> dict:
    """Create the schema and seed if missing. Safe to call on every boot."""
    db.init_db(db_path)
    with db.get_conn(db_path) as conn:
        return seed_if_empty(conn, anchor=anchor)


def main() -> int:
    result = ensure_seeded()
    with db.get_conn() as conn:
        counts = {
            "users": db.count(conn, "users"),
            "datasets": db.count(conn, "datasets"),
            "series": db.count(conn, "series"),
            "points": db.count(conn, "points"),
        }
    print("Metricscope seed complete")
    print(f"  new users:      {result['users']}")
    print(f"  new datasets:   {result['datasets']}")
    print(f"  new points:     {result['points']}")
    print(f"  window anchor:  {result['anchor']} UTC")
    print(f"  totals:         {counts}")
    print("  demo login:     cenius@cenius.ai / cenius  (username: cenius)")
    print("  documented anomaly spikes (day offset, hour UTC):")
    for row in anomaly_catalogue(datetime.fromisoformat(result["anchor"])):
        print(
            f"    - {row['dataset']} / {row['series']}: {row['timestamp']} UTC"
            f" (day {row['day_offset']}, {row['hour_utc']:02d}:00)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

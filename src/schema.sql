-- Metricscope Time-Series Explorer schema (SQLite).
-- Applied idempotently by src/db.py:init_db on every boot.

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT    NOT NULL UNIQUE,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    salt          TEXT    NOT NULL,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT    PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL,
    expires_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS datasets (
    id                 INTEGER PRIMARY KEY,
    name               TEXT    NOT NULL,
    source_filename    TEXT,
    uploaded_by        INTEGER REFERENCES users(id) ON DELETE SET NULL,
    row_count          INTEGER NOT NULL DEFAULT 0,
    dropped_row_count  INTEGER NOT NULL DEFAULT 0,
    is_seed            INTEGER NOT NULL DEFAULT 0 CHECK (is_seed IN (0, 1)),
    seed_key           TEXT    UNIQUE,
    created_at         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS series (
    id         INTEGER PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    name       TEXT    NOT NULL,
    unit       TEXT,
    UNIQUE (dataset_id, name)
);

CREATE TABLE IF NOT EXISTS points (
    id         INTEGER PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    series_id  INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    ts         TEXT    NOT NULL,
    value      REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS ix_series_dataset ON series(dataset_id);
CREATE INDEX IF NOT EXISTS ix_points_dataset ON points(dataset_id);
CREATE INDEX IF NOT EXISTS ix_points_series_ts ON points(series_id, ts);

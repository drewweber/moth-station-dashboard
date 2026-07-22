"""SQLite schema and helpers."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3


SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    enabled         INTEGER NOT NULL,
    timezone        TEXT,
    county_place_id INTEGER,
    state_place_id  INTEGER,
    public_location TEXT,
    notes           TEXT,
    website         TEXT,
    updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS observations (
    station_id    TEXT NOT NULL,
    inat_obs_id   INTEGER NOT NULL,
    uuid          TEXT,
    observed_on   TEXT,
    observed_at   TEXT,
    created_at    TEXT,
    updated_at    TEXT,
    taxon_id      INTEGER,
    taxon_name    TEXT,
    common_name   TEXT,
    rank          TEXT,
    quality_grade TEXT,
    observer_login TEXT,
    observer_name TEXT,
    latitude      REAL,
    longitude     REAL,
    url           TEXT,
    photo_url     TEXT,
    photo_attribution TEXT,
    photo_license TEXT,
    captive       INTEGER,
    PRIMARY KEY (station_id, inat_obs_id)
);

CREATE INDEX IF NOT EXISTS idx_obs_station_taxon
    ON observations(station_id, taxon_id);
CREATE INDEX IF NOT EXISTS idx_obs_observed
    ON observations(observed_on);
CREATE INDEX IF NOT EXISTS idx_obs_created
    ON observations(created_at);

CREATE TABLE IF NOT EXISTS station_taxon_stats (
    station_id        TEXT NOT NULL,
    taxon_id          INTEGER NOT NULL,
    county_place_id   INTEGER,
    state_place_id    INTEGER,
    station_first_date TEXT,
    county_first_date TEXT,
    state_first_date  TEXT,
    is_county_first   INTEGER,
    is_state_first    INTEGER,
    cached_at         TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (station_id, taxon_id)
);

CREATE INDEX IF NOT EXISTS idx_station_taxon_stats_flags
    ON station_taxon_stats(is_county_first, is_state_first);

CREATE TABLE IF NOT EXISTS regional_watch_runs (
    station_id   TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end   TEXT NOT NULL,
    latitude     REAL NOT NULL,
    longitude    REAL NOT NULL,
    radius_km    REAL NOT NULL,
    cached_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (station_id, window_start)
);

CREATE TABLE IF NOT EXISTS regional_watch_taxa (
    station_id   TEXT NOT NULL,
    window_start TEXT NOT NULL,
    taxon_id     INTEGER NOT NULL,
    taxon_name   TEXT,
    common_name  TEXT,
    photo_url    TEXT,
    record_count INTEGER NOT NULL,
    PRIMARY KEY (station_id, window_start, taxon_id)
);

CREATE INDEX IF NOT EXISTS idx_regional_watch_taxa_window
    ON regional_watch_taxa(station_id, window_start);

CREATE TABLE IF NOT EXISTS regional_watch_day_runs (
    station_id   TEXT NOT NULL,
    calendar_day TEXT NOT NULL,
    latitude     REAL NOT NULL,
    longitude    REAL NOT NULL,
    radius_km    REAL NOT NULL,
    cached_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (station_id, calendar_day)
);

CREATE TABLE IF NOT EXISTS regional_watch_day_taxa (
    station_id   TEXT NOT NULL,
    calendar_day TEXT NOT NULL,
    taxon_id     INTEGER NOT NULL,
    taxon_name   TEXT,
    common_name  TEXT,
    photo_url    TEXT,
    record_count INTEGER NOT NULL,
    PRIMARY KEY (station_id, calendar_day, taxon_id)
);

CREATE INDEX IF NOT EXISTS idx_regional_watch_day_taxa_day
    ON regional_watch_day_taxa(station_id, calendar_day);

CREATE TABLE IF NOT EXISTS sync_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id     TEXT NOT NULL,
    synced_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    full_sync      INTEGER NOT NULL,
    observations_added INTEGER NOT NULL,
    observations_seen  INTEGER NOT NULL,
    max_inat_obs_id INTEGER
);
"""


@contextmanager
def connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(path: Path) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)

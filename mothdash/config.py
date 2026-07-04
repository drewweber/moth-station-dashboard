"""Configuration loading for station-driven iNaturalist queries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib
from typing import Any


STATION_META_KEYS = {
    "id",
    "name",
    "enabled",
    "timezone",
    "county_place_id",
    "state_place_id",
    "public_location",
    "notes",
    "website",
    "color",
    "habitat",
    "light_setup",
    "station_history",
}

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class Settings:
    root: Path
    data_dir: Path
    public_dir: Path
    database: Path
    session_cutoff_hour: int = 12
    recent_limit: int = 50
    default_taxon_id: int = 47157
    default_without_taxon_id: int = 47224
    user_agent: str = "moth-station-dashboard/0.1"
    custom_domain: str = ""
    stats_refresh_limit: int = 80


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    enabled: bool
    query: dict[str, Any]
    timezone: str = "America/New_York"
    county_place_id: int | None = None
    state_place_id: int | None = None
    public_location: str = ""
    notes: str = ""
    website: str = ""
    color: str = ""
    habitat: str = ""
    light_setup: str = ""
    station_history: str = ""

    def api_params(self, settings: Settings) -> dict[str, Any]:
        params = dict(self.query)
        params.setdefault("taxon_id", settings.default_taxon_id)
        params.setdefault("without_taxon_id", settings.default_without_taxon_id)
        return params


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def load_config(path: str | Path = "stations.toml") -> tuple[Settings, list[Station]]:
    config_path = Path(path).resolve()
    root = config_path.parent
    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))

    raw_settings = raw.get("settings", {})
    settings = Settings(
        root=root,
        data_dir=_resolve(root, raw_settings.get("data_dir", "data")),
        public_dir=_resolve(root, raw_settings.get("public_dir", "public")),
        database=_resolve(root, raw_settings.get("database", "data/mothdash.db")),
        session_cutoff_hour=int(raw_settings.get("session_cutoff_hour", 12)),
        recent_limit=int(raw_settings.get("recent_limit", 50)),
        default_taxon_id=int(raw_settings.get("default_taxon_id", 47157)),
        default_without_taxon_id=int(raw_settings.get("default_without_taxon_id", 47224)),
        user_agent=str(raw_settings.get("user_agent", "moth-station-dashboard/0.1")),
        custom_domain=str(raw_settings.get("custom_domain", "")),
        stats_refresh_limit=int(raw_settings.get("stats_refresh_limit", 80)),
    )

    stations = []
    seen = set()
    for raw_station in raw.get("stations", []):
        station_id = str(raw_station["id"])
        if not ID_RE.match(station_id):
            raise ValueError(f"Invalid station id: {station_id!r}")
        if station_id in seen:
            raise ValueError(f"Duplicate station id: {station_id}")
        seen.add(station_id)

        query = {
            k: v
            for k, v in raw_station.items()
            if k not in STATION_META_KEYS and v is not None
        }
        stations.append(
            Station(
                id=station_id,
                name=str(raw_station.get("name", station_id)),
                enabled=bool(raw_station.get("enabled", True)),
                query=query,
                timezone=str(raw_station.get("timezone", "America/New_York")),
                county_place_id=raw_station.get("county_place_id"),
                state_place_id=raw_station.get("state_place_id"),
                public_location=str(raw_station.get("public_location", "")),
                notes=str(raw_station.get("notes", "")),
                website=str(raw_station.get("website", "")),
                color=str(raw_station.get("color", "")),
                habitat=str(raw_station.get("habitat", "")),
                light_setup=str(raw_station.get("light_setup", "")),
                station_history=str(raw_station.get("station_history", "")),
            )
        )

    return settings, stations

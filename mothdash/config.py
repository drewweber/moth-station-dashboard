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
    "active",
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
    "live_place_id",
    "live_project_id",
    "live_user_login",
    "public_live_precise_query",
    "regional_watch_lat",
    "regional_watch_lng",
    "regional_watch_radius_km",
}

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TAXON_SCOPES: dict[str, dict[str, int]] = {
    "moths": {
        # iNaturalist does not expose moths as a single taxon, so the moth
        # scope is implemented as Lepidoptera minus butterflies.
        "taxon_id": 47157,
        "without_taxon_id": 47224,
    },
}


@dataclass(frozen=True)
class Settings:
    root: Path
    data_dir: Path
    public_dir: Path
    database: Path
    session_cutoff_hour: int = 12
    timezone: str = "America/New_York"
    recent_limit: int = 50
    taxon_scope: str = "moths"
    user_agent: str = "moth-station-dashboard/0.1"
    custom_domain: str = ""
    stats_refresh_limit: int = 80
    regional_watch_radius_km: float = 100.0
    regional_watch_days: int = 14
    regional_watch_cache_hours: int = 168

    def taxon_params(self) -> dict[str, int]:
        try:
            return dict(TAXON_SCOPES[self.taxon_scope])
        except KeyError as exc:
            available = ", ".join(sorted(TAXON_SCOPES))
            raise ValueError(
                f"Unknown taxon_scope {self.taxon_scope!r}; expected one of: {available}"
            ) from exc


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    enabled: bool
    active: bool
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
    live_query: dict[str, Any] | None = None
    public_live_precise_query: bool = False
    regional_watch_lat: float | None = None
    regional_watch_lng: float | None = None
    regional_watch_radius_km: float | None = None

    def api_params(self, settings: Settings) -> dict[str, Any]:
        params = dict(self.query)
        for key, value in settings.taxon_params().items():
            params.setdefault(key, value)
        return params

    def live_api_params(self, settings: Settings) -> dict[str, Any]:
        params = dict(self.live_query or self.query)
        for key, value in settings.taxon_params().items():
            params.setdefault(key, value)
        return params


def historical_stations(stations: list[Station]) -> list[Station]:
    """Stations whose cached history remains part of the dashboard."""
    return [station for station in stations if station.enabled]


def active_stations(stations: list[Station]) -> list[Station]:
    """Stations allowed to perform current sync and Live API work."""
    return [station for station in stations if station.enabled and station.active]


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
        timezone=str(raw_settings.get("timezone", "America/New_York")),
        recent_limit=int(raw_settings.get("recent_limit", 50)),
        taxon_scope=str(raw_settings.get("taxon_scope", "moths")),
        user_agent=str(raw_settings.get("user_agent", "moth-station-dashboard/0.1")),
        custom_domain=str(raw_settings.get("custom_domain", "")),
        stats_refresh_limit=int(raw_settings.get("stats_refresh_limit", 80)),
        regional_watch_radius_km=float(raw_settings.get("regional_watch_radius_km", 100)),
        regional_watch_days=int(raw_settings.get("regional_watch_days", 14)),
        regional_watch_cache_hours=int(raw_settings.get("regional_watch_cache_hours", 168)),
    )
    settings.taxon_params()
    if settings.regional_watch_radius_km <= 0:
        raise ValueError("regional_watch_radius_km must be greater than zero")
    if settings.regional_watch_days <= 0:
        raise ValueError("regional_watch_days must be greater than zero")
    if settings.regional_watch_cache_hours <= 0:
        raise ValueError("regional_watch_cache_hours must be greater than zero")

    stations = []
    seen = set()
    for raw_station in raw.get("stations", []):
        station_id = str(raw_station["id"])
        if not ID_RE.match(station_id):
            raise ValueError(f"Invalid station id: {station_id!r}")
        if station_id in seen:
            raise ValueError(f"Duplicate station id: {station_id}")
        seen.add(station_id)

        anchor_values = (
            raw_station.get("regional_watch_lat"),
            raw_station.get("regional_watch_lng"),
        )
        if (anchor_values[0] is None) != (anchor_values[1] is None):
            raise ValueError(
                f"Station {station_id} must define both regional_watch_lat and regional_watch_lng"
            )
        if raw_station.get("regional_watch_radius_km") is not None and float(
            raw_station["regional_watch_radius_km"]
        ) <= 0:
            raise ValueError(
                f"Station {station_id} regional_watch_radius_km must be greater than zero"
            )

        query = {
            k: v
            for k, v in raw_station.items()
            if k not in STATION_META_KEYS and v is not None
        }
        live_query = {
            key.removeprefix("live_"): value
            for key, value in raw_station.items()
            if key.startswith("live_") and value is not None
        }
        stations.append(
            Station(
                id=station_id,
                name=str(raw_station.get("name", station_id)),
                enabled=bool(raw_station.get("enabled", True)),
                active=bool(raw_station.get("active", True)),
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
                live_query=live_query or None,
                public_live_precise_query=bool(raw_station.get("public_live_precise_query", False)),
                regional_watch_lat=raw_station.get("regional_watch_lat"),
                regional_watch_lng=raw_station.get("regional_watch_lng"),
                regional_watch_radius_km=raw_station.get("regional_watch_radius_km"),
            )
        )

    return settings, stations

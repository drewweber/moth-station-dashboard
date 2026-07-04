"""Sync configured iNaturalist stations into SQLite."""

from __future__ import annotations

from typing import Any

from .config import Settings, Station
from .db import connect, init_db
from .inat_api import iter_observations


SPECIES_RANKS = {
    "species",
    "subspecies",
    "variety",
    "form",
    "hybrid",
    "subvariety",
    "subform",
}


OBS_INSERT = """
INSERT OR REPLACE INTO observations (
    station_id, inat_obs_id, uuid, observed_on, observed_at, created_at,
    updated_at, taxon_id, taxon_name, common_name, rank, quality_grade,
    observer_login, observer_name, latitude, longitude, url, photo_url,
    photo_attribution, photo_license, captive
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


def _bool_int(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def _parse_location(obs: dict[str, Any]) -> tuple[float | None, float | None]:
    loc = obs.get("location")
    if not loc:
        return None, None
    try:
        lat, lng = str(loc).split(",", 1)
        return float(lat), float(lng)
    except ValueError:
        return None, None


def _first_photo(obs: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    photos = obs.get("photos") or []
    if not photos:
        return None, None, None
    photo = photos[0]
    url = (photo.get("url") or "").replace("square", "medium") or None
    return url, photo.get("attribution"), photo.get("license_code")


def _observation_row(station_id: str, obs: dict[str, Any]) -> tuple[Any, ...] | None:
    taxon = obs.get("taxon") or {}
    rank = taxon.get("rank")
    if rank not in SPECIES_RANKS:
        return None

    user = obs.get("user") or {}
    lat, lng = _parse_location(obs)
    photo_url, photo_attr, photo_license = _first_photo(obs)

    return (
        station_id,
        obs["id"],
        obs.get("uuid"),
        obs.get("observed_on"),
        obs.get("time_observed_at"),
        obs.get("created_at"),
        obs.get("updated_at"),
        taxon.get("id"),
        taxon.get("name"),
        taxon.get("preferred_common_name"),
        rank,
        obs.get("quality_grade"),
        user.get("login"),
        user.get("name"),
        lat,
        lng,
        obs.get("uri"),
        photo_url,
        photo_attr,
        photo_license,
        _bool_int(obs.get("captive")),
    )


def _upsert_station(settings: Settings, station: Station) -> None:
    with connect(settings.database) as conn:
        conn.execute(
            """
            INSERT INTO stations (
                id, name, enabled, timezone, county_place_id, state_place_id,
                public_location, notes, website, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                enabled = excluded.enabled,
                timezone = excluded.timezone,
                county_place_id = excluded.county_place_id,
                state_place_id = excluded.state_place_id,
                public_location = excluded.public_location,
                notes = excluded.notes,
                website = excluded.website,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                station.id,
                station.name,
                int(station.enabled),
                station.timezone,
                station.county_place_id,
                station.state_place_id,
                station.public_location,
                station.notes,
                station.website,
            ),
        )


def sync_station(settings: Settings, station: Station, full: bool = False) -> tuple[int, int]:
    init_db(settings.database)
    _upsert_station(settings, station)

    with connect(settings.database) as conn:
        if full:
            conn.execute("DELETE FROM observations WHERE station_id = ?", (station.id,))
            cursor = 0
        else:
            row = conn.execute(
                "SELECT COALESCE(MAX(inat_obs_id), 0) AS max_id "
                "FROM observations WHERE station_id = ?",
                (station.id,),
            ).fetchone()
            cursor = int(row["max_id"])

    seen = 0
    added = 0
    max_id = cursor
    params = station.api_params(settings)

    for obs in iter_observations(params, user_agent=settings.user_agent, id_above=cursor):
        seen += 1
        max_id = max(max_id, int(obs["id"]))
        row = _observation_row(station.id, obs)
        if row is None:
            continue
        with connect(settings.database) as conn:
            before = conn.total_changes
            conn.execute(OBS_INSERT, row)
            if conn.total_changes > before:
                added += 1

    with connect(settings.database) as conn:
        conn.execute(
            """
            INSERT INTO sync_log (
                station_id, full_sync, observations_added, observations_seen,
                max_inat_obs_id
            ) VALUES (?,?,?,?,?)
            """,
            (station.id, int(full), added, seen, max_id),
        )

    return added, seen


def sync_all(settings: Settings, stations: list[Station], full: bool = False) -> None:
    for station in stations:
        if not station.enabled:
            continue
        added, seen = sync_station(settings, station, full=full)
        print(f"[{station.id}] seen {seen}, stored {added}")


"""Sync configured iNaturalist stations into SQLite."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Settings, Station, active_stations
from .db import connect, init_db
from .inat_api import (
    ObservationResultLimitExceeded,
    first_observed_date,
    iter_observations,
    iter_updated_observations,
    latest_observation_id,
)
from .regional import refresh_regional_watchlists


SPECIES_RANKS = {
    "species",
    "subspecies",
    "variety",
    "form",
    "hybrid",
    "subvariety",
    "subform",
}
UPDATE_WATERMARK_OVERLAP = timedelta(minutes=5)


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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_sync_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_api_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _latest_sync_state(settings: Settings, station_id: str) -> dict[str, Any] | None:
    with connect(settings.database) as conn:
        row = conn.execute(
            """
            SELECT * FROM sync_log
            WHERE station_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (station_id,),
        ).fetchone()
    return dict(row) if row else None


def _latest_full_sync_at(settings: Settings, station_id: str) -> datetime | None:
    with connect(settings.database) as conn:
        row = conn.execute(
            """
            SELECT synced_at FROM sync_log
            WHERE station_id = ? AND full_sync = 1
            ORDER BY id DESC
            LIMIT 1
            """,
            (station_id,),
        ).fetchone()
    return _parse_sync_time(row["synced_at"]) if row else None


def _full_sync_due(
    settings: Settings,
    station_id: str,
    now: datetime | None = None,
) -> bool:
    last_full = _latest_full_sync_at(settings, station_id)
    if last_full is None:
        return True
    current = now or _utc_now()
    return current - last_full >= timedelta(days=settings.full_sync_interval_days)


def _updated_since(settings: Settings, station_id: str) -> str | None:
    with connect(settings.database) as conn:
        row = conn.execute(
            """
            SELECT updates_through FROM sync_log
            WHERE station_id = ? AND updates_through IS NOT NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (station_id,),
        ).fetchone()
    watermark = _parse_sync_time(row["updates_through"]) if row else None
    if watermark is None:
        watermark = _latest_full_sync_at(settings, station_id)
    if watermark is None:
        return None
    return _format_api_time(watermark - UPDATE_WATERMARK_OVERLAP)


def _taxon_lineage_ids(obs: dict[str, Any]) -> set[int]:
    taxon = obs.get("taxon") or {}
    values = list(taxon.get("ancestor_ids") or [])
    if not values and taxon.get("ancestry"):
        values.extend(str(taxon["ancestry"]).split("/"))
    values.append(taxon.get("id"))
    lineage = set()
    for value in values:
        try:
            lineage.add(int(value))
        except (TypeError, ValueError):
            continue
    return lineage


def _scope_ids(value: Any) -> set[int]:
    values = value if isinstance(value, (list, tuple, set)) else (value,)
    result = set()
    for item in values:
        try:
            result.add(int(item))
        except (TypeError, ValueError):
            continue
    return result


def _observation_matches_taxon_scope(settings: Settings, obs: dict[str, Any]) -> bool:
    lineage = _taxon_lineage_ids(obs)
    if not lineage:
        return False
    scope = settings.taxon_params()
    included = _scope_ids(scope.get("taxon_id"))
    excluded = _scope_ids(scope.get("without_taxon_id"))
    return (not included or bool(lineage & included)) and not bool(lineage & excluded)


def _reconcile_updated_observations(
    conn,
    settings: Settings,
    station: Station,
    updated_since: str,
) -> tuple[int, int, int]:
    """Refresh older source records whose current iNaturalist state changed."""
    added = 0
    reconciled = 0
    removed = 0
    for obs in iter_updated_observations(
        station.query,
        user_agent=settings.user_agent,
        updated_since=updated_since,
    ):
        reconciled += 1
        observation_id = int(obs["id"])
        cached = conn.execute(
            "SELECT 1 FROM observations WHERE station_id = ? AND inat_obs_id = ?",
            (station.id, observation_id),
        ).fetchone()
        row = None
        if _observation_matches_taxon_scope(settings, obs):
            row = _observation_row(station.id, obs)
        if row is None:
            if cached:
                conn.execute(
                    "DELETE FROM observations WHERE station_id = ? AND inat_obs_id = ?",
                    (station.id, observation_id),
                )
                removed += 1
            continue
        conn.execute(OBS_INSERT, row)
        if not cached:
            added += 1
    return added, reconciled, removed


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

    sync_started_at = _utc_now()
    if not full and _full_sync_due(settings, station.id, now=sync_started_at):
        full = True
        print(
            f"[{station.id}] full reconciliation due "
            f"(every {settings.full_sync_interval_days} days)"
        )

    state = _latest_sync_state(settings, station.id)
    if full:
        cursor = 0
    elif state and state.get("max_inat_obs_id") is not None:
        cursor = int(state["max_inat_obs_id"])
    else:
        with connect(settings.database) as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(inat_obs_id), 0) AS max_id "
                "FROM observations WHERE station_id = ?",
                (station.id,),
            ).fetchone()
        cursor = int(row["max_id"])

    seen = 0
    added = 0
    reconciled = 0
    removed = 0
    max_id = cursor
    params = station.api_params(settings)
    updated_since = None if full else _updated_since(settings, station.id)

    # Keep the whole station write in one SQLite transaction. Opening and
    # committing a connection for every iNaturalist observation was the
    # dominant cost of a first sync and adds no recovery benefit here.
    try:
        with connect(settings.database) as conn:
            old_ids = set()
            stored_ids = set()
            if full:
                old_ids = {
                    int(row["inat_obs_id"])
                    for row in conn.execute(
                        "SELECT inat_obs_id FROM observations WHERE station_id = ?",
                        (station.id,),
                    )
                }
                conn.execute(
                    "DELETE FROM observations WHERE station_id = ?",
                    (station.id,),
                )
            try:
                for obs in iter_observations(
                    params,
                    user_agent=settings.user_agent,
                    id_above=cursor,
                ):
                    seen += 1
                    observation_id = int(obs["id"])
                    max_id = max(max_id, observation_id)
                    row = _observation_row(station.id, obs)
                    if row is None:
                        continue
                    conn.execute(OBS_INSERT, row)
                    stored_ids.add(observation_id)
                    added += 1

                if full:
                    # A valid empty station is possible, but never replace a
                    # populated cache after one surprising empty page without
                    # confirming the current source query is truly empty.
                    if old_ids and seen == 0:
                        confirmed_latest_id = latest_observation_id(
                            settings.user_agent,
                            **params,
                        )
                        if confirmed_latest_id:
                            raise RuntimeError(
                                f"[{station.id}] full reconciliation returned "
                                "no observations, but the source query still "
                                f"contains observation {confirmed_latest_id}"
                            )
                    removed = len(old_ids - stored_ids)
                elif updated_since:
                    update_added, reconciled, removed = _reconcile_updated_observations(
                        conn,
                        settings,
                        station,
                        updated_since,
                    )
                    added += update_added
                    seen += reconciled
            except Exception:
                if full:
                    conn.rollback()
                raise
    except ObservationResultLimitExceeded as exc:
        print(f"[{station.id}] {exc}; falling back to a full reconciliation")
        return sync_station(settings, station, full=True)

    with connect(settings.database) as conn:
        conn.execute(
            """
            INSERT INTO sync_log (
                station_id, full_sync, observations_added, observations_seen,
                max_inat_obs_id, observations_reconciled,
                observations_removed, updates_through
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                station.id,
                int(full),
                added,
                seen,
                max_id,
                reconciled,
                removed,
                _format_api_time(sync_started_at),
            ),
        )

    if reconciled or removed:
        print(
            f"[{station.id}] reconciled {reconciled} changed source records, "
            f"removed {removed} stale cached records"
        )
    return added, seen


def pending_station_updates(settings: Settings, stations: list[Station]) -> list[Station]:
    """Return active stations with iNat records newer than the cached cursor.

    The cursor comes from ``sync_log`` rather than the stored species rows so
    an intervening genus-level record does not repeatedly trigger full builds.
    """
    init_db(settings.database)
    pending: list[Station] = []
    for station in active_stations(stations):
        with connect(settings.database) as conn:
            row = conn.execute(
                """
                SELECT COALESCE(max_inat_obs_id, 0) AS max_id
                FROM sync_log
                WHERE station_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (station.id,),
            ).fetchone()
        cached_id = int(row["max_id"]) if row else 0
        newest_id = latest_observation_id(
            settings.user_agent,
            **station.api_params(settings),
        )
        if newest_id > cached_id:
            pending.append(station)
    return pending


def _station_first_taxa(settings: Settings, station: Station) -> list[dict[str, Any]]:
    with connect(settings.database) as conn:
        rows = conn.execute(
            """
            SELECT taxon_id,
                   MAX(taxon_name) AS taxon_name,
                   MAX(common_name) AS common_name,
                   MIN(observed_on) AS station_first_date
            FROM observations
            WHERE station_id = ?
              AND taxon_id IS NOT NULL
              AND observed_on IS NOT NULL
              AND rank = 'species'
            GROUP BY taxon_id
            ORDER BY station_first_date
            """,
            (station.id,),
        ).fetchall()
    return [dict(row) for row in rows]


def refresh_station_stats(settings: Settings, stations: list[Station]) -> None:
    """Refresh cached county/state first dates for station taxa.

    These are iNaturalist firsts, not absolute historical records.
    """
    remaining = settings.stats_refresh_limit
    for station in active_stations(stations):
        if remaining <= 0:
            print("[stats] refresh budget exhausted")
            return
        if not station.county_place_id and not station.state_place_id:
            continue

        taxa = _station_first_taxa(settings, station)
        refreshed = 0
        for row in taxa:
            taxon_id = row["taxon_id"]
            station_first = row["station_first_date"]
            with connect(settings.database) as conn:
                cached = conn.execute(
                    """
                    SELECT taxon_id FROM station_taxon_stats
                    WHERE station_id = ?
                      AND taxon_id = ?
                      AND station_first_date = ?
                      AND county_place_id IS ?
                      AND state_place_id IS ?
                      AND cached_at > datetime('now', '-30 days')
                    """,
                    (
                        station.id,
                        taxon_id,
                        station_first,
                        station.county_place_id,
                        station.state_place_id,
                    ),
                ).fetchone()
            if cached:
                continue
            if remaining <= 0:
                break

            county_first = None
            state_first = None
            if station.county_place_id:
                county_first = first_observed_date(
                    settings.user_agent,
                    taxon_id=taxon_id,
                    place_id=station.county_place_id,
                )
            if station.state_place_id:
                state_first = first_observed_date(
                    settings.user_agent,
                    taxon_id=taxon_id,
                    place_id=station.state_place_id,
                )

            is_county_first = bool(
                station_first and county_first and station_first <= county_first
            )
            is_state_first = bool(
                station_first and state_first and station_first <= state_first
            )
            with connect(settings.database) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO station_taxon_stats (
                        station_id, taxon_id, county_place_id, state_place_id,
                        station_first_date, county_first_date, state_first_date,
                        is_county_first, is_state_first, cached_at
                    ) VALUES (?,?,?,?,?,?,?,?,?, CURRENT_TIMESTAMP)
                    """,
                    (
                        station.id,
                        taxon_id,
                        station.county_place_id,
                        station.state_place_id,
                        station_first,
                        county_first,
                        state_first,
                        int(is_county_first),
                        int(is_state_first),
                    ),
                )
            refreshed += 1
            remaining -= 1
        print(f"[{station.id}] refreshed first-record stats for {refreshed} taxa")


def sync_all(settings: Settings, stations: list[Station], full: bool = False) -> None:
    for station in stations:
        if not station.enabled:
            continue
        if not station.active:
            # Inactive stations keep their historical data but are no longer
            # queried for new iNaturalist observations.
            init_db(settings.database)
            _upsert_station(settings, station)
            print(f"[{station.id}] skipped (inactive)")
            continue
        added, seen = sync_station(settings, station, full=full)
        print(f"[{station.id}] seen {seen}, stored {added}")
    refresh_station_stats(settings, active_stations(stations))
    refresh_regional_watchlists(settings, stations)

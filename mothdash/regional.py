"""Cached, date-specific iNaturalist evidence for station watchlists."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .config import Settings, Station
from .db import connect, init_db
from .inat_api import iter_species_counts


def regional_reference_date(settings: Settings, now: datetime | None = None) -> date:
    """Return the local calendar date used for the upcoming watch window."""
    zone = ZoneInfo(settings.timezone)
    if now is None:
        return datetime.now(zone).date()
    if now.tzinfo is None:
        return now.replace(tzinfo=zone).date()
    return now.astimezone(zone).date()


def _station_anchor(settings: Settings, station: Station) -> tuple[float, float, float] | None:
    """Return the intentionally configured public reference point for a station."""
    if station.regional_watch_lat is None or station.regional_watch_lng is None:
        return None
    return (
        float(station.regional_watch_lat),
        float(station.regional_watch_lng),
        float(station.regional_watch_radius_km or settings.regional_watch_radius_km),
    )


def _medium_photo_url(taxon: dict[str, Any]) -> str | None:
    photo = taxon.get("default_photo") or {}
    return photo.get("medium_url") or (photo.get("url") or "").replace("square", "medium") or None


def _fetch_day_counts(
    settings: Settings,
    latitude: float,
    longitude: float,
    radius_km: float,
    calendar_day: date,
) -> dict[int, dict[str, Any]]:
    """Fetch all species-level records on one recurring calendar day."""
    counts: dict[int, dict[str, Any]] = {}
    params: dict[str, Any] = {
        "lat": latitude,
        "lng": longitude,
        "radius": radius_km,
        "month": calendar_day.month,
        "day": calendar_day.day,
        "verifiable": "any",
        **settings.taxon_params(),
    }
    for item in iter_species_counts(params, user_agent=settings.user_agent):
        taxon = item.get("taxon") or {}
        if taxon.get("rank") != "species" or not taxon.get("id"):
            continue
        taxon_id = int(taxon["id"])
        candidate = counts.setdefault(
            taxon_id,
            {
                "taxon_id": taxon_id,
                "taxon_name": taxon.get("name"),
                "common_name": taxon.get("preferred_common_name"),
                "photo_url": _medium_photo_url(taxon),
                "record_count": 0,
            },
        )
        candidate["record_count"] += int(item.get("count") or 0)
        if not candidate.get("photo_url"):
            candidate["photo_url"] = _medium_photo_url(taxon)
    return counts


def _fresh_day_cache_exists(
    settings: Settings,
    station_id: str,
    calendar_day: date,
    latitude: float,
    longitude: float,
    radius_km: float,
) -> bool:
    with connect(settings.database) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM regional_watch_day_runs
            WHERE station_id = ?
              AND calendar_day = ?
              AND latitude = ?
              AND longitude = ?
              AND radius_km = ?
              AND cached_at > datetime('now', ?)
            """,
            (
                station_id,
                calendar_day.isoformat(),
                latitude,
                longitude,
                radius_km,
                f"-{settings.regional_watch_cache_hours} hours",
            ),
        ).fetchone()
    return row is not None


def _store_day_counts(
    settings: Settings,
    station_id: str,
    calendar_day: date,
    latitude: float,
    longitude: float,
    radius_km: float,
    counts: dict[int, dict[str, Any]],
) -> None:
    with connect(settings.database) as conn:
        conn.execute(
            "DELETE FROM regional_watch_day_taxa WHERE station_id = ? AND calendar_day = ?",
            (station_id, calendar_day.isoformat()),
        )
        conn.executemany(
            """
            INSERT INTO regional_watch_day_taxa (
                station_id, calendar_day, taxon_id, taxon_name, common_name,
                photo_url, record_count
            ) VALUES (?,?,?,?,?,?,?)
            """,
            [
                (
                    station_id,
                    calendar_day.isoformat(),
                    item["taxon_id"],
                    item["taxon_name"],
                    item["common_name"],
                    item["photo_url"],
                    item["record_count"],
                )
                for item in counts.values()
            ],
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO regional_watch_day_runs (
                station_id, calendar_day, latitude, longitude, radius_km
            ) VALUES (?,?,?,?,?)
            """,
            (station_id, calendar_day.isoformat(), latitude, longitude, radius_km),
        )


def _aggregate_window_counts(
    settings: Settings,
    station_id: str,
    window_start: date,
) -> list[dict[str, Any]]:
    days = [
        (window_start + timedelta(days=offset)).isoformat()
        for offset in range(settings.regional_watch_days)
    ]
    placeholders = ",".join("?" for _ in days)
    with connect(settings.database) as conn:
        rows = conn.execute(
            f"""
            SELECT taxon_id,
                   MAX(taxon_name) AS taxon_name,
                   MAX(common_name) AS common_name,
                   MAX(photo_url) AS photo_url,
                   SUM(record_count) AS record_count
            FROM regional_watch_day_taxa
            WHERE station_id = ? AND calendar_day IN ({placeholders})
            GROUP BY taxon_id
            """,
            (station_id, *days),
        ).fetchall()
    return [dict(row) for row in rows]


def refresh_regional_watchlists(
    settings: Settings,
    stations: list[Station],
    *,
    today: date | None = None,
) -> None:
    """Refresh a daily bounded nearby-iNat cache without blocking a dashboard build."""
    init_db(settings.database)
    window_start = today or regional_reference_date(settings)
    window_end = window_start + timedelta(days=settings.regional_watch_days - 1)
    keep_after = (window_start - timedelta(days=7)).isoformat()
    keep_before = (window_end + timedelta(days=7)).isoformat()

    for station in stations:
        if not station.enabled:
            continue
        anchor = _station_anchor(settings, station)
        if anchor is None:
            print(f"[{station.id}] regional watchlist skipped (no anchor)")
            continue
        latitude, longitude, radius_km = anchor
        refreshed_days = 0
        for offset in range(settings.regional_watch_days):
            calendar_day = window_start + timedelta(days=offset)
            if _fresh_day_cache_exists(
                settings, station.id, calendar_day, latitude, longitude, radius_km
            ):
                continue
            try:
                counts = _fetch_day_counts(
                    settings, latitude, longitude, radius_km, calendar_day
                )
            except Exception as exc:  # Keep a dashboard deploy available during iNat API outages.
                print(f"[{station.id}] regional day {calendar_day} skipped ({exc})")
                continue
            _store_day_counts(
                settings,
                station.id,
                calendar_day,
                latitude,
                longitude,
                radius_km,
                counts,
            )
            refreshed_days += 1

        counts = _aggregate_window_counts(settings, station.id, window_start)

        with connect(settings.database) as conn:
            conn.execute(
                "DELETE FROM regional_watch_taxa WHERE station_id = ? AND window_start = ?",
                (station.id, window_start.isoformat()),
            )
            conn.executemany(
                """
                INSERT INTO regional_watch_taxa (
                    station_id, window_start, taxon_id, taxon_name, common_name,
                    photo_url, record_count
                ) VALUES (?,?,?,?,?,?,?)
                """,
                [
                    (
                        station.id,
                        window_start.isoformat(),
                        item["taxon_id"],
                        item["taxon_name"],
                        item["common_name"],
                        item["photo_url"],
                        item["record_count"],
                    )
                    for item in counts
                ],
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO regional_watch_runs (
                    station_id, window_start, window_end, latitude, longitude, radius_km
                ) VALUES (?,?,?,?,?,?)
                """,
                (
                    station.id,
                    window_start.isoformat(),
                    window_end.isoformat(),
                    latitude,
                    longitude,
                    radius_km,
                ),
            )
            conn.execute(
                "DELETE FROM regional_watch_taxa WHERE station_id = ? AND window_start < ?",
                (station.id, keep_after),
            )
            conn.execute(
                "DELETE FROM regional_watch_runs WHERE station_id = ? AND window_start < ?",
                (station.id, keep_after),
            )
            conn.execute(
                """
                DELETE FROM regional_watch_day_taxa
                WHERE station_id = ? AND (calendar_day < ? OR calendar_day > ?)
                """,
                (station.id, keep_after, keep_before),
            )
            conn.execute(
                """
                DELETE FROM regional_watch_day_runs
                WHERE station_id = ? AND (calendar_day < ? OR calendar_day > ?)
                """,
                (station.id, keep_after, keep_before),
            )
        print(
            f"[{station.id}] cached {len(counts)} nearby seasonal moth taxa "
            f"({refreshed_days} calendar days refreshed)"
        )


def cached_regional_watchlist(
    settings: Settings,
    station_id: str,
    reference_day: date,
) -> dict[str, Any] | None:
    """Return the cache for exactly this upcoming window, if it was built."""
    with connect(settings.database) as conn:
        run = conn.execute(
            """
            SELECT window_start, window_end, radius_km, cached_at
            FROM regional_watch_runs
            WHERE station_id = ? AND window_start = ?
            """,
            (station_id, reference_day.isoformat()),
        ).fetchone()
        if run is None:
            return None
        rows = conn.execute(
            """
            SELECT taxon_id, taxon_name, common_name, photo_url, record_count
            FROM regional_watch_taxa
            WHERE station_id = ? AND window_start = ?
            ORDER BY record_count DESC, taxon_name
            """,
            (station_id, reference_day.isoformat()),
        ).fetchall()
    return {"run": dict(run), "rows": [dict(row) for row in rows]}

"""Analysis queries for station comparison and first-of-season timing."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from .config import Settings
from .db import connect


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def session_date(observed_on: str | None, observed_at: str | None, cutoff_hour: int) -> date | None:
    base = parse_date(observed_on)
    if base is None:
        return None
    if observed_at and len(observed_at) >= 13:
        try:
            hour = int(observed_at[11:13])
        except ValueError:
            hour = None
        if hour is not None and hour < cutoff_hour:
            return base - timedelta(days=1)
    return base


def _label(row: dict[str, Any]) -> str:
    common = row.get("common_name")
    sci = row.get("taxon_name") or ""
    if common and sci:
        return f"{common} ({sci})"
    return common or sci or "Unknown taxon"


def load_rows(settings: Settings) -> list[dict[str, Any]]:
    with connect(settings.database) as conn:
        rows = conn.execute(
            """
            SELECT o.*, s.name AS station_name
            FROM observations o
            JOIN stations s ON s.id = o.station_id
            WHERE s.enabled = 1
            ORDER BY o.observed_on, o.inat_obs_id
            """
        ).fetchall()
    out = [dict(row) for row in rows]
    for row in out:
        row["session_date"] = session_date(
            row.get("observed_on"),
            row.get("observed_at"),
            settings.session_cutoff_hour,
        )
        row["label"] = _label(row)
    return out


def station_summaries(settings: Settings) -> list[dict[str, Any]]:
    rows = load_rows(settings)
    by_station: dict[str, dict[str, Any]] = {}
    for row in rows:
        sid = row["station_id"]
        summary = by_station.setdefault(
            sid,
            {
                "station_id": sid,
                "station_name": row["station_name"],
                "observations": 0,
                "taxa": set(),
                "latest_session": None,
            },
        )
        summary["observations"] += 1
        if row["taxon_id"]:
            summary["taxa"].add(row["taxon_id"])
        sd = row["session_date"]
        if sd and (summary["latest_session"] is None or sd > summary["latest_session"]):
            summary["latest_session"] = sd

    results = []
    for summary in by_station.values():
        summary = dict(summary)
        summary["species"] = len(summary.pop("taxa"))
        results.append(summary)
    return sorted(results, key=lambda item: item["station_name"])


def recent_observations(settings: Settings) -> list[dict[str, Any]]:
    with connect(settings.database) as conn:
        rows = conn.execute(
            """
            SELECT o.*, s.name AS station_name
            FROM observations o
            JOIN stations s ON s.id = o.station_id
            WHERE s.enabled = 1
            ORDER BY COALESCE(o.created_at, o.observed_on) DESC, o.inat_obs_id DESC
            LIMIT ?
            """,
            (settings.recent_limit,),
        ).fetchall()
    out = [dict(row) for row in rows]
    for row in out:
        row["session_date"] = session_date(
            row.get("observed_on"),
            row.get("observed_at"),
            settings.session_cutoff_hour,
        )
        row["label"] = _label(row)
    return out


def hero_photos(settings: Settings, limit: int = 8) -> list[dict[str, Any]]:
    """Recent photo observations balanced across stations for the hero rail."""
    with connect(settings.database) as conn:
        rows = conn.execute(
            """
            SELECT o.*, s.name AS station_name
            FROM observations o
            JOIN stations s ON s.id = o.station_id
            WHERE s.enabled = 1
              AND o.photo_url IS NOT NULL
            ORDER BY COALESCE(o.created_at, o.observed_on) DESC, o.inat_obs_id DESC
            LIMIT 600
            """
        ).fetchall()
    candidates = [dict(row) for row in rows]
    for row in candidates:
        row["session_date"] = session_date(
            row.get("observed_on"),
            row.get("observed_at"),
            settings.session_cutoff_hour,
        )
        row["label"] = _label(row)

    selected = []
    seen_photos = set()
    seen_stations = set()

    for row in candidates:
        if row["station_id"] in seen_stations:
            continue
        if row["photo_url"] in seen_photos:
            continue
        selected.append(row)
        seen_stations.add(row["station_id"])
        seen_photos.add(row["photo_url"])
        if len(selected) >= limit:
            return selected

    per_station_counts = defaultdict(int)
    for row in selected:
        per_station_counts[row["station_id"]] += 1

    for row in candidates:
        if row["photo_url"] in seen_photos:
            continue
        if per_station_counts[row["station_id"]] >= 2:
            continue
        selected.append(row)
        per_station_counts[row["station_id"]] += 1
        seen_photos.add(row["photo_url"])
        if len(selected) >= limit:
            break

    for row in candidates:
        if len(selected) >= limit:
            break
        if row["photo_url"] in seen_photos:
            continue
        selected.append(row)
        seen_photos.add(row["photo_url"])

    return selected


def active_year(settings: Settings) -> int | None:
    with connect(settings.database) as conn:
        row = conn.execute(
            "SELECT MAX(substr(observed_on, 1, 4)) AS year FROM observations"
        ).fetchone()
    return int(row["year"]) if row and row["year"] else None


def first_of_season(
    settings: Settings,
    year: int | None = None,
    all_time: bool = False,
) -> list[dict[str, Any]]:
    rows = load_rows(settings)
    if year is None and not all_time:
        year = active_year(settings)
    if year is None and not all_time:
        return []

    firsts: dict[tuple[int, str], dict[str, Any]] = {}
    taxon_labels: dict[int, str] = {}
    station_names: dict[str, str] = {}

    for row in rows:
        taxon_id = row.get("taxon_id")
        sd = row.get("session_date")
        if not taxon_id or sd is None:
            continue
        if not all_time and sd.year != year:
            continue
        station_id = row["station_id"]
        key = (int(taxon_id), station_id)
        taxon_labels[int(taxon_id)] = row["label"]
        station_names[station_id] = row["station_name"]
        if key not in firsts or sd < firsts[key]["date"]:
            firsts[key] = {
                "date": sd,
                "obs_id": row["inat_obs_id"],
                "url": row.get("url"),
            }

    by_taxon: dict[int, dict[str, Any]] = defaultdict(lambda: {"stations": {}})
    for (taxon_id, station_id), info in firsts.items():
        by_taxon[taxon_id]["taxon_id"] = taxon_id
        by_taxon[taxon_id]["label"] = taxon_labels[taxon_id]
        by_taxon[taxon_id]["stations"][station_id] = {
            **info,
            "station_name": station_names.get(station_id, station_id),
        }

    results = []
    for item in by_taxon.values():
        station_dates = [entry["date"] for entry in item["stations"].values()]
        if len(station_dates) < 2:
            continue
        earliest = min(station_dates)
        latest = max(station_dates)
        spread = (latest - earliest).days
        if spread == 0:
            pulse = "same night"
        elif spread <= 2:
            pulse = "highly synchronized"
        elif spread <= 7:
            pulse = "same flight pulse"
        else:
            pulse = "staggered"
        item.update(
            {
                "year": year,
                "all_time": all_time,
                "station_count": len(station_dates),
                "earliest": earliest,
                "latest": latest,
                "spread_days": spread,
                "pulse": pulse,
            }
        )
        results.append(dict(item))

    return sorted(
        results,
        key=lambda item: (item["spread_days"], item["earliest"], item["label"]),
    )


def station_taxa(settings: Settings, year: int | None = None) -> list[dict[str, Any]]:
    rows = load_rows(settings)
    with connect(settings.database) as conn:
        stats_rows = conn.execute("SELECT * FROM station_taxon_stats").fetchall()
    stats = {
        (row["station_id"], row["taxon_id"]): dict(row)
        for row in stats_rows
    }
    grouped: dict[tuple[int, str], dict[str, Any]] = {}
    for row in rows:
        taxon_id = row.get("taxon_id")
        if not taxon_id:
            continue
        sd = row.get("session_date")
        if year is not None and (sd is None or sd.year != year):
            continue
        key = (int(taxon_id), row["station_id"])
        item = grouped.setdefault(
            key,
            {
                "taxon_id": int(taxon_id),
                "label": row["label"],
                "station_id": row["station_id"],
                "station_name": row["station_name"],
                "count": 0,
                "first": None,
                "latest": None,
            },
        )
        item["count"] += 1
        if sd:
            if item["first"] is None or sd < item["first"]:
                item["first"] = sd
            if item["latest"] is None or sd > item["latest"]:
                item["latest"] = sd

    by_taxon: dict[int, dict[str, Any]] = defaultdict(lambda: {"stations": {}})
    for item in grouped.values():
        stat = stats.get((item["station_id"], item["taxon_id"]), {})
        item["is_county_first"] = bool(stat.get("is_county_first"))
        item["is_state_first"] = bool(stat.get("is_state_first"))
        item["county_first_date"] = parse_date(stat.get("county_first_date"))
        item["state_first_date"] = parse_date(stat.get("state_first_date"))
        item["first_among_tracked"] = False
        taxon = by_taxon[item["taxon_id"]]
        taxon["taxon_id"] = item["taxon_id"]
        taxon["label"] = item["label"]
        taxon["stations"][item["station_id"]] = item

    results = []
    for item in by_taxon.values():
        station_firsts = [
            station["first"] for station in item["stations"].values()
            if station.get("first")
        ]
        earliest = min(station_firsts) if station_firsts else None
        first_station_names = []
        station_count = len(item["stations"])
        for station in item["stations"].values():
            if station_count > 1 and earliest and station.get("first") == earliest:
                station["first_among_tracked"] = True
                first_station_names.append(station["station_name"])
        item["station_count"] = station_count
        item["total_count"] = sum(station["count"] for station in item["stations"].values())
        item["first_among_tracked_date"] = earliest
        item["first_among_tracked_stations"] = first_station_names
        results.append(dict(item))
    return sorted(results, key=lambda item: (-item["station_count"], item["label"]))


def daily_species_counts(settings: Settings, year: int | None = None) -> list[dict[str, Any]]:
    rows = load_rows(settings)
    days: dict[str, dict[str, Any]] = {}
    for row in rows:
        taxon_id = row.get("taxon_id")
        sd = row.get("session_date")
        if not taxon_id or sd is None:
            continue
        if year is not None:
            if sd.year != year:
                continue
            day_key = sd.isoformat()
            label = f"{sd:%b} {sd.day}"
            sort_key = sd.isoformat()
        else:
            day_key = sd.strftime("%m-%d")
            label = f"{sd:%b} {sd.day}"
            sort_key = day_key
        day = days.setdefault(
            day_key,
            {
                "key": day_key,
                "label": label,
                "sort_key": sort_key,
                "stations": defaultdict(set),
            },
        )
        day["stations"][row["station_id"]].add(int(taxon_id))

    results = []
    for day in days.values():
        stations = {
            station_id: len(taxa)
            for station_id, taxa in day["stations"].items()
        }
        total = sum(stations.values())
        active_stations = sum(1 for count in stations.values() if count)
        results.append(
            {
                "key": day["key"],
                "label": day["label"],
                "sort_key": day["sort_key"],
                "stations": stations,
                "total": total,
                "active_stations": active_stations,
            }
        )
    return sorted(results, key=lambda item: item["sort_key"])


def record_highlights(settings: Settings) -> list[dict[str, Any]]:
    highlights = []
    for taxon in station_taxa(settings):
        for station in taxon["stations"].values():
            flags = []
            if station.get("is_state_first"):
                flags.append("state iNat first")
            if station.get("is_county_first"):
                flags.append("county iNat first")
            if station.get("first_among_tracked"):
                flags.append("first among tracked")
            if not flags:
                continue
            highlights.append({
                "taxon_id": taxon["taxon_id"],
                "label": taxon["label"],
                "station_name": station["station_name"],
                "station_id": station["station_id"],
                "first": station["first"],
                "count": station["count"],
                "flags": flags,
                "is_state_first": station.get("is_state_first"),
                "is_county_first": station.get("is_county_first"),
                "first_among_tracked": station.get("first_among_tracked"),
            })
    return sorted(
        highlights,
        key=lambda item: (
            not item["is_state_first"],
            not item["is_county_first"],
            not item["first_among_tracked"],
            item["first"] or date.max,
            item["label"],
        ),
    )


def unique_station_taxa(settings: Settings) -> list[dict[str, Any]]:
    uniques = []
    for taxon in station_taxa(settings):
        if taxon["station_count"] != 1:
            continue
        station = next(iter(taxon["stations"].values()))
        uniques.append({
            "taxon_id": taxon["taxon_id"],
            "label": taxon["label"],
            "station_name": station["station_name"],
            "station_id": station["station_id"],
            "first": station["first"],
            "latest": station["latest"],
            "count": station["count"],
        })
    return sorted(uniques, key=lambda item: (item["station_name"], item["label"]))


def generated_at() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")

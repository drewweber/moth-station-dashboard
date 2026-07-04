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


def active_year(settings: Settings) -> int | None:
    with connect(settings.database) as conn:
        row = conn.execute(
            "SELECT MAX(substr(observed_on, 1, 4)) AS year FROM observations"
        ).fetchone()
    return int(row["year"]) if row and row["year"] else None


def first_of_season(settings: Settings, year: int | None = None) -> list[dict[str, Any]]:
    rows = load_rows(settings)
    if year is None:
        year = active_year(settings)
    if year is None:
        return []

    firsts: dict[tuple[int, str], dict[str, Any]] = {}
    taxon_labels: dict[int, str] = {}
    station_names: dict[str, str] = {}

    for row in rows:
        taxon_id = row.get("taxon_id")
        sd = row.get("session_date")
        if not taxon_id or sd is None or sd.year != year:
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


def station_taxa(settings: Settings) -> list[dict[str, Any]]:
    rows = load_rows(settings)
    grouped: dict[tuple[int, str], dict[str, Any]] = {}
    for row in rows:
        taxon_id = row.get("taxon_id")
        if not taxon_id:
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
        sd = row.get("session_date")
        if sd:
            if item["first"] is None or sd < item["first"]:
                item["first"] = sd
            if item["latest"] is None or sd > item["latest"]:
                item["latest"] = sd

    by_taxon: dict[int, dict[str, Any]] = defaultdict(lambda: {"stations": {}})
    for item in grouped.values():
        taxon = by_taxon[item["taxon_id"]]
        taxon["taxon_id"] = item["taxon_id"]
        taxon["label"] = item["label"]
        taxon["stations"][item["station_id"]] = item

    results = []
    for item in by_taxon.values():
        item["station_count"] = len(item["stations"])
        item["total_count"] = sum(station["count"] for station in item["stations"].values())
        results.append(dict(item))
    return sorted(results, key=lambda item: (-item["station_count"], item["label"]))


def generated_at() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


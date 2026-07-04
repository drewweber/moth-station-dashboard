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
                "taxa": set(),
                "stations": defaultdict(set),
            },
        )
        taxon_id = int(taxon_id)
        day["taxa"].add(taxon_id)
        day["stations"][row["station_id"]].add(taxon_id)

    results = []
    for day in days.values():
        stations = {
            station_id: len(taxa)
            for station_id, taxa in day["stations"].items()
        }
        total = len(day["taxa"])
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


def _insight(
    category: str,
    title: str,
    body: str,
    meta: str = "",
    score: int = 0,
) -> dict[str, Any]:
    return {
        "category": category,
        "title": title,
        "body": body,
        "meta": meta,
        "score": score,
    }


def dashboard_insights(settings: Settings, limit: int = 16) -> list[dict[str, Any]]:
    """Build deterministic naturalist-feed stories from the current dataset."""
    rows = load_rows(settings)
    if not rows:
        return []

    insights: list[dict[str, Any]] = []
    session_dates = [row["session_date"] for row in rows if row.get("session_date")]
    latest = max(session_dates) if session_dates else None
    year = active_year(settings)

    if latest:
        latest_firsts = []
        first_by_station_taxon: dict[tuple[str, int], dict[str, Any]] = {}
        for row in rows:
            taxon_id = row.get("taxon_id")
            sd = row.get("session_date")
            if not taxon_id or not sd:
                continue
            key = (row["station_id"], int(taxon_id))
            current = first_by_station_taxon.get(key)
            if current is None or sd < current["date"]:
                first_by_station_taxon[key] = {
                    "date": sd,
                    "label": row["label"],
                    "station_name": row["station_name"],
                }
        for item in first_by_station_taxon.values():
            if item["date"] == latest:
                latest_firsts.append(item)
        latest_firsts = sorted(
            latest_firsts,
            key=lambda item: (item["station_name"], item["label"]),
        )
        for item in latest_firsts[:4]:
            insights.append(
                _insight(
                    "New station record",
                    f"{item['station_name']} added {item['label']}",
                    "This species appeared in that station's tracked moth list for the first time on the latest session.",
                    latest.isoformat(),
                    92,
                )
            )

        week_start = latest - timedelta(days=6)
        weekly: dict[str, dict[str, Any]] = {}
        for row in rows:
            sd = row.get("session_date")
            taxon_id = row.get("taxon_id")
            if not sd or not taxon_id or sd < week_start or sd > latest:
                continue
            item = weekly.setdefault(
                row["station_id"],
                {
                    "station_name": row["station_name"],
                    "observations": 0,
                    "taxa": set(),
                },
            )
            item["observations"] += 1
            item["taxa"].add(int(taxon_id))
        if weekly:
            active = max(
                weekly.values(),
                key=lambda item: (len(item["taxa"]), item["observations"]),
            )
            insights.append(
                _insight(
                    "This week",
                    f"{active['station_name']} is carrying the strongest weekly signal",
                    f"{len(active['taxa'])} moth taxa and {active['observations']} observations in the latest seven-night window.",
                    f"{week_start.isoformat()} to {latest.isoformat()}",
                    82,
                )
            )

    if year:
        for pulse in first_of_season(settings, year)[:4]:
            if pulse["spread_days"] > 2:
                continue
            names = [
                station["station_name"]
                for station in pulse["stations"].values()
            ]
            insights.append(
                _insight(
                    "Synchronized flight",
                    f"{pulse['label']} moved through {pulse['station_count']} stations together",
                    f"First-of-season dates were within {pulse['spread_days']} days across {', '.join(sorted(names))}.",
                    pulse["pulse"],
                    88 - pulse["spread_days"],
                )
            )

        current_firsts: dict[int, date] = {}
        historical_firsts: dict[int, date] = {}
        labels: dict[int, str] = {}
        for row in rows:
            taxon_id = row.get("taxon_id")
            sd = row.get("session_date")
            if not taxon_id or not sd:
                continue
            taxon_id = int(taxon_id)
            labels[taxon_id] = row["label"]
            if sd.year == year:
                if taxon_id not in current_firsts or sd < current_firsts[taxon_id]:
                    current_firsts[taxon_id] = sd
            elif sd.year < year:
                if taxon_id not in historical_firsts or sd.timetuple().tm_yday < historical_firsts[taxon_id].timetuple().tm_yday:
                    historical_firsts[taxon_id] = sd
        early = []
        for taxon_id, current in current_firsts.items():
            historical = historical_firsts.get(taxon_id)
            if not historical:
                continue
            delta = historical.timetuple().tm_yday - current.timetuple().tm_yday
            if 7 <= delta <= 60:
                early.append((delta, labels[taxon_id], current, historical))
        for delta, label, current, historical in sorted(early, reverse=True)[:3]:
            insights.append(
                _insight(
                    "Early emergence",
                    f"{label} is running {delta} days earlier than its prior earliest date",
                    f"This year's first tracked session was {current.isoformat()}; the previous earliest was {historical.isoformat()}.",
                    str(year),
                    84 + min(delta, 30),
                )
            )

        calendar = daily_species_counts(settings, year)
        if calendar:
            peak = max(calendar, key=lambda item: item["total"])
            insights.append(
                _insight(
                    "Peak night",
                    f"{peak['label']} is the richest night of {year} so far",
                    f"The network recorded {peak['total']} unique moth taxa across {peak['active_stations']} active station{'s' if peak['active_stations'] != 1 else ''}.",
                    "unique species across stations",
                    76,
                )
            )

    taxa = station_taxa(settings)
    shared = [taxon for taxon in taxa if taxon["station_count"] > 1]
    if shared:
        top = max(shared, key=lambda item: (item["station_count"], item["total_count"]))
        insights.append(
            _insight(
                "Shared fauna",
                f"{top['label']} is the most widely shared moth in the network",
                f"It has appeared at {top['station_count']} tracked stations, with {top['total_count']} total observations.",
                "all time",
                78,
            )
        )

    longest = None
    for taxon in taxa:
        for station in taxon["stations"].values():
            first = station.get("first")
            latest_seen = station.get("latest")
            if not first or not latest_seen:
                continue
            span = (latest_seen - first).days
            if longest is None or span > longest[0]:
                longest = (span, taxon["label"], station["station_name"], first, latest_seen)
    if longest and longest[0] > 0:
        span, label, station_name, first, latest_seen = longest
        insights.append(
            _insight(
                "Long flight period",
                f"{label} has the longest tracked flight span",
                f"{station_name} has records from {first.isoformat()} through {latest_seen.isoformat()}, a {span}-day span.",
                "all time",
                70,
            )
        )

    if latest:
        recent_unique = [
            item for item in unique_station_taxa(settings)
            if item.get("latest") and (latest - item["latest"]).days <= 14
        ]
        for item in recent_unique[:3]:
            insights.append(
                _insight(
                    "Unique station species",
                    f"{item['label']} is currently unique to {item['station_name']}",
                    f"This species has {item['count']} tracked observation{'s' if item['count'] != 1 else ''} and has not appeared at another station yet.",
                    f"latest {item['latest'].isoformat()}",
                    68,
                )
            )

    seen_titles = set()
    deduped = []
    for insight in sorted(insights, key=lambda item: (-item["score"], item["title"])):
        if insight["title"] in seen_titles:
            continue
        seen_titles.add(insight["title"])
        deduped.append(insight)
        if len(deduped) >= limit:
            break
    return deduped


def station_profile(settings: Settings, station_id: str) -> dict[str, Any]:
    rows = [
        row for row in load_rows(settings)
        if row["station_id"] == station_id
    ]
    taxa = station_taxa(settings)
    unique_taxa = unique_station_taxa(settings)

    taxa_seen = {int(row["taxon_id"]) for row in rows if row.get("taxon_id")}
    dates = [row["session_date"] for row in rows if row.get("session_date")]
    latest = max(dates) if dates else None
    first = min(dates) if dates else None

    by_month: dict[int, set[int]] = defaultdict(set)
    for row in rows:
        taxon_id = row.get("taxon_id")
        sd = row.get("session_date")
        if taxon_id and sd:
            by_month[sd.month].add(int(taxon_id))
    seasonal_richness = [
        {
            "month": month,
            "label": date(2000, month, 1).strftime("%b"),
            "species": len(by_month.get(month, set())),
        }
        for month in range(1, 13)
    ]

    taxa_by_date: dict[date, set[int]] = defaultdict(set)
    for row in rows:
        taxon_id = row.get("taxon_id")
        sd = row.get("session_date")
        if taxon_id and sd:
            taxa_by_date[sd].add(int(taxon_id))
    seen = set()
    accumulation = []
    for sd in sorted(taxa_by_date):
        before = len(seen)
        seen.update(taxa_by_date[sd])
        if len(seen) != before:
            accumulation.append({"date": sd, "species": len(seen)})
    if len(accumulation) > 40:
        step = max(1, (len(accumulation) + 39) // 40)
        accumulation = accumulation[::step]
        if accumulation[-1]["species"] != len(seen):
            accumulation.append({"date": max(dates), "species": len(seen)})

    signature = []
    for taxon in taxa:
        entry = taxon["stations"].get(station_id)
        if not entry:
            continue
        total = max(1, taxon["total_count"])
        share = entry["count"] / total
        signature.append(
            {
                "label": taxon["label"],
                "count": entry["count"],
                "network_count": total,
                "station_count": taxon["station_count"],
                "share": share,
            }
        )
    signature = sorted(
        signature,
        key=lambda item: (-item["share"], -item["count"], item["label"]),
    )[:12]

    station_uniques = [
        item for item in unique_taxa
        if item["station_id"] == station_id
    ]
    station_uniques = sorted(
        station_uniques,
        key=lambda item: (-item["count"], item["label"]),
    )[:12]

    recent = sorted(
        rows,
        key=lambda row: (
            row.get("created_at") or row.get("observed_on") or "",
            row.get("inat_obs_id") or 0,
        ),
        reverse=True,
    )[:12]

    active_sessions = len({row["session_date"] for row in rows if row.get("session_date")})
    observations = len(rows)
    species = len(taxa_seen)
    unique_count = len([item for item in unique_taxa if item["station_id"] == station_id])
    narrative_bits = []
    if species:
        narrative_bits.append(
            f"This station has documented {species} moth taxa from {observations} observations."
        )
    if active_sessions:
        narrative_bits.append(
            f"The dataset spans {active_sessions} moth sessions from {first} through {latest}."
        )
    if unique_count:
        narrative_bits.append(
            f"{unique_count} taxa are currently unique to this station within the tracked network."
        )
    if signature:
        narrative_bits.append(
            f"{signature[0]['label']} is the strongest station-associated species by current share of network observations."
        )

    return {
        "station_id": station_id,
        "observations": observations,
        "species": species,
        "active_sessions": active_sessions,
        "first_session": first,
        "latest_session": latest,
        "unique_count": unique_count,
        "seasonal_richness": seasonal_richness,
        "accumulation": accumulation,
        "signature_species": signature,
        "unique_species": station_uniques,
        "recent": recent,
        "narrative": " ".join(narrative_bits) if narrative_bits else "This station is configured and waiting for synced moth observations.",
    }


def trend_summary(settings: Settings) -> dict[str, Any]:
    rows = load_rows(settings)
    taxa = station_taxa(settings)
    if not rows:
        return {
            "phenology": [],
            "network_accumulation": [],
            "rank_abundance": [],
            "station_similarity": [],
        }

    by_taxon: dict[int, dict[str, Any]] = {}
    for row in rows:
        taxon_id = row.get("taxon_id")
        sd = row.get("session_date")
        if not taxon_id or not sd:
            continue
        taxon_id = int(taxon_id)
        item = by_taxon.setdefault(
            taxon_id,
            {
                "taxon_id": taxon_id,
                "label": row["label"],
                "count": 0,
                "stations": set(),
                "dates": [],
                "months": defaultdict(int),
            },
        )
        item["count"] += 1
        item["stations"].add(row["station_id"])
        item["dates"].append(sd)
        item["months"][sd.month] += 1

    phenology = []
    for item in sorted(
        by_taxon.values(),
        key=lambda value: (-len(value["stations"]), -value["count"], value["label"]),
    )[:16]:
        dates = item["dates"]
        days = [seen_date.timetuple().tm_yday for seen_date in dates]
        first_day = min(days)
        latest_day = max(days)
        first_label = date(2000, 1, 1) + timedelta(days=first_day - 1)
        latest_label = date(2000, 1, 1) + timedelta(days=latest_day - 1)
        peak_month = max(item["months"], key=item["months"].get)
        phenology.append(
            {
                "taxon_id": item["taxon_id"],
                "label": item["label"],
                "count": item["count"],
                "station_count": len(item["stations"]),
                "first_day": first_day,
                "latest_day": latest_day,
                "first_label": first_label.strftime("%b ") + str(first_label.day),
                "latest_label": latest_label.strftime("%b ") + str(latest_label.day),
                "peak_month": date(2000, peak_month, 1).strftime("%b"),
            }
        )

    taxa_by_date: dict[date, set[int]] = defaultdict(set)
    for row in rows:
        taxon_id = row.get("taxon_id")
        sd = row.get("session_date")
        if taxon_id and sd:
            taxa_by_date[sd].add(int(taxon_id))
    seen = set()
    network_accumulation = []
    for sd in sorted(taxa_by_date):
        before = len(seen)
        seen.update(taxa_by_date[sd])
        if len(seen) != before:
            network_accumulation.append(
                {
                    "date": sd.isoformat(),
                    "species": len(seen),
                    "new_species": len(seen) - before,
                }
            )
    if len(network_accumulation) > 44:
        step = max(1, (len(network_accumulation) + 43) // 44)
        network_accumulation = network_accumulation[::step]
        if network_accumulation[-1]["species"] != len(seen):
            latest_date = max(taxa_by_date)
            network_accumulation.append(
                {
                    "date": latest_date.isoformat(),
                    "species": len(seen),
                    "new_species": 0,
                }
            )

    rank_abundance = [
        {
            "rank": rank,
            "taxon_id": taxon["taxon_id"],
            "label": taxon["label"],
            "count": taxon["total_count"],
            "station_count": taxon["station_count"],
        }
        for rank, taxon in enumerate(
            sorted(taxa, key=lambda item: (-item["total_count"], item["label"]))[:24],
            start=1,
        )
    ]

    station_taxa_sets: dict[str, dict[str, Any]] = {}
    for row in rows:
        taxon_id = row.get("taxon_id")
        if not taxon_id:
            continue
        item = station_taxa_sets.setdefault(
            row["station_id"],
            {"station_id": row["station_id"], "station_name": row["station_name"], "taxa": set()},
        )
        item["taxa"].add(int(taxon_id))

    station_similarity = []
    stations = sorted(station_taxa_sets.values(), key=lambda item: item["station_name"])
    for left in stations:
        matrix_row = []
        for right in stations:
            shared = len(left["taxa"] & right["taxa"])
            union = len(left["taxa"] | right["taxa"])
            similarity = shared / union if union else 0
            matrix_row.append(
                {
                    "station_id": right["station_id"],
                    "station_name": right["station_name"],
                    "shared": shared,
                    "union": union,
                    "similarity": similarity,
                }
            )
        station_similarity.append(
            {
                "station_id": left["station_id"],
                "station_name": left["station_name"],
                "cells": matrix_row,
            }
        )

    return {
        "phenology": phenology,
        "network_accumulation": network_accumulation,
        "rank_abundance": rank_abundance,
        "station_similarity": station_similarity,
    }


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

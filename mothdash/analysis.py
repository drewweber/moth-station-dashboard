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


def flight_season_date(day: date) -> tuple[int, date]:
    """Group January with the preceding winter and normalize month/day."""
    season_year = day.year - 1 if day.month == 1 else day.year
    normalized_year = 2001 if day.month == 1 else 2000
    return season_year, date(normalized_year, day.month, day.day)


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


def latest_session_taxa(settings: Settings) -> dict[str, Any]:
    rows = load_rows(settings)
    session_dates = [row["session_date"] for row in rows if row.get("session_date")]
    latest = max(session_dates) if session_dates else None
    if latest is None:
        return {"session_date": None, "taxa": [], "station_counts": {}, "observations": 0}

    grouped: dict[tuple[int, str], dict[str, Any]] = {}
    station_taxa_seen: dict[str, set[int]] = defaultdict(set)
    observation_count = 0

    for row in rows:
        taxon_id = row.get("taxon_id")
        if not taxon_id or row.get("session_date") != latest:
            continue
        observation_count += 1
        taxon_id = int(taxon_id)
        station_id = row["station_id"]
        station_taxa_seen[station_id].add(taxon_id)
        key = (taxon_id, station_id)
        item = grouped.setdefault(
            key,
            {
                "taxon_id": taxon_id,
                "label": row["label"],
                "station_id": station_id,
                "station_name": row["station_name"],
                "count": 0,
                "first": latest,
                "latest": latest,
                "photo_url": None,
                "url": None,
                "observer_login": None,
            },
        )
        item["count"] += 1
        if row.get("photo_url") and not item["photo_url"]:
            item["photo_url"] = row["photo_url"]
            item["url"] = row.get("url")
            item["observer_login"] = row.get("observer_login")
        elif row.get("url") and not item["url"]:
            item["url"] = row.get("url")
            item["observer_login"] = row.get("observer_login")

    by_taxon: dict[int, dict[str, Any]] = defaultdict(lambda: {"stations": {}})
    for item in grouped.values():
        item["is_county_first"] = False
        item["is_state_first"] = False
        item["first_among_tracked"] = False
        taxon = by_taxon[item["taxon_id"]]
        taxon["taxon_id"] = item["taxon_id"]
        taxon["label"] = item["label"]
        taxon["stations"][item["station_id"]] = item
        if item.get("photo_url") and not taxon.get("photo_url"):
            taxon["photo_url"] = item["photo_url"]
            taxon["url"] = item.get("url")
            taxon["photo_station_name"] = item["station_name"]
            taxon["observer_login"] = item.get("observer_login")

    taxa = []
    for item in by_taxon.values():
        item["station_count"] = len(item["stations"])
        item["total_count"] = sum(station["count"] for station in item["stations"].values())
        item["first_among_tracked_date"] = latest
        item["first_among_tracked_stations"] = []
        taxa.append(dict(item))

    return {
        "session_date": latest,
        "taxa": sorted(taxa, key=lambda item: (-item["station_count"], -item["total_count"], item["label"])),
        "station_counts": {
            station_id: len(station_taxa)
            for station_id, station_taxa in station_taxa_seen.items()
        },
        "observations": observation_count,
    }


def daily_species_counts(settings: Settings, year: int | None = None) -> list[dict[str, Any]]:
    rows = load_rows(settings)
    days: dict[str, dict[str, Any]] = {}
    for row in rows:
        taxon_id = row.get("taxon_id")
        sd = row.get("session_date")
        if not taxon_id or sd is None or row.get("rank") != "species":
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
    subject: str = "",
) -> dict[str, Any]:
    return {
        "category": category,
        "title": title,
        "body": body,
        "meta": meta,
        "score": score,
        "subject": subject,
    }


def _select_varied_insights(
    insights: list[dict[str, Any]],
    limit: int,
    category_limit: int = 2,
) -> list[dict[str, Any]]:
    """Keep the feed timely without allowing one template to dominate it."""
    ordered = []
    seen_titles = set()
    for insight in sorted(insights, key=lambda item: (-item["score"], item["title"])):
        if insight["title"] in seen_titles:
            continue
        seen_titles.add(insight["title"])
        ordered.append(insight)

    selected = []
    selected_titles = set()
    selected_subjects = set()
    category_counts: dict[str, int] = defaultdict(int)
    diversity_target = min(limit, 12)
    for insight in ordered:
        category = insight["category"]
        if category_counts[category]:
            continue
        subject = insight.get("subject")
        if subject and subject in selected_subjects:
            continue
        selected.append(insight)
        selected_titles.add(insight["title"])
        if subject:
            selected_subjects.add(subject)
        category_counts[category] += 1
        if len(selected) >= diversity_target:
            break

    for insight in ordered:
        if len(selected) >= limit:
            break
        if insight["title"] in selected_titles:
            continue
        category = insight["category"]
        if category_counts[category] >= category_limit:
            continue
        subject = insight.get("subject")
        if subject and subject in selected_subjects:
            continue
        selected.append(insight)
        selected_titles.add(insight["title"])
        if subject:
            selected_subjects.add(subject)
        category_counts[category] += 1

    return selected


def dashboard_insights(settings: Settings, limit: int = 16) -> list[dict[str, Any]]:
    """Build deterministic naturalist-feed stories from the current dataset."""
    rows = load_rows(settings)
    if not rows:
        return []

    insights: list[dict[str, Any]] = []
    session_dates = [row["session_date"] for row in rows if row.get("session_date")]
    latest = max(session_dates) if session_dates else None
    year = active_year(settings)
    taxon_sessions: dict[int, set[date]] = defaultdict(set)
    taxon_observations: dict[int, set[int]] = defaultdict(set)
    taxon_labels: dict[int, str] = {}
    for row in rows:
        taxon_id = row.get("taxon_id")
        sd = row.get("session_date")
        if not taxon_id or not sd:
            continue
        taxon_id = int(taxon_id)
        taxon_sessions[taxon_id].add(sd)
        if row.get("inat_obs_id"):
            taxon_observations[taxon_id].add(int(row["inat_obs_id"]))
        taxon_labels[taxon_id] = row["label"]

    if latest:
        latest_firsts = []
        latest_by_taxon: dict[int, dict[str, Any]] = {}
        first_by_station_taxon: dict[tuple[str, int], dict[str, Any]] = {}
        for row in rows:
            taxon_id = row.get("taxon_id")
            sd = row.get("session_date")
            if not taxon_id or not sd:
                continue
            taxon_id = int(taxon_id)
            if sd == latest:
                current = latest_by_taxon.setdefault(
                    taxon_id,
                    {"stations": set(), "observations": set(), "label": row["label"]},
                )
                current["stations"].add(row["station_name"])
                if row.get("inat_obs_id"):
                    current["observations"].add(int(row["inat_obs_id"]))
            key = (row["station_id"], int(taxon_id))
            current = first_by_station_taxon.get(key)
            if current is None or sd < current["date"]:
                first_by_station_taxon[key] = {
                    "date": sd,
                    "label": row["label"],
                    "station_name": row["station_name"],
                    "taxon_id": taxon_id,
                }
        network_firsts = {
            taxon_id: min(dates)
            for taxon_id, dates in taxon_sessions.items()
            if dates
        }
        for item in first_by_station_taxon.values():
            if item["date"] == latest:
                latest_firsts.append(item)
        latest_firsts = sorted(
            latest_firsts,
            key=lambda item: (item["station_name"], item["label"]),
        )
        for item in latest_firsts:
            if network_firsts.get(item["taxon_id"]) == latest:
                station_names = sorted(latest_by_taxon[item["taxon_id"]]["stations"])
                insights.append(
                    _insight(
                        "Network newcomer",
                        f"{item['label']} just entered the tracked network",
                        f"Its first network record came from {', '.join(station_names)} on the latest moth night.",
                        latest.isoformat(),
                        97,
                        subject=f"taxon:{item['taxon_id']}",
                    )
                )
            else:
                insights.append(
                    _insight(
                        "New station record",
                        f"{item['station_name']} added {item['label']}",
                        "This species appeared in that station's tracked moth list for the first time on the latest session.",
                        latest.isoformat(),
                        92,
                        subject=f"taxon:{item['taxon_id']}",
                    )
                )

        for taxon_id, item in latest_by_taxon.items():
            station_names = sorted(item["stations"])
            if len(station_names) > 1 and len(item["observations"]) > 1:
                insights.append(
                    _insight(
                        "Same-night connection",
                        f"{item['label']} connected {len(station_names)} stations in one moth night",
                        f"It was recorded across {', '.join(station_names)} during the latest session.",
                        latest.isoformat(),
                        94,
                        subject=f"taxon:{taxon_id}",
                    )
                )

            previous_dates = sorted(day for day in taxon_sessions[taxon_id] if day < latest)
            if previous_dates:
                gap = (latest - previous_dates[-1]).days
                if gap >= 30:
                    insights.append(
                        _insight(
                            "Back in flight",
                            f"{item['label']} returned after {gap} quiet days",
                            f"The previous tracked session was {previous_dates[-1].isoformat()}; it reappeared at {', '.join(station_names)}.",
                            latest.isoformat(),
                            80 + min(gap // 20, 9),
                            subject=f"taxon:{taxon_id}",
                        )
                    )

            regional_records = len(taxon_observations[taxon_id])
            if regional_records <= 3 and network_firsts.get(taxon_id) != latest:
                insights.append(
                    _insight(
                        "Under-documented find",
                        f"{item['label']} has only {regional_records} tracked network record{'s' if regional_records != 1 else ''}",
                        f"The latest came from {', '.join(station_names)} and adds useful evidence for its regional flight timing.",
                        latest.isoformat(),
                        83 - regional_records,
                        subject=f"taxon:{taxon_id}",
                    )
                )

        try:
            history_date = latest.replace(year=latest.year - 1)
        except ValueError:
            history_date = None
        if history_date:
            then_taxa = {
                int(row["taxon_id"])
                for row in rows
                if row.get("taxon_id") and row.get("session_date") == history_date
            }
            now_taxa = set(latest_by_taxon)
            echoes = sorted(then_taxa & now_taxa, key=lambda taxon_id: taxon_labels[taxon_id])
            if echoes:
                examples = ", ".join(taxon_labels[taxon_id] for taxon_id in echoes[:3])
                insights.append(
                    _insight(
                        "This date in history",
                        f"{len(echoes)} species echoed the same moth night one year later",
                        f"Recorded on both {history_date.isoformat()} and {latest.isoformat()}, including {examples}.",
                        "year-over-year return",
                        79,
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
                    subject=f"taxon:{pulse['taxon_id']}",
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
                early.append((delta, labels[taxon_id], current, historical, taxon_id))
        for delta, label, current, historical, taxon_id in sorted(early, reverse=True)[:3]:
            insights.append(
                _insight(
                    "Early emergence",
                    f"{label} is running {delta} days earlier than its prior earliest date",
                    f"This year's first tracked session was {current.isoformat()}; the previous earliest was {historical.isoformat()}.",
                    str(year),
                    84 + min(delta, 30),
                    subject=f"taxon:{taxon_id}",
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
                subject=f"taxon:{top['taxon_id']}",
            )
        )

    seasonal_dates: dict[tuple[str, int, int], dict[str, Any]] = {}
    for row in rows:
        taxon_id = row.get("taxon_id")
        sd = row.get("session_date")
        if not taxon_id or not sd or row.get("rank") != "species":
            continue
        taxon_id = int(taxon_id)
        season_year, normalized_date = flight_season_date(sd)
        item = seasonal_dates.setdefault(
            (row["station_id"], taxon_id, season_year),
            {
                "taxon_id": taxon_id,
                "label": row["label"],
                "station_name": row["station_name"],
                "season_year": season_year,
                "days": set(),
            },
        )
        item["days"].add(normalized_date)

    longest = None
    for item in seasonal_dates.values():
        days = sorted(item["days"])
        if len(days) < 10:
            continue
        first = days[0]
        latest_seen = days[-1]
        span = (latest_seen - first).days
        if longest is None or span > longest[0]:
            longest = (
                span,
                item["label"],
                item["station_name"],
                first,
                latest_seen,
                item["taxon_id"],
                len(days),
                item["season_year"],
            )
    if longest and longest[0] > 0:
        span, label, station_name, first, latest_seen, taxon_id, session_count, season_year = longest
        insights.append(
            _insight(
                "Long flight period",
                f"{label} has the longest tracked seasonal flight window",
                f"{station_name} has records from {first:%b} {first.day} through {latest_seen:%b} {latest_seen.day} within the {season_year} flight season across {session_count} distinct moth dates, a {span}-day window.",
                "longest single tracked season",
                70,
                subject=f"taxon:{taxon_id}",
            )
        )

    if latest:
        recent_unique = [
            item for item in unique_station_taxa(settings)
            if item.get("latest")
            and item["latest"] < latest
            and (latest - item["latest"]).days <= 14
        ]
        for item in recent_unique[:3]:
            insights.append(
                _insight(
                    "Unique station species",
                    f"{item['label']} is currently unique to {item['station_name']}",
                    f"This species has {item['count']} tracked observation{'s' if item['count'] != 1 else ''} and has not appeared at another station yet.",
                    f"latest {item['latest'].isoformat()}",
                    68,
                    subject=f"taxon:{item['taxon_id']}",
                )
            )

    if latest and taxa:
        spotlight = sorted(taxa, key=lambda item: (item["label"], item["taxon_id"]))[
            latest.toordinal() % len(taxa)
        ]
        station_count = spotlight["station_count"]
        insights.append(
            _insight(
                "Species spotlight",
                spotlight["label"],
                f"Across the tracked record it has {spotlight['total_count']} observation{'s' if spotlight['total_count'] != 1 else ''} from {station_count} station{'s' if station_count != 1 else ''}.",
                "rotates with each new moth night",
                60,
                subject=f"taxon:{spotlight['taxon_id']}",
            )
        )

    return _select_varied_insights(insights, limit)


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
    by_week: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"taxa": set(), "observations": 0}
    )
    for row in rows:
        taxon_id = row.get("taxon_id")
        sd = row.get("session_date")
        if taxon_id and sd:
            by_month[sd.month].add(int(taxon_id))
            week = min(52, max(1, ((sd.timetuple().tm_yday - 1) // 7) + 1))
            by_week[week]["taxa"].add(int(taxon_id))
            by_week[week]["observations"] += 1
    seasonal_richness = [
        {
            "month": month,
            "label": date(2000, month, 1).strftime("%b"),
            "species": len(by_month.get(month, set())),
        }
        for month in range(1, 13)
    ]
    phenology_weeks = []
    for week in range(1, 53):
        start = date(2000, 1, 1) + timedelta(days=(week - 1) * 7)
        phenology_weeks.append(
            {
                "week": week,
                "label": f"{start:%b} {start.day}",
                "species": len(by_week[week]["taxa"]),
                "observations": by_week[week]["observations"],
            }
        )

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

    expected_next = []
    if latest:
        latest_year_taxa = {
            int(row["taxon_id"]) for row in rows
            if row.get("taxon_id")
            and row.get("session_date")
            and row["session_date"].year == latest.year
        }
        start_day = latest.timetuple().tm_yday
        next_window: dict[int, dict[str, Any]] = {}
        for row in rows:
            taxon_id = row.get("taxon_id")
            sd = row.get("session_date")
            if not taxon_id or not sd:
                continue
            day = sd.timetuple().tm_yday
            delta = (day - start_day) % 366
            if delta == 0 or delta > 30:
                continue
            taxon_id = int(taxon_id)
            item = next_window.setdefault(
                taxon_id,
                {
                    "taxon_id": taxon_id,
                    "label": row["label"],
                    "records": 0,
                    "days": [],
                    "seen_this_year": taxon_id in latest_year_taxa,
                },
            )
            item["records"] += 1
            item["days"].append(day)
        for item in next_window.values():
            first_day = min(item["days"])
            last_day = max(item["days"])
            first_label = date(2000, 1, 1) + timedelta(days=first_day - 1)
            last_label = date(2000, 1, 1) + timedelta(days=last_day - 1)
            item["window"] = (
                f"{first_label:%b} {first_label.day}"
                if first_day == last_day
                else f"{first_label:%b} {first_label.day} to {last_label:%b} {last_label.day}"
            )
            del item["days"]
            expected_next.append(item)
        expected_next = sorted(
            expected_next,
            key=lambda item: (item["seen_this_year"], -item["records"], item["label"]),
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
        "phenology_weeks": phenology_weeks,
        "accumulation": accumulation,
        "signature_species": signature,
        "unique_species": station_uniques,
        "expected_next": expected_next,
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
            "monthly_overlays": [],
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

    by_year_month: dict[int, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
    by_year_month_station: dict[
        int, dict[int, dict[str, dict[str, Any]]]
    ] = defaultdict(lambda: defaultdict(dict))
    for row in rows:
        taxon_id = row.get("taxon_id")
        sd = row.get("session_date")
        if not taxon_id or not sd or row.get("rank") != "species":
            continue
        taxon_id = int(taxon_id)
        by_year_month[sd.year][sd.month].add(taxon_id)
        station = by_year_month_station[sd.year][sd.month].setdefault(
            row["station_id"],
            {
                "station_id": row["station_id"],
                "station_name": row["station_name"],
                "taxa": set(),
            },
        )
        station["taxa"].add(taxon_id)
    monthly_overlays = []
    for year, months in sorted(by_year_month.items()):
        values = [
            {
                "month": month,
                "label": date(2000, month, 1).strftime("%b"),
                "species": len(months.get(month, set())),
                "stations": [
                    {
                        "station_id": station["station_id"],
                        "station_name": station["station_name"],
                        "species": len(station["taxa"]),
                    }
                    for station in sorted(
                        by_year_month_station[year].get(month, {}).values(),
                        key=lambda value: value["station_name"],
                    )
                ],
            }
            for month in range(1, 13)
        ]
        monthly_overlays.append(
            {
                "year": year,
                "total_species": len(set().union(*months.values())) if months else 0,
                "months": values,
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
        "monthly_overlays": monthly_overlays,
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

"""Static HTML renderer."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

from .analysis import (
    active_year,
    daily_species_counts,
    dashboard_insights,
    first_of_season,
    generated_at,
    diversify_by_station,
    habitat_summary,
    hero_photos,
    latest_session_taxa,
    record_highlights,
    recent_days_taxa,
    recent_observations,
    station_profile,
    station_summaries,
    station_taxa,
    trend_summary,
    unique_station_taxa,
    weekly_recap,
)
from .config import Settings, Station, active_stations
from .db import connect, init_db


FALLBACK_COLORS = [
    "#d7b56d",
    "#6eb7a8",
    "#cf7d92",
    "#9b8ed4",
    "#7fb3d5",
    "#90b66f",
    "#d88b61",
    "#c8a7d8",
]


def h(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    return escape(str(value))


def _mode_toggle(history_href: str, live_href: str, active: str) -> str:
    """Render the primary History/Live navigation used across generated pages."""
    history_current = ' aria-current="page"' if active == "history" else ""
    live_current = ' aria-current="page"' if active == "live" else ""
    return f"""
    <nav class="mode-toggle" aria-label="Dashboard mode">
      <a class="{'is-active' if active == 'history' else ''}" href="{h(history_href)}"{history_current}>History</a>
      <a class="{'is-active' if active == 'live' else ''}" href="{h(live_href)}"{live_current}>Live</a>
    </nav>
    """


def _dashboard_section_nav(index_href: str = "index.html") -> str:
    """Render the dashboard section menu for pages outside the dashboard root."""
    items = (
        ("Last night", "last-night"),
        ("Past week", "past-week"),
        ("Stations", "stations"),
        ("Feed", "feed"),
        ("Recent", "recent"),
        ("First arrivals", "pulses"),
        ("Firsts", "records"),
        ("Unique", "unique"),
        ("Calendar", "calendar"),
        ("Trends", "trends"),
        ("Species", "species"),
    )
    links = "".join(
        f'<a href="{h(index_href)}#{section_id}">{h(label)}</a>'
        for label, section_id in items
    )
    return f'<nav class="section-nav" aria-label="Dashboard sections">{links}</nav>'


def _insight_feedback_id(insight: dict[str, Any]) -> str:
    """Create a stable browser-storage key for a generated feed item."""
    source = "\x1f".join(
        str(insight.get(field, ""))
        for field in ("category", "title", "body", "meta")
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def _summary_map(summaries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["station_id"]: item for item in summaries}


def _station_color(station: Station, index: int) -> str:
    return station.color or FALLBACK_COLORS[index % len(FALLBACK_COLORS)]


def _station_color_map(stations: list[Station]) -> dict[str, str]:
    return {
        station.id: _station_color(station, index)
        for index, station in enumerate([station for station in stations if station.enabled])
    }


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        return f"rgba(215, 181, 109, {alpha:.3f})"
    try:
        red = int(value[0:2], 16)
        green = int(value[2:4], 16)
        blue = int(value[4:6], 16)
    except ValueError:
        return f"rgba(215, 181, 109, {alpha:.3f})"
    return f"rgba({red}, {green}, {blue}, {alpha:.3f})"


def _sort_button(label: str, sort_type: str = "text", default: str = "") -> str:
    default_attr = f' data-sort-default="{h(default)}"' if default else ""
    return (
        f'<button class="sort-button" type="button" data-sort-type="{h(sort_type)}"'
        f'{default_attr}>{h(label)}<span aria-hidden="true"></span></button>'
    )


def _station_short_label(station: Station) -> str:
    labels = {
        "kingfisher": "Kingfisher",
        "bosque-neimi": "Bosque",
        "dombroskie-homestead": "Dombroskie",
        "zeledonia-monkey-run": "Monkey Run",
        "iandavies-dove-dr": "Dove Dr",
        "durfee-hill": "Durfee",
        "tompkins-map-area": "Woodlawn",
    }
    return labels.get(station.id, station.name.split()[0])


def _station_page_path(station: Station) -> str:
    return f"stations/{station.id}.html"


def _metric(label: str, value: Any, compact: bool = False) -> str:
    class_name = "hero-metric hero-metric-compact" if compact else "hero-metric"
    return f"""
    <div class="{class_name}">
      <strong>{h(value)}</strong>
      <span>{h(label)}</span>
    </div>
    """


def _hero_metrics(
    summaries: list[dict[str, Any]],
    taxa: list[dict[str, Any]],
    pulses: list[dict[str, Any]],
    stations: list[Station],
    records: list[dict[str, Any]],
) -> str:
    total_observations = sum(item["observations"] for item in summaries)
    latest_sessions = [item["latest_session"] for item in summaries if item.get("latest_session")]
    latest = max(latest_sessions) if latest_sessions else "waiting"
    notable = len([
        item for item in records
        if item.get("is_county_first") or item.get("is_state_first")
    ])
    return "".join(
        [
            _metric("enabled stations", len([s for s in stations if s.enabled])),
            _metric("moth observations", f"{total_observations:,}"),
            _metric("unique species", f"{len(taxa):,}"),
            _metric("iNat firsts", f"{notable:,}"),
            _metric("latest session", latest, compact=True),
        ]
    )


def _photo_strip(rows: list[dict[str, Any]]) -> str:
    photos = []
    seen = set()
    for row in rows:
        url = row.get("photo_url")
        if not url or url in seen:
            continue
        seen.add(url)
        label = row.get("label") or "Moth observation"
        station = row.get("station_name") or "Station"
        photos.append(
            f"""
            <a class="photo-tile" href="{h(row.get("url"))}" aria-label="{h(label)} at {h(station)}">
              <img src="{h(url)}" alt="{h(label)}" loading="lazy">
              <span>
                <strong>{h(label)}</strong>
                <small>{h(station)}</small>
              </span>
            </a>
            """
        )
        if len(photos) >= 8:
            break
    if not photos:
        return '<div class="photo-empty">Photos will appear here after the next sync.</div>'
    return "".join(photos)


def _station_cards(summaries: list[dict[str, Any]], stations: list[Station]) -> str:
    enabled = sorted(
        (station for station in stations if station.enabled),
        key=lambda station: station.name.lower(),
    )
    if not enabled:
        return '<p class="empty">No stations are enabled. Add one in stations.toml and run a sync.</p>'
    by_station = _summary_map(summaries)
    cards = []
    for index, station in enumerate(enabled):
        item = by_station.get(station.id)
        species = item["species"] if item else 0
        observations = item["observations"] if item else 0
        latest = item["latest_session"] if item else "not synced"
        location = station.public_location or "configured station"
        if not station.active:
            status = "inactive"
        else:
            status = "active" if item else "queued"
        cards.append(
            f"""
            <article class="station-card" style="--station-color: {_station_color(station, index)}">
              <div>
                <p class="station-status station-status-{h(status).replace(" ", "-")}">{h(status)}</p>
                <h3><a href="{h(_station_page_path(station))}">{h(station.name)}</a></h3>
                <p>{h(location)}</p>
              </div>
              <div class="station-numbers">
                <span><strong>{h(species)}</strong> species</span>
                <span><strong>{h(f"{observations:,}")}</strong> observations</span>
              </div>
              <p class="latest">Latest session: {h(latest)}</p>
            </article>
            """
        )
    return "\n".join(cards)


def _insight_cards(insights: list[dict[str, Any]]) -> str:
    if not insights:
        return '<p class="empty">Insight cards will appear after observations are synced.</p>'
    cards = []
    for index, insight in enumerate(insights[:12], start=1):
        feedback_id = _insight_feedback_id(insight)
        category = h(insight["category"])
        title = h(insight["title"])
        meta = h(insight.get("meta"))
        cards.append(
            f"""
            <article class="insight-card" data-insight-feedback
              data-insight-id="{feedback_id}"
              data-insight-category="{category}"
              data-insight-title="{title}"
              data-insight-meta="{meta}">
              <div class="insight-index">{index:02d}</div>
              <p>{category}</p>
              <h3>{title}</h3>
              <span>{h(insight["body"])}</span>
              <small>{meta}</small>
              <div class="insight-feedback" role="group" aria-label="Rate this insight">
                <span>Useful?</span>
                <button type="button" class="insight-rating" data-insight-rating="up"
                  aria-label="Good insight" aria-pressed="false">&#128077;</button>
                <button type="button" class="insight-rating" data-insight-rating="down"
                  aria-label="Needs improvement" aria-pressed="false">&#128078;</button>
              </div>
            </article>
            """
        )
    return "\n".join(cards)


def _recent_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">No recent observations yet. Run a sync to populate this dashboard.</p>'
    body = []
    for row in rows:
        label = h(row["label"])
        if row.get("url"):
            label = f'<a href="{h(row["url"])}">{label}</a>'
        body.append(
            f"""
            <tr>
              <td>{h(row.get("created_at", "")[:10])}</td>
              <td>{h(row.get("session_date"))}</td>
              <td>{h(row["station_name"])}</td>
              <td>{label}</td>
              <td>{h(row.get("observer_login"))}</td>
            </tr>
            """
        )
    return f"""
    <table class="sortable-table">
      <thead>
        <tr>
          <th scope="col">{_sort_button("Uploaded", "date")}</th>
          <th scope="col">{_sort_button("Session", "date")}</th>
          <th scope="col">{_sort_button("Station")}</th>
          <th scope="col">{_sort_button("Taxon")}</th>
          <th scope="col">{_sort_button("Observer")}</th>
        </tr>
      </thead>
      <tbody>{''.join(body)}</tbody>
    </table>
    """


def _recent_cards(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">No recent observations yet. Run a sync to populate this dashboard.</p>'
    cards = []
    for row in rows[:12]:
        label = h(row["label"])
        image = ""
        if row.get("photo_url"):
            image = f'<img src="{h(row["photo_url"])}" alt="{label}" loading="lazy">'
        else:
            image = '<div class="sighting-placeholder" aria-hidden="true">light sheet</div>'
        taxon = label
        if row.get("url"):
            taxon = f'<a href="{h(row["url"])}">{label}</a>'
        cards.append(
            f"""
            <article class="sighting-card">
              <div class="sighting-image">{image}</div>
              <div class="sighting-copy">
                <p>{h(row["station_name"])} · {h(row.get("session_date"))}</p>
                <h3>{taxon}</h3>
                <span>{h(row.get("observer_login"))}</span>
              </div>
            </article>
            """
        )
    return "".join(cards)


def _taxa_period_dashboard(
    payload: dict[str, Any],
    stations: list[Station],
    period_caption: str,
    empty_message: str,
) -> str:
    period_label = payload.get("period_label")
    taxa = payload.get("taxa") or []
    if not period_label:
        return f'<p class="empty">{h(empty_message)}</p>'
    if not taxa:
        latest = payload.get("latest_session")
        latest_note = (
            f" Latest synced session: {h(latest)}."
            if latest
            else " No station sessions have been synced yet."
        )
        return f"""
        <div class="night-summary night-summary-empty">
          <div>
            <strong>{h(period_label)}</strong>
            <span>{h(period_caption)}</span>
          </div>
        </div>
        <p class="empty">{h(empty_message)}{latest_note}</p>
        """

    colors = _station_color_map(stations)
    station_lookup = {station.id: station for station in stations if station.enabled}
    station_counts = payload.get("station_counts") or {}
    active_station_ids = [
        station.id for station in stations
        if station.enabled and station_counts.get(station.id, 0)
    ]
    shared_taxa = sum(1 for row in taxa if row.get("station_count", 0) > 1)
    station_only_totals = {
        station_id: sum(
            1
            for row in taxa
            if row.get("station_count", 0) == 1 and station_id in row.get("stations", {})
        )
        for station_id in active_station_ids
    }

    # Keep shared flights first by default, while reserving a small real
    # preview for every station-only filter.
    preview_taxa = list(taxa[:PERIOD_CARD_PREVIEW_LIMIT])
    preview_taxon_ids = {row.get("taxon_id") for row in preview_taxa}
    for station_id in active_station_ids:
        station_only_rows = [
            row
            for row in taxa
            if row.get("station_count", 0) == 1 and station_id in row.get("stations", {})
        ]
        for row in station_only_rows[:PERIOD_STATION_ONLY_PREVIEW_LIMIT]:
            if row.get("taxon_id") not in preview_taxon_ids:
                preview_taxa.append(row)
                preview_taxon_ids.add(row.get("taxon_id"))

    station_chips = []
    if shared_taxa:
        station_chips.append(
            f"""
            <button type="button" class="night-station-chip night-filter-chip night-shared-chip"
                    style="--station-color: var(--amber)"
                    data-night-shared-filter
                    data-night-shared-total="{h(shared_taxa)}"
                    aria-pressed="false"
                    aria-label="Show species shared by multiple stations in this period">
              Shared
            </button>
            """
        )
    for station_id in active_station_ids:
        station = station_lookup[station_id]
        station_chips.append(
            f"""
            <button type="button" class="night-station-chip night-filter-chip"
                    style="--station-color: {h(colors[station_id])}"
                    data-night-station-filter="{h(station_id)}"
                    data-station-name="{h(station.name)}"
                    data-night-station-total="{h(station_only_totals[station_id])}"
                    aria-pressed="false"
                    aria-label="Show species only seen at {h(station.name)} in this period">
              {h(_station_short_label(station))}
              <strong>{h(station_counts.get(station_id, 0))}</strong>
            </button>
            """
        )

    cards = []
    for row in preview_taxa:
        label = h(row["label"])
        photo_url = row.get("photo_url")
        if photo_url:
            image = f'<img src="{h(photo_url)}" alt="{label}" loading="lazy">'
        else:
            image = '<div class="night-placeholder" aria-hidden="true">no photo</div>'
        title = label
        if row.get("url"):
            title = f'<a href="{h(row["url"])}">{label}</a>'
        badges = []
        for station_id, entry in row["stations"].items():
            station = station_lookup.get(station_id)
            name = _station_short_label(station) if station else entry["station_name"]
            badges.append(
                f'<span style="--station-color: {h(colors.get(station_id, "#d7b56d"))}">{h(name)}</span>'
            )
        status = "shared" if row.get("station_count", 0) > 1 else "single station"
        card_station_ids = "|".join(sorted(row["stations"]))
        single_station_id = next(iter(row["stations"])) if row.get("station_count", 0) == 1 else ""
        cards.append(
            f"""
            <article class="night-card"
                     data-night-card
                     data-station-ids="{h(card_station_ids)}"
                     data-single-station-id="{h(single_station_id)}"
                     data-station-count="{h(row.get("station_count", 0))}">
              <div class="night-image">{image}</div>
              <div class="night-copy">
                <p>{h(status)} · {h(row.get("total_count", 0))} obs</p>
                <h3>{title}</h3>
                <div class="night-badges">{''.join(badges)}</div>
              </div>
            </article>
            """
        )

    return f"""
    <div class="night-summary">
      <div>
        <strong>{h(period_label)}</strong>
        <span>{h(period_caption)}</span>
      </div>
      <div>
        <strong>{h(len(taxa))}</strong>
        <span>unique moth species</span>
      </div>
      <div>
        <strong>{h(payload.get("observations", 0))}</strong>
        <span>observations</span>
      </div>
      <div>
        <strong>{h(shared_taxa)}</strong>
        <span>shared by stations</span>
      </div>
    </div>
    <div class="night-period-filter" data-night-period-filter>
      <div class="night-stations" aria-label="Species count by station">{''.join(station_chips)}</div>
      <p class="night-filter-status" data-night-filter-status aria-live="polite" hidden></p>
    </div>
    <div class="night-grid">{''.join(cards)}</div>
    <p class="empty night-filter-empty" data-night-filter-empty hidden></p>
    """


def _last_night_dashboard(payload: dict[str, Any], stations: list[Station]) -> str:
    return _taxa_period_dashboard(
        payload,
        stations,
        "latest moth session",
        "No latest-session moth observations are available yet.",
    )


def _recent_week_dashboard(payload: dict[str, Any], stations: list[Station]) -> str:
    return _taxa_period_dashboard(
        payload,
        stations,
        "past 7 nights",
        "No species-level moth observations were recorded in this seven-night range.",
    )


def _pulse_cards(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">No multi-station first-of-season records yet. Add another station and sync observations to compare seasonal timing.</p>'
    cards = []
    for row in rows[:6]:
        cards.append(
            f"""
            <article class="pulse-card">
              <p>{h(row["pulse"])}</p>
              <h3>{h(row["label"])}</h3>
              <div>
                <span>{h(row["station_count"])} stations</span>
                <span>{h(row["spread_days"])} day spread</span>
                <span>{h(row["earliest"])} to {h(row["latest"])}</span>
              </div>
            </article>
            """
        )
    return "".join(cards)


def _flag_list(flags: list[str]) -> str:
    return "".join(f'<span class="flag">{h(flag)}</span>' for flag in flags)


RECORD_FLAG_TYPES = ("state iNat first", "county iNat first", "first among tracked")
RECORD_CARD_PREVIEW_LIMIT = 12
RECORD_TABLE_PAGE_SIZE = 100
PERIOD_CARD_PREVIEW_LIMIT = 36
PERIOD_STATION_ONLY_PREVIEW_LIMIT = 12


def _record_cards(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">No county, state, or tracked-station firsts are cached yet. Run a sync to refresh record context.</p>'
    cards = []
    for row in rows[:RECORD_CARD_PREVIEW_LIMIT]:
        label = h(row["label"])
        photo_url = row.get("photo_url")
        if photo_url:
            image = f'<img src="{h(photo_url)}" alt="{label}" loading="lazy">'
        else:
            image = '<div class="record-placeholder" aria-hidden="true">no photo</div>'
        title = label
        if row.get("url"):
            title = f'<a href="{h(row["url"])}">{label}</a>'
        cards.append(
            f"""
            <article class="record-card">
              <div class="record-image">{image}</div>
              <div class="record-copy">
                <div class="record-flags">{_flag_list(row["flags"])}</div>
                <h3>{title}</h3>
                <p>{h(row["station_name"])} · {h(row["first"])}</p>
              </div>
            </article>
            """
        )
    return "".join(cards)


def _record_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">No first-record highlights are available yet.</p>'
    body = []
    for row in rows:
        body.append(
            f"""
            <tr data-record-row data-flags="{h('|'.join(row["flags"]))}"
              data-station-id="{h(row["station_id"])}"
              data-label="{h(row["label"])}"
              data-station-name="{h(row["station_name"])}"
              data-first="{h(row["first"])}"
              data-photo-url="{h(row.get("photo_url") or "")}"
              data-href="{h(row.get("url") or "")}">
              <td>{f'<a href="{h(row["url"])}">{h(row["label"])}</a>' if row.get("url") else h(row["label"])}</td>
              <td>{h(row["station_name"])}</td>
              <td data-sort-value="{h(row['first'])}">{h(row["first"])}</td>
              <td>{_flag_list(row["flags"])}</td>
            </tr>
            """
        )
    return f"""
    <table class="sortable-table" data-record-table>
      <thead>
        <tr>
          <th scope="col">{_sort_button("Species")}</th>
          <th scope="col">{_sort_button("Station")}</th>
          <th scope="col">{_sort_button("Station first", "date", "desc")}</th>
          <th scope="col">{_sort_button("Flags")}</th>
        </tr>
      </thead>
      <tbody>{''.join(body)}</tbody>
    </table>
    <div class="record-archive-controls">
      <span data-record-count aria-live="polite">Showing all {h(len(rows))} records</span>
      <button type="button" data-record-show-more data-page-size="{RECORD_TABLE_PAGE_SIZE}">
        Show {RECORD_TABLE_PAGE_SIZE} more
      </button>
    </div>
    """


def _record_filters(stations: list[Station]) -> str:
    location_options = "".join(
        f'<option value="{h(station.id)}">{h(station.name)}</option>'
        for station in sorted(
            (station for station in stations if station.enabled),
            key=lambda station: station.name.lower(),
        )
    )
    flag_labels = {
        "state iNat first": "State iNat first",
        "county iNat first": "County iNat first",
        "first among tracked": "First among tracked",
    }
    type_options = "".join(
        f'<option value="{h(flag_type)}">{h(flag_labels.get(flag_type, flag_type))}</option>'
        for flag_type in RECORD_FLAG_TYPES
    )
    return f"""
    <div class="record-filter-row">
      <div>
        <label for="record-filter-type">Type of first</label>
        <select id="record-filter-type" data-record-filter="type">
          <option value="">All types</option>
          {type_options}
        </select>
      </div>
      <div>
        <label for="record-filter-location">Location</label>
        <select id="record-filter-location" data-record-filter="location">
          <option value="">All locations</option>
          {location_options}
        </select>
      </div>
    </div>
    <p class="empty" data-record-empty hidden>No firsts match that type and location yet.</p>
    """


def _unique_station_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">No station-unique moths are available yet.</p>'
    body = []
    for row in rows:
        body.append(
            f"""
            <tr>
              <td>{h(row["label"])}</td>
              <td>{h(row["station_name"])}</td>
              <td>{h(row["count"])}</td>
              <td>{h(row["first"])}</td>
              <td>{h(row["latest"])}</td>
            </tr>
            """
        )
    return f"""
    <table class="sortable-table">
      <thead>
        <tr>
          <th scope="col">{_sort_button("Species")}</th>
          <th scope="col">{_sort_button("Only station")}</th>
          <th scope="col">{_sort_button("Obs", "number")}</th>
          <th scope="col">{_sort_button("First", "date")}</th>
          <th scope="col">{_sort_button("Latest", "date")}</th>
        </tr>
      </thead>
      <tbody>{''.join(body)}</tbody>
    </table>
    """


def _unique_species_chip(row: dict[str, Any]) -> str:
    return f"""
    <li>
      <strong>{h(row["label"])}</strong>
      <span>{h(row["count"])} obs · {h(row["first"])} to {h(row["latest"])}</span>
    </li>
    """


def _unique_station_sections(rows: list[dict[str, Any]], stations: list[Station]) -> str:
    if not rows:
        return '<p class="empty">No station-unique moths are available yet.</p>'

    colors = _station_color_map(stations)
    by_station: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_station.setdefault(row["station_id"], []).append(row)

    panels = []
    for station in [station for station in stations if station.enabled]:
        station_rows = by_station.get(station.id, [])
        count = len(station_rows)
        if not station_rows:
            panels.append(
                f"""
                <article class="unique-station-panel unique-station-empty" style="--station-color: {h(colors[station.id])}">
                  <div class="unique-station-head">
                    <div>
                      <p>{h(station.public_location or "tracked station")}</p>
                      <h3>{h(station.name)}</h3>
                    </div>
                    <strong>0</strong>
                  </div>
                  <p class="unique-empty-note">No taxa are currently unique to this station in the tracked network.</p>
                </article>
                """
            )
            continue

        most_observed = sorted(station_rows, key=lambda item: (-item["count"], item["label"]))[:8]
        recently_active = sorted(
            station_rows,
            key=lambda item: (item["latest"] or date.min, item["count"], item["label"]),
            reverse=True,
        )[:8]
        panels.append(
            f"""
            <article class="unique-station-panel" style="--station-color: {h(colors[station.id])}">
              <div class="unique-station-head">
                <div>
                  <p>{h(station.public_location or "tracked station")}</p>
                  <h3>{h(station.name)}</h3>
                </div>
                <strong>{h(count)}</strong>
              </div>
              <div class="unique-lists">
                <div>
                  <h4>Most observed here</h4>
                  <ul>{''.join(_unique_species_chip(row) for row in most_observed)}</ul>
                </div>
                <div>
                  <h4>Recently active uniques</h4>
                  <ul>{''.join(_unique_species_chip(row) for row in recently_active)}</ul>
                </div>
              </div>
              <details class="unique-full-list">
                <summary>Full station-unique list ({h(count)} taxa)</summary>
                <div class="table-wrap unique-table-wrap">{_unique_station_table(sorted(station_rows, key=lambda item: item["label"]))}</div>
              </details>
            </article>
            """
        )

    return f"""
    <div class="unique-filter-row">
      <label for="unique-filter">Filter unique moths</label>
      <input id="unique-filter" type="search" placeholder="Try Jeweled, slug, sphinx..." data-unique-filter>
    </div>
    <div class="unique-station-grid">{''.join(panels)}</div>
    """


def _pulse_table(rows: list[dict[str, Any]], stations: list[Station]) -> str:
    if not rows:
        return '<p class="empty">No multi-station first-of-season records yet. Add another station and sync observations to compare seasonal timing.</p>'
    enabled = [station for station in stations if station.enabled]
    colors = _station_color_map(stations)
    headers = "".join(
        f'<th scope="col" class="station-head" style="--station-color: {h(colors[station.id])}">'
        f'{_sort_button(station.name, "date")}</th>'
        for station in enabled
    )
    body = []
    for row in rows[:80]:
        station_cells = []
        for station in enabled:
            entry = row["stations"].get(station.id)
            if entry:
                value = h(entry["date"])
                sort_value = h(entry["date"])
                if entry.get("url"):
                    value = f'<a href="{h(entry["url"])}">{value}</a>'
            else:
                value = ""
                sort_value = ""
            station_cells.append(f'<td data-sort-value="{sort_value}">{value}</td>')
        body.append(
            f"""
            <tr>
              <td>{h(row["label"])}</td>
              <td data-sort-value="{h(row["station_count"])}">{h(row["station_count"])}</td>
              <td data-sort-value="{h(row["spread_days"])}">{h(row["spread_days"])}</td>
              <td><span class="tag">{h(row["pulse"])}</span></td>
              {''.join(station_cells)}
            </tr>
            """
        )
    return f"""
    <table class="sortable-table">
      <thead>
        <tr>
          <th scope="col">{_sort_button("Species")}</th>
          <th scope="col">{_sort_button("Stations", "number", "desc")}</th>
          <th scope="col">{_sort_button("Spread", "number")}</th>
          <th scope="col">{_sort_button("Pulse")}</th>
          {headers}
        </tr>
      </thead>
      <tbody>{''.join(body)}</tbody>
    </table>
    """


def _comparison_table(rows: list[dict[str, Any]], stations: list[Station]) -> str:
    if not rows:
        return '<p class="empty">No station species have been synced yet. Run a sync to populate this dashboard.</p>'
    enabled = [station for station in stations if station.enabled]
    colors = _station_color_map(stations)
    headers = "".join(
        f'<th scope="col" class="station-head" style="--station-color: {h(colors[station.id])}">'
        f'{_sort_button(station.name, "number")}</th>'
        for station in enabled
    )
    body = []
    for row in rows[:250]:
        cells = []
        for station in enabled:
            entry = row["stations"].get(station.id)
            if entry:
                flags = []
                if entry.get("is_state_first"):
                    flags.append("state")
                if entry.get("is_county_first"):
                    flags.append("county")
                if entry.get("first_among_tracked"):
                    flags.append("tracked")
                flag_html = _flag_list(flags)
                cells.append(
                    f"<td data-sort-value=\"{h(entry['count'])}\"><strong>{h(entry['count'])}</strong><br>"
                    f"<span>{h(entry['first'])}</span>{flag_html}</td>"
                )
            else:
                cells.append('<td data-sort-value="0"></td>')
        body.append(
            f"""
            <tr>
              <td>{h(row["label"])}</td>
              <td data-sort-value="{h(row["station_count"])}">{h(row["station_count"])}</td>
              {''.join(cells)}
            </tr>
            """
        )
    return f"""
    <table class="sortable-table">
      <thead>
        <tr>
          <th scope="col">{_sort_button("Species")}</th>
          <th scope="col">{_sort_button("Stations", "number", "desc")}</th>
          {headers}
        </tr>
      </thead>
      <tbody>{''.join(body)}</tbody>
    </table>
    """


def _calendar_table(rows: list[dict[str, Any]], stations: list[Station], mode: str) -> str:
    if not rows:
        return '<p class="empty">No calendar counts are available yet.</p>'
    enabled = [station for station in stations if station.enabled]
    colors = _station_color_map(stations)
    max_count = max(
        [count for row in rows for count in row["stations"].values()] + [1]
    )
    headers = "".join(
        f'<th scope="col" class="station-head" style="--station-color: {h(colors[station.id])}">'
        f'{_sort_button(_station_short_label(station), "number")}</th>'
        for station in enabled
    )
    label = "Date" if mode == "year" else "Month day"
    body = []
    for row in rows:
        cells = []
        for station in enabled:
            count = row["stations"].get(station.id, 0)
            intensity = 0 if count == 0 else 0.16 + (0.74 * count / max_count)
            color = colors[station.id]
            background = _hex_to_rgba(color, intensity)
            cells.append(
                f"""
                <td class="calendar-cell" data-sort-value="{h(count)}">
                  <span style="--station-color: {h(color)}; --cell-bg: {h(background)}">{h(count) if count else ""}</span>
                </td>
                """
            )
        body.append(
            f"""
            <tr>
              <td data-sort-value="{h(row["sort_key"])}">{h(row["label"])}</td>
              <td data-sort-value="{h(row["active_stations"])}">{h(row["active_stations"])}</td>
              <td data-sort-value="{h(row["total"])}">{h(row["total"])}</td>
              {''.join(cells)}
            </tr>
            """
        )
    return f"""
    <table class="sortable-table calendar-table" aria-label="{h(label)} species counts by station">
      <thead>
        <tr>
          <th scope="col">{_sort_button(label, "date", "desc")}</th>
          <th scope="col">{_sort_button("Active stations", "number")}</th>
          <th scope="col">{_sort_button("Unique spp.", "number")}</th>
          {headers}
        </tr>
      </thead>
      <tbody>{''.join(body)}</tbody>
    </table>
    """


def _daily_species_line_chart(rows: list[dict[str, Any]], stations: list[Station], mode: str) -> str:
    """Render daily network richness as stacked union bars with overlap shown once."""
    if not rows:
        return '<p class="empty">No daily species counts are available yet.</p>'

    enabled = [station for station in stations if station.enabled]
    colors = _station_color_map(stations)
    dates = []
    for row in rows:
        if mode == "year":
            row_date = date.fromisoformat(row["key"])
        else:
            month, day = (int(part) for part in row["key"].split("-"))
            row_date = date(2000, month, day)
        dates.append(row_date)

    width = 900
    height = 300
    left = 52
    right = 22
    top = 22
    bottom = 42
    plot_width = width - left - right
    plot_height = height - top - bottom
    min_date = min(dates)
    max_date = max(dates)
    date_span = max(1, max_date.toordinal() - min_date.toordinal())
    date_count = len(rows)
    max_species = max(
        [row["total"] for row in rows]
        + [count for row in rows for count in row["stations"].values()]
        + [1]
    )

    def point(row: dict[str, Any], row_date: date, count: int) -> tuple[float, float]:
        if len(rows) == 1:
            x = left + plot_width / 2
        else:
            x = left + ((row_date.toordinal() - min_date.toordinal()) / date_span * plot_width)
        y = top + plot_height - (count / max_species * plot_height)
        return x, y

    station_series = []
    legend = ['<li class="daily-richness-shared-key"><i></i><span>Shared by 2+ stations</span></li>']
    for station in enabled:
        values = [
            row.get("station_unique", {}).get(station.id, row["stations"].get(station.id, 0))
            for row in rows
        ]
        if not any(values):
            continue
        color = colors[station.id]
        station_series.append((station, values, color))
        legend.append(
            f'<li style="--series-color: {h(color)}"><i></i><span>{h(_station_short_label(station))} only</span></li>'
        )

    if date_count <= 1:
        group_width = plot_width
    else:
        group_width = plot_width / (date_count - 1)
    bar_width = max(4, min(12, group_width * 0.74))

    stacked_bars = []
    for row, row_date in zip(rows, dates):
        x, _ = point(row, row_date, row["total"])
        bar_x = x - bar_width / 2
        y_cursor = top + plot_height
        for station, _values, color in station_series:
            count = row.get("station_unique", {}).get(station.id, row["stations"].get(station.id, 0))
            if not count:
                continue
            bar_height = count / max_species * plot_height
            y_cursor -= bar_height
            stacked_bars.append(
                f'<rect class="daily-richness-station-bar" style="--series-color: {h(color)}" '
                f'x="{bar_x:.1f}" y="{y_cursor:.1f}" '
                f'width="{bar_width:.1f}" height="{bar_height:.1f}" '
                f'fill="{h(color)}"></rect>'
            )
        shared_count = row.get("shared")
        if shared_count is None:
            shared_count = max(
                0,
                row["total"] - sum(row.get("station_unique", {}).values()),
            )
        if shared_count:
            bar_height = shared_count / max_species * plot_height
            y_cursor -= bar_height
            stacked_bars.append(
                f'<rect class="daily-richness-shared-bar" '
                f'x="{bar_x:.1f}" y="{y_cursor:.1f}" '
                f'width="{bar_width:.1f}" height="{bar_height:.1f}"></rect>'
            )

    markers = []
    for row, row_date in zip(rows, dates):
        x, y = point(row, row_date, row["total"])
        shared_count = row.get("shared", 0)
        station_rows = "".join(
            f'<li><i style="--station-color: {h(colors[station.id])}"></i>'
            f'<span>{h(_station_short_label(station))}</span>'
            f'<strong>{h(row["stations"].get(station.id, 0))} total · {h(row.get("station_unique", {}).get(station.id, 0))} only</strong></li>'
            for station in enabled
        )
        tooltip_html = (
            f'<div class="monthly-tooltip-head"><strong>{h(row["label"])}</strong>'
            f'<span>{h(row["total"])} network species</span></div>'
            f'<ul>{station_rows}<li><i class="shared-dot"></i><span>Shared by 2+ stations</span><strong>{h(shared_count)}</strong></li></ul>'
        )
        aria_values = "; ".join(
            f"{station.name}: {row['stations'].get(station.id, 0)} total, {row.get('station_unique', {}).get(station.id, 0)} only"
            for station in enabled
        )
        markers.append(
            f"""
            <g class="monthly-point-group daily-richness-hit-group" style="--series-color: var(--ink)" tabindex="0" role="img"
               aria-label="{h(row['label'])}: {h(row['total'])} network species; {h(aria_values)}"
               data-tooltip-html="{h(tooltip_html)}">
              <circle class="monthly-hit-target" cx="{x:.1f}" cy="{y:.1f}" r="9"></circle>
            </g>
            """
        )

    date_labels = []
    for fraction in (0, 0.25, 0.5, 0.75, 1):
        ordinal = round(min_date.toordinal() + date_span * fraction)
        tick_date = date.fromordinal(ordinal)
        x = left + plot_width * fraction
        date_labels.append(
            f'<text class="chart-label" x="{x:.1f}" y="{height - 12}" text-anchor="middle">{h(tick_date.strftime("%b"))} {h(tick_date.day)}</text>'
        )

    mode_description = (
        "Each point is one moth session date in the selected year."
        if mode == "year"
        else "Each point combines the same calendar day across all synced years."
    )
    return f"""
    <figure class="daily-richness-line-chart">
      <ul class="daily-richness-legend" aria-label="Daily richness legend">{''.join(legend)}</ul>
      <svg viewBox="0 0 {width} {height}" role="img" aria-labelledby="daily-richness-title-{h(mode)} daily-richness-desc-{h(mode)}">
        <title id="daily-richness-title-{h(mode)}">Daily species richness by contribution and overlap</title>
        <desc id="daily-richness-desc-{h(mode)}">Each stacked bar totals the network unique-species union. Station-colored segments show species found only at that station on that date; the neutral segment shows species shared by two or more stations. {h(mode_description)} Focus or point at a bar to see station values.</desc>
        <line class="chart-axis" x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}"></line>
        <line class="chart-axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}"></line>
        <line class="chart-grid" x1="{left}" y1="{top}" x2="{left + plot_width}" y2="{top}"></line>
        <line class="chart-grid" x1="{left}" y1="{top + plot_height / 2:.1f}" x2="{left + plot_width}" y2="{top + plot_height / 2:.1f}"></line>
        <text class="chart-label" x="{left - 8}" y="{top + 4}" text-anchor="end">{h(max_species)}</text>
        <text class="chart-label" x="{left - 8}" y="{top + plot_height / 2 + 4:.1f}" text-anchor="end">{h(round(max_species / 2))}</text>
        <text class="chart-label" x="{left - 8}" y="{top + plot_height + 4}" text-anchor="end">0</text>
        {''.join(date_labels)}
        {''.join(stacked_bars)}
        {''.join(markers)}
      </svg>
      <div class="monthly-tooltip" role="tooltip" hidden></div>
    </figure>
    """


def _view_toggle(name: str, *views: tuple[str, str]) -> str:
    buttons = []
    for index, (view_id, label) in enumerate(views):
        active = " is-active" if index == 0 else ""
        buttons.append(
            f'<button type="button" class="view-toggle-button{active}" '
            f'data-view-target="{h(view_id)}">{h(label)}</button>'
        )
    return f"""
    <div class="view-toggle" role="group" aria-label="{h(name)}">
      {''.join(buttons)}
    </div>
    """


def _profile_metric(label: str, value: Any) -> str:
    return f'<div class="profile-metric"><strong>{h(value)}</strong><span>{h(label)}</span></div>'


def _seasonal_bars(profile: dict[str, Any]) -> str:
    rows = profile["seasonal_richness"]
    max_species = max([row["species"] for row in rows] + [1])
    bars = []
    for row in rows:
        width = 100 * row["species"] / max_species if max_species else 0
        bars.append(
            f"""
            <div class="month-bar">
              <span>{h(row["label"])}</span>
              <div><i style="width: {width:.1f}%"></i></div>
              <strong>{h(row["species"])} <small>{h(row["nights"])} nights</small></strong>
            </div>
            """
        )
    return "".join(bars)


def _format_upload_lag(minutes: float | None) -> str:
    if minutes is None:
        return "not available"
    rounded = max(0, round(minutes))
    if rounded < 60:
        return f"{rounded} min"
    hours, remaining_minutes = divmod(rounded, 60)
    if hours < 24:
        return f"{hours}h" if remaining_minutes < 30 else f"{hours}h {remaining_minutes}m"
    days, remaining_hours = divmod(hours, 24)
    return f"{days}d" if remaining_hours < 12 else f"{days}d {remaining_hours}h"


def _sampling_context(profile: dict[str, Any]) -> str:
    yearly = profile["yearly_coverage"]
    upload_timing = profile["upload_timing"]
    max_nights = max([row["nights"] for row in yearly] + [1])
    annual_rows = []
    for row in yearly:
        width = 100 * row["nights"] / max_nights
        annual_rows.append(
            f"""
            <div class="sampling-year-row">
              <span>{h(row["year"])}</span>
              <div aria-hidden="true"><i style="width: {width:.1f}%"></i></div>
              <strong>{h(row["nights"])} nights <small>{h(row["species"])} species</small></strong>
            </div>
            """
        )
    upload_metric = ""
    if upload_timing["timestamped_records"]:
        upload_metric = f"""
        <div>
          <dt>median upload lag</dt>
          <dd>{h(_format_upload_lag(upload_timing["median_lag_minutes"]))}</dd>
          <small>{h(upload_timing["timestamped_records"])} timestamped records</small>
        </div>
        """
    return f"""
    <div class="sampling-context">
      <dl class="sampling-context-metrics">
        <div>
          <dt>species-recorded nights</dt>
          <dd>{h(profile["active_sessions"])}</dd>
          <small>{h(profile["first_session"] or "waiting")} to {h(profile["latest_session"] or "waiting")}</small>
        </div>
        <div>
          <dt>calendar years covered</dt>
          <dd>{h(len(yearly))}</dd>
          <small>{h(" · ".join(str(row["year"]) for row in yearly) or "waiting")}</small>
        </div>
        {upload_metric}
      </dl>
      <figure class="sampling-year-chart">
        <figcaption>Moth-night coverage by year</figcaption>
        <div class="sampling-year-list">{"".join(annual_rows) or '<p class="empty">Moth-night coverage will appear after synced observations.</p>'}</div>
      </figure>
    </div>
    """


def _accumulation_bars(profile: dict[str, Any]) -> str:
    rows = profile["accumulation"]
    if not rows:
        return '<p class="empty">Species accumulation will appear after synced observations.</p>'
    max_species = max(row["species"] for row in rows)
    width = 720
    height = 260
    left = 52
    right = 24
    top = 22
    bottom = 42
    plot_width = width - left - right
    plot_height = height - top - bottom
    dates = [row["date"] for row in rows]
    min_date = min(dates)
    max_date = max(dates)
    date_span = max(1, max_date.toordinal() - min_date.toordinal())

    points = []
    for row in rows:
        x = left + ((row["date"].toordinal() - min_date.toordinal()) / date_span * plot_width)
        y = top + plot_height - ((row["species"] / max_species) * plot_height if max_species else 0)
        points.append((x, y, row))
    point_attr = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
    area_attr = f"{left},{top + plot_height:.1f} {point_attr} {left + plot_width:.1f},{top + plot_height:.1f}"
    markers = []
    for x, y, row in points:
        tooltip_html = (
            f'<div class="monthly-tooltip-head"><strong>{h(row["date"])}</strong>'
            f'<span>{h(row["species"])} species · {h(row["nights"])} nights</span></div>'
        )
        markers.append(
            f"""
            <g class="monthly-point-group" style="--series-color: var(--amber)" tabindex="0" role="img"
               aria-label="{h(row['date'])}: {h(row['species'])} species after {h(row['nights'])} active moth nights"
               data-tooltip-html="{h(tooltip_html)}">
              <circle class="monthly-hit-target" cx="{x:.1f}" cy="{y:.1f}" r="9"></circle>
              <circle class="monthly-point" cx="{x:.1f}" cy="{y:.1f}" r="2.6"></circle>
            </g>
            """
        )
    latest = rows[-1]
    return f"""
    <figure class="accumulation-line-chart">
      <svg viewBox="0 0 {width} {height}" role="img" aria-labelledby="accumulation-title accumulation-desc">
        <title id="accumulation-title">Station species accumulation curve</title>
        <desc id="accumulation-desc">Running moth species count from {h(min_date)} to {h(max_date)}, ending at {h(latest["species"])} species after {h(latest["nights"])} active moth nights. Focus or point at a node to see its date, count, and moth-night coverage.</desc>
        <line class="chart-axis" x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}"></line>
        <line class="chart-axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}"></line>
        <line class="chart-grid" x1="{left}" y1="{top}" x2="{left + plot_width}" y2="{top}"></line>
        <text class="chart-label" x="{left - 8}" y="{top + 4}" text-anchor="end">{h(max_species)}</text>
        <text class="chart-label" x="{left - 8}" y="{top + plot_height + 4}" text-anchor="end">0</text>
        <text class="chart-label" x="{left}" y="{height - 12}" text-anchor="start">{h(min_date)}</text>
        <text class="chart-label" x="{left + plot_width}" y="{height - 12}" text-anchor="end">{h(max_date)}</text>
        <polygon class="accumulation-area" points="{area_attr}"></polygon>
        <polyline class="accumulation-line" points="{point_attr}"></polyline>
        {''.join(markers)}
        <text class="chart-callout" x="{points[-1][0] - 8:.1f}" y="{points[-1][1] - 10:.1f}" text-anchor="end">{h(latest["species"])} species</text>
      </svg>
      <div class="monthly-tooltip" role="tooltip" hidden></div>
    </figure>
    """


def _profile_phenology_calendar(profile: dict[str, Any]) -> str:
    rows = profile["phenology_weeks"]
    if not rows:
        return '<p class="empty">Phenology calendar will appear after synced observations.</p>'
    max_species = max([row["species"] for row in rows] + [1])
    cells = []
    for row in rows:
        intensity = 0 if row["species"] == 0 else 0.14 + (0.72 * row["species"] / max_species)
        cells.append(
            f"""
            <div class="profile-week" style="--cell-bg: {_hex_to_rgba("#d7b56d", intensity)}">
              <strong>{h(row["species"]) if row["species"] else ""}</strong>
              <span>{h(row["label"])}</span>
              <small>{h(row["nights"])} nights</small>
            </div>
            """
        )
    return f'<div class="profile-week-grid">{"".join(cells)}</div>'


def _expected_next_list(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">No next-flight suggestions are available from the current station history.</p>'
    items = []
    for row in rows:
        label = h(row["label"])
        status = "already seen this year" if row["seen_this_year"] else "not yet seen this year"
        media = (
            f'<img src="{h(row["photo_url"])}" alt="{label}" loading="lazy">'
            if row.get("photo_url")
            else '<div class="watch-placeholder" aria-hidden="true">No photo</div>'
        )
        title = (
            f'<a href="{h(row["url"])}">{label}</a>'
            if row.get("url")
            else label
        )
        items.append(
            f"""
            <li class="watch-card">
              <div class="watch-image">{media}</div>
              <div class="watch-copy">
                <span>{title}</span>
                <small>{h(row["window"])} · {h(row["records"])} historical record{'s' if row["records"] != 1 else ''}</small>
                <em>{h(status)}</em>
              </div>
            </li>
            """
        )
    return f'<ul class="watch-grid">{"".join(items)}</ul>'


def _signature_species_gallery(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">Signature species will appear after observations are shared across stations.</p>'
    cards = []
    for row in rows:
        label = h(row["label"])
        media = (
            f'<img src="{h(row["photo_url"])}" alt="{label}" loading="lazy">'
            if row.get("photo_url")
            else '<div class="signature-placeholder" aria-hidden="true">No photo</div>'
        )
        content = f"""
          <div class="signature-media">{media}</div>
          <div class="signature-copy">
            <h3>{label}</h3>
            <p>{h(row['count'])} observations here · {h(f"{row['share']:.0%}")} of its network records</p>
            <small>Recorded at {h(row['station_count'])} tracked stations</small>
          </div>
        """
        if row.get("url"):
            cards.append(
                f'<a class="signature-card" href="{h(row["url"])}" aria-label="View {label} on iNaturalist">{content}</a>'
            )
        else:
            cards.append(f'<article class="signature-card">{content}</article>')
    return f'<div class="signature-gallery">{"".join(cards)}</div>'


def _recap_showcase_card(item: dict[str, Any], kicker: str, detail: str) -> str:
    label = h(item["label"])
    title = f'<a href="{h(item["url"])}">{label}</a>' if item.get("url") else label
    photo = (
        f'<img src="{h(item["photo_url"])}" alt="{label}" loading="lazy">'
        if item.get("photo_url")
        else '<div class="record-placeholder" aria-hidden="true">no photo</div>'
    )
    return f"""
      <article class="recap-showcase-card">
        <div class="recap-showcase-image">{photo}</div>
        <div class="recap-showcase-copy">
          <p class="recap-card-label">{h(kicker)}</p>
          <h4>{title}</h4>
          <p>{h(detail)}</p>
        </div>
      </article>
    """


def _weekly_recap(data: dict[str, Any]) -> str:
    week_range = f"{h(data['week_start'])} to {h(data['week_end'])}"
    if not data.get("has_data"):
        return f"""
          <p class="empty">Last week ({week_range}) was quiet at this station -- no species-level observations recorded.</p>
        """

    if data["previous_total_species"] == 0:
        trend_copy = "no prior week to compare yet"
    elif data["trend"] > 0:
        trend_copy = f"up {data['trend']} from {data['previous_total_species']} the week before"
    elif data["trend"] < 0:
        trend_copy = f"down {abs(data['trend'])} from {data['previous_total_species']} the week before"
    else:
        trend_copy = f"steady with {data['previous_total_species']} the week before"

    moths = data.get("moths_of_the_week") or []
    showcase_cards = []
    for index, moth in enumerate(moths, start=1):
        kicker = "Moth of the Week" if len(moths) == 1 else f"Moth of the Week #{index}"
        record_word = "record" if moth["network_count"] == 1 else "records"
        rarity_copy = "the rarest visitor of the week" if index == 1 else "another standout rarity this week"
        showcase_cards.append(
            _recap_showcase_card(
                moth,
                kicker,
                f"{moth['network_count']} tracked network {record_word} -- {rarity_copy}.",
            )
        )
    showcase_cards.append(
        _recap_showcase_card(
            data["frequent_flyer"],
            "Frequent Flyer",
            f"Seen {data['frequent_flyer']['count']} times here last week, more than anything else.",
        )
    )
    showcase_html = "".join(showcase_cards)

    new_in_town = data["new_in_town"]
    new_in_town_count = data.get("new_in_town_count", len(new_in_town))
    if not new_in_town:
        new_in_town_body = '<p class="recap-empty-line">No brand-new arrivals at this station last week.</p>'
    else:
        preview = new_in_town[:2]
        names = ", ".join(
            f'<a href="{h(item["url"])}">{h(item["label"])}</a>' if item.get("url") else h(item["label"])
            for item in preview
        )
        remainder = new_in_town_count - len(preview)
        tail = f", and {remainder} more" if remainder > 0 else ""
        plural = "species" if new_in_town_count == 1 else "species"
        new_in_town_body = (
            f'<p class="recap-stacked-copy">{h(new_in_town_count)} new {plural} first appeared here '
            f"this week, including {names}{tail}.</p>"
        )

    if data["top_shared_station_name"]:
        shared_copy = (
            f"Shared the most species with {h(data['top_shared_station_name'])} "
            f"({h(data['top_shared_count'])} species in common)."
        )
    else:
        shared_copy = "No species overlap with other tracked stations last week."

    return f"""
      <p class="recap-range">{week_range}</p>
      <div class="recap-showcase">{showcase_html}</div>
      <div class="recap-stats">
        <article class="recap-card recap-headline">
          <strong>{h(data['total_species'])}</strong>
          <span>species recorded last week</span>
          <small>{h(trend_copy)}</small>
        </article>
        <article class="recap-card">
          <strong>{h(data['nights_active'])}/{h(data['nights_total'])}</strong>
          <span>moth nights with uploads</span>
          <small>Perfect attendance is 7 of 7.</small>
        </article>
        <article class="recap-card">
          <p class="recap-card-label">New in Town</p>
          {new_in_town_body}
        </article>
        <article class="recap-card recap-card-wide">
          <p class="recap-card-label">How You Stacked Up</p>
          <p class="recap-stacked-copy">
            {h(data['total_species'])} species here, {h(data['total_shared_species'])} of them also seen
            elsewhere in the network last week. {shared_copy}
          </p>
        </article>
      </div>
    """

def _habitat_host_list(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="habitat-empty">No host-plant matches yet for species confirmed at this station.</p>'

    host_items = []
    for row in rows:
        label = h(row["label"])
        title = f'<a href="{h(row["url"])}">{label}</a>' if row.get("url") else label
        host_bits = []
        for hst in row["hosts"]:
            bit = h(hst["family"])
            if hst["genus"]:
                bit = f"{h(hst['genus'])} {h(hst['species'])}".strip() if hst["species"] else h(hst["genus"])
                if hst["family"]:
                    bit = f"{bit} ({h(hst['family'])})"
            host_bits.append(bit)
        host_text = "; ".join(host_bits)
        genus_note = (
            ' <small class="habitat-genus-note">(known at the genus level only)</small>'
            if row.get("genus_level_only") else ""
        )
        host_items.append(
            f'<li><span class="habitat-species">{title}</span>{genus_note}'
            f'<p class="habitat-hosts">{host_text}</p></li>'
        )
    return f'<ul class="habitat-list">{"".join(host_items)}</ul>'


def _habitat_summary(data: dict[str, Any], browse_url: str | None = None, full: bool = False) -> str:
    if not data.get("has_data"):
        return '<p class="empty">No host-plant reference data is available for confirmed species at this station yet.</p>'

    host_list_html = _habitat_host_list(data["host_plants"] if full else data["host_preview"])

    def candidate_list(items: list[dict[str, Any]], empty_copy: str) -> str:
        if not items:
            return f'<p class="habitat-empty">{h(empty_copy)}</p>'
        rows = []
        for item in items:
            genera = ", ".join(h(g) for g in item["shared_genera"])
            matches = ", ".join(h(label) for label in item.get("matching_species", []))
            rows.append(
                f'<li><a href="{h(item["inat_taxon_url"])}">{h(item["label"])}</a>'
                f'<small>shares {genera} with {matches}</small></li>'
            )
        return f'<ul class="habitat-list habitat-candidates">{"".join(rows)}</ul>'

    network_html = candidate_list(
        data["network_candidates"],
        "No matching companions confirmed at other tracked stations yet.",
    )
    regional_html = candidate_list(
        data["regional_candidates"],
        "No matching companions reported elsewhere in New York yet.",
    )

    coverage_note = h(data.get("coverage_note") or "")
    retrieved_at = h(data.get("retrieved_at") or "unknown date")
    source_label = h(data.get("source_label") or "the HOSTS database")
    source_url = data.get("source_url")
    source_link = f'<a href="{h(source_url)}">{source_label}</a>' if source_url else source_label
    browse_link = (
        f'<p class="habitat-browse"><a href="{h(browse_url)}">Browse all documented host associations ({h(data["matched_count"])})</a></p>'
        if browse_url and not full else ""
    )
    preview_note = "Most recently recorded matches are shown here." if not full else "All documented matches are shown here."

    return f"""
      <p class="habitat-overview">
        {h(data['matched_count'])} of {h(data['confirmed_count'])} species confirmed at this station have
        documented host plants ({h(data['unmatched_count'])} not yet matched).
      </p>
      <p class="habitat-preview-note">{preview_note}</p>
      {host_list_html}
      {browse_link}
      <details class="habitat-info">
        <summary><span aria-hidden="true">?</span> About this data</summary>
        <p>
          Host-plant records come from {source_link}, a CC0-licensed archive from the Natural History
          Museum, London. It has not been updated since 2023, so it reflects historical literature rather
          than necessarily current or local usage -- some matches are only known at the genus level, not
          the exact species, and some confirmed species here have no HOSTS record at all. {coverage_note}
          Retrieved {retrieved_at}.
        </p>
      </details>
      <div class="habitat-companions">
        <div>
          <p class="recap-card-label">Seen at other tracked stations</p>
          {network_html}
        </div>
        <div>
          <p class="recap-card-label">Reported elsewhere in New York, not yet tracked</p>
          {regional_html}
        </div>
      </div>
    """



def _distinctive_records(data: dict[str, Any]) -> str:
    if not data.get("total"):
        return '<p class="empty">No firsts or network-rare species are available yet.</p>'

    def record_rows(rows: list[dict[str, Any]], unique: bool) -> str:
        if not rows:
            return '<p class="distinctive-empty">None in the current dataset.</p>'
        items = []
        for row in rows:
            label = h(row["label"])
            count_detail = (
                "Only tracked record, network-wide"
                if unique
                else f"{row['network_count']} tracked network records"
            )
            detail = f"{count_detail} · {row['count']} observations here · last {row['latest']}"
            title = (
                f'<a href="{h(row["url"])}">{label}</a>'
                if row.get("url")
                else label
            )
            flags = _flag_list(row["flags"]) if row.get("flags") else ""
            items.append(
                f"""
                <li>
                  <span>{title}{flags}</span>
                  <small>{h(detail)}</small>
                </li>
                """
            )
        return f'<ol class="distinctive-list">{"".join(items)}</ol>'

    return f"""
      <div class="distinctive-overview" aria-label="Distinctive record summary">
        <strong>{h(data['total'])}</strong>
        <span>firsts or network-rare species recorded here</span>
        <small>{h(data['unique_count'])} unique network-wide · {h(data['rare_count'])} with 2-10 tracked network records</small>
      </div>
      <div class="distinctive-ledger">
        <section class="distinctive-group">
          <div class="distinctive-heading">
            <p>Uniques</p>
            <span>The only tracked record of this species anywhere in the network.</span>
          </div>
          {record_rows(data['uniques'], True)}
        </section>
        <section class="distinctive-group">
          <div class="distinctive-heading">
            <p>2-10 network records</p>
            <span>Rare across the whole network, or a state/county/network first, and worth a second look.</span>
          </div>
          {record_rows(data['rare'], False)}
        </section>
      </div>
    """


def _profile_recent(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">Recent observations will appear after the next sync.</p>'
    cards = []
    for row in rows:
        label = h(row["label"])
        image = ""
        if row.get("photo_url"):
            image = f'<img src="{h(row["photo_url"])}" alt="{label}" loading="lazy">'
        else:
            image = '<div class="sighting-placeholder" aria-hidden="true">light sheet</div>'
        title = f'<a href="{h(row["url"])}">{label}</a>' if row.get("url") else label
        cards.append(
            f"""
            <article class="sighting-card">
              <div class="sighting-image">{image}</div>
              <div class="sighting-copy">
                <p>{h(row.get("session_date"))}</p>
                <h3>{title}</h3>
                <span>{h(row.get("observer_login"))}</span>
              </div>
            </article>
            """
        )
    return "".join(cards)


def _phenology_ribbons(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">Phenology ribbons will appear after synced observations.</p>'
    items = []
    for row in rows:
        start = max(0, min(100, (row["first_day"] - 1) / 365 * 100))
        end = max(start + 1, min(100, row["latest_day"] / 365 * 100))
        width = end - start
        items.append(
            f"""
            <div class="phenology-row">
              <div>
                <strong>{h(row["label"])}</strong>
                <span>{h(row["station_count"])} stations · {h(row["count"])} obs · peak {h(row["peak_month"])}</span>
              </div>
              <div class="phenology-track" aria-label="{h(row["label"])} observed from {h(row["first_label"])} to {h(row["latest_label"])}">
                <i style="left: {start:.2f}%; width: {width:.2f}%"></i>
              </div>
              <small>{h(row["first_label"])} to {h(row["latest_label"])}</small>
            </div>
            """
        )
    return "".join(items)


def _network_accumulation(
    rows: list[dict[str, Any]],
    launches: list[dict[str, Any]],
    stations: list[Station],
) -> str:
    if not rows:
        return '<p class="empty">Network accumulation will appear after synced observations.</p>'
    max_species = max(row["species"] for row in rows)
    width = 720
    height = 260
    left = 52
    right = 24
    top = 22
    bottom = 42
    plot_width = width - left - right
    plot_height = height - top - bottom
    dates = [date.fromisoformat(row["date"]) for row in rows]
    min_date = min(dates)
    max_date = max(dates)
    date_span = max(1, max_date.toordinal() - min_date.toordinal())

    points = []
    for row, row_date in zip(rows, dates):
        x = left + ((row_date.toordinal() - min_date.toordinal()) / date_span * plot_width)
        y = top + plot_height - ((row["species"] / max_species) * plot_height if max_species else 0)
        points.append((x, y, row, row_date))
    point_attr = " ".join(f"{x:.1f},{y:.1f}" for x, y, _, _ in points)
    area_attr = f"{left},{top + plot_height:.1f} {point_attr} {left + plot_width:.1f},{top + plot_height:.1f}"
    markers = []
    for x, y, row, row_date in points:
        tooltip_html = (
            f'<div class="monthly-tooltip-head"><strong>{h(row_date)}</strong>'
            f'<span>{h(row["species"])} species · +{h(row["new_species"])} new</span></div>'
        )
        markers.append(
            f"""
            <g class="monthly-point-group" style="--series-color: var(--leaf)" tabindex="0" role="img"
               aria-label="{h(row_date)}: {h(row['species'])} species, {h(row['new_species'])} new"
               data-tooltip-html="{h(tooltip_html)}">
              <circle class="monthly-hit-target" cx="{x:.1f}" cy="{y:.1f}" r="9"></circle>
              <circle class="monthly-point" cx="{x:.1f}" cy="{y:.1f}" r="2.6"></circle>
            </g>
            """
        )
    colors = _station_color_map(stations)
    station_lookup = {station.id: station for station in stations}
    launch_markers = []
    launch_legend = []
    for launch in launches:
        launch_date = date.fromisoformat(launch["date"])
        if launch_date < min_date or launch_date > max_date:
            continue
        x = left + ((launch_date.toordinal() - min_date.toordinal()) / date_span * plot_width)
        color = colors.get(launch["station_id"], FALLBACK_COLORS[0])
        station = station_lookup.get(launch["station_id"])
        short_label = _station_short_label(station) if station else launch["station_name"]
        launch_markers.append(
            f"""
            <g class="station-launch-marker" style="--station-color: {h(color)}">
              <line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_height}"></line>
              <circle cx="{x:.1f}" cy="{top + plot_height:.1f}" r="4.2"></circle>
              <title>{h(launch['station_name'])} came online {h(launch_date)}</title>
            </g>
            """
        )
        launch_legend.append(
            f'<li style="--station-color: {h(color)}"><i></i><span>{h(short_label)}</span><time datetime="{h(launch_date)}">{h(launch_date)}</time></li>'
        )
    latest = rows[-1]
    return f"""
    <figure class="accumulation-line-chart network-line-chart">
      <svg viewBox="0 0 {width} {height}" role="img" aria-labelledby="network-accumulation-title network-accumulation-desc">
        <title id="network-accumulation-title">Network species accumulation curve</title>
        <desc id="network-accumulation-desc">Running network moth species count from {h(min_date)} to {h(max_date)}, ending at {h(latest["species"])} species.</desc>
        <line class="chart-axis" x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}"></line>
        <line class="chart-axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}"></line>
        <line class="chart-grid" x1="{left}" y1="{top}" x2="{left + plot_width}" y2="{top}"></line>
        <text class="chart-label" x="{left - 8}" y="{top + 4}" text-anchor="end">{h(max_species)}</text>
        <text class="chart-label" x="{left - 8}" y="{top + plot_height + 4}" text-anchor="end">0</text>
        <text class="chart-label" x="{left}" y="{height - 12}" text-anchor="start">{h(min_date)}</text>
        <text class="chart-label" x="{left + plot_width}" y="{height - 12}" text-anchor="end">{h(max_date)}</text>
        <polygon class="accumulation-area" points="{area_attr}"></polygon>
        {''.join(launch_markers)}
        <polyline class="accumulation-line" points="{point_attr}"></polyline>
        {''.join(markers)}
        <text class="chart-callout" x="{points[-1][0] - 8:.1f}" y="{points[-1][1] - 10:.1f}" text-anchor="end">{h(latest["species"])} species</text>
      </svg>
      <div class="monthly-tooltip" role="tooltip" hidden></div>
      <div class="station-launches">
        <p>Stations online</p>
        <ul>{''.join(launch_legend)}</ul>
      </div>
    </figure>
    """


def _monthly_overlays(rows: list[dict[str, Any]], stations: list[Station]) -> str:
    if not rows:
        return '<p class="empty">Monthly overlays will appear after synced observations.</p>'
    width = 720
    height = 260
    left = 46
    right = 64
    top = 20
    bottom = 42
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_species = max(
        [month["species"] for row in rows for month in row["months"]] + [1]
    )
    colors = ["#d7b56d", "#8aa77a", "#7fb3d5", "#cf7d92", "#9b8ed4"]
    enabled_stations = [station for station in stations if station.enabled]
    station_colors = _station_color_map(stations)
    series_rows = rows[-5:]
    polylines = []
    markers = []
    legend = []
    for index, row in enumerate(series_rows):
        color = colors[index % len(colors)]
        legend.append(
            f'<li style="--series-color: {h(color)}"><i></i><strong>{h(row["year"])}</strong><span>{h(row["total_species"])} total species</span></li>'
        )
        points = []
        for month in row["months"]:
            x = left + ((month["month"] - 1) / 11 * plot_width)
            y = top + plot_height - ((month["species"] / max_species) * plot_height if max_species else 0)
            points.append((x, y, month))
        point_attr = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
        polylines.append(
            f'<polyline class="monthly-line" style="--series-color: {h(color)}" points="{point_attr}"></polyline>'
        )
        for x, y, month in points:
            if month["species"] == 0:
                continue
            station_values = {
                item["station_id"]: item["species"]
                for item in month.get("stations", [])
            }
            station_rows = "".join(
                f'<li><i style="--station-color: {h(station_colors[station.id])}"></i>'
                f'<span>{h(_station_short_label(station))}</span>'
                f'<strong>{h(station_values.get(station.id, 0))}</strong></li>'
                for station in enabled_stations
            )
            tooltip_html = (
                f'<div class="monthly-tooltip-head"><strong>{h(month["label"])} {h(row["year"])}</strong>'
                f'<span>{h(month["species"])} network species</span></div>'
                f'<ul>{station_rows}</ul>'
            )
            aria_values = "; ".join(
                f"{station.name}: {station_values.get(station.id, 0)}"
                for station in enabled_stations
            )
            visible_point = f'<circle class="monthly-point" style="--series-color: {h(color)}" cx="{x:.1f}" cy="{y:.1f}" r="3"></circle>'
            markers.append(
                f"""
                <g class="monthly-point-group" tabindex="0" role="img"
                   aria-label="{h(row['year'])} {h(month['label'])}: {h(month['species'])} network species; {h(aria_values)}"
                   data-tooltip-html="{h(tooltip_html)}">
                  <circle class="monthly-hit-target" cx="{x:.1f}" cy="{y:.1f}" r="11"></circle>
                  {visible_point}
                </g>
                """
            )
    month_labels = []
    for month in [1, 4, 7, 10, 12]:
        x = left + ((month - 1) / 11 * plot_width)
        label = date(2000, month, 1).strftime("%b")
        month_labels.append(
            f'<text class="chart-label" x="{x:.1f}" y="{height - 12}" text-anchor="middle">{h(label)}</text>'
        )
    return f"""
    <figure class="monthly-overlay-chart">
      <ul class="monthly-legend" aria-label="Year legend">{''.join(legend)}</ul>
      <svg viewBox="0 0 {width} {height}" role="img" aria-labelledby="monthly-overlay-title monthly-overlay-desc">
        <title id="monthly-overlay-title">Monthly species richness by year</title>
        <desc id="monthly-overlay-desc">One line per year showing unique moth species by month across the station network. Focus or point at a month to compare station values.</desc>
        <line class="chart-axis" x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}"></line>
        <line class="chart-axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}"></line>
        <line class="chart-grid" x1="{left}" y1="{top}" x2="{left + plot_width}" y2="{top}"></line>
        <text class="chart-label" x="{left - 8}" y="{top + 4}" text-anchor="end">{h(max_species)}</text>
        <text class="chart-label" x="{left - 8}" y="{top + plot_height + 4}" text-anchor="end">0</text>
        {''.join(month_labels)}
        {''.join(polylines)}
        {''.join(markers)}
      </svg>
      <div class="monthly-tooltip" role="tooltip" hidden></div>
    </figure>
    """


def _rank_abundance(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">Rank abundance will appear after synced observations.</p>'
    max_count = max(row["count"] for row in rows)
    items = []
    for row in rows:
        width = 100 * row["count"] / max_count if max_count else 0
        items.append(
            f"""
            <div class="rank-row">
              <span>{h(row["rank"])}</span>
              <div>
                <strong>{h(row["label"])}</strong>
                <small>{h(row["station_count"])} stations · {h(row["count"])} obs</small>
                <i style="width: {width:.1f}%"></i>
              </div>
            </div>
            """
        )
    return "".join(items)


def _station_similarity_matrix(rows: list[dict[str, Any]], stations: list[Station]) -> str:
    if not rows:
        return '<p class="empty">Station similarity will appear after synced observations.</p>'
    by_station = {station.id: station for station in stations}
    colors = _station_color_map(stations)
    def row_label(station_id: str, station_name: str) -> str:
        station = by_station.get(station_id)
        return _station_short_label(station) if station else station_name

    headers = "".join(
        f'<th scope="col">{h(row_label(row["station_id"], row["station_name"]))}</th>'
        for row in rows
    )
    body = []
    for row in rows:
        label = row_label(row["station_id"], row["station_name"])
        cells = []
        for cell in row["cells"]:
            alpha = 0.08 + (0.78 * cell["similarity"])
            color = _hex_to_rgba(colors.get(cell["station_id"], FALLBACK_COLORS[0]), alpha)
            cells.append(
                f"""
                <td style="--cell-bg: {h(color)}" data-sort-value="{cell["similarity"]:.3f}">
                  <span>{cell["similarity"]:.0%}</span>
                  <small>{h(cell["shared"])} shared</small>
                </td>
                """
            )
        body.append(
            f"""
            <tr>
              <th scope="row">{h(label)}</th>
              {''.join(cells)}
            </tr>
            """
        )
    return f"""
    <table class="similarity-table">
      <thead><tr><th scope="col">Station</th>{headers}</tr></thead>
      <tbody>{''.join(body)}</tbody>
    </table>
    """


def _trend_section(trends: dict[str, Any], stations: list[Station]) -> str:
    return f"""
    <div class="trend-grid">
      <article class="trend-panel trend-panel-wide">
        <h3>Phenology ribbons</h3>
        <p>Common network species, shown by observed flight span across all synced years.</p>
        {_phenology_ribbons(trends["phenology"])}
      </article>
      <article class="trend-panel">
        <h3>Network accumulation</h3>
        <p>Running species list across all tracked stations.</p>
        {_network_accumulation(trends["network_accumulation"], trends["station_launches"], stations)}
      </article>
      <article class="trend-panel">
        <h3>Monthly overlays</h3>
        <p>Unique moth species by month, with one line per synced year. Hover, tap, or focus a point for station values.</p>
        {_monthly_overlays(trends["monthly_overlays"], stations)}
      </article>
      <article class="trend-panel">
        <h3>Rank abundance</h3>
        <p>Most frequently observed moth taxa in the current network cache.</p>
        {_rank_abundance(trends["rank_abundance"])}
      </article>
      <article class="trend-panel trend-panel-wide">
        <h3>Station similarity</h3>
        <p>Overlap coefficient based on shared moth taxa: shared species divided by the smaller station's total, so a small station whose species are a subset of a larger one's shows as fully similar. Darker cells mean more overlap.</p>
        <div class="similarity-wrap">{_station_similarity_matrix(trends["station_similarity"], stations)}</div>
      </article>
    </div>
    """


SENSITIVE_LIVE_QUERY_KEYS = {
    "lat",
    "lng",
    "radius",
    "nelat",
    "nelng",
    "swlat",
    "swlng",
}


def _public_live_query(settings: Settings, station: Station) -> tuple[dict[str, Any], bool]:
    query = station.live_api_params(settings)
    if (
        any(key in query for key in SENSITIVE_LIVE_QUERY_KEYS)
        and not station.public_live_precise_query
    ):
        return {}, False
    return query, True


def _snapshot_payload(settings: Settings, stations: list[Station], taxa: list[dict[str, Any]]) -> dict[str, Any]:
    known_taxa: dict[str, list[int]] = {}
    first_dates: dict[str, dict[str, str]] = {}
    with connect(settings.database) as conn:
        network_counts = {
            str(row["taxon_id"]): int(row["observation_count"])
            for row in conn.execute(
                """
                SELECT o.taxon_id, COUNT(DISTINCT o.inat_obs_id) AS observation_count
                FROM observations o
                JOIN stations s ON s.id = o.station_id
                WHERE s.enabled = 1
                  AND o.taxon_id IS NOT NULL
                  AND o.rank = 'species'
                GROUP BY o.taxon_id
                """
            ).fetchall()
        }
    for taxon in taxa:
        taxon_id = taxon.get("taxon_id")
        if not taxon_id:
            continue
        for station_id, station_taxon in taxon["stations"].items():
            known_taxa.setdefault(station_id, []).append(int(taxon_id))
            first = station_taxon.get("first")
            if first:
                first_dates.setdefault(station_id, {})[str(taxon_id)] = first.isoformat()

    colors = _station_color_map(stations)
    enabled = []
    for station in active_stations(stations):
        query, live_supported = _public_live_query(settings, station)
        enabled.append({
            "id": station.id,
            "name": station.name,
            "short_name": _station_short_label(station),
            "color": colors[station.id],
            "public_location": station.public_location,
            "query": query,
            "live_supported": live_supported,
            "live_note": "" if live_supported else "Live polling disabled for precise-location queries.",
            "known_taxa": sorted(known_taxa.get(station.id, [])),
            "first_dates": first_dates.get(station.id, {}),
        })

    return {
        "generated_at": generated_at(),
        "api_base": "https://api.inaturalist.org/v1",
        "live_mode_hours": 2,
        "poll_seconds": 10 * 60,
        "network_counts": network_counts,
        "stations": enabled,
    }


def _station_profile_page(station: Station, profile: dict[str, Any], recap: dict[str, Any], habitat: dict[str, Any], color: str) -> str:
    location = station.public_location or "Configured station"
    website = (
        f'<a href="{h(station.website)}">iNaturalist source</a>'
        if station.website else ""
    )
    metrics = "".join(
        [
            _profile_metric("moth species", f"{profile['species']:,}"),
            _profile_metric("observations", f"{profile['observations']:,}"),
            _profile_metric("moth sessions", f"{profile['active_sessions']:,}"),
            _profile_metric("unique here", f"{profile['unique_count']:,}"),
            _profile_metric("latest session", profile["latest_session"] or "waiting"),
        ]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(station.name)} · Moth Station Dashboard</title>
  <meta name="description" content="Station profile for {h(station.name)} in the moth stations dashboard.">
  <meta name="theme-color" content="#151611">
  <style>{CSS}</style>
</head>
<body>
  <a class="skip-link" href="#main">Skip to station profile</a>
  <header>
    <div class="topbar">
      <div class="topbar-primary">
        <a class="brand" href="../index.html"><span class="brand-mark" aria-hidden="true"></span><span>Moth stations</span></a>
        {_mode_toggle("../index.html", "../live.html", "history")}
      </div>
      {_dashboard_section_nav("../index.html")}
    </div>
    <div class="profile-hero" style="--station-color: {h(color)}">
      <p class="eyebrow">station profile</p>
      <h1>{h(station.name)}</h1>
      <p class="subhead">{h(location)}</p>
      <div class="profile-links">{website}</div>
      <div class="profile-metrics">{metrics}</div>
    </div>
  </header>
  <main id="main" class="site-shell">
    <section>
      <div class="section-head">
        <h2>Station story</h2>
        <p>{h(profile["narrative"])}</p>
      </div>
    </section>

    <section>
      <div class="section-head">
        <h2>Your Week at the Sheet</h2>
        <p>A recap of the most recently completed Monday-through-Sunday week at this station.</p>
      </div>
      {_weekly_recap(recap)}
    </section>

    <section>
      <div class="section-head">
        <h2>Sampling context</h2>
        <p>Automatically derived from species-level iNaturalist timestamps. These records show active moth nights and upload timing, not trap duration or light setup.</p>
      </div>
      {_sampling_context(profile)}
    </section>

    <section>
      <div class="section-head">
        <h2>Seasonal richness</h2>
        <p>Unique moth species by month across all synced years. Each row also shows how many active moth nights contributed to that month.</p>
      </div>
      <div class="profile-chart">{_seasonal_bars(profile)}</div>
    </section>

    <section>
      <div class="section-head">
        <h2>Phenology calendar</h2>
        <p>Weekly unique moth species across all synced years. Each cell includes active moth-night coverage for that week.</p>
      </div>
      <div class="profile-chart">{_profile_phenology_calendar(profile)}</div>
    </section>

    <section>
      <div class="section-head">
        <h2>Species accumulation</h2>
        <p>Running species list, with active moth-night coverage in each chart point.</p>
      </div>
      <div class="profile-chart">{_accumulation_bars(profile)}</div>
    </section>

    <section>
      <div class="section-head">
        <h2>Watch next</h2>
        <p>A visual field guide to species historically recorded here in the 30 calendar days after the latest synced session.</p>
      </div>
      {_expected_next_list(profile["expected_next"])}
    </section>

    <section>
      <div class="section-head">
        <h2>Signature species</h2>
        <p>Shared species that lean most strongly toward this station, based on its share of their network observations.</p>
      </div>
      {_signature_species_gallery(profile["signature_species"])}
    </section>

    <section>
      <div class="section-head">
        <h2>Distinctive records</h2>
        <p>State, county, or network firsts recorded here, plus anything with fewer than 10 tracked network records overall.</p>
      </div>
      {_distinctive_records(profile["distinctive_records"])}
    </section>

    <section>
      <div class="section-head">
        <h2>Habitat summary</h2>
        <p>Recent documented host associations, with a separate full archive and specificity-weighted companion suggestions.</p>
      </div>
      {_habitat_summary(habitat, f"{station.id}-habitat.html")}
    </section>

    <section>
      <div class="section-head">
        <h2>Recent observations</h2>
        <p>Latest synced observations from this station.</p>
      </div>
      <div class="sighting-grid">{_profile_recent(profile["recent"])}</div>
    </section>
  </main>
  <footer><div>Generated {h(generated_at())}. Station profiles are generated from the synced iNaturalist observation cache.</div></footer>
  <script>{DASHBOARD_JS}</script>
</body>
</html>
"""


def _station_habitat_page(station: Station, habitat: dict[str, Any], color: str) -> str:
    location = station.public_location or "Configured station"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Habitat archive · {h(station.name)} · Moth Station Dashboard</title>
  <meta name="description" content="Documented moth host-plant associations for {h(station.name)}.">
  <meta name="theme-color" content="#151611">
  <style>{CSS}</style>
</head>
<body>
  <a class="skip-link" href="#main">Skip to habitat archive</a>
  <header>
    <div class="topbar">
      <div class="topbar-primary">
        <a class="brand" href="../index.html"><span class="brand-mark" aria-hidden="true"></span><span>Moth stations</span></a>
        {_mode_toggle("../index.html", "../live.html", "history")}
      </div>
      {_dashboard_section_nav("../index.html")}
    </div>
    <div class="profile-hero" style="--station-color: {h(color)}">
      <p class="eyebrow">habitat archive</p>
      <h1>{h(station.name)}</h1>
      <p class="subhead">{h(location)}</p>
    </div>
  </header>
  <main id="main" class="site-shell">
    <section>
      <div class="section-head">
        <h2>Documented host associations</h2>
        <p>Full static archive of host-plant records for moth species confirmed at this station.</p>
      </div>
      {_habitat_summary(habitat, full=True)}
    </section>
  </main>
  <footer><div>Generated {h(generated_at())}. Host records come from the HOSTS reference data described above.</div></footer>
</body>
</html>
"""


DASHBOARD_JS = r"""
function cellValue(row, index, type) {
  const cell = row.children[index];
  const raw = (cell?.dataset.sortValue || cell?.textContent || "").trim();
  if (type === "number") return raw === "" ? -Infinity : Number(raw.replace(/,/g, ""));
  if (type === "date") return raw || "9999-99-99";
  return raw.toLocaleLowerCase();
}

function compareValues(a, b, type) {
  if (type === "number") return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
}

function sortTable(table, columnIndex, direction, type) {
  const tbody = table.tBodies[0];
  if (!tbody) return;
  const rows = Array.from(tbody.rows);
  rows.sort((a, b) => {
    const result = compareValues(cellValue(a, columnIndex, type), cellValue(b, columnIndex, type), type);
    return direction === "asc" ? result : -result;
  });
  rows.forEach((row) => tbody.appendChild(row));
  table.querySelectorAll(".sort-button").forEach((button) => {
    button.dataset.direction = "";
    button.closest("th")?.removeAttribute("aria-sort");
  });
  const button = table.tHead?.rows[0]?.cells[columnIndex]?.querySelector(".sort-button");
  if (button) {
    button.dataset.direction = direction;
    button.closest("th")?.setAttribute("aria-sort", direction === "asc" ? "ascending" : "descending");
  }
  table.dispatchEvent(new CustomEvent("table-sorted"));
}

function initSortableTables() {
  document.querySelectorAll(".sortable-table").forEach((table) => {
    table.querySelectorAll("thead .sort-button").forEach((button, index) => {
      const type = button.dataset.sortType || "text";
      button.addEventListener("click", () => {
        const next = button.dataset.direction === "asc" ? "desc" : "asc";
        sortTable(table, index, next, type);
      });
      if (button.dataset.sortDefault) {
        sortTable(table, index, button.dataset.sortDefault, type);
      }
    });
  });
}

function initViewToggles() {
  document.querySelectorAll(".view-toggle").forEach((group) => {
    group.addEventListener("click", (event) => {
      const button = event.target.closest("[data-view-target]");
      if (!button) return;
      const targetId = button.dataset.viewTarget;
      const section = group.closest("section");
      section.querySelectorAll(".view-panel").forEach((panel) => {
        panel.hidden = panel.id !== targetId;
      });
      group.querySelectorAll(".view-toggle-button").forEach((item) => {
        item.classList.toggle("is-active", item === button);
      });
    });
  });
}

function initNightStationFilters() {
  document.querySelectorAll("[data-night-period-filter]").forEach((filter) => {
    const section = filter.closest("section");
    if (!section) return;
    const buttons = Array.from(filter.querySelectorAll("[data-night-station-filter], [data-night-shared-filter]"));
    const grid = section.querySelector(".night-grid");
    const cards = Array.from(section.querySelectorAll("[data-night-card]"));
    const status = filter.querySelector("[data-night-filter-status]");
    const empty = section.querySelector("[data-night-filter-empty]");
    if (!buttons.length || !cards.length || !grid) return;
    cards.forEach((card, index) => {
      card.dataset.originalIndex = String(index);
    });

    const restoreCardOrder = () => {
      cards
        .slice()
        .sort((a, b) => Number(a.dataset.originalIndex || 0) - Number(b.dataset.originalIndex || 0))
        .forEach((card) => grid.appendChild(card));
    };

    const sortSharedCards = () => {
      cards
        .slice()
        .sort((a, b) => {
          const countDiff = Number(b.dataset.stationCount || 0) - Number(a.dataset.stationCount || 0);
          if (countDiff) return countDiff;
          return Number(a.dataset.originalIndex || 0) - Number(b.dataset.originalIndex || 0);
        })
        .forEach((card) => grid.appendChild(card));
    };

    const applyFilter = (mode, stationId, stationName, total) => {
      let visible = 0;
      cards.forEach((card) => {
        const stationCount = Number(card.dataset.stationCount || 0);
        const show =
          mode === "shared"
            ? stationCount > 1
            : !stationId || card.dataset.singleStationId === stationId;
        card.hidden = !show;
        if (show) visible += 1;
      });
      if (mode === "shared") {
        sortSharedCards();
      } else {
        restoreCardOrder();
      }
      buttons.forEach((button) => {
        const pressed =
          mode === "shared"
            ? button.hasAttribute("data-night-shared-filter")
            : Boolean(stationId && button.dataset.nightStationFilter === stationId);
        button.setAttribute("aria-pressed", String(pressed));
      });
      if (status) {
        status.hidden = !mode;
        const previewNote = total > visible ? ` · showing ${visible}` : "";
        status.textContent =
          mode === "shared"
            ? `Shared species: ${total}${previewNote}, sorted by station coverage`
            : stationId
              ? `${stationName}-only species: ${total}${previewNote}`
              : "";
      }
      if (empty) {
        empty.hidden = !mode || total > 0;
        empty.textContent =
          mode === "shared"
            ? "No species were shared by multiple stations in this period."
            : stationId
              ? `No species are unique to ${stationName} in this period.`
              : "";
      }
    };

    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        const mode = button.hasAttribute("data-night-shared-filter") ? "shared" : "station";
        const stationId = button.dataset.nightStationFilter || "";
        const isActive = button.getAttribute("aria-pressed") === "true";
        const total = Number(
          mode === "shared"
            ? button.dataset.nightSharedTotal || 0
            : button.dataset.nightStationTotal || 0
        );
        applyFilter(
          isActive ? "" : mode,
          isActive ? "" : stationId,
          button.dataset.stationName || button.textContent.trim(),
          isActive ? 0 : total,
        );
      });
    });
  });
}

function initUniqueFilter() {
  const input = document.querySelector("[data-unique-filter]");
  if (!input) return;
  const panels = Array.from(document.querySelectorAll(".unique-station-panel"));
  input.addEventListener("input", () => {
    const query = input.value.trim().toLowerCase();
    panels.forEach((panel) => {
      let matches = !query;
      panel.querySelectorAll(".unique-lists li, tbody tr").forEach((item) => {
        const hit = !query || item.textContent.toLowerCase().includes(query);
        item.hidden = !hit;
        matches = matches || hit;
      });
      panel.hidden = !matches;
      const details = panel.querySelector(".unique-full-list");
      if (details && query && matches) details.open = true;
    });
  });
}

function recordEscapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function buildRecordCardHtml(row) {
  const label = row.dataset.label || "";
  const stationName = row.dataset.stationName || "";
  const first = row.dataset.first || "";
  const flags = (row.dataset.flags || "").split("|").filter(Boolean);
  const photoUrl = row.dataset.photoUrl || "";
  const href = row.dataset.href || "";
  const image = photoUrl
    ? `<img src="${recordEscapeHtml(photoUrl)}" alt="${recordEscapeHtml(label)}" loading="lazy">`
    : '<div class="record-placeholder" aria-hidden="true">no photo</div>';
  const title = href
    ? `<a href="${recordEscapeHtml(href)}">${recordEscapeHtml(label)}</a>`
    : recordEscapeHtml(label);
  const flagHtml = flags.map((flag) => `<span class="flag">${recordEscapeHtml(flag)}</span>`).join("");
  return `
    <article class="record-card">
      <div class="record-image">${image}</div>
      <div class="record-copy">
        <div class="record-flags">${flagHtml}</div>
        <h3>${title}</h3>
        <p>${recordEscapeHtml(stationName)} · ${recordEscapeHtml(first)}</p>
      </div>
    </article>
  `;
}

function initRecordFilters() {
  const section = document.querySelector("#records");
  if (!section) return;
  const typeSelect = section.querySelector('[data-record-filter="type"]');
  const locationSelect = section.querySelector('[data-record-filter="location"]');
  const emptyMessage = section.querySelector("[data-record-empty]");
  const cardGrid = section.querySelector("[data-record-grid]");
  const gridControls = section.querySelector("[data-record-grid-controls]");
  const gridCount = section.querySelector("[data-record-grid-count]");
  const gridExpand = section.querySelector("[data-record-grid-expand]");
  const archive = section.querySelector(".record-archive");
  const table = section.querySelector("[data-record-table]");
  const showMore = section.querySelector("[data-record-show-more]");
  const count = section.querySelector("[data-record-count]");
  if (!typeSelect || !locationSelect) return;
  const pageSize = Number(showMore?.dataset.pageSize || 100);
  const cardPageSize = Number(gridExpand?.dataset.pageSize || 12);
  const originalGridHtml = cardGrid ? cardGrid.innerHTML : "";
  let visibleLimit = pageSize;
  let cardsExpanded = false;

  const apply = () => {
    const type = typeSelect.value;
    const location = locationSelect.value;
    const filterActive = Boolean(type) || Boolean(location);
    const rows = Array.from(table?.tBodies[0]?.rows || []);
    const matching = rows.filter((item) => {
      const flags = (item.dataset.flags || "").split("|").filter(Boolean);
      const matchesType = !type || flags.includes(type);
      const matchesLocation = !location || item.dataset.stationId === location;
      return matchesType && matchesLocation;
    });
    const matchingRows = new Set(matching);

    rows.forEach((item) => {
      if (filterActive) {
        item.hidden = !matchingRows.has(item);
      } else {
        item.hidden = rows.indexOf(item) >= visibleLimit;
      }
    });

    if (filterActive && archive) archive.open = true;

    if (cardGrid) {
      if (filterActive) {
        const cap = cardsExpanded ? matching.length : cardPageSize;
        cardGrid.innerHTML = matching.slice(0, cap).map(buildRecordCardHtml).join("");
      } else {
        cardGrid.innerHTML = originalGridHtml;
      }
    }
    if (gridControls) gridControls.hidden = !filterActive;
    if (gridCount) {
      gridCount.textContent = matching.length <= cardPageSize
        ? `Showing all ${matching.length} matching photo${matching.length === 1 ? "" : "s"}`
        : cardsExpanded
          ? `Showing all ${matching.length} matching photos`
          : `Showing ${Math.min(cardPageSize, matching.length)} of ${matching.length} matching photos`;
    }
    if (gridExpand) {
      gridExpand.hidden = matching.length <= cardPageSize;
      gridExpand.textContent = cardsExpanded ? "Show fewer photos" : `Show all ${matching.length} matching photos`;
    }

    if (emptyMessage) emptyMessage.hidden = matching.length > 0;
    if (showMore) {
      showMore.hidden = filterActive || visibleLimit >= rows.length;
      const remaining = Math.max(0, rows.length - visibleLimit);
      showMore.textContent = `Show ${Math.min(pageSize, remaining)} more`;
    }
    if (count) {
      count.textContent = filterActive
        ? `${matching.length} matching record${matching.length === 1 ? "" : "s"}`
        : `Showing ${Math.min(visibleLimit, rows.length)} of ${rows.length} records`;
    }
  };

  const filterChanged = () => {
    visibleLimit = pageSize;
    cardsExpanded = false;
    apply();
  };
  typeSelect.addEventListener("change", filterChanged);
  locationSelect.addEventListener("change", filterChanged);
  showMore?.addEventListener("click", () => {
    visibleLimit += pageSize;
    apply();
  });
  gridExpand?.addEventListener("click", () => {
    cardsExpanded = !cardsExpanded;
    apply();
  });
  table?.addEventListener("table-sorted", () => {
    visibleLimit = pageSize;
    apply();
  });
  apply();
}

const INSIGHT_FEEDBACK_KEY = "mothdash-insight-feedback-v1";

function readInsightFeedback() {
  try {
    const saved = JSON.parse(localStorage.getItem(INSIGHT_FEEDBACK_KEY) || "{}");
    return saved && typeof saved === "object" ? saved : {};
  } catch {
    return {};
  }
}

function writeInsightFeedback(feedback) {
  try {
    localStorage.setItem(INSIGHT_FEEDBACK_KEY, JSON.stringify(feedback));
    return true;
  } catch {
    return false;
  }
}

function copyText(text) {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text);
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  return copied ? Promise.resolve() : Promise.reject(new Error("Copy failed"));
}

function initInsightFeedback() {
  const cards = Array.from(document.querySelectorAll("[data-insight-feedback]"));
  const copyButton = document.querySelector("[data-insight-feedback-copy]");
  const status = document.querySelector("[data-insight-feedback-status]");
  if (!cards.length) return;
  let feedback = readInsightFeedback();

  const setStatus = (message) => {
    if (status) status.textContent = message;
  };
  const syncCard = (card) => {
    const rating = feedback[card.dataset.insightId]?.rating || "";
    card.querySelectorAll("[data-insight-rating]").forEach((button) => {
      const selected = button.dataset.insightRating === rating;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
  };
  const ratedEntries = () => cards.map((card) => {
    const item = feedback[card.dataset.insightId];
    if (!item?.rating) return null;
    return {
      id: card.dataset.insightId,
      category: card.dataset.insightCategory,
      title: card.dataset.insightTitle,
      meta: card.dataset.insightMeta,
      rating: item.rating,
      ratedAt: item.ratedAt,
    };
  }).filter(Boolean);
  const updateStatus = () => {
    const count = ratedEntries().length;
    setStatus(count ? `${count} rating${count === 1 ? "" : "s"} saved on this device.` : "");
  };

  cards.forEach((card) => {
    syncCard(card);
    card.querySelectorAll("[data-insight-rating]").forEach((button) => {
      button.addEventListener("click", () => {
        const id = card.dataset.insightId;
        const rating = button.dataset.insightRating;
        if (feedback[id]?.rating === rating) {
          delete feedback[id];
        } else {
          feedback[id] = { rating, ratedAt: new Date().toISOString() };
        }
        if (!writeInsightFeedback(feedback)) {
          setStatus("Ratings could not be saved in this browser.");
          return;
        }
        syncCard(card);
        updateStatus();
      });
    });
  });

  copyButton?.addEventListener("click", async () => {
    const entries = ratedEntries();
    if (!entries.length) {
      setStatus("Rate one or more insights before copying feedback.");
      return;
    }
    const lines = ["Naturalist feed feedback", ""];
    entries.forEach((entry) => {
      const details = [entry.category, entry.title, entry.meta].filter(Boolean).join(" | ");
      lines.push(`- ${entry.rating === "up" ? "Good" : "Needs improvement"}: ${details} [${entry.id}]`);
    });
    try {
      await copyText(lines.join("\n"));
      setStatus(`${entries.length} rating${entries.length === 1 ? "" : "s"} copied.`);
    } catch {
      setStatus("Could not copy ratings. Please try again.");
    }
  });

  updateStatus();
}

function initMonthlyTooltips() {
  document.querySelectorAll(".monthly-overlay-chart, .accumulation-line-chart, .daily-richness-line-chart").forEach((figure) => {
    const tooltip = figure.querySelector(".monthly-tooltip");
    if (!tooltip) return;

    const positionTooltip = (target, event) => {
      const figureRect = figure.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();
      const anchorX = event?.clientX || (targetRect.left + targetRect.width / 2);
      const anchorY = event?.clientY || targetRect.top;
      let left = anchorX - figureRect.left + 12;
      let top = anchorY - figureRect.top + 12;
      const maxLeft = Math.max(8, figureRect.width - tooltip.offsetWidth - 8);
      left = Math.max(8, Math.min(left, maxLeft));
      if (top + tooltip.offsetHeight > figureRect.height - 8) {
        top = Math.max(8, anchorY - figureRect.top - tooltip.offsetHeight - 12);
      }
      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
    };

    const showTooltip = (target, event) => {
      tooltip.innerHTML = target.dataset.tooltipHtml || "";
      tooltip.hidden = false;
      positionTooltip(target, event);
    };
    const hideTooltip = () => {
      tooltip.hidden = true;
    };

    figure.querySelectorAll(".monthly-point-group").forEach((target) => {
      target.addEventListener("pointerenter", (event) => showTooltip(target, event));
      target.addEventListener("pointermove", (event) => positionTooltip(target, event));
      target.addEventListener("pointerleave", () => {
        if (document.activeElement !== target) hideTooltip();
      });
      target.addEventListener("focus", () => showTooltip(target));
      target.addEventListener("blur", hideTooltip);
      target.addEventListener("click", (event) => {
        event.preventDefault();
        target.focus();
        showTooltip(target, event);
      });
      target.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          hideTooltip();
          target.blur();
        }
      });
    });
  });
}

initSortableTables();
initViewToggles();
initNightStationFilters();
initUniqueFilter();
initRecordFilters();
initInsightFeedback();
initMonthlyTooltips();
"""


LIVE_JS = r"""
const state = {
  snapshot: null,
  timer: null,
  stopAt: 0,
  known: new Map(),
  seenThisSession: new Set(),
  seenObservations: new Set(),
  stationSummaries: new Map(),
};

const LIVE_KEY = "mothdash-live-until";
const els = {};

function setStatus(message) {
  els.status.textContent = message;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function liveUntil() {
  return Number(localStorage.getItem(LIVE_KEY) || 0);
}

function liveIsOn() {
  return liveUntil() > Date.now();
}

function updateToggleState() {
  els.toggle.checked = liveIsOn();
}

function stationKnownSet(station) {
  if (!state.known.has(station.id)) {
    state.known.set(station.id, new Set(station.known_taxa || []));
  }
  return state.known.get(station.id);
}

function stationFirstDate(station, taxonId) {
  return (station.first_dates || {})[String(taxonId)] || "";
}

function observationLabel(obs) {
  const taxon = obs.taxon || {};
  const common = taxon.preferred_common_name;
  const scientific = taxon.name;
  if (common && scientific) return `${common} (${scientific})`;
  return common || scientific || "Unknown taxon";
}

function obsPhoto(obs) {
  const photo = (obs.photos || [])[0];
  if (!photo || !photo.url) return "";
  return photo.url.replace("square", "medium");
}

function fmtMinuteStamp(date) {
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function fmtTimestamp(timestamp) {
  if (!timestamp) return "not yet";
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? "not yet" : fmtMinuteStamp(date);
}

function latestTimestamp(current, candidate) {
  if (!candidate) return current;
  const candidateDate = new Date(candidate);
  if (Number.isNaN(candidateDate.getTime())) return current;
  if (!current) return candidate;
  const currentDate = new Date(current);
  return Number.isNaN(currentDate.getTime()) || candidateDate > currentDate
    ? candidate
    : current;
}

function sessionDate(date) {
  const session = new Date(date);
  if (session.getHours() < 12) session.setDate(session.getDate() - 1);
  return isoDate(session);
}

function isoDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function currentEventWindow(date) {
  const start = new Date(date);
  if (start.getHours() < 12) start.setDate(start.getDate() - 1);
  start.setHours(12, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return { start, end };
}

function observationInEvent(obs, eventWindow) {
  if (obs.time_observed_at) {
    const observedAt = new Date(obs.time_observed_at);
    if (!Number.isNaN(observedAt.getTime())) {
      return observedAt >= eventWindow.start && observedAt < eventWindow.end;
    }
  }
  if (!obs.observed_on) return true;
  const startDate = isoDate(eventWindow.start);
  const endDate = isoDate(new Date(eventWindow.end.getTime() - 1));
  return obs.observed_on === startDate || obs.observed_on === endDate;
}

function initStationSummaries() {
  state.stationSummaries.clear();
  for (const station of state.snapshot.stations) {
    state.stationSummaries.set(station.id, {
      station,
      active: false,
      checked: false,
      observationCount: 0,
      stationFirstCount: 0,
      latestObservedAt: "",
      latestUploadedAt: "",
      photos: [],
      currentSpecies: new Map(),
      stationFirstSpecies: new Map(),
      error: "",
    });
  }
}

function addSpecies(map, item) {
  if (!map.has(item.taxonId)) {
    map.set(item.taxonId, item);
    return;
  }
  const existing = map.get(item.taxonId);
  existing.count += item.count || 1;
  if (item.photo && !existing.photo) existing.photo = item.photo;
}

function updateStationSummary(station, observations, now, eventWindow) {
  const summary = state.stationSummaries.get(station.id);
  if (!summary) return { stationFirsts: 0, currentObs: 0 };

  summary.checked = true;
  summary.error = "";
  let stationFirsts = 0;
  let currentObs = 0;
  const known = stationKnownSet(station);
  const eventDate = isoDate(eventWindow.start);

  for (const obs of observations) {
    if (!observationInEvent(obs, eventWindow)) continue;
    const taxon = obs.taxon || {};
    const taxonId = taxon.id;
    if (!taxonId || taxon.rank !== "species") continue;
    const observationKey = `${station.id}:${obs.id || `${taxonId}:${obs.observed_on || ""}`}`;
    if (state.seenObservations.has(observationKey)) continue;
    state.seenObservations.add(observationKey);

    currentObs += 1;
    summary.active = true;
    summary.observationCount += 1;
    summary.latestObservedAt = latestTimestamp(summary.latestObservedAt, obs.time_observed_at);
    summary.latestUploadedAt = latestTimestamp(summary.latestUploadedAt, obs.created_at);

    const item = {
      taxonId,
      label: observationLabel(obs),
      url: obs.uri || `https://www.inaturalist.org/observations/${obs.id}`,
      photo: obsPhoto(obs),
      count: 1,
      networkCount: Number((state.snapshot.network_counts || {})[String(taxonId)] || 0),
    };
    addSpecies(summary.currentSpecies, item);
    if (item.photo && !summary.photos.some((photo) => photo.url === item.photo)) {
      summary.photos.unshift({ url: item.photo, label: item.label, href: item.url });
      summary.photos = summary.photos.slice(0, 6);
    }

    const firstDate = stationFirstDate(station, taxonId);
    const isFirstThisEvent = firstDate === eventDate || (!firstDate && !known.has(taxonId));
    if (!isFirstThisEvent) continue;
    const key = `${station.id}:${taxonId}`;
    if (state.seenThisSession.has(key)) continue;
    state.seenThisSession.add(key);
    known.add(taxonId);
    stationFirsts += 1;
    summary.stationFirstCount += 1;
    addSpecies(summary.stationFirstSpecies, item);
  }

  return { stationFirsts, currentObs };
}

function sharedStationPills(taxonId, stationId) {
  if (!stationId) return "";
  const shared = Array.from(state.stationSummaries.values())
    .filter((summary) => summary.station.id !== stationId && summary.currentSpecies.has(taxonId))
    .map((summary) => summary.station)
    .sort((a, b) => (a.short_name || a.name).localeCompare(b.short_name || b.name));
  if (!shared.length) return "";
  const stationNames = shared.map((station) => station.name).join(", ");
  return `<div class="live-shared-stations" aria-label="Also seen this event at ${escapeHtml(stationNames)}">
    ${shared.map((station) => `<span class="live-shared-pill" style="--station-color: ${escapeHtml(station.color || "#d7b56d")}" title="Also seen at ${escapeHtml(station.name)}">${escapeHtml(station.short_name || station.name)}</span>`).join("")}
  </div>`;
}

function networkFirstBadge(networkCount) {
  if (!Number.isFinite(networkCount) || networkCount > 2) return "";
  const tiers = [
    { rank: "1", tier: "gold", label: "First tracked network record of this species" },
    { rank: "2", tier: "silver", label: "Second tracked network record of this species" },
    { rank: "3", tier: "bronze", label: "Third tracked network record of this species" },
  ];
  const tier = tiers[networkCount];
  if (!tier) return "";
  return `<span class="network-badge network-badge-${tier.tier}" title="${escapeHtml(tier.label)}" aria-label="${escapeHtml(tier.label)}">${tier.rank}</span>`;
}

function renderSpeciesList(species, emptyText, excludedSpecies = new Set(), limit = 24, rarityFirst = false, stationId = "", showNetwork = null, showBadge = false) {
  const excluded = excludedSpecies instanceof Map
    ? new Set(excludedSpecies.keys())
    : excludedSpecies;
  const includeNetwork = showNetwork === null ? rarityFirst : showNetwork;
  const sortedItems = Array.from(species.values())
    .filter((item) => !excluded.has(item.taxonId))
    .sort((a, b) => rarityFirst
      ? a.networkCount - b.networkCount || b.count - a.count || a.label.localeCompare(b.label)
      : b.count - a.count || a.label.localeCompare(b.label));
  const items = Number.isFinite(limit) ? sortedItems.slice(0, limit) : sortedItems;
  if (!items.length) return `<p class="live-muted">${escapeHtml(emptyText)}</p>`;
  return `<ul>${items.map((item) => `
    <li>
      <div class="live-species-name">
        <a href="${escapeHtml(item.url)}">${escapeHtml(item.label)}</a>
        ${sharedStationPills(item.taxonId, stationId)}
      </div>
      <span class="live-species-meta">${showBadge ? networkFirstBadge(item.networkCount) : ""}${includeNetwork
        ? `${item.count} event · ${item.networkCount} network`
        : item.count > 1 ? `${item.count} obs` : "1 obs"}</span>
    </li>
  `).join("")}</ul>`;
}

function renderStationSummaries() {
  const allSummaries = Array.from(state.stationSummaries.values());
  const summaries = allSummaries.filter((summary) => summary.active).sort((a, b) => {
    if (a.active !== b.active) return a.active ? -1 : 1;
    if (a.stationFirstCount !== b.stationFirstCount) return b.stationFirstCount - a.stationFirstCount;
    if (a.currentSpecies.size !== b.currentSpecies.size) return b.currentSpecies.size - a.currentSpecies.size;
    if (a.observationCount !== b.observationCount) return b.observationCount - a.observationCount;
    return a.station.name.localeCompare(b.station.name);
  });
  const latestObservation = allSummaries.reduce(
    (latest, summary) => latestTimestamp(latest, summary.latestObservedAt),
    "",
  );
  const latestUpload = allSummaries.reduce(
    (latest, summary) => latestTimestamp(latest, summary.latestUploadedAt),
    "",
  );
  if (els.latestObservation) els.latestObservation.textContent = fmtTimestamp(latestObservation);
  if (els.latestUpload) els.latestUpload.textContent = fmtTimestamp(latestUpload);
  const activeEventStations = allSummaries
    .filter((summary) => summary.currentSpecies.size > 0)
    .sort((a, b) => b.currentSpecies.size - a.currentSpecies.size
      || a.station.name.localeCompare(b.station.name));
  const networkEventSpecies = new Set(
    activeEventStations.flatMap((summary) => Array.from(summary.currentSpecies.keys())),
  );
  const stationsPerEventSpecies = new Map();
  for (const summary of activeEventStations) {
    for (const taxonId of summary.currentSpecies.keys()) {
      stationsPerEventSpecies.set(taxonId, (stationsPerEventSpecies.get(taxonId) || 0) + 1);
    }
  }
  if (els.newSpeciesCounter) {
    els.newSpeciesCounter.hidden = !activeEventStations.length;
    els.newSpeciesCounter.innerHTML = `
      <span class="night-station-chip network-total-chip" style="--station-color: var(--amber)"
        title="Unique moth species across all active stations in this event">
        All stations
        <strong>${networkEventSpecies.size}</strong>
      </span>
    ` + activeEventStations.map((summary) => {
      const eventUniqueCount = Array.from(summary.currentSpecies.keys())
        .filter((taxonId) => stationsPerEventSpecies.get(taxonId) === 1).length;
      const name = escapeHtml(summary.station.short_name || summary.station.name);
      return `
      <a href="#live-station-${escapeHtml(summary.station.id)}" class="night-station-chip" style="--station-color: ${escapeHtml(summary.station.color || "#d7b56d")}" aria-label="${name}: ${summary.currentSpecies.size} event species, ${eventUniqueCount} unique to this station tonight, ${summary.stationFirstCount} new to this station">
        <span class="live-station-chip-name">${name}</span>
        <strong>${summary.currentSpecies.size}</strong>
        <small><b>${eventUniqueCount}</b> unique · <b>${summary.stationFirstCount}</b> new</small>
      </a>
    `;
    }).join("");
  }

  if (!summaries.length) {
    const hasChecked = allSummaries.some((summary) => summary.checked);
    els.log.innerHTML = `
      <p class="empty">${hasChecked
        ? "No stations have species-level uploads in the current 12pm-to-12pm moth event yet. The next live check will add station cards as activity appears."
        : "No active stations yet. Opening Live will check the current moth event."}</p>
    `;
    return;
  }

  els.log.innerHTML = summaries.map((summary) => {
    const station = summary.station;
    const status = "active updates";
    const photos = summary.photos.length
      ? summary.photos.map((photo) => `
          <a href="${escapeHtml(photo.href)}" class="live-thumb">
            <img src="${escapeHtml(photo.url)}" alt="${escapeHtml(photo.label)}" loading="lazy">
          </a>
        `).join("")
      : `<div class="live-photo-empty">No current-event photos yet</div>`;
    const classes = [
      "live-station-card",
      "is-active",
    ].filter(Boolean).join(" ");
    const otherSpeciesCount = Array.from(summary.currentSpecies.keys())
      .filter((taxonId) => !summary.stationFirstSpecies.has(taxonId)).length;

    return `
      <article id="live-station-${escapeHtml(station.id)}" class="${classes}">
        <div class="live-station-head">
          <div>
            <p>${escapeHtml(station.public_location || "tracked station")}</p>
            <h2>${escapeHtml(station.name)}</h2>
          </div>
          <span>${escapeHtml(status)}</span>
        </div>
        <div class="live-stats">
          <div><strong>${summary.observationCount}</strong><span>moth-night uploads</span></div>
          <div><strong>${summary.currentSpecies.size}</strong><span>event species</span></div>
          <div><strong>${summary.stationFirstCount}</strong><span>new to station</span></div>
          <div><strong>${escapeHtml(fmtTimestamp(summary.latestUploadedAt))}</strong><span>latest upload</span></div>
        </div>
        <div class="live-photo-strip">${photos}</div>
        <div class="live-station-lists">
          <div class="live-firsts">
            <h3>New species this event</h3>
            ${renderSpeciesList(summary.stationFirstSpecies, summary.checked ? "No new station species in this event yet." : "Waiting for the first check.", new Set(), 20, false, station.id, true, true)}
          </div>
          <div class="live-other">
            <details>
              <summary>Other species this event <span>${otherSpeciesCount}</span></summary>
              <div class="live-other-full">
                ${renderSpeciesList(summary.currentSpecies, station.live_supported ? "No other species-level moths in this event yet." : station.live_note, summary.stationFirstSpecies, Number.POSITIVE_INFINITY, true, station.id)}
              </div>
            </details>
            <div class="live-other-preview">
              ${renderSpeciesList(summary.currentSpecies, station.live_supported ? "No other species-level moths in this event yet." : station.live_note, summary.stationFirstSpecies, 10, true, station.id)}
            </div>
          </div>
        </div>
      </article>
    `;
  }).join("");
}

async function fetchStation(station, createdAfter) {
  const baseParams = new URLSearchParams();
  for (const [key, value] of Object.entries(station.query || {})) {
    if (value === null || value === undefined || value === "") continue;
    baseParams.set(key, String(value));
  }
  baseParams.set("created_d1", createdAfter);
  baseParams.set("order_by", "created_at");
  baseParams.set("order", "desc");
  baseParams.set("per_page", "200");

  const results = [];
  let total = 0;
  let page = 1;
  do {
    const params = new URLSearchParams(baseParams);
    params.set("page", String(page));
    const url = `${state.snapshot.api_base}/observations?${params.toString()}`;
    const response = await fetch(url, { headers: { accept: "application/json" } });
    if (!response.ok) throw new Error(`${station.name}: iNaturalist returned ${response.status}`);
    const data = await response.json();
    total = data.total_results || 0;
    results.push(...(data.results || []));
    page += 1;
  } while (results.length < total && page <= 5);

  return { results };
}

async function runCheck() {
  const now = new Date();
  const eventWindow = currentEventWindow(now);
  const createdAfter = eventWindow.start.toISOString();
  setStatus(`Checking iNaturalist at ${now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`);
  let found = 0;
  let activeUploads = 0;
  for (const station of state.snapshot.stations) {
    if (!station.live_supported) continue;
    const data = await fetchStation(station, createdAfter);
    const result = updateStationSummary(station, data.results || [], now, eventWindow);
    found += result.stationFirsts;
    activeUploads += result.currentObs;
  }
  els.lastCheck.textContent = fmtMinuteStamp(now);
  renderStationSummaries();
  const activeStations = Array.from(state.stationSummaries.values()).filter((summary) => summary.active).length;
  setStatus(found
    ? `Found ${found} new station species in the current moth event.`
    : activeUploads
      ? `Found ${activeUploads} current-event species-level uploads; no new station species in this check.`
      : activeStations
        ? "No additional current-event species-level uploads since the previous check."
        : "No current-event station species-level uploads found in this check.");
}

function stopScan(message) {
  if (state.timer) window.clearInterval(state.timer);
  state.timer = null;
  state.stopAt = 0;
  if (message) setStatus(message);
}

async function startLiveUpdates(checkImmediately = true) {
  if (!state.snapshot) return;
  stopScan();
  state.stopAt = liveUntil();
  if (state.stopAt <= Date.now()) {
    stopScan("Live updates expired.");
    return;
  }
  if (checkImmediately) {
    try {
      await runCheck();
    } catch (error) {
      setStatus(error.message || "Live check failed.");
    }
  }
  state.timer = window.setInterval(async () => {
    if (!liveIsOn()) {
      updateToggleState();
      stopScan("Live updates expired. Toggle them on to continue.");
      return;
    }
    try {
      await runCheck();
    } catch (error) {
      setStatus(error.message || "Live check failed.");
    }
  }, state.snapshot.poll_seconds * 1000);
}

async function loadSnapshot() {
  const embeddedSnapshot = (() => {
    const el = document.getElementById("live-snapshot-data");
    if (!el) return null;
    try {
      return JSON.parse(el.textContent || "{}");
    } catch {
      return null;
    }
  })();
  if (embeddedSnapshot && embeddedSnapshot.stations && embeddedSnapshot.stations.length) {
    state.snapshot = embeddedSnapshot;
    initStationSummaries();
    renderStationSummaries();
    return;
  }
  const response = await fetch("live-snapshot.json", { cache: "no-store" });
  if (!response.ok) throw new Error("Could not load live snapshot.");
  state.snapshot = await response.json();
  initStationSummaries();
  renderStationSummaries();
}

async function init() {
  els.toggle = document.querySelector("#live-toggle");
  els.status = document.querySelector("#live-status");
  els.lastCheck = document.querySelector("#last-check");
  els.latestObservation = document.querySelector("#latest-observation");
  els.latestUpload = document.querySelector("#latest-upload");
  els.newSpeciesCounter = document.querySelector("#live-new-species-counter");
  els.log = document.querySelector("#live-log");

  await loadSnapshot();
  updateToggleState();
  window.setInterval(updateToggleState, 30000);

  try {
    await runCheck();
  } catch (error) {
    setStatus(error.message || "Live check failed.");
  }

  els.toggle.addEventListener("change", async () => {
    if (els.toggle.checked) {
      const until = Date.now() + state.snapshot.live_mode_hours * 60 * 60 * 1000;
      localStorage.setItem(LIVE_KEY, String(until));
      updateToggleState();
      await startLiveUpdates(true);
    } else {
      localStorage.removeItem(LIVE_KEY);
      updateToggleState();
      stopScan("Live mode off.");
    }
  });

  if (liveIsOn()) {
    await startLiveUpdates(false);
  }
}

init().catch((error) => {
  setStatus(error.message || "Live page could not start.");
});
"""


def _live_page(live_snapshot: dict) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Live station summary · Moth Station Dashboard</title>
  <meta name="description" content="Run a short live check for current moth-event iNaturalist activity at tracked moth stations.">
  <meta name="theme-color" content="#151611">
  <style>{CSS}
  .live-shell {{
    width: min(980px, calc(100% - 32px));
    margin: 0 auto;
    padding: 42px 0 60px;
  }}
  .live-panel {{
    margin-top: 26px;
    padding: 18px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 6px;
  }}
  .live-new-station-counter {{
    margin: 22px 0 0;
  }}
  .toggle-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
    flex-wrap: wrap;
  }}
  .switch {{
    display: inline-flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
  }}
  .switch input {{
    width: 48px;
    height: 28px;
    accent-color: var(--amber);
  }}
  .live-freshness {{
    display: flex;
    flex-wrap: wrap;
    gap: 4px 14px;
    margin: 12px 0 0;
    color: var(--faint);
    font-size: 0.78rem;
  }}
  .live-freshness span {{
    white-space: nowrap;
  }}
  .live-freshness span + span::before {{
    content: "·";
    margin-right: 14px;
    color: var(--line);
  }}
  .live-freshness strong {{
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: inherit;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
  }}
  .live-log {{
    display: grid;
    gap: 14px;
    margin-top: 18px;
  }}
  .live-station-card {{
    display: grid;
    gap: 14px;
    padding: 16px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-left: 5px solid var(--line);
    border-radius: 6px;
  }}
  .live-station-card.is-active {{
    border-left-color: var(--amber);
    background: color-mix(in srgb, var(--panel) 86%, var(--amber));
  }}
  .live-station-card.is-disabled {{
    opacity: 0.72;
  }}
  .live-station-head {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 14px;
  }}
  .live-station-head p {{
    margin: 0;
    color: var(--muted);
    font-size: 0.82rem;
  }}
  .live-station-head h2 {{
    margin: 4px 0 0;
    font-size: clamp(1.18rem, 3vw, 1.7rem);
    line-height: 1.1;
  }}
  .live-station-head > span {{
    flex: 0 0 auto;
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 5px 8px;
    color: var(--amber);
    background: var(--panel-2);
    font-size: 0.78rem;
  }}
  .live-stats {{
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 1px;
    background: var(--line);
    border: 1px solid var(--line);
  }}
  .live-stats div {{
    min-width: 0;
    padding: 10px;
    background: var(--panel-2);
  }}
  .live-stats strong,
  .live-stats span {{
    display: block;
  }}
  .live-stats strong {{
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-variant-numeric: tabular-nums;
    overflow-wrap: anywhere;
  }}
  .live-stats span {{
    color: var(--muted);
    font-size: 0.76rem;
  }}
  .live-photo-strip {{
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 6px;
  }}
  .live-thumb,
  .live-photo-empty {{
    aspect-ratio: 1;
    min-width: 0;
    background: var(--panel-2);
    border: 1px solid var(--line);
    border-radius: 4px;
    overflow: hidden;
  }}
  .live-thumb img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
  }}
  .live-photo-empty {{
    grid-column: 1 / -1;
    display: grid;
    place-items: center;
    min-height: 76px;
    color: var(--faint);
    font-size: 0.82rem;
  }}
  .live-station-lists {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }}
  .live-station-lists h3 {{
    margin: 0 0 8px;
    color: var(--amber);
    font-size: 0.9rem;
  }}
  .live-firsts {{
    border-left: 3px solid var(--amber);
    background: color-mix(in srgb, var(--amber) 7%, transparent);
    padding: 10px 12px;
  }}
  .live-firsts h3 {{
    font-size: 1rem;
  }}
  .live-other {{
    min-width: 0;
    border-top: 1px solid var(--line);
  }}
  .live-other summary {{
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 0;
    color: var(--amber);
    font-size: 0.9rem;
    font-weight: 650;
  }}
  .live-other summary > span {{
    display: inline-grid;
    min-width: 28px;
    height: 28px;
    place-items: center;
    border: 1px solid var(--line);
    border-radius: 999px;
    color: var(--muted);
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
  }}
  .live-other details[open] summary {{
    margin-bottom: 8px;
  }}
  .live-other details[open] + .live-other-preview {{
    display: none;
  }}
  .live-other-full {{
    padding-bottom: 2px;
  }}
  .live-station-lists ul {{
    display: grid;
    gap: 6px;
    margin: 0;
    padding: 0;
    list-style: none;
  }}
  .live-station-lists li {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
    min-width: 0;
    border-bottom: 1px solid var(--line);
    padding-bottom: 6px;
  }}
  .live-species-name {{
    min-width: 0;
  }}
  .live-station-lists li a {{
    min-width: 0;
    overflow-wrap: anywhere;
  }}
  .live-species-meta,
  .live-muted {{
    color: var(--muted);
    font-size: 0.78rem;
  }}
  .live-species-meta {{
    flex: 0 0 auto;
    text-align: right;
    white-space: nowrap;
  }}
  .network-badge {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 15px;
    height: 15px;
    margin-right: 5px;
    border-radius: 50%;
    font-size: 0.6rem;
    font-weight: 700;
    line-height: 1;
    color: #2b2410;
    vertical-align: -2px;
  }}
  .network-badge-gold {{
    background: #e8c14d;
  }}
  .network-badge-silver {{
    background: #c7cdd6;
  }}
  .network-badge-bronze {{
    background: #c98a4b;
  }}
  .live-shared-stations {{
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 4px;
  }}
  .live-shared-pill {{
    display: inline-flex;
    align-items: center;
    min-height: 19px;
    padding: 1px 6px;
    border: 1px solid color-mix(in srgb, var(--station-color) 70%, var(--line));
    border-radius: 999px;
    background: color-mix(in srgb, var(--station-color) 15%, transparent);
    color: var(--ink);
    font-size: 0.65rem;
    line-height: 1;
    white-space: nowrap;
  }}
  .live-muted {{
    margin: 0;
  }}
  @media (max-width: 620px) {{
    .live-station-head,
    .live-station-lists {{
      grid-template-columns: 1fr;
      flex-direction: column;
    }}
    .live-stats {{
      grid-template-columns: 1fr;
    }}
    .live-photo-strip {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }}
  }}
  </style>
</head>
<body class="live-page">
  <a class="skip-link" href="#live-main">Skip to live log</a>
  <header>
    <div class="topbar topbar-mode-only">
      <div class="topbar-primary">
        <a class="brand" href="index.html"><span class="brand-mark" aria-hidden="true"></span><span>Moth stations</span></a>
        {_mode_toggle("index.html", "live.html", "live")}
      </div>
    </div>
  </header>
  <script id="live-snapshot-data" type="application/json">{json.dumps(live_snapshot, sort_keys=True)}</script>
  <main id="live-main" class="live-shell">
    <p class="eyebrow">10-minute iNaturalist check</p>
    <h1>Live station summary.</h1>
    <p class="subhead">Opening Live checks iNaturalist once for the current 12pm-to-12pm moth event. Turn on updates to refresh every 10 minutes for 2 hours.</p>
    <div id="live-new-species-counter" class="night-stations live-new-station-counter"
      aria-label="Unique moth species by active station in this event" hidden></div>

    <section class="live-panel" aria-labelledby="live-controls">
      <div class="toggle-row">
        <div>
          <h2 id="live-controls">Live updates</h2>
          <p id="live-status">Preparing live check.</p>
        </div>
        <label class="switch">
          <input id="live-toggle" type="checkbox">
          <span>Keep checking</span>
        </label>
      </div>
      <p class="live-freshness" aria-label="Live update timing">
        <span>Checked <strong id="last-check">not yet</strong></span>
        <span>Latest observation <strong id="latest-observation">not yet</strong></span>
        <span>Latest upload <strong id="latest-upload">not yet</strong></span>
      </p>
    </section>

    <section aria-labelledby="live-log-title">
      <div class="section-head">
        <h2 id="live-log-title">Live station summary</h2>
        <p>Active stations appear when species-level uploads arrive. New station species from the current 12pm-to-12pm event are shown first and are not repeated in the rest of the event list.</p>
      </div>
      <div id="live-log" class="live-log">
        <p class="empty">No live station results yet. Toggle live mode to start a 10-minute scan.</p>
      </div>
    </section>
  </main>
  <script>{LIVE_JS}</script>
</body>
</html>
"""


CSS = """
:root {
  color-scheme: dark;
  --bg: #151611;
  --bg-2: #202116;
  --ink: #f3ead7;
  --muted: #b8b09d;
  --faint: #7f786a;
  --line: #3c3a2d;
  --panel: #24251b;
  --panel-2: #2d2b1f;
  --amber: #d7b56d;
  --leaf: #8aa77a;
  --rust: #b66d45;
  --focus: #f0cf7a;
  --max: 1380px;
  --topbar-height: 64px;
}
* { box-sizing: border-box; }
html {
  scroll-behavior: smooth;
  scroll-padding-top: calc(var(--topbar-height) + 18px);
}
body {
  margin: 0;
  padding-top: var(--topbar-height);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--ink);
  line-height: 1.5;
}
.skip-link {
  position: absolute;
  left: 16px;
  top: -48px;
  z-index: 80;
  padding: 10px 12px;
  background: var(--amber);
  color: #17140e;
  border-radius: 4px;
}
.skip-link:focus { top: 16px; }
.site-shell {
  width: min(var(--max), calc(100% - 32px));
  margin: 0 auto;
}
header {
  border-bottom: 1px solid var(--line);
  background: var(--bg);
}
.topbar {
  position: fixed;
  inset: 0 0 auto 0;
  z-index: 50;
  width: 100%;
  min-height: 64px;
  padding: 0 max(16px, calc((100vw - var(--max)) / 2));
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  border-bottom: 1px solid rgba(240, 232, 214, 0.12);
  background: rgba(21, 22, 17, 0.94);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}
.topbar-primary {
  display: flex;
  align-items: center;
  gap: 18px;
  flex: 0 0 auto;
}
.topbar-mode-only {
  justify-content: center;
}
.topbar-mode-only .topbar-primary {
  width: min(var(--max), calc(100% - 32px));
  justify-content: space-between;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--ink);
  text-decoration: none;
  font-weight: 650;
}
.brand-mark {
  width: 14px;
  height: 14px;
  background: var(--amber);
  transform: rotate(45deg);
  box-shadow: 0 0 0 5px rgba(215, 181, 109, 0.12);
}
.mode-toggle {
  display: inline-flex;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 5px;
  background: #181910;
}
.mode-toggle a {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 4px 9px;
  color: var(--muted);
  text-decoration: none;
  font-size: 0.74rem;
  font-weight: 650;
}
.mode-toggle a:hover {
  color: var(--ink);
}
.mode-toggle a.is-active {
  background: var(--amber);
  color: #1b170f;
}
.mode-toggle a:focus-visible {
  position: relative;
  z-index: 1;
  outline: 3px solid var(--focus);
  outline-offset: -3px;
}
.section-nav {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 14px;
}
.section-nav a {
  color: var(--muted);
  text-decoration: none;
  font-size: 0.9rem;
}
.hero {
  width: min(var(--max), calc(100% - 32px));
  margin: 0 auto;
  padding: 30px 0 22px;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.95fr);
  gap: clamp(24px, 5vw, 72px);
  align-items: start;
}
.profile-hero {
  width: min(var(--max), calc(100% - 32px));
  margin: 0 auto;
  padding: 54px 0 38px;
  border-top: 6px solid var(--station-color);
}
.profile-hero h1 {
  max-width: 980px;
}
.profile-links {
  margin-top: 14px;
}
.profile-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 30px;
}
.profile-metric {
  min-width: 0;
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  padding: 9px 14px;
  border: 1px solid color-mix(in srgb, var(--station-color) 46%, var(--line));
  border-radius: 999px;
  background: color-mix(in srgb, var(--station-color) 9%, var(--panel));
}
.profile-metric strong {
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 0.96rem;
  color: var(--ink);
  font-weight: 720;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.profile-metric span {
  color: var(--muted);
  font-size: 0.76rem;
  white-space: nowrap;
}
.hero-copy {
  grid-column: 1;
}
.eyebrow {
  color: var(--amber);
  margin: 0 0 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.82rem;
}
h1 {
  margin: 0;
  max-width: 880px;
  font-family: Georgia, "Times New Roman", serif;
  font-size: clamp(3.2rem, 10vw, 8.4rem);
  font-weight: 500;
  line-height: 0.92;
  letter-spacing: 0;
}
h1, h2 {
  text-wrap: balance;
}
.hero-copy h1 {
  max-width: 620px;
  font-size: clamp(1.6rem, 3.4vw, 2.6rem);
  line-height: 1.05;
}
.subhead {
  max-width: 660px;
  color: var(--muted);
  margin: 10px 0 0;
  font-size: clamp(0.92rem, 1.6vw, 1.05rem);
  text-wrap: pretty;
}
.hero-metrics {
  grid-column: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.hero-metric {
  min-width: 0;
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  padding: 9px 14px;
  border: 1px solid color-mix(in srgb, var(--amber) 46%, var(--line));
  border-radius: 999px;
  background: color-mix(in srgb, var(--amber) 9%, var(--panel));
}
.hero-metric strong {
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 0.96rem;
  font-weight: 720;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.hero-metric-compact strong {
  font-size: 0.88rem;
}
.hero-metric span {
  color: var(--muted);
  font-size: 0.76rem;
  white-space: nowrap;
}
.photo-rail {
  grid-column: 2;
  grid-row: 1 / span 2;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  grid-auto-flow: row dense;
  grid-auto-rows: 132px;
  gap: 8px;
  min-width: 0;
  overflow: hidden;
  border-radius: 6px;
}
.photo-tile {
  min-width: 0;
  min-height: 0;
  position: relative;
  display: block;
  overflow: hidden;
  background: #322f21;
  color: var(--ink);
  text-decoration: none;
}
.photo-tile:nth-child(1) {
  grid-column: span 2;
  grid-row: span 2;
}
.photo-tile:nth-child(6) {
  grid-column: span 2;
}
.photo-tile img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  filter: saturate(0.95) contrast(1.08) brightness(1.08);
  opacity: 0.96;
  transition: transform 180ms ease-out, opacity 180ms ease-out;
}
.photo-tile:hover img {
  transform: scale(1.025);
  opacity: 1;
}
.photo-tile:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: -3px;
  z-index: 2;
}
.photo-tile span {
  position: absolute;
  inset: auto 0 0;
  min-width: 0;
  padding: 28px 10px 9px;
  background: linear-gradient(to bottom, transparent, rgba(14, 15, 11, 0.92) 56%);
  color: var(--ink);
}
.photo-tile strong,
.photo-tile small {
  display: block;
  min-width: 0;
}
.photo-tile strong {
  display: -webkit-box;
  overflow: hidden;
  color: var(--ink);
  font-size: 0.75rem;
  font-weight: 650;
  line-height: 1.16;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.photo-tile small {
  margin-top: 4px;
  overflow: hidden;
  color: var(--amber);
  font-size: 0.64rem;
  line-height: 1.1;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.photo-empty {
  min-height: 280px;
  display: grid;
  place-items: center;
  border: 1px dashed var(--line);
  color: var(--muted);
}
main {
  padding: 20px 0 54px;
}
section {
  margin-top: 42px;
}
h2 {
  font-family: Georgia, "Times New Roman", serif;
  font-size: clamp(1.55rem, 3vw, 2.4rem);
  font-weight: 500;
  margin: 0;
  letter-spacing: 0;
}
.section-head {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: end;
  margin-bottom: 16px;
}
.section-head p {
  max-width: 520px;
  margin: 0;
  color: var(--muted);
  text-wrap: pretty;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 10px;
}
.profile-chart {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
  overflow-x: auto;
}
.profile-week-grid {
  min-width: 760px;
  display: grid;
  grid-template-columns: repeat(13, minmax(54px, 1fr));
  gap: 6px;
}
.profile-week {
  min-height: 54px;
  display: grid;
  align-content: space-between;
  padding: 6px;
  border: 1px solid var(--line);
  background: var(--cell-bg);
}
.profile-week strong {
  color: var(--ink);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.95rem;
}
.profile-week span,
.profile-week small {
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.66rem;
  line-height: 1.05;
}
.month-bar {
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr) 56px;
  gap: 10px;
  align-items: center;
  min-height: 28px;
}
.month-bar span,
.month-bar strong {
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8rem;
  font-weight: 500;
}
.month-bar strong {
  color: var(--ink);
  text-align: right;
}
.month-bar small,
.sampling-year-row small {
  color: var(--muted);
  font-size: 0.66rem;
  font-weight: 500;
  white-space: nowrap;
}
.month-bar div {
  height: 12px;
  background: #191a12;
  border: 1px solid var(--line);
}
.month-bar i {
  display: block;
  height: 100%;
  background: var(--amber);
}
.sampling-context {
  display: grid;
  gap: 22px;
  padding: 2px 0;
}
.sampling-context-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(168px, 1fr));
  margin: 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}
.sampling-context-metrics > div {
  min-width: 0;
  padding: 14px 16px;
  border-right: 1px solid var(--line);
}
.sampling-context-metrics > div:last-child {
  border-right: 0;
}
.sampling-context-metrics dt,
.sampling-context-metrics small,
.sampling-year-chart figcaption {
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.7rem;
  line-height: 1.2;
}
.sampling-context-metrics dd {
  margin: 5px 0 3px;
  color: var(--ink);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 1.35rem;
  font-weight: 720;
  font-variant-numeric: tabular-nums;
}
.sampling-year-chart {
  max-width: 620px;
  margin: 0;
}
.sampling-year-chart figcaption {
  margin-bottom: 9px;
}
.sampling-year-list {
  display: grid;
  gap: 7px;
}
.sampling-year-row {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) minmax(110px, auto);
  gap: 10px;
  align-items: center;
}
.sampling-year-row > span,
.sampling-year-row strong {
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.76rem;
  font-weight: 500;
}
.sampling-year-row strong {
  color: var(--ink);
  text-align: right;
  white-space: nowrap;
}
.sampling-year-row > div {
  height: 10px;
  overflow: hidden;
  border: 1px solid var(--line);
  background: #191a12;
}
.sampling-year-row i {
  display: block;
  height: 100%;
  background: var(--amber);
}
.accumulation-line-chart {
  margin: 0;
  position: relative;
}
.accumulation-line-chart svg {
  width: 100%;
  aspect-ratio: 720 / 260;
  height: auto;
  max-height: 340px;
  display: block;
}
.chart-axis,
.chart-grid {
  vector-effect: non-scaling-stroke;
  stroke: var(--line);
  stroke-width: 1;
}
.chart-grid {
  stroke-dasharray: 4 6;
}
.accumulation-area {
  fill: rgba(215, 181, 109, 0.12);
}
.accumulation-line {
  fill: none;
  stroke: var(--amber);
  stroke-width: 4;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}
.chart-label,
.chart-callout {
  fill: var(--muted);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 0.72rem;
  font-variant-numeric: tabular-nums;
}
.chart-callout {
  fill: var(--ink);
  font-size: 0.76rem;
  font-weight: 720;
}
.profile-species-list,
.distinctive-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.profile-species-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 10px;
}
.profile-species-list li {
  min-height: 82px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 13px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
}
.profile-species-list span {
  color: var(--ink);
  line-height: 1.2;
}
.profile-species-list small {
  color: var(--muted);
  font-size: 0.78rem;
}
.watch-grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(330px, 1fr));
  gap: 10px;
}
.watch-card {
  min-width: 0;
  min-height: 124px;
  display: grid;
  grid-template-columns: 118px minmax(0, 1fr);
  border: 1px solid var(--line);
  border-radius: 6px;
  overflow: hidden;
  background: var(--panel);
}
.watch-image {
  min-height: 124px;
  background: var(--panel-2);
}
.watch-image img,
.watch-placeholder {
  width: 100%;
  height: 100%;
}
.watch-image img {
  display: block;
  object-fit: cover;
}
.watch-placeholder {
  display: grid;
  place-items: center;
  color: var(--faint);
  font-size: 0.72rem;
}
.watch-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  padding: 12px;
}
.watch-copy span,
.watch-copy a {
  color: var(--ink);
  font-weight: 650;
  line-height: 1.18;
}
.watch-copy a:hover {
  color: var(--amber);
}
.watch-copy small,
.watch-copy em {
  display: block;
  margin-top: 7px;
  color: var(--muted);
  font-size: 0.75rem;
  font-style: normal;
  line-height: 1.3;
}
.watch-copy em {
  margin-top: 5px;
  color: var(--amber);
  font-size: 0.68rem;
  text-transform: uppercase;
}
.signature-gallery {
  display: grid;
  grid-template-columns: 1.5fr repeat(3, minmax(0, 1fr));
  min-height: 340px;
  border: 1px solid var(--line);
  border-radius: 6px;
  overflow: hidden;
  background: var(--panel);
}
.signature-card {
  min-width: 0;
  position: relative;
  display: flex;
  align-items: flex-end;
  min-height: 340px;
  overflow: hidden;
  color: var(--ink);
  border-left: 1px solid var(--line);
  text-decoration: none;
}
.signature-card:first-child {
  border-left: 0;
}
.signature-media,
.signature-media img,
.signature-placeholder {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.signature-media img {
  object-fit: cover;
  transition: transform 220ms ease;
}
.signature-placeholder {
  display: grid;
  place-items: center;
  color: var(--faint);
  background: var(--panel-2);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.75rem;
}
.signature-copy {
  width: 100%;
  position: relative;
  z-index: 1;
  padding: 48px 14px 14px;
  background: linear-gradient(to bottom, transparent, rgba(16, 17, 13, 0.94) 46%);
}
.signature-copy h3,
.signature-copy p,
.signature-copy small {
  margin: 0;
}
.signature-copy h3 {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 1.16rem;
  font-weight: 500;
  line-height: 1.05;
}
.signature-card:first-child .signature-copy h3 {
  font-size: 1.48rem;
}
.signature-copy p,
.signature-copy small {
  display: block;
  margin-top: 7px;
  color: var(--ink);
  font-size: 0.78rem;
  line-height: 1.3;
}
.signature-copy small {
  color: var(--muted);
}
.signature-card:hover .signature-media img {
  transform: scale(1.025);
}
.signature-card:focus-visible {
  outline: 3px solid var(--amber);
  outline-offset: -3px;
}
.distinctive-overview {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: baseline;
  column-gap: 12px;
  padding: 0 0 18px;
  border-bottom: 1px solid var(--line);
}
.distinctive-overview strong {
  grid-row: span 2;
  color: var(--amber);
  font-family: Georgia, "Times New Roman", serif;
  font-size: 3rem;
  font-weight: 500;
  line-height: 0.9;
}
.distinctive-overview span {
  color: var(--ink);
  font-size: 1rem;
}
.distinctive-overview small {
  color: var(--muted);
  font-size: 0.78rem;
}
.distinctive-ledger {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 40px;
  padding-top: 24px;
}
.distinctive-heading p,
.distinctive-heading span {
  margin: 0;
}
.distinctive-heading p {
  color: var(--amber);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.82rem;
  text-transform: uppercase;
}
.distinctive-heading span {
  display: block;
  min-height: 42px;
  margin-top: 6px;
  color: var(--muted);
  font-size: 0.85rem;
  line-height: 1.35;
}
.distinctive-list {
  margin-top: 10px;
  counter-reset: distinctive;
}
.distinctive-list li {
  counter-increment: distinctive;
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  padding: 11px 0;
  border-top: 1px solid var(--line);
}
.distinctive-list li::before {
  content: counter(distinctive, decimal-leading-zero);
  color: var(--faint);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.68rem;
}
.distinctive-list span,
.distinctive-list small {
  grid-column: 2;
}
.distinctive-list span,
.distinctive-list a {
  color: var(--ink);
  line-height: 1.25;
}
.distinctive-list a:hover {
  color: var(--amber);
}
.distinctive-list small,
.distinctive-empty {
  margin-top: 4px;
  color: var(--muted);
  font-size: 0.76rem;
}
.recap-range {
  margin: 0 0 16px;
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.82rem;
  text-transform: uppercase;
}
.recap-showcase {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}
.recap-showcase-card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 6px;
  min-width: 0;
}
.recap-showcase-image {
  height: 150px;
  background: var(--panel);
}
.recap-showcase-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.recap-showcase-image .record-placeholder {
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--faint);
  font-size: 0.7rem;
}
.recap-showcase-copy {
  padding: 12px 14px 16px;
}
.recap-showcase-copy h4 {
  margin: 0 0 4px;
  font-size: 1rem;
  line-height: 1.25;
}
.recap-showcase-copy p {
  margin: 0;
  color: var(--muted);
  font-size: 0.82rem;
}
.recap-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}
.recap-card {
  padding: 16px 18px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 6px;
  min-width: 0;
}
.recap-card-wide {
  grid-column: span 2;
}
@media (max-width: 720px) {
  .recap-card-wide {
    grid-column: span 1;
  }
}
.recap-headline strong {
  display: block;
  color: var(--amber);
  font-family: Georgia, "Times New Roman", serif;
  font-size: 2.6rem;
  font-weight: 500;
  line-height: 1;
}
.recap-headline span {
  display: block;
  margin-top: 6px;
  color: var(--ink);
}
.recap-headline small {
  display: block;
  margin-top: 6px;
  color: var(--muted);
  font-size: 0.78rem;
}
.recap-card-label {
  margin: 0 0 10px;
  color: var(--amber);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.78rem;
  text-transform: uppercase;
}
.recap-empty-line {
  margin: 0;
  color: var(--muted);
  font-size: 0.85rem;
}
.recap-stacked-copy {
  margin: 0;
  color: var(--ink);
  line-height: 1.45;
}
.habitat-overview {
  margin: 0 0 14px;
  color: var(--muted);
  font-size: 0.9rem;
}
.habitat-preview-note {
  margin: -6px 0 14px;
  color: var(--faint);
  font-size: 0.8rem;
}
.habitat-browse {
  margin: 0 0 18px;
}
.habitat-browse a {
  display: inline-block;
  padding: 9px 12px;
  color: var(--amber);
  border: 1px solid var(--line);
  border-radius: 4px;
  font-size: 0.84rem;
}
.habitat-browse a:hover {
  border-color: var(--amber);
}
.habitat-list {
  list-style: none;
  margin: 0 0 14px;
  padding: 0;
  display: grid;
  gap: 10px;
}
.habitat-list li {
  padding: 12px 14px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 6px;
}
.habitat-species {
  font-weight: 600;
}
.habitat-genus-note {
  color: var(--muted);
  font-size: 0.76rem;
}
.habitat-hosts {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 0.84rem;
}
.habitat-empty {
  margin: 0 0 14px;
  color: var(--muted);
  font-size: 0.86rem;
}
.habitat-info {
  border-top: 1px solid var(--line);
  margin-bottom: 16px;
}
.habitat-info summary {
  cursor: pointer;
  padding: 10px 2px;
  color: var(--amber);
  font-size: 0.84rem;
  list-style: none;
}
.habitat-info summary::-webkit-details-marker {
  display: none;
}
.habitat-info summary span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  margin-right: 6px;
  border: 1px solid var(--amber);
  border-radius: 50%;
  font-size: 0.72rem;
}
.habitat-info p {
  margin: 0 0 12px;
  padding: 0 2px;
  color: var(--muted);
  font-size: 0.82rem;
  line-height: 1.5;
}
.habitat-companions {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
}
.habitat-candidates li {
  padding: 10px 12px;
}
.habitat-candidates a {
  color: var(--amber);
}
.habitat-candidates small {
  display: block;
  margin-top: 4px;
  color: var(--muted);
  font-size: 0.76rem;
}
.trend-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.trend-panel {
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
}
.trend-panel-wide {
  grid-column: 1 / -1;
}
.trend-panel h3 {
  margin: 0 0 6px;
  font-size: 1.15rem;
}
.trend-panel p {
  margin: 0 0 14px;
  color: var(--muted);
  font-size: 0.9rem;
}
.phenology-row {
  display: grid;
  grid-template-columns: minmax(220px, 0.8fr) minmax(260px, 1fr) 132px;
  gap: 12px;
  align-items: center;
  padding: 9px 0;
  border-top: 1px solid var(--line);
}
.phenology-row strong,
.rank-row strong {
  display: block;
  color: var(--ink);
  line-height: 1.15;
}
.phenology-row span,
.phenology-row small,
.rank-row small {
  color: var(--muted);
  font-size: 0.78rem;
}
.phenology-track {
  position: relative;
  height: 14px;
  background: #191a12;
  border: 1px solid var(--line);
}
.phenology-track::before,
.phenology-track::after {
  position: absolute;
  top: 18px;
  color: var(--faint);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.68rem;
}
.phenology-track::before {
  content: "Jan";
  left: 0;
}
.phenology-track::after {
  content: "Dec";
  right: 0;
}
.phenology-track i {
  position: absolute;
  top: -1px;
  bottom: -1px;
  display: block;
  background: var(--amber);
}
.rank-row span {
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.78rem;
  font-weight: 500;
}
.network-line-chart .accumulation-area {
  fill: rgba(138, 167, 122, 0.14);
}
.network-line-chart .accumulation-line {
  stroke: var(--leaf);
}
.station-launch-marker line {
  stroke: var(--station-color);
  stroke-width: 1;
  stroke-dasharray: 3 5;
  opacity: 0.7;
  vector-effect: non-scaling-stroke;
}
.network-line-chart .station-launch-marker circle {
  fill: var(--panel);
  stroke: var(--station-color);
  stroke-width: 3;
  vector-effect: non-scaling-stroke;
}
.station-launches {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 10px 2px 0;
}
.station-launches p {
  flex: 0 0 auto;
  margin: 2px 0 0;
  color: var(--muted);
  font-size: 0.72rem;
  text-transform: uppercase;
}
.station-launches ul,
.monthly-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 7px 14px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.station-launches li {
  display: grid;
  grid-template-columns: 8px auto;
  align-items: center;
  column-gap: 6px;
  color: var(--ink);
  font-size: 0.72rem;
}
.station-launches li i {
  grid-row: span 2;
  width: 7px;
  height: 7px;
  border: 2px solid var(--station-color);
  border-radius: 50%;
}
.station-launches time {
  color: var(--muted);
  font-size: 0.64rem;
  font-variant-numeric: tabular-nums;
}
.monthly-overlay-chart {
  margin: 0;
  position: relative;
}
.monthly-legend {
  margin-bottom: 10px;
}
.monthly-legend li {
  display: grid;
  grid-template-columns: 20px auto;
  align-items: center;
  column-gap: 7px;
}
.monthly-legend i {
  grid-row: span 2;
  width: 20px;
  height: 3px;
  background: var(--series-color);
}
.monthly-legend strong {
  color: var(--ink);
  font-size: 0.74rem;
  line-height: 1;
}
.monthly-legend span {
  color: var(--muted);
  font-size: 0.64rem;
  line-height: 1.2;
}
.monthly-overlay-chart svg {
  width: 100%;
  aspect-ratio: 720 / 260;
  height: auto;
  max-height: 340px;
  display: block;
}
.monthly-line {
  fill: none;
  stroke: var(--series-color);
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}
.monthly-point {
  fill: var(--panel);
  stroke: var(--series-color);
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}
.monthly-hit-target {
  fill: transparent;
  stroke: transparent;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
  cursor: crosshair;
}
.monthly-point-group:focus {
  outline: none;
}
.monthly-point-group:hover .monthly-hit-target,
.monthly-point-group:focus .monthly-hit-target {
  fill: rgba(215, 181, 109, 0.12);
  stroke: var(--amber);
}
.monthly-point-group:hover .monthly-point,
.monthly-point-group:focus .monthly-point {
  fill: var(--amber);
  stroke-width: 3;
}
.monthly-tooltip {
  position: absolute;
  z-index: 4;
  width: min(240px, calc(100% - 16px));
  border: 1px solid var(--amber);
  background: rgba(21, 22, 17, 0.97);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.32);
  padding: 10px 12px;
  pointer-events: none;
}
.monthly-tooltip-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 7px;
}
.monthly-tooltip-head strong {
  color: var(--paper);
}
.monthly-tooltip-head span {
  color: var(--amber);
  font-size: 0.72rem;
  text-align: right;
}
.monthly-tooltip ul {
  display: grid;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.monthly-tooltip li {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) auto;
  align-items: center;
  gap: 7px;
  color: var(--muted);
  font-size: 0.76rem;
}
.monthly-tooltip li i {
  width: 7px;
  height: 7px;
  background: var(--station-color);
}
.monthly-tooltip li i.shared-dot {
  background: color-mix(in srgb, var(--muted) 58%, var(--panel));
}
.monthly-tooltip li strong {
  color: var(--paper);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.rank-row {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 9px;
  padding: 8px 0;
  border-top: 1px solid var(--line);
}
.rank-row div {
  position: relative;
  min-height: 42px;
}
.rank-row i {
  display: block;
  height: 4px;
  margin-top: 7px;
  background: var(--amber);
}
.similarity-wrap {
  overflow-x: auto;
}
.similarity-table {
  min-width: 760px;
  table-layout: fixed;
}
.similarity-table th,
.similarity-table td {
  text-align: center;
  padding: 8px;
}
.similarity-table th:first-child {
  text-align: left;
  width: 118px;
}
.similarity-table td {
  background: var(--cell-bg);
}
.similarity-table td span,
.similarity-table td small {
  display: block;
  color: var(--ink);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.similarity-table td small {
  color: var(--muted);
  font-size: 0.68rem;
}
.insight-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 8px;
}
.insight-card {
  min-height: 128px;
  grid-column: span 3;
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: linear-gradient(135deg, rgba(215, 181, 109, 0.08), rgba(255, 255, 255, 0.015) 46%), var(--panel);
}
.insight-card p,
.insight-card small {
  margin: 0;
  color: var(--amber);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.72rem;
}
.insight-card h3 {
  margin: 10px 0 6px;
  font-family: Georgia, "Times New Roman", serif;
  font-size: clamp(1rem, 1.4vw, 1.25rem);
  font-weight: 500;
  line-height: 1.1;
  text-wrap: balance;
}
.insight-card span {
  display: block;
  color: var(--muted);
  font-size: 0.84rem;
  text-wrap: pretty;
}
.insight-card small {
  color: var(--faint);
  padding-top: 8px;
}
.feed-section-copy {
  display: grid;
  justify-items: end;
  gap: 8px;
}
.insight-feedback-copy {
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 6px 9px;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 0.76rem;
  cursor: pointer;
}
.insight-feedback-copy:hover {
  border-color: var(--amber);
  color: var(--amber);
}
.insight-feedback-status {
  min-height: 1.25em;
  margin: -8px 0 12px;
  color: var(--faint);
  font-size: 0.78rem;
}
.insight-feedback {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 12px;
  padding-top: 9px;
  border-top: 1px solid rgba(240, 232, 214, 0.09);
}
.insight-feedback > span {
  margin-right: auto;
  color: var(--faint);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.68rem;
}
.insight-rating {
  display: inline-grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: transparent;
  color: var(--muted);
  font: inherit;
  line-height: 1;
  cursor: pointer;
}
.insight-rating:hover {
  border-color: var(--amber);
  color: var(--ink);
}
.insight-rating.is-selected[data-insight-rating="up"] {
  border-color: var(--leaf);
  background: color-mix(in srgb, var(--leaf) 18%, transparent);
  color: var(--ink);
}
.insight-rating.is-selected[data-insight-rating="down"] {
  border-color: var(--rust);
  background: color-mix(in srgb, var(--rust) 18%, transparent);
  color: var(--ink);
}
.insight-rating:focus-visible,
.insight-feedback-copy:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 2px;
}
.insight-index {
  position: absolute;
  top: 10px;
  right: 12px;
  color: rgba(243, 234, 215, 0.24);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 1rem;
}
.station-card {
  min-height: 210px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  position: relative;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 16px;
}
.station-card::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 5px;
  background: var(--station-color, var(--amber));
  border-radius: 6px 0 0 6px;
}
.station-card h3 {
  margin: 8px 0 8px;
  font-size: 1.25rem;
  line-height: 1.1;
}
.station-card p {
  margin: 0;
  color: var(--muted);
}
.station-status {
  color: var(--leaf);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.76rem;
}
.station-status-inactive {
  color: var(--faint);
}
.station-numbers {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 18px;
}
.station-numbers span {
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 5px 8px;
  color: var(--muted);
  background: rgba(255, 255, 255, 0.02);
  font-size: 0.86rem;
}
.latest {
  padding-top: 14px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8rem;
}
.sighting-grid,
.pulse-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.sighting-card {
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr);
  min-height: 128px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  overflow: hidden;
}
.sighting-image {
  background: var(--panel-2);
}
.sighting-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.sighting-placeholder {
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--faint);
  font-size: 0.8rem;
}
.sighting-copy {
  min-width: 0;
  padding: 12px;
}
.sighting-copy p,
.sighting-copy span {
  margin: 0;
  color: var(--muted);
  font-size: 0.8rem;
}
.sighting-copy h3 {
  margin: 7px 0 8px;
  font-size: 1rem;
  line-height: 1.2;
}
.night-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border: 1px solid var(--line);
  background: var(--panel);
  margin-bottom: 12px;
}
.night-summary div {
  padding: 14px 16px;
  border-right: 1px solid var(--line);
}
.night-summary div:last-child {
  border-right: 0;
}
.night-summary strong {
  display: block;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: clamp(1.15rem, 2vw, 1.65rem);
  line-height: 1.1;
}
.night-summary span {
  display: block;
  margin-top: 4px;
  color: var(--muted);
  font-size: 0.82rem;
}
.night-stations {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}
.night-station-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  border: 1px solid color-mix(in srgb, var(--station-color) 64%, var(--line));
  border-left-width: 5px;
  border-radius: 4px;
  padding: 5px 10px;
  background: rgba(255, 255, 255, 0.025);
  color: var(--muted);
  text-decoration: none;
  font: inherit;
}
.night-filter-chip {
  cursor: pointer;
}
.night-station-chip:hover {
  color: var(--ink);
  background: color-mix(in srgb, var(--station-color) 12%, var(--panel));
}
.night-filter-chip[aria-pressed="true"] {
  color: var(--ink);
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--station-color) 22%, transparent), transparent),
    var(--panel-2);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--station-color) 52%, transparent);
}
.night-station-chip:focus-visible {
  outline: 2px solid var(--station-color);
  outline-offset: 2px;
}
.night-station-chip strong {
  color: var(--ink);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.night-filter-status {
  margin: -8px 0 12px;
  color: var(--muted);
  font-size: 0.82rem;
}
.night-filter-empty {
  margin-top: 14px;
}
.network-total-chip {
  background: color-mix(in srgb, var(--amber) 12%, var(--panel));
  color: var(--ink);
}
.live-new-station-counter .night-station-chip:not(.network-total-chip) {
  display: grid;
  grid-template-columns: auto auto;
  column-gap: 8px;
  row-gap: 1px;
}
.live-station-chip-name {
  min-width: 0;
}
.live-new-station-counter .night-station-chip small {
  grid-column: 1 / -1;
  color: var(--muted);
  font-size: 0.72rem;
  line-height: 1.15;
}
.live-new-station-counter .night-station-chip small b {
  color: var(--ink);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-weight: 700;
}
.night-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(178px, 1fr));
  gap: 10px;
}
.night-card {
  display: grid;
  grid-template-rows: 150px minmax(116px, auto);
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
}
.night-card[hidden] {
  display: none;
}
.night-image {
  min-width: 0;
  background: var(--panel-2);
}
.night-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.night-placeholder {
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--faint);
  font-size: 0.82rem;
}
.night-copy {
  min-width: 0;
  padding: 10px;
}
.night-copy p {
  margin: 0 0 6px;
  color: var(--muted);
  font-size: 0.76rem;
}
.night-copy h3 {
  margin: 0 0 10px;
  font-size: 0.95rem;
  line-height: 1.18;
}
.night-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.night-badges span {
  border-left: 4px solid var(--station-color, var(--amber));
  background: rgba(255, 255, 255, 0.035);
  color: var(--muted);
  padding: 3px 6px;
  border-radius: 3px;
  font-size: 0.72rem;
}
.pulse-card {
  padding: 16px;
  background: var(--panel-2);
  border-left: 4px solid var(--amber);
  border-radius: 4px;
}
.pulse-card p {
  margin: 0 0 10px;
  color: var(--amber);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.78rem;
}
.pulse-card h3 {
  margin: 0 0 16px;
  font-size: 1.05rem;
  line-height: 1.2;
}
.pulse-card div {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.pulse-card span {
  color: var(--muted);
  font-size: 0.82rem;
}
.record-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(270px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.record-card {
  display: grid;
  grid-template-rows: 150px minmax(116px, auto);
  min-width: 0;
  overflow: hidden;
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 6px;
}
.record-image {
  min-width: 0;
  background: var(--panel);
}
.record-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.record-placeholder {
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--faint);
  font-size: 0.82rem;
}
.record-copy {
  min-width: 0;
  padding: 12px 16px;
}
.record-flags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.record-card h3 {
  margin: 10px 0 6px;
  font-size: 1.02rem;
  line-height: 1.2;
}
.record-card p {
  margin: 0;
  color: var(--muted);
}
.record-archive {
  border-top: 1px solid var(--line);
}
.record-archive summary {
  cursor: pointer;
  padding: 13px 2px;
  color: var(--amber);
  font-size: 0.86rem;
}
.record-archive[open] summary {
  margin-bottom: 8px;
}
.record-archive-controls,
.record-grid-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 2px 2px;
  color: var(--muted);
  font-size: 0.86rem;
}
.record-grid-controls {
  padding: 0 2px 14px;
}
.record-archive-controls button,
.record-grid-controls button {
  border: 1px solid var(--amber);
  border-radius: 4px;
  padding: 8px 12px;
  background: transparent;
  color: var(--amber);
  font: inherit;
  cursor: pointer;
}
.record-archive-controls button:hover,
.record-grid-controls button:hover {
  background: color-mix(in srgb, var(--amber) 10%, transparent);
}
.record-archive-controls button:focus-visible,
.record-grid-controls button:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 2px;
}
.record-filter-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
}
.record-filter-row label {
  display: block;
  margin-bottom: 6px;
  color: var(--muted);
  font-size: 0.86rem;
}
.record-filter-row select {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 10px 12px;
  background: #181910;
  color: var(--ink);
  font: inherit;
}
.record-filter-row select:focus {
  outline: 3px solid var(--focus);
  outline-offset: 2px;
}
.unique-filter-row {
  display: grid;
  grid-template-columns: minmax(140px, 0.22fr) minmax(220px, 1fr);
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
}
.unique-filter-row label {
  color: var(--muted);
  font-size: 0.86rem;
}
.unique-filter-row input {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 10px 12px;
  background: #181910;
  color: var(--ink);
  font: inherit;
}
.unique-filter-row input:focus {
  outline: 3px solid var(--focus);
  outline-offset: 2px;
}
.unique-station-grid {
  display: grid;
  gap: 14px;
}
.unique-station-panel {
  border: 1px solid var(--line);
  border-left: 5px solid var(--station-color, var(--amber));
  border-radius: 6px;
  background: var(--panel);
  overflow: hidden;
}
.unique-station-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 16px;
  border-bottom: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.02);
}
.unique-station-head p {
  margin: 0 0 5px;
  color: var(--muted);
  font-size: 0.82rem;
}
.unique-station-head h3 {
  margin: 0;
  font-size: 1.25rem;
  line-height: 1.1;
}
.unique-station-head strong {
  color: var(--station-color, var(--amber));
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: clamp(1.6rem, 4vw, 2.4rem);
  line-height: 0.95;
}
.unique-lists {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 14px;
}
.unique-lists h4 {
  margin: 0 0 8px;
  color: var(--amber);
  font-size: 0.9rem;
}
.unique-lists ul {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.unique-lists li {
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 8px;
  background: rgba(255, 255, 255, 0.02);
}
.unique-lists li strong,
.unique-lists li span {
  display: block;
}
.unique-lists li strong {
  font-size: 0.9rem;
  line-height: 1.2;
}
.unique-lists li span {
  margin-top: 4px;
  color: var(--muted);
  font-size: 0.76rem;
}
.unique-full-list {
  border-top: 1px solid var(--line);
  padding: 0 14px 14px;
}
.unique-full-list summary {
  cursor: pointer;
  padding: 12px 0;
  color: var(--amber);
}
.unique-table-wrap {
  max-height: min(62vh, 620px);
}
.unique-empty-note {
  margin: 0;
  padding: 16px;
  color: var(--muted);
}
.flag {
  display: inline-block;
  margin: 0 5px 5px 0;
  padding: 2px 7px;
  color: #1b170f;
  background: var(--amber);
  border-radius: 4px;
  font-size: 0.74rem;
  line-height: 1.4;
  white-space: nowrap;
}
.table-wrap {
  max-height: min(72vh, 760px);
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
}
table {
  width: 100%;
  min-width: 860px;
  border-collapse: collapse;
  font-size: 0.92rem;
  font-variant-numeric: tabular-nums;
}
th, td {
  text-align: left;
  padding: 11px 12px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: #1c1d15;
  color: var(--amber);
  font-weight: 650;
  white-space: nowrap;
}
th.station-head {
  color: var(--station-color);
}
th.station-head::before {
  content: "";
  display: inline-block;
  width: 0.7rem;
  height: 0.7rem;
  margin-right: 0.45rem;
  background: var(--station-color);
  vertical-align: -0.05rem;
}
.sort-button {
  appearance: none;
  border: 0;
  padding: 0;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
  text-align: left;
}
.sort-button span::after {
  content: "↕";
  color: var(--faint);
  font-size: 0.78rem;
}
.sort-button[data-direction="asc"] span::after {
  content: "↑";
  color: var(--ink);
}
.sort-button[data-direction="desc"] span::after {
  content: "↓";
  color: var(--ink);
}
.sort-button:focus-visible,
.view-toggle-button:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 3px;
}
td span {
  color: var(--muted);
  font-size: 0.84rem;
}
a {
  color: var(--amber);
  text-decoration-thickness: 1px;
  text-underline-offset: 2px;
}
a:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 2px;
}
a:hover { color: #f2d78e; }
.tag {
  display: inline-block;
  color: #1b170f;
  background: var(--amber);
  border-radius: 4px;
  padding: 2px 8px;
  white-space: nowrap;
}
.empty {
  color: var(--muted);
  margin: 0;
  padding: 18px;
  border: 1px dashed var(--line);
  border-radius: 6px;
}
.view-toggle {
  display: inline-flex;
  gap: 1px;
  padding: 3px;
  margin: 0 0 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #181910;
}
.view-toggle-button {
  appearance: none;
  border: 0;
  border-radius: 4px;
  padding: 7px 10px;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 0.86rem;
  cursor: pointer;
}
.view-toggle-button.is-active {
  background: var(--amber);
  color: #1b170f;
}
.view-panel[hidden] {
  display: none;
}
.calendar-table {
  table-layout: fixed;
  min-width: 920px;
}
.calendar-table th,
.calendar-table td {
  text-align: center;
  padding: 8px;
}
.calendar-table td:first-child,
.calendar-table th:first-child {
  width: 96px;
  text-align: left;
}
.calendar-table th:nth-child(2),
.calendar-table td:nth-child(2) {
  width: 92px;
}
.calendar-table th:nth-child(3),
.calendar-table td:nth-child(3) {
  width: 88px;
}
.calendar-table th.station-head {
  width: 82px;
}
.calendar-table th.station-head::before {
  display: block;
  margin: 0 auto 4px;
}
.calendar-table .sort-button {
  width: 100%;
  justify-content: center;
  white-space: normal;
  line-height: 1.1;
}
.calendar-table th:first-child .sort-button {
  justify-content: flex-start;
}
.calendar-line-head {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: baseline;
  margin: 0 0 12px;
}
.calendar-line-head h3 {
  margin: 0;
  color: var(--ink);
  font-size: 1.08rem;
}
.calendar-line-head p {
  max-width: 520px;
  margin: 0;
  color: var(--muted);
  font-size: 0.86rem;
}
.daily-richness-line-chart {
  position: relative;
  margin: 0 0 16px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
}
.daily-richness-line-chart svg {
  width: 100%;
  aspect-ratio: 900 / 300;
  height: auto;
  display: block;
}
.daily-richness-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 7px 14px;
  margin: 0 0 10px;
  padding: 0;
  list-style: none;
}
.daily-richness-legend li {
  display: inline-grid;
  grid-template-columns: 18px auto;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font-size: 0.72rem;
}
.daily-richness-legend i {
  width: 16px;
  height: 9px;
  border-radius: 2px;
  opacity: 0.85;
  background: var(--series-color);
}
.daily-richness-shared-key {
  --series-color: color-mix(in srgb, var(--muted) 58%, var(--panel));
}
.daily-richness-station-bar {
  fill: var(--series-color);
  opacity: 0.9;
}
.daily-richness-shared-bar {
  fill: color-mix(in srgb, var(--muted) 58%, var(--panel));
  opacity: 0.88;
}
.calendar-cell {
  width: 82px;
}
.calendar-cell span {
  width: 100%;
  min-height: 38px;
  display: grid;
  place-items: center;
  border: 1px solid var(--station-color);
  background: var(--cell-bg);
  color: var(--ink);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.86rem;
}
footer {
  color: var(--muted);
  border-top: 1px solid var(--line);
  padding: 22px 0 34px;
  font-size: 0.9rem;
}
footer div {
  width: min(var(--max), calc(100% - 32px));
  margin: 0 auto;
}
@media (max-width: 980px) {
  .hero {
    grid-template-columns: 1fr;
  }
  .hero-copy,
  .hero-metrics,
  .photo-rail {
    grid-column: auto;
    grid-row: auto;
  }
  .hero-copy {
    order: 1;
  }
  .hero-metrics {
    order: 2;
  }
  .photo-rail {
    order: 3;
    grid-auto-rows: 146px;
  }
  .signature-gallery {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .signature-card,
  .signature-card:first-child {
    min-height: 280px;
    border: 1px solid var(--line);
  }
  .signature-card:nth-child(odd) {
    border-left: 0;
  }
  .distinctive-ledger {
    grid-template-columns: 1fr;
    gap: 30px;
  }
  .trend-grid {
    grid-template-columns: 1fr;
  }
  .phenology-row {
    grid-template-columns: 1fr;
  }
  .phenology-track {
    margin-bottom: 20px;
  }
  .section-head {
    display: block;
  }
  .section-head p {
    margin-top: 8px;
  }
  .calendar-line-head {
    display: block;
  }
  .calendar-line-head p {
    margin-top: 5px;
  }
  .feed-section-copy {
    justify-items: start;
    margin-top: 8px;
  }
  .insight-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .insight-card,
  .insight-card:nth-child(1),
  .insight-card:nth-child(2) {
    grid-column: span 1;
  }
}
@media (max-width: 620px) {
  :root {
    --topbar-height: 108px;
  }
  .live-page {
    --topbar-height: 64px;
  }
  .topbar {
    align-items: stretch;
    flex-direction: column;
    justify-content: flex-start;
    gap: 0;
    min-height: var(--topbar-height);
    padding: 10px 16px 0;
  }
  .topbar-primary {
    width: 100%;
    min-height: 38px;
    justify-content: space-between;
  }
  .topbar-mode-only {
    min-height: var(--topbar-height);
    padding: 10px 16px;
  }
  .topbar-mode-only .topbar-primary {
    width: 100%;
  }
  .section-nav {
    width: 100%;
    min-width: 0;
    min-height: 44px;
    flex-wrap: nowrap;
    justify-content: flex-start;
    align-items: center;
    gap: 18px;
    overflow-x: auto;
    overflow-y: hidden;
    overscroll-behavior-x: contain;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }
  .section-nav::-webkit-scrollbar {
    display: none;
  }
  .section-nav a {
    flex: 0 0 auto;
    white-space: nowrap;
  }
  h1 {
    font-size: clamp(3rem, 17vw, 5rem);
  }
  .insight-grid {
    grid-template-columns: 1fr;
  }
  .photo-rail {
    width: calc(100vw - 16px);
    margin-right: calc(50% - 50vw);
    padding-right: 16px;
    display: grid;
    grid-template-columns: none;
    grid-template-rows: 230px;
    grid-auto-flow: column;
    grid-auto-columns: min(78vw, 320px);
    grid-auto-rows: auto;
    gap: 8px;
    overflow-x: auto;
    overflow-y: hidden;
    border-radius: 0;
    scroll-padding-left: 0;
    scroll-snap-type: x mandatory;
    scrollbar-width: none;
    overscroll-behavior-inline: contain;
    touch-action: pan-x;
  }
  .photo-rail::-webkit-scrollbar {
    display: none;
  }
  .photo-tile,
  .photo-tile:nth-child(1),
  .photo-tile:nth-child(6) {
    grid-column: auto;
    grid-row: 1;
    scroll-snap-align: start;
  }
  .sighting-card {
    grid-template-columns: 92px minmax(0, 1fr);
  }
  .watch-grid {
    grid-template-columns: 1fr;
  }
  .watch-card {
    grid-template-columns: 104px minmax(0, 1fr);
  }
  .signature-gallery {
    grid-template-columns: 1fr;
  }
  .signature-card,
  .signature-card:first-child,
  .signature-card:nth-child(odd) {
    min-height: 260px;
    border: 0;
    border-top: 1px solid var(--line);
  }
  .signature-card:first-child {
    min-height: 320px;
    border-top: 0;
  }
  .signature-copy h3,
  .signature-card:first-child .signature-copy h3 {
    font-size: 1.3rem;
  }
  .distinctive-overview {
    align-items: start;
  }
  .distinctive-overview strong {
    font-size: 2.5rem;
  }
  .unique-filter-row,
  .unique-lists {
    grid-template-columns: 1fr;
  }
  .unique-station-head {
    gap: 12px;
  }
  .night-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .night-summary div {
    border-right: 1px solid var(--line);
    border-bottom: 1px solid var(--line);
  }
  .night-summary div:nth-child(2n) {
    border-right: 0;
  }
  .night-summary div:nth-last-child(-n + 2) {
    border-bottom: 0;
  }
  .night-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .night-card {
    grid-template-rows: 132px minmax(126px, auto);
  }
  .sampling-context-metrics > div:last-child:nth-child(odd) {
    grid-column: 1 / -1;
    border-right: 0;
  }
}
"""


def render(settings: Settings, stations: list[Station], output: Path | None = None) -> Path:
    init_db(settings.database)
    output = output or settings.public_dir / "index.html"
    settings.public_dir.mkdir(parents=True, exist_ok=True)

    summaries = station_summaries(settings)
    recent = recent_observations(settings)
    recent_spotlight = diversify_by_station(recent, limit=12, dedupe_key="url")
    hero_photo_rows = hero_photos(settings)
    year = active_year(settings)
    pulses = first_of_season(settings, year)
    all_time_pulses = first_of_season(settings, all_time=True)
    latest_night = latest_session_taxa(settings)
    recent_week = recent_days_taxa(settings)
    taxa = station_taxa(settings)
    year_taxa = station_taxa(settings, year) if year else []
    latest_night_taxa = latest_night.get("taxa") or []
    recent_week_taxa = recent_week.get("taxa") or []
    year_calendar = daily_species_counts(settings, year) if year else []
    all_time_calendar = daily_species_counts(settings)
    records = record_highlights(settings)
    uniques = unique_station_taxa(settings)
    insights = dashboard_insights(settings)
    trends = trend_summary(settings)

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Moth Station Dashboard</title>
  <meta name="description" content="Compare recent moth observations and first-of-season records across iNaturalist stations.">
  <meta name="theme-color" content="#151611">
  <style>{CSS}</style>
</head>
<body>
  <a class="skip-link" href="#main">Skip to dashboard</a>
  <header>
    <div class="topbar">
      <div class="topbar-primary">
        <a class="brand" href="#main"><span class="brand-mark" aria-hidden="true"></span><span>Moth stations</span></a>
        {_mode_toggle("#main", "live.html", "history")}
      </div>
      <nav class="section-nav" aria-label="Dashboard sections">
        <a href="#last-night">Last night</a>
        <a href="#past-week">Past week</a>
        <a href="#stations">Stations</a>
        <a href="#feed">Feed</a>
        <a href="#recent">Recent</a>
        <a href="#pulses">First arrivals</a>
        <a href="#records">Firsts</a>
        <a href="#unique">Unique</a>
        <a href="#calendar">Calendar</a>
        <a href="#trends">Trends</a>
        <a href="#species">Species</a>
      </nav>
    </div>
    <div class="hero">
      <div class="hero-copy">
        <p class="eyebrow">regional light-sheet telemetry</p>
        <h1>Night flights, compared.</h1>
        <p class="subhead">A working dashboard for seeing which moth stations are active, what just arrived, and whether first-of-season records are breaking across the region on the same nights.</p>
      </div>
      <div class="photo-rail" aria-label="Recent moth photos">{_photo_strip(hero_photo_rows)}</div>
      <div class="hero-metrics">{_hero_metrics(summaries, taxa, pulses, stations, records)}</div>
    </div>
  </header>
  <main id="main" class="site-shell">
    <section id="last-night">
      <div class="section-head">
        <h2>Last night</h2>
        <p>A photo-first scan of the latest synced moth session, grouped by unique species so shared and station-only sightings are easy to compare.</p>
      </div>
      {_last_night_dashboard(latest_night, stations)}
    </section>

    <section id="past-week">
      <div class="section-head">
        <h2>Past week</h2>
        <p>The same view as last night, widened to the trailing seven nights so slower-moving activity and multi-night visitors are easier to spot.</p>
      </div>
      {_recent_week_dashboard(recent_week, stations)}
    </section>

    <section id="stations">
      <div class="section-head">
        <h2>All-time location info</h2>
        <p>Configured stations stay visible even before their first sync, so owners can see what is online, what is waiting for observations, and what is no longer active.</p>
      </div>
      <div class="cards">{_station_cards(summaries, stations)}</div>
    </section>

    <section id="feed">
      <div class="section-head feed-section-head">
        <h2>Naturalist feed</h2>
        <div class="feed-section-copy">
          <p>Build-generated headlines from the station network, meant to surface discoveries, timing shifts, and shared flight pulses before the tables.</p>
          <button type="button" class="insight-feedback-copy" data-insight-feedback-copy>Copy ratings</button>
        </div>
      </div>
      <p class="insight-feedback-status" data-insight-feedback-status aria-live="polite"></p>
      <div class="insight-grid">{_insight_cards(insights)}</div>
    </section>

    <section id="recent">
      <div class="section-head">
        <h2>Recent sightings</h2>
        <p>Fresh uploads are shown as a field log first, with the full table kept below for scanning dates, observers, and links.</p>
      </div>
      <div class="sighting-grid">{_recent_cards(recent_spotlight)}</div>
      <div class="table-wrap">{_recent_table(recent)}</div>
    </section>

    <section id="pulses">
      <div class="section-head">
        <h2>{h(year) if year else "Current"} first-of-season pulses</h2>
        <p>Species appearing at two or more stations are grouped by how tightly their first session dates line up. Switch to all-time to compare first arrivals across the full station history.</p>
      </div>
      <div class="pulse-grid">{_pulse_cards(pulses)}</div>
      {_view_toggle("First arrival view", ("pulse-year", f"{year} season" if year else "Current season"), ("pulse-all-time", "All time"))}
      <div class="view-panel" id="pulse-year"><div class="table-wrap">{_pulse_table(pulses, stations)}</div></div>
      <div class="view-panel" id="pulse-all-time" hidden><div class="table-wrap">{_pulse_table(all_time_pulses, stations)}</div></div>
    </section>

    <section id="records">
      <div class="section-head">
        <h2>Recent firsts</h2>
        <p>The newest county, state, and tracked-network firsts, ordered by observation date. Filter by type or location to see everything that matches, not just the newest batch.</p>
      </div>
      {_record_filters(stations)}
      <div class="record-grid" data-record-grid>{_record_cards(records)}</div>
      <div class="record-grid-controls" data-record-grid-controls hidden>
        <span data-record-grid-count aria-live="polite"></span>
        <button type="button" data-record-grid-expand data-page-size="{RECORD_CARD_PREVIEW_LIMIT}">Show all matching photos</button>
      </div>
      <details class="record-archive">
        <summary>Browse all flagged firsts ({h(len(records))})</summary>
        <div class="table-wrap">{_record_table(records)}</div>
      </details>
    </section>

    <section id="unique">
      <div class="section-head">
        <h2>Moths unique to one station</h2>
        <p>These species currently appear at only one tracked station, which can reflect habitat, effort, observer focus, or upload timing.</p>
      </div>
      {_unique_station_sections(uniques, stations)}
    </section>

    <section id="calendar">
      <div class="section-head">
        <h2>Daily species calendar</h2>
        <p>Station cells show unique moth species per station per night. The total column is the unique species union across stations, not a sum of site counts.</p>
      </div>
      {_view_toggle("Calendar view", ("calendar-year", f"{year} dates" if year else "Current dates"), ("calendar-all-years", "All years"))}
      <div class="view-panel" id="calendar-year">
        <div class="calendar-line-head"><h3>Daily richness by contribution</h3><p>Each bar totals the network species union. Color shows species only found at one station; gray shows species shared by multiple stations.</p></div>
        {_daily_species_line_chart(year_calendar, stations, "year")}
        <div class="table-wrap">{_calendar_table(year_calendar, stations, "year")}</div>
      </div>
      <div class="view-panel" id="calendar-all-years" hidden>
        <div class="calendar-line-head"><h3>Daily richness by contribution</h3><p>Same calendar dates are combined across synced years. Each bar totals the network species union, split into station-only and shared species.</p></div>
        {_daily_species_line_chart(all_time_calendar, stations, "all")}
        <div class="table-wrap">{_calendar_table(all_time_calendar, stations, "all")}</div>
      </div>
    </section>

    <section id="trends">
      <div class="section-head">
        <h2>Trend views</h2>
        <p>Build-time visual summaries for flight timing, network growth, abundance structure, and shared fauna.</p>
      </div>
      {_trend_section(trends, stations)}
    </section>

    <section id="species">
      <div class="section-head">
        <h2>Station species comparison</h2>
        <p>Each cell shows the observation count, first session date, and any county, state, or tracked-station first flags. Default sort favors species found across the most stations.</p>
      </div>
      {_view_toggle("Species comparison view", ("species-all-time", "All time"), ("species-year", f"{year} only" if year else "Current year"), ("species-past-week", "Past week"), ("species-last-night", "Last night"))}
      <div class="view-panel" id="species-all-time"><div class="table-wrap">{_comparison_table(taxa, stations)}</div></div>
      <div class="view-panel" id="species-year" hidden><div class="table-wrap">{_comparison_table(year_taxa, stations)}</div></div>
      <div class="view-panel" id="species-past-week" hidden><div class="table-wrap">{_comparison_table(recent_week_taxa, stations)}</div></div>
      <div class="view-panel" id="species-last-night" hidden><div class="table-wrap">{_comparison_table(latest_night_taxa, stations)}</div></div>
    </section>
  </main>
  <footer><div>Generated {h(generated_at())}. First-of-season dates use moth session dates, with records before noon assigned to the previous evening.</div></footer>
  <script>{DASHBOARD_JS}</script>
</body>
</html>
"""
    output.write_text(html, encoding="utf-8")
    (settings.public_dir / "insights.json").write_text(
        json.dumps(insights, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (settings.public_dir / "trends.json").write_text(
        json.dumps(trends, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    snapshot = _snapshot_payload(settings, stations, taxa)
    (settings.public_dir / "live-snapshot.json").write_text(
        json.dumps(snapshot, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (settings.public_dir / "live.html").write_text(
        _live_page(snapshot),
        encoding="utf-8",
    )
    stations_dir = settings.public_dir / "stations"
    stations_dir.mkdir(parents=True, exist_ok=True)
    station_colors = _station_color_map(stations)
    for station in stations:
        if not station.enabled:
            continue
        profile = station_profile(settings, station.id)
        recap = weekly_recap(settings, station.id)
        habitat = habitat_summary(settings, station.id, taxa)
        color = station_colors.get(station.id, station.color or FALLBACK_COLORS[0])
        (stations_dir / f"{station.id}.html").write_text(
            _station_profile_page(
                station,
                profile,
                recap,
                habitat,
                color,
            ),
            encoding="utf-8",
        )
        (stations_dir / f"{station.id}-habitat.html").write_text(
            _station_habitat_page(station, habitat, color),
            encoding="utf-8",
        )
    if settings.custom_domain:
        (settings.public_dir / "CNAME").write_text(
            f"{settings.custom_domain.strip()}\n",
            encoding="utf-8",
        )
    return output

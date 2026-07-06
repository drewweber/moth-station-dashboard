"""Static HTML renderer."""

from __future__ import annotations

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
    hero_photos,
    latest_session_taxa,
    record_highlights,
    recent_observations,
    station_profile,
    station_summaries,
    station_taxa,
    trend_summary,
    unique_station_taxa,
)
from .config import Settings, Station
from .db import init_db


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
        "kingfisher": "KH",
        "bosque-neimi": "Bosque",
        "dombroskie-homestead": "Dombroskie",
        "zeledonia-monkey-run": "Monkey Run",
        "iandavies-dove-dr": "Dove Dr",
        "durfee-hill": "Durfee",
        "tompkins-map-area": "Map Area",
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
            _metric("unique taxa", f"{len(taxa):,}"),
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
              <span>{h(station)}</span>
            </a>
            """
        )
        if len(photos) >= 8:
            break
    if not photos:
        return '<div class="photo-empty">Photos will appear here after the next sync.</div>'
    return "".join(photos)


def _station_cards(summaries: list[dict[str, Any]], stations: list[Station]) -> str:
    enabled = [station for station in stations if station.enabled]
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
        status = "active" if item else "queued"
        cards.append(
            f"""
            <article class="station-card" style="--station-color: {_station_color(station, index)}">
              <div>
                <p class="station-status">{h(status)}</p>
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
        cards.append(
            f"""
            <article class="insight-card">
              <div class="insight-index">{index:02d}</div>
              <p>{h(insight["category"])}</p>
              <h3>{h(insight["title"])}</h3>
              <span>{h(insight["body"])}</span>
              <small>{h(insight.get("meta"))}</small>
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


def _last_night_dashboard(payload: dict[str, Any], stations: list[Station]) -> str:
    session_date = payload.get("session_date")
    taxa = payload.get("taxa") or []
    if not session_date or not taxa:
        return '<p class="empty">No latest-session moth observations are available yet.</p>'

    colors = _station_color_map(stations)
    station_lookup = {station.id: station for station in stations if station.enabled}
    station_counts = payload.get("station_counts") or {}
    active_station_ids = [
        station.id for station in stations
        if station.enabled and station_counts.get(station.id, 0)
    ]
    shared_taxa = sum(1 for row in taxa if row.get("station_count", 0) > 1)
    station_chips = []
    for station_id in active_station_ids:
        station = station_lookup[station_id]
        station_chips.append(
            f"""
            <span class="night-station-chip" style="--station-color: {h(colors[station_id])}">
              {h(_station_short_label(station))}
              <strong>{h(station_counts.get(station_id, 0))}</strong>
            </span>
            """
        )

    cards = []
    for row in taxa[:36]:
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
        cards.append(
            f"""
            <article class="night-card">
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
        <strong>{h(session_date)}</strong>
        <span>latest moth session</span>
      </div>
      <div>
        <strong>{h(len(taxa))}</strong>
        <span>unique moth taxa</span>
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
    <div class="night-stations" aria-label="Latest session species count by station">{''.join(station_chips)}</div>
    <div class="night-grid">{''.join(cards)}</div>
    """


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


def _record_cards(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">No county, state, or tracked-station firsts are cached yet. Run a sync to refresh record context.</p>'
    cards = []
    for row in rows[:12]:
        cards.append(
            f"""
            <article class="record-card">
              <div>{_flag_list(row["flags"])}</div>
              <h3>{h(row["label"])}</h3>
              <p>{h(row["station_name"])} · {h(row["first"])}</p>
            </article>
            """
        )
    return "".join(cards)


def _record_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">No first-record highlights are available yet.</p>'
    body = []
    for row in rows[:120]:
        body.append(
            f"""
            <tr>
              <td>{h(row["label"])}</td>
              <td>{h(row["station_name"])}</td>
              <td>{h(row["first"])}</td>
              <td>{_flag_list(row["flags"])}</td>
            </tr>
            """
        )
    return f"""
    <table class="sortable-table">
      <thead>
        <tr>
          <th scope="col">{_sort_button("Species")}</th>
          <th scope="col">{_sort_button("Station")}</th>
          <th scope="col">{_sort_button("Station first", "date")}</th>
          <th scope="col">{_sort_button("Flags")}</th>
        </tr>
      </thead>
      <tbody>{''.join(body)}</tbody>
    </table>
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
          <th scope="col">{_sort_button(label, "text")}</th>
          <th scope="col">{_sort_button("Active stations", "number", "desc")}</th>
          <th scope="col">{_sort_button("Unique spp.", "number")}</th>
          {headers}
        </tr>
      </thead>
      <tbody>{''.join(body)}</tbody>
    </table>
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


def _profile_context(station: Station) -> str:
    items = [
        ("Habitat", station.habitat),
        ("Light setup", station.light_setup),
        ("Station history", station.station_history),
    ]
    rows = []
    for label, value in items:
        rows.append(
            f"""
            <article class="profile-context-item">
              <p>{h(label)}</p>
              <span>{h(value) if value else "Not documented yet."}</span>
            </article>
            """
        )
    return "".join(rows)


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
              <strong>{h(row["species"])}</strong>
            </div>
            """
        )
    return "".join(bars)


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
        markers.append(
            f"""
            <circle cx="{x:.1f}" cy="{y:.1f}" r="3.2">
              <title>{h(row["date"])} · {h(row["species"])} species</title>
            </circle>
            """
        )
    latest = rows[-1]
    return f"""
    <figure class="accumulation-line-chart">
      <svg viewBox="0 0 {width} {height}" role="img" aria-labelledby="accumulation-title accumulation-desc" preserveAspectRatio="none">
        <title id="accumulation-title">Station species accumulation curve</title>
        <desc id="accumulation-desc">Running moth species count from {h(min_date)} to {h(max_date)}, ending at {h(latest["species"])} species.</desc>
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
              <small>{h(row["observations"])} obs</small>
            </div>
            """
        )
    return f'<div class="profile-week-grid">{"".join(cells)}</div>'


def _expected_next_list(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">No next-flight suggestions are available from the current station history.</p>'
    items = []
    for row in rows:
        status = "already seen this year" if row["seen_this_year"] else "not yet seen this year"
        items.append(
            f"""
            <li>
              <span>{h(row["label"])}</span>
              <small>{h(row["window"])} · {h(row["records"])} historical record{'s' if row["records"] != 1 else ''} · {h(status)}</small>
            </li>
            """
        )
    return f'<ul class="profile-species-list profile-watch-list">{"".join(items)}</ul>'


def _profile_species_list(rows: list[dict[str, Any]], empty: str) -> str:
    if not rows:
        return f'<p class="empty">{h(empty)}</p>'
    items = []
    for row in rows:
        detail = []
        if "count" in row:
            detail.append(f"{row['count']} obs")
        if "share" in row:
            detail.append(f"{row['share']:.0%} of network records")
        elif row.get("latest"):
            detail.append(f"latest {row['latest']}")
        items.append(
            f"""
            <li>
              <span>{h(row["label"])}</span>
              <small>{h(" · ".join(detail))}</small>
            </li>
            """
        )
    return f'<ul class="profile-species-list">{"".join(items)}</ul>'


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


def _network_accumulation(rows: list[dict[str, Any]]) -> str:
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
        markers.append(
            f"""
            <circle cx="{x:.1f}" cy="{y:.1f}" r="3.1">
              <title>{h(row_date)} · {h(row["species"])} species · +{h(row["new_species"])} new</title>
            </circle>
            """
        )
    latest = rows[-1]
    return f"""
    <figure class="accumulation-line-chart network-line-chart">
      <svg viewBox="0 0 {width} {height}" role="img" aria-labelledby="network-accumulation-title network-accumulation-desc" preserveAspectRatio="none">
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
        <polyline class="accumulation-line" points="{point_attr}"></polyline>
        {''.join(markers)}
        <text class="chart-callout" x="{points[-1][0] - 8:.1f}" y="{points[-1][1] - 10:.1f}" text-anchor="end">{h(latest["species"])} species</text>
      </svg>
    </figure>
    """


def _monthly_overlays(rows: list[dict[str, Any]]) -> str:
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
    polylines = []
    markers = []
    labels = []
    for index, row in enumerate(rows[-5:]):
        color = colors[index % len(colors)]
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
            markers.append(
                f"""
                <circle class="monthly-point" style="--series-color: {h(color)}" cx="{x:.1f}" cy="{y:.1f}" r="3">
                  <title>{h(row["year"])} {h(month["label"])} · {h(month["species"])} species</title>
                </circle>
                """
            )
        last_x, last_y, _ = points[-1]
        labels.append(
            f'<text class="monthly-label" style="--series-color: {h(color)}" x="{last_x + 8:.1f}" y="{last_y + 4:.1f}">{h(row["year"])}</text>'
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
      <svg viewBox="0 0 {width} {height}" role="img" aria-labelledby="monthly-overlay-title monthly-overlay-desc" preserveAspectRatio="none">
        <title id="monthly-overlay-title">Monthly species richness by year</title>
        <desc id="monthly-overlay-desc">One line per year showing unique moth taxa by month across the station network.</desc>
        <line class="chart-axis" x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}"></line>
        <line class="chart-axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}"></line>
        <line class="chart-grid" x1="{left}" y1="{top}" x2="{left + plot_width}" y2="{top}"></line>
        <text class="chart-label" x="{left - 8}" y="{top + 4}" text-anchor="end">{h(max_species)}</text>
        <text class="chart-label" x="{left - 8}" y="{top + plot_height + 4}" text-anchor="end">0</text>
        {''.join(month_labels)}
        {''.join(polylines)}
        {''.join(markers)}
        {''.join(labels)}
      </svg>
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
        {_network_accumulation(trends["network_accumulation"])}
      </article>
      <article class="trend-panel">
        <h3>Monthly overlays</h3>
        <p>Unique moth taxa by month, with one line per synced year.</p>
        {_monthly_overlays(trends["monthly_overlays"])}
      </article>
      <article class="trend-panel">
        <h3>Rank abundance</h3>
        <p>Most frequently observed moth taxa in the current network cache.</p>
        {_rank_abundance(trends["rank_abundance"])}
      </article>
      <article class="trend-panel trend-panel-wide">
        <h3>Station similarity</h3>
        <p>Jaccard similarity based on shared moth taxa. Darker cells mean more overlap.</p>
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
    query = station.api_params(settings)
    if any(key in query for key in SENSITIVE_LIVE_QUERY_KEYS):
        return {}, False
    return query, True


def _snapshot_payload(settings: Settings, stations: list[Station], taxa: list[dict[str, Any]]) -> dict[str, Any]:
    known_taxa: dict[str, list[int]] = {}
    for taxon in taxa:
        taxon_id = taxon.get("taxon_id")
        if not taxon_id:
            continue
        for station_id in taxon["stations"]:
            known_taxa.setdefault(station_id, []).append(int(taxon_id))

    enabled = []
    for station in stations:
        if not station.enabled:
            continue
        query, live_supported = _public_live_query(settings, station)
        enabled.append({
            "id": station.id,
            "name": station.name,
            "public_location": station.public_location,
            "query": query,
            "live_supported": live_supported,
            "live_note": "" if live_supported else "Live polling disabled for precise-location queries.",
            "known_taxa": sorted(known_taxa.get(station.id, [])),
        })

    return {
        "generated_at": generated_at(),
        "api_base": "https://api.inaturalist.org/v1",
        "live_mode_hours": 2,
        "scan_minutes": 10,
        "poll_seconds": 60,
        "stations": enabled,
    }


def _station_profile_page(station: Station, profile: dict[str, Any], color: str) -> str:
    location = station.public_location or "Configured station"
    website = (
        f'<a href="{h(station.website)}">iNaturalist source</a>'
        if station.website else ""
    )
    metrics = "".join(
        [
            _profile_metric("moth taxa", f"{profile['species']:,}"),
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
      <a class="brand" href="../index.html"><span class="brand-mark" aria-hidden="true"></span><span>Moth stations</span></a>
      <nav aria-label="Station navigation">
        <a href="../index.html#feed">Feed</a>
        <a href="../index.html#stations">Stations</a>
        <a href="../index.html#calendar">Calendar</a>
        <a href="../live.html">Live</a>
      </nav>
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
      <div class="profile-context">{_profile_context(station)}</div>
    </section>

    <section>
      <div class="section-head">
        <h2>Seasonal richness</h2>
        <p>Unique moth taxa by month, using all synced observations for this station.</p>
      </div>
      <div class="profile-chart">{_seasonal_bars(profile)}</div>
    </section>

    <section>
      <div class="section-head">
        <h2>Phenology calendar</h2>
        <p>Weekly unique moth taxa for this station across all synced years. Darker weeks have richer station activity.</p>
      </div>
      <div class="profile-chart">{_profile_phenology_calendar(profile)}</div>
    </section>

    <section>
      <div class="section-head">
        <h2>Species accumulation</h2>
        <p>Recent milestones in the running species list for this station.</p>
      </div>
      <div class="profile-chart">{_accumulation_bars(profile)}</div>
    </section>

    <section>
      <div class="section-head">
        <h2>Watch next</h2>
        <p>Species historically recorded at this station in the 30 calendar days after the latest synced session.</p>
      </div>
      {_expected_next_list(profile["expected_next"])}
    </section>

    <section>
      <div class="section-head">
        <h2>Signature species</h2>
        <p>Species most associated with this station based on its share of current network observations.</p>
      </div>
      {_profile_species_list(profile["signature_species"], "Signature species will appear after synced observations.")}
    </section>

    <section>
      <div class="section-head">
        <h2>Frequently unique here</h2>
        <p>Species currently recorded at this station and no other tracked station.</p>
      </div>
      {_profile_species_list(profile["unique_species"], "No station-unique species are available yet.")}
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

initSortableTables();
initViewToggles();
initUniqueFilter();
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

function fmtTime(ms) {
  if (ms <= 0) return "off";
  const total = Math.ceil(ms / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}

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
  const remaining = liveUntil() - Date.now();
  els.toggle.checked = remaining > 0;
  els.remaining.textContent = remaining > 0 ? fmtTime(remaining) : "off";
}

function stationKnownSet(station) {
  if (!state.known.has(station.id)) {
    state.known.set(station.id, new Set(station.known_taxa || []));
  }
  return state.known.get(station.id);
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

function sessionDate(date) {
  const session = new Date(date);
  if (session.getHours() < 12) session.setDate(session.getDate() - 1);
  const year = session.getFullYear();
  const month = String(session.getMonth() + 1).padStart(2, "0");
  const day = String(session.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function initStationSummaries() {
  state.stationSummaries.clear();
  for (const station of state.snapshot.stations) {
    state.stationSummaries.set(station.id, {
      station,
      active: false,
      checked: false,
      observationCount: 0,
      newSpeciesCount: 0,
      latestDetectedAt: "",
      latestObservedOn: "",
      photos: [],
      currentSpecies: new Map(),
      newSpecies: new Map(),
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

function updateStationSummary(station, observations, now) {
  const summary = state.stationSummaries.get(station.id);
  if (!summary) return { newSpecies: 0, currentObs: 0 };

  summary.checked = true;
  summary.error = "";
  const currentSession = sessionDate(now);
  let newSpecies = 0;
  let currentObs = 0;
  const known = stationKnownSet(station);

  for (const obs of observations) {
    if (obs.observed_on && obs.observed_on !== currentSession) continue;
    const taxon = obs.taxon || {};
    const taxonId = taxon.id;
    if (!taxonId) continue;
    const observationKey = `${station.id}:${obs.id || `${taxonId}:${obs.observed_on || ""}`}`;
    if (state.seenObservations.has(observationKey)) continue;
    state.seenObservations.add(observationKey);

    currentObs += 1;
    summary.active = true;
    summary.observationCount += 1;
    summary.latestDetectedAt = fmtMinuteStamp(now);
    summary.latestObservedOn = obs.observed_on || summary.latestObservedOn;

    const item = {
      taxonId,
      label: observationLabel(obs),
      url: obs.uri || `https://www.inaturalist.org/observations/${obs.id}`,
      photo: obsPhoto(obs),
      count: 1,
    };
    addSpecies(summary.currentSpecies, item);
    if (item.photo && !summary.photos.some((photo) => photo.url === item.photo)) {
      summary.photos.unshift({ url: item.photo, label: item.label, href: item.url });
      summary.photos = summary.photos.slice(0, 6);
    }

    if (known.has(taxonId)) continue;
    const key = `${station.id}:${taxonId}`;
    if (state.seenThisSession.has(key)) continue;
    state.seenThisSession.add(key);
    known.add(taxonId);
    newSpecies += 1;
    summary.newSpeciesCount += 1;
    addSpecies(summary.newSpecies, item);
  }

  return { newSpecies, currentObs };
}

function renderSpeciesList(species, emptyText) {
  const items = Array.from(species.values())
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
    .slice(0, 8);
  if (!items.length) return `<p class="live-muted">${escapeHtml(emptyText)}</p>`;
  return `<ul>${items.map((item) => `
    <li>
      <a href="${escapeHtml(item.url)}">${escapeHtml(item.label)}</a>
      <span>${item.count > 1 ? `${item.count} obs` : "1 obs"}</span>
    </li>
  `).join("")}</ul>`;
}

function renderStationSummaries() {
  const allSummaries = Array.from(state.stationSummaries.values());
  const summaries = allSummaries.filter((summary) => summary.active).sort((a, b) => {
    if (a.active !== b.active) return a.active ? -1 : 1;
    if (a.newSpeciesCount !== b.newSpeciesCount) return b.newSpeciesCount - a.newSpeciesCount;
    if (a.observationCount !== b.observationCount) return b.observationCount - a.observationCount;
    return a.station.name.localeCompare(b.station.name);
  });
  const activeCount = summaries.length;
  const supportedCount = allSummaries.filter((summary) => summary.station.live_supported).length;
  els.stationCount.textContent = `${activeCount} / ${supportedCount}`;

  if (!summaries.length) {
    const hasChecked = allSummaries.some((summary) => summary.checked);
    els.log.innerHTML = `
      <p class="empty">${hasChecked
        ? "No stations have current-night uploads yet. The next live check will add station cards as activity appears."
        : "No active stations yet. Toggle live mode to start a 10-minute scan."}</p>
    `;
    return;
  }

  els.log.innerHTML = summaries.map((summary) => {
    const station = summary.station;
    const status = "active tonight";
    const photos = summary.photos.length
      ? summary.photos.map((photo) => `
          <a href="${escapeHtml(photo.href)}" class="live-thumb">
            <img src="${escapeHtml(photo.url)}" alt="${escapeHtml(photo.label)}" loading="lazy">
          </a>
        `).join("")
      : `<div class="live-photo-empty">No current-night photos yet</div>`;
    const classes = [
      "live-station-card",
      "is-active",
    ].filter(Boolean).join(" ");

    return `
      <article class="${classes}">
        <div class="live-station-head">
          <div>
            <p>${escapeHtml(station.public_location || "tracked station")}</p>
            <h2>${escapeHtml(station.name)}</h2>
          </div>
          <span>${escapeHtml(status)}</span>
        </div>
        <div class="live-stats">
          <div><strong>${summary.observationCount}</strong><span>current-night uploads</span></div>
          <div><strong>${summary.newSpeciesCount}</strong><span>new station species</span></div>
          <div><strong>${escapeHtml(summary.latestDetectedAt || "not yet")}</strong><span>latest added</span></div>
        </div>
        <div class="live-photo-strip">${photos}</div>
        <div class="live-station-lists">
          <div>
            <h3>New since build</h3>
            ${renderSpeciesList(summary.newSpecies, station.live_supported ? "No new station species yet." : station.live_note)}
          </div>
          <div>
            <h3>Seen tonight</h3>
            ${renderSpeciesList(summary.currentSpecies, summary.checked ? "No current-night uploads in this scan." : "Waiting for the first check.")}
          </div>
        </div>
      </article>
    `;
  }).join("");
}

async function fetchStation(station, createdAfter) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(station.query || {})) {
    if (value === null || value === undefined || value === "") continue;
    params.set(key, String(value));
  }
  params.set("created_d1", createdAfter);
  params.set("order_by", "created_at");
  params.set("order", "desc");
  params.set("per_page", "50");
  const url = `${state.snapshot.api_base}/observations?${params.toString()}`;
  const response = await fetch(url, { headers: { accept: "application/json" } });
  if (!response.ok) throw new Error(`${station.name}: iNaturalist returned ${response.status}`);
  return response.json();
}

async function runCheck() {
  if (!liveIsOn()) {
    stopScan("Live mode expired.");
    return;
  }
  const now = new Date();
  const createdAfter = new Date(Date.now() - state.snapshot.live_mode_hours * 60 * 60 * 1000).toISOString();
  setStatus(`Checking iNaturalist at ${now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`);
  let found = 0;
  let activeUploads = 0;
  for (const station of state.snapshot.stations) {
    if (!station.live_supported) continue;
    const data = await fetchStation(station, createdAfter);
    const result = updateStationSummary(station, data.results || [], now);
    found += result.newSpecies;
    activeUploads += result.currentObs;
  }
  els.lastCheck.textContent = now.toLocaleString();
  renderStationSummaries();
  const activeStations = Array.from(state.stationSummaries.values()).filter((summary) => summary.active).length;
  setStatus(found
    ? `Found ${found} new station species across active stations.`
    : activeUploads
      ? `Found ${activeUploads} current-night uploads; no new station species in this check.`
      : activeStations
        ? "No additional current-night uploads since the previous check."
        : "No current-night station uploads found in this check.");
}

function stopScan(message) {
  if (state.timer) window.clearInterval(state.timer);
  state.timer = null;
  state.stopAt = 0;
  if (message) setStatus(message);
}

async function startScan() {
  if (!state.snapshot) return;
  stopScan();
  state.stopAt = Date.now() + state.snapshot.scan_minutes * 60 * 1000;
  setStatus("Live scan started.");
  try {
    await runCheck();
  } catch (error) {
    setStatus(error.message || "Live check failed.");
  }
  state.timer = window.setInterval(async () => {
    if (Date.now() >= state.stopAt) {
      stopScan("10-minute scan complete. Toggle live mode again to start another scan.");
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
  const response = await fetch("live-snapshot.json", { cache: "no-store" });
  if (!response.ok) throw new Error("Could not load live snapshot.");
  state.snapshot = await response.json();
  els.snapshotTime.textContent = state.snapshot.generated_at;
  initStationSummaries();
  renderStationSummaries();
}

async function init() {
  els.toggle = document.querySelector("#live-toggle");
  els.status = document.querySelector("#live-status");
  els.remaining = document.querySelector("#live-remaining");
  els.lastCheck = document.querySelector("#last-check");
  els.snapshotTime = document.querySelector("#snapshot-time");
  els.stationCount = document.querySelector("#station-count");
  els.log = document.querySelector("#live-log");

  await loadSnapshot();
  updateToggleState();
  window.setInterval(updateToggleState, 30000);

  els.toggle.addEventListener("change", async () => {
    if (els.toggle.checked) {
      const until = Date.now() + state.snapshot.live_mode_hours * 60 * 60 * 1000;
      localStorage.setItem(LIVE_KEY, String(until));
      updateToggleState();
      await startScan();
    } else {
      localStorage.removeItem(LIVE_KEY);
      updateToggleState();
      stopScan("Live mode off.");
    }
  });

  if (liveIsOn()) {
    await startScan();
  } else {
    setStatus("Live mode is off.");
  }
}

init().catch((error) => {
  setStatus(error.message || "Live page could not start.");
});
"""


def _live_page() -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Live station summary · Moth Station Dashboard</title>
  <meta name="description" content="Run a short live check for current-night iNaturalist activity at tracked moth stations.">
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
  .live-meta {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 1px;
    margin-top: 18px;
    background: var(--line);
    border: 1px solid var(--line);
  }}
  .live-meta div {{
    padding: 12px;
    background: var(--panel-2);
  }}
  .live-meta strong {{
    display: block;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-variant-numeric: tabular-nums;
  }}
  .live-meta span {{
    color: var(--muted);
    font-size: 0.82rem;
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
  .live-station-lists li a {{
    min-width: 0;
    overflow-wrap: anywhere;
  }}
  .live-station-lists li span,
  .live-muted {{
    color: var(--muted);
    font-size: 0.78rem;
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
<body>
  <a class="skip-link" href="#live-main">Skip to live log</a>
  <header>
    <div class="topbar">
      <a class="brand" href="index.html"><span class="brand-mark" aria-hidden="true"></span><span>Moth stations</span></a>
      <nav aria-label="Live page navigation">
        <a href="index.html">Dashboard</a>
        <a href="#live-log">Log</a>
      </nav>
    </div>
  </header>
  <main id="live-main" class="live-shell">
    <p class="eyebrow">10-minute iNaturalist check</p>
    <h1>Live station summary.</h1>
    <p class="subhead">Turn on live mode to check recent iNaturalist uploads and feature stations with observations from the current moth night. Live mode stays available in this browser for 2 hours.</p>

    <section class="live-panel" aria-labelledby="live-controls">
      <div class="toggle-row">
        <div>
          <h2 id="live-controls">Live mode</h2>
          <p id="live-status">Preparing live check.</p>
        </div>
        <label class="switch">
          <input id="live-toggle" type="checkbox">
          <span>Run live checks</span>
        </label>
      </div>
      <div class="live-meta">
        <div><strong id="live-remaining">off</strong><span>live mode remaining</span></div>
        <div><strong>10 min</strong><span>scan duration</span></div>
        <div><strong id="station-count">0 / 0</strong><span>active / checkable stations</span></div>
        <div><strong id="last-check">not yet</strong><span>last check</span></div>
        <div><strong id="snapshot-time">loading</strong><span>snapshot generated</span></div>
      </div>
    </section>

    <section aria-labelledby="live-log-title">
      <div class="section-head">
        <h2 id="live-log-title">Live station summary</h2>
        <p>Active stations rise to the top when current-night uploads appear. New station species are still flagged, but the main view is organized around each station's night.</p>
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
nav {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 14px;
}
nav a {
  color: var(--muted);
  text-decoration: none;
  font-size: 0.9rem;
}
.hero {
  width: min(var(--max), calc(100% - 32px));
  margin: 0 auto;
  padding: 48px 0 34px;
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
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 1px;
  margin-top: 30px;
  border: 1px solid var(--line);
  background: var(--line);
}
.profile-metric {
  min-height: 92px;
  padding: 12px;
  background: var(--panel);
}
.profile-metric strong {
  display: block;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: clamp(1.02rem, 1.8vw, 1.5rem);
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}
.profile-metric span {
  color: var(--muted);
  font-size: 0.82rem;
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
.subhead {
  max-width: 660px;
  color: var(--muted);
  margin: 18px 0 0;
  font-size: clamp(1rem, 2vw, 1.2rem);
  text-wrap: pretty;
}
.hero-metrics {
  grid-column: 1;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 1px;
  border: 1px solid var(--line);
  background: var(--line);
}
.hero-metric {
  min-height: 92px;
  padding: 12px;
  background: var(--panel);
}
.hero-metric strong {
  display: block;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: clamp(1.18rem, 2.2vw, 1.7rem);
  color: var(--ink);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.hero-metric-compact strong {
  font-size: clamp(0.95rem, 1.45vw, 1.18rem);
}
.hero-metric span {
  color: var(--muted);
  font-size: 0.82rem;
}
.photo-rail {
  grid-column: 2;
  grid-row: 1 / span 2;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.photo-tile {
  position: relative;
  display: block;
  min-height: 132px;
  overflow: hidden;
  background: #322f21;
  color: var(--ink);
  text-decoration: none;
}
.photo-tile:nth-child(1),
.photo-tile:nth-child(6) {
  grid-column: span 2;
}
.photo-tile img {
  width: 100%;
  height: 100%;
  min-height: 132px;
  object-fit: cover;
  filter: saturate(0.95) contrast(1.08) brightness(1.08);
  opacity: 0.96;
  transition: transform 180ms ease-out, opacity 180ms ease-out;
}
.photo-tile:hover img {
  transform: scale(1.025);
  opacity: 1;
}
.photo-tile span {
  position: absolute;
  left: 8px;
  bottom: 8px;
  max-width: calc(100% - 16px);
  padding: 3px 7px;
  background: rgba(21, 22, 17, 0.82);
  color: var(--ink);
  font-size: 0.72rem;
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
.profile-context {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.profile-context-item {
  min-height: 150px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
}
.profile-context-item p {
  margin: 0 0 12px;
  color: var(--amber);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.78rem;
}
.profile-context-item span {
  color: var(--muted);
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
.accumulation-line-chart {
  margin: 0;
}
.accumulation-line-chart svg {
  width: 100%;
  height: clamp(230px, 32vw, 340px);
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
.accumulation-line-chart circle {
  fill: var(--panel);
  stroke: var(--amber);
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}
.chart-label,
.chart-callout {
  fill: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.78rem;
}
.chart-callout {
  fill: var(--ink);
  font-weight: 650;
}
.profile-species-list {
  list-style: none;
  margin: 0;
  padding: 0;
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
.profile-watch-list li {
  min-height: 92px;
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
.network-line-chart circle {
  stroke: var(--leaf);
}
.monthly-overlay-chart {
  margin: 0;
}
.monthly-overlay-chart svg {
  width: 100%;
  height: clamp(230px, 32vw, 340px);
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
.monthly-label {
  fill: var(--series-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.78rem;
  font-weight: 650;
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
  gap: 10px;
}
.insight-card {
  min-height: 220px;
  grid-column: span 4;
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: linear-gradient(135deg, rgba(215, 181, 109, 0.08), rgba(255, 255, 255, 0.015) 46%), var(--panel);
}
.insight-card:nth-child(1),
.insight-card:nth-child(2) {
  grid-column: span 6;
}
.insight-card p,
.insight-card small {
  margin: 0;
  color: var(--amber);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.76rem;
}
.insight-card h3 {
  margin: 22px 0 14px;
  font-family: Georgia, "Times New Roman", serif;
  font-size: clamp(1.2rem, 2vw, 1.75rem);
  font-weight: 500;
  line-height: 1.05;
  text-wrap: balance;
}
.insight-card span {
  display: block;
  color: var(--muted);
  font-size: 0.93rem;
  text-wrap: pretty;
}
.insight-card small {
  color: var(--faint);
  padding-top: 20px;
}
.insight-index {
  position: absolute;
  top: 12px;
  right: 14px;
  color: rgba(243, 234, 215, 0.24);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 1.2rem;
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
}
.night-station-chip strong {
  color: var(--ink);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
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
  min-height: 150px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 16px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 6px;
}
.record-card h3 {
  margin: 14px 0;
  font-size: 1.08rem;
  line-height: 1.2;
}
.record-card p {
  margin: 0;
  color: var(--muted);
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
  .hero-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .profile-metrics,
  .profile-context {
    grid-template-columns: 1fr;
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
    --topbar-height: 128px;
  }
  .topbar {
    align-items: flex-start;
    flex-direction: column;
    justify-content: center;
    padding: 14px 16px;
  }
  nav {
    justify-content: flex-start;
  }
  h1 {
    font-size: clamp(3rem, 17vw, 5rem);
  }
  .hero-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .insight-grid {
    grid-template-columns: 1fr;
  }
  .photo-rail {
    grid-template-columns: repeat(2, 1fr);
  }
  .photo-tile:nth-child(1),
  .photo-tile:nth-child(6) {
    grid-column: span 1;
  }
  .sighting-card {
    grid-template-columns: 92px minmax(0, 1fr);
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
}
"""


def render(settings: Settings, stations: list[Station], output: Path | None = None) -> Path:
    init_db(settings.database)
    output = output or settings.public_dir / "index.html"
    settings.public_dir.mkdir(parents=True, exist_ok=True)

    summaries = station_summaries(settings)
    recent = recent_observations(settings)
    hero_photo_rows = hero_photos(settings)
    year = active_year(settings)
    pulses = first_of_season(settings, year)
    all_time_pulses = first_of_season(settings, all_time=True)
    latest_night = latest_session_taxa(settings)
    taxa = station_taxa(settings)
    year_taxa = station_taxa(settings, year) if year else []
    latest_night_taxa = latest_night.get("taxa") or []
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
      <a class="brand" href="#main"><span class="brand-mark" aria-hidden="true"></span><span>Moth stations</span></a>
      <nav aria-label="Dashboard sections">
        <a href="#stations">Stations</a>
        <a href="#feed">Feed</a>
        <a href="#last-night">Last night</a>
        <a href="#recent">Recent</a>
        <a href="#pulses">Firsts</a>
        <a href="#records">Records</a>
        <a href="#unique">Unique</a>
        <a href="#calendar">Calendar</a>
        <a href="#trends">Trends</a>
        <a href="#species">Species</a>
        <a href="live.html">Live</a>
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
    <section id="feed">
      <div class="section-head">
        <h2>Naturalist feed</h2>
        <p>Build-generated headlines from the station network, meant to surface discoveries, timing shifts, and shared flight pulses before the tables.</p>
      </div>
      <div class="insight-grid">{_insight_cards(insights)}</div>
    </section>

    <section id="stations">
      <div class="section-head">
        <h2>Station signals</h2>
        <p>Configured stations stay visible even before their first sync, so owners can see what is online and what is waiting for observations.</p>
      </div>
      <div class="cards">{_station_cards(summaries, stations)}</div>
    </section>

    <section id="last-night">
      <div class="section-head">
        <h2>Last night</h2>
        <p>A photo-first scan of the latest synced moth session, grouped by unique taxa so shared and station-only sightings are easy to compare.</p>
      </div>
      {_last_night_dashboard(latest_night, stations)}
    </section>

    <section id="recent">
      <div class="section-head">
        <h2>Recent sightings</h2>
        <p>Fresh uploads are shown as a field log first, with the full table kept below for scanning dates, observers, and links.</p>
      </div>
      <div class="sighting-grid">{_recent_cards(recent)}</div>
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
        <h2>Record flags</h2>
        <p>County and state labels are iNaturalist firsts. Tracked labels mark the first station in this dashboard to record that moth.</p>
      </div>
      <div class="record-grid">{_record_cards(records)}</div>
      <div class="table-wrap">{_record_table(records)}</div>
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
        <p>Station cells show unique moth taxa per station per night. The total column is the unique species union across stations, not a sum of site counts.</p>
      </div>
      {_view_toggle("Calendar view", ("calendar-year", f"{year} dates" if year else "Current dates"), ("calendar-all-years", "All years"))}
      <div class="view-panel" id="calendar-year"><div class="table-wrap">{_calendar_table(year_calendar, stations, "year")}</div></div>
      <div class="view-panel" id="calendar-all-years" hidden><div class="table-wrap">{_calendar_table(all_time_calendar, stations, "all")}</div></div>
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
      {_view_toggle("Species comparison view", ("species-all-time", "All time"), ("species-year", f"{year} only" if year else "Current year"), ("species-last-night", "Last night"))}
      <div class="view-panel" id="species-all-time"><div class="table-wrap">{_comparison_table(taxa, stations)}</div></div>
      <div class="view-panel" id="species-year" hidden><div class="table-wrap">{_comparison_table(year_taxa, stations)}</div></div>
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
        _live_page(),
        encoding="utf-8",
    )
    stations_dir = settings.public_dir / "stations"
    stations_dir.mkdir(parents=True, exist_ok=True)
    station_colors = _station_color_map(stations)
    for station in stations:
        if not station.enabled:
            continue
        profile = station_profile(settings, station.id)
        (stations_dir / f"{station.id}.html").write_text(
            _station_profile_page(
                station,
                profile,
                station_colors.get(station.id, station.color or FALLBACK_COLORS[0]),
            ),
            encoding="utf-8",
        )
    if settings.custom_domain:
        (settings.public_dir / "CNAME").write_text(
            f"{settings.custom_domain.strip()}\n",
            encoding="utf-8",
        )
    return output

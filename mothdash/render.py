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
    first_of_season,
    generated_at,
    hero_photos,
    record_highlights,
    recent_observations,
    station_summaries,
    station_taxa,
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
                <h3>{h(station.name)}</h3>
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
    for row in rows[:160]:
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
        f'{_sort_button(station.name, "number")}</th>'
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
    <table class="sortable-table calendar-table">
      <thead>
        <tr>
          <th scope="col">{_sort_button(label, "text")}</th>
          <th scope="col">{_sort_button("Active stations", "number", "desc")}</th>
          <th scope="col">{_sort_button("Species total", "number")}</th>
          {headers}
        </tr>
      </thead>
      <tbody>{''.join(body)}</tbody>
    </table>
    """


def _view_toggle(name: str, first_id: str, first_label: str, second_id: str, second_label: str) -> str:
    return f"""
    <div class="view-toggle" role="group" aria-label="{h(name)}">
      <button type="button" class="view-toggle-button is-active" data-view-target="{h(first_id)}">{h(first_label)}</button>
      <button type="button" class="view-toggle-button" data-view-target="{h(second_id)}">{h(second_label)}</button>
    </div>
    """


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
        enabled.append({
            "id": station.id,
            "name": station.name,
            "public_location": station.public_location,
            "query": station.api_params(settings),
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

initSortableTables();
initViewToggles();
"""


LIVE_JS = r"""
const state = {
  snapshot: null,
  timer: null,
  stopAt: 0,
  known: new Map(),
  seenThisSession: new Set(),
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

function addLogItem(item) {
  const empty = els.log.querySelector(".empty");
  if (empty) empty.remove();
  const article = document.createElement("article");
  article.className = "live-item";
  const image = item.photo
    ? `<img src="${item.photo}" alt="${item.label}" loading="lazy">`
    : `<div class="live-placeholder" aria-hidden="true">sheet</div>`;
  article.innerHTML = `
    <div class="live-image">${image}</div>
    <div>
      <p>${item.stationName} · ${item.observedOn || "undated"}</p>
      <h2><a href="${item.url}">${item.label}</a></h2>
      <span>New to this station since the last dashboard build</span>
    </div>
  `;
  els.log.prepend(article);
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
  for (const station of state.snapshot.stations) {
    const known = stationKnownSet(station);
    const data = await fetchStation(station, createdAfter);
    for (const obs of data.results || []) {
      const taxon = obs.taxon || {};
      const taxonId = taxon.id;
      if (!taxonId || known.has(taxonId)) continue;
      const key = `${station.id}:${taxonId}`;
      if (state.seenThisSession.has(key)) continue;
      state.seenThisSession.add(key);
      known.add(taxonId);
      found += 1;
      addLogItem({
        stationName: station.name,
        label: observationLabel(obs),
        observedOn: obs.observed_on,
        url: obs.uri || `https://www.inaturalist.org/observations/${obs.id}`,
        photo: obsPhoto(obs),
      });
    }
  }
  els.lastCheck.textContent = now.toLocaleString();
  setStatus(found ? `Found ${found} new station species.` : "No new station species found in this check.");
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
  els.stationCount.textContent = state.snapshot.stations.length;
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
  <title>Live species log · Moth Station Dashboard</title>
  <meta name="description" content="Run a short live check for moth species newly appearing at tracked iNaturalist stations.">
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
    gap: 10px;
    margin-top: 18px;
  }}
  .live-item {{
    display: grid;
    grid-template-columns: 120px minmax(0, 1fr);
    gap: 14px;
    padding: 12px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 6px;
  }}
  .live-image img, .live-placeholder {{
    width: 120px;
    height: 120px;
    object-fit: cover;
    background: var(--panel-2);
  }}
  .live-placeholder {{
    display: grid;
    place-items: center;
    color: var(--faint);
  }}
  .live-item p, .live-item span {{
    margin: 0;
    color: var(--muted);
  }}
  .live-item h2 {{
    margin: 8px 0;
    font-size: 1.25rem;
  }}
  @media (max-width: 620px) {{
    .live-item {{
      grid-template-columns: 88px minmax(0, 1fr);
    }}
    .live-image img, .live-placeholder {{
      width: 88px;
      height: 88px;
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
    <h1>Live species log.</h1>
    <p class="subhead">Turn on live mode to check recent iNaturalist uploads for moth species not present in the last dashboard build. Live mode stays available in this browser for 2 hours.</p>

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
        <div><strong id="station-count">0</strong><span>stations checked</span></div>
        <div><strong id="last-check">not yet</strong><span>last check</span></div>
        <div><strong id="snapshot-time">loading</strong><span>snapshot generated</span></div>
      </div>
    </section>

    <section aria-labelledby="live-log-title">
      <div class="section-head">
        <h2 id="live-log-title">New species log</h2>
        <p>The page compares recent uploads to the species known at the last static build. Results are provisional until the regular dashboard sync runs.</p>
      </div>
      <div id="live-log" class="live-log">
        <p class="empty">No live results yet. Toggle live mode to start a 10-minute scan.</p>
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
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--ink);
  line-height: 1.5;
}
.skip-link {
  position: absolute;
  left: 16px;
  top: -48px;
  z-index: 10;
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
  width: min(var(--max), calc(100% - 32px));
  margin: 0 auto;
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
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
.calendar-table td,
.calendar-table th {
  text-align: center;
}
.calendar-table td:first-child,
.calendar-table th:first-child {
  text-align: left;
}
.calendar-cell {
  min-width: 92px;
  padding: 7px;
}
.calendar-cell span {
  min-height: 34px;
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
  .section-head {
    display: block;
  }
  .section-head p {
    margin-top: 8px;
  }
}
@media (max-width: 620px) {
  .topbar {
    align-items: flex-start;
    flex-direction: column;
    padding: 16px 0;
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
    taxa = station_taxa(settings)
    year_taxa = station_taxa(settings, year) if year else []
    year_calendar = daily_species_counts(settings, year) if year else []
    all_time_calendar = daily_species_counts(settings)
    records = record_highlights(settings)
    uniques = unique_station_taxa(settings)

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
        <a href="#recent">Recent</a>
        <a href="#pulses">Firsts</a>
        <a href="#records">Records</a>
        <a href="#unique">Unique</a>
        <a href="#calendar">Calendar</a>
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
    <section id="stations">
      <div class="section-head">
        <h2>Station signals</h2>
        <p>Configured stations stay visible even before their first sync, so owners can see what is online and what is waiting for observations.</p>
      </div>
      <div class="cards">{_station_cards(summaries, stations)}</div>
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
      {_view_toggle("First arrival view", "pulse-year", f"{year} season" if year else "Current season", "pulse-all-time", "All time")}
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
      <div class="table-wrap">{_unique_station_table(uniques)}</div>
    </section>

    <section id="calendar">
      <div class="section-head">
        <h2>Daily species calendar</h2>
        <p>Counts are unique moth taxa per station per night. The all-years view compresses the record into month-day rows, which helps common seasonal signals stand out.</p>
      </div>
      {_view_toggle("Calendar view", "calendar-year", f"{year} dates" if year else "Current dates", "calendar-all-years", "All years")}
      <div class="view-panel" id="calendar-year"><div class="table-wrap">{_calendar_table(year_calendar, stations, "year")}</div></div>
      <div class="view-panel" id="calendar-all-years" hidden><div class="table-wrap">{_calendar_table(all_time_calendar, stations, "all")}</div></div>
    </section>

    <section id="species">
      <div class="section-head">
        <h2>Station species comparison</h2>
        <p>Each cell shows the observation count, first session date, and any county, state, or tracked-station first flags. Default sort favors species found across the most stations.</p>
      </div>
      {_view_toggle("Species comparison view", "species-all-time", "All time", "species-year", f"{year} only" if year else "Current year")}
      <div class="view-panel" id="species-all-time"><div class="table-wrap">{_comparison_table(taxa, stations)}</div></div>
      <div class="view-panel" id="species-year" hidden><div class="table-wrap">{_comparison_table(year_taxa, stations)}</div></div>
    </section>
  </main>
  <footer><div>Generated {h(generated_at())}. First-of-season dates use moth session dates, with records before noon assigned to the previous evening.</div></footer>
  <script>{DASHBOARD_JS}</script>
</body>
</html>
"""
    output.write_text(html, encoding="utf-8")
    snapshot = _snapshot_payload(settings, stations, taxa)
    (settings.public_dir / "live-snapshot.json").write_text(
        json.dumps(snapshot, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (settings.public_dir / "live.html").write_text(
        _live_page(),
        encoding="utf-8",
    )
    if settings.custom_domain:
        (settings.public_dir / "CNAME").write_text(
            f"{settings.custom_domain.strip()}\n",
            encoding="utf-8",
        )
    return output

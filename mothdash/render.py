"""Static HTML renderer."""

from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path
from typing import Any

from .analysis import (
    active_year,
    first_of_season,
    generated_at,
    recent_observations,
    station_summaries,
    station_taxa,
)
from .config import Settings, Station
from .db import init_db


def h(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    return escape(str(value))


def _summary_map(summaries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["station_id"]: item for item in summaries}


def _metric(label: str, value: Any) -> str:
    return f"""
    <div class="hero-metric">
      <strong>{h(value)}</strong>
      <span>{h(label)}</span>
    </div>
    """


def _hero_metrics(
    summaries: list[dict[str, Any]],
    taxa: list[dict[str, Any]],
    pulses: list[dict[str, Any]],
    stations: list[Station],
) -> str:
    total_observations = sum(item["observations"] for item in summaries)
    latest_sessions = [item["latest_session"] for item in summaries if item.get("latest_session")]
    latest = max(latest_sessions) if latest_sessions else "waiting"
    return "".join(
        [
            _metric("enabled stations", len([s for s in stations if s.enabled])),
            _metric("moth observations", f"{total_observations:,}"),
            _metric("unique taxa", f"{len(taxa):,}"),
            _metric("shared firsts", f"{len(pulses):,}"),
            _metric("latest session", latest),
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
    for station in enabled:
        item = by_station.get(station.id)
        species = item["species"] if item else 0
        observations = item["observations"] if item else 0
        latest = item["latest_session"] if item else "not synced"
        location = station.public_location or "configured station"
        status = "active" if item else "queued"
        cards.append(
            f"""
            <article class="station-card">
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
    <table>
      <thead>
        <tr>
          <th scope="col">Uploaded</th>
          <th scope="col">Session</th>
          <th scope="col">Station</th>
          <th scope="col">Taxon</th>
          <th scope="col">Observer</th>
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


def _pulse_table(rows: list[dict[str, Any]], stations: list[Station]) -> str:
    if not rows:
        return '<p class="empty">No multi-station first-of-season records yet. Add another station and sync observations to compare seasonal timing.</p>'
    enabled = [station for station in stations if station.enabled]
    headers = "".join(f'<th scope="col">{h(station.name)}</th>' for station in enabled)
    body = []
    for row in rows[:80]:
        station_cells = []
        for station in enabled:
            entry = row["stations"].get(station.id)
            if entry:
                value = h(entry["date"])
                if entry.get("url"):
                    value = f'<a href="{h(entry["url"])}">{value}</a>'
            else:
                value = ""
            station_cells.append(f"<td>{value}</td>")
        body.append(
            f"""
            <tr>
              <td>{h(row["label"])}</td>
              <td>{h(row["station_count"])}</td>
              <td>{h(row["spread_days"])}</td>
              <td><span class="tag">{h(row["pulse"])}</span></td>
              {''.join(station_cells)}
            </tr>
            """
        )
    return f"""
    <table>
      <thead>
        <tr>
          <th scope="col">Species</th>
          <th scope="col">Stations</th>
          <th scope="col">Spread</th>
          <th scope="col">Pulse</th>
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
    headers = "".join(f'<th scope="col">{h(station.name)}</th>' for station in enabled)
    body = []
    for row in rows[:250]:
        cells = []
        for station in enabled:
            entry = row["stations"].get(station.id)
            if entry:
                cells.append(
                    f"<td><strong>{h(entry['count'])}</strong><br>"
                    f"<span>{h(entry['first'])}</span></td>"
                )
            else:
                cells.append("<td></td>")
        body.append(
            f"""
            <tr>
              <td>{h(row["label"])}</td>
              <td>{h(row["station_count"])}</td>
              {''.join(cells)}
            </tr>
            """
        )
    return f"""
    <table>
      <thead>
        <tr>
          <th scope="col">Species</th>
          <th scope="col">Stations</th>
          {headers}
        </tr>
      </thead>
      <tbody>{''.join(body)}</tbody>
    </table>
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
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 16px;
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
.table-wrap {
  overflow-x: auto;
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
  background: #1c1d15;
  color: var(--amber);
  font-weight: 650;
  white-space: nowrap;
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
    year = active_year(settings)
    pulses = first_of_season(settings, year)
    taxa = station_taxa(settings)

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
        <a href="#species">Species</a>
      </nav>
    </div>
    <div class="hero">
      <div class="hero-copy">
        <p class="eyebrow">regional light-sheet telemetry</p>
        <h1>Night flights, compared.</h1>
        <p class="subhead">A working dashboard for seeing which moth stations are active, what just arrived, and whether first-of-season records are breaking across the region on the same nights.</p>
      </div>
      <div class="photo-rail" aria-label="Recent moth photos">{_photo_strip(recent)}</div>
      <div class="hero-metrics">{_hero_metrics(summaries, taxa, pulses, stations)}</div>
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
        <p>Species appearing at two or more stations are grouped by how tightly their first session dates line up.</p>
      </div>
      <div class="pulse-grid">{_pulse_cards(pulses)}</div>
      <div class="table-wrap">{_pulse_table(pulses, stations)}</div>
    </section>

    <section id="species">
      <div class="section-head">
        <h2>All-time station comparison</h2>
        <p>Each cell shows the observation count and first session date for that species at that station.</p>
      </div>
      <div class="table-wrap">{_comparison_table(taxa, stations)}</div>
    </section>
  </main>
  <footer><div>Generated {h(generated_at())}. First-of-season dates use moth session dates, with records before noon assigned to the previous evening.</div></footer>
</body>
</html>
"""
    output.write_text(html, encoding="utf-8")
    if settings.custom_domain:
        (settings.public_dir / "CNAME").write_text(
            f"{settings.custom_domain.strip()}\n",
            encoding="utf-8",
        )
    return output

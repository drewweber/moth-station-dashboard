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


def _station_cards(summaries: list[dict[str, Any]]) -> str:
    if not summaries:
        return '<p class="empty">No station data has been synced yet. Run a sync to populate this dashboard.</p>'
    cards = []
    for item in summaries:
        cards.append(
            f"""
            <article class="station-card">
              <h3>{h(item["station_name"])}</h3>
              <div class="metrics">
                <span><strong>{h(item["species"])}</strong> species</span>
                <span><strong>{h(item["observations"])}</strong> observations</span>
              </div>
              <p>Latest session: {h(item["latest_session"]) or "none yet"}</p>
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
  color-scheme: light;
  --bg: #f5f7f3;
  --ink: #1d241f;
  --muted: #627066;
  --line: #d7ded5;
  --panel: #ffffff;
  --accent: #1d6f72;
  --accent-2: #9b5c1e;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--ink);
  line-height: 1.45;
}
header {
  padding: 28px clamp(18px, 4vw, 48px) 18px;
  border-bottom: 1px solid var(--line);
  background: #ffffff;
}
h1 {
  margin: 0;
  font-size: clamp(2rem, 5vw, 4rem);
  line-height: 1;
  letter-spacing: 0;
}
h1, h2 {
  text-wrap: balance;
}
.subhead {
  max-width: 780px;
  color: var(--muted);
  margin: 12px 0 0;
  font-size: 1rem;
  text-wrap: pretty;
}
main {
  padding: 22px clamp(18px, 4vw, 48px) 48px;
}
section {
  margin-top: 28px;
}
h2 {
  font-size: 1.15rem;
  margin: 0 0 12px;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
.station-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
}
.station-card h3 {
  margin: 0 0 10px;
  font-size: 1rem;
}
.station-card p {
  margin: 10px 0 0;
  color: var(--muted);
}
.metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.metrics span {
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 4px 9px;
  background: #f9faf8;
}
.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}
table {
  width: 100%;
  min-width: 760px;
  border-collapse: collapse;
  font-size: 0.92rem;
  font-variant-numeric: tabular-nums;
}
th, td {
  text-align: left;
  padding: 9px 10px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
th {
  background: #eef3ef;
  color: #334039;
  font-weight: 700;
  white-space: nowrap;
}
td span {
  color: var(--muted);
  font-size: 0.84rem;
}
a {
  color: var(--accent);
  text-decoration-thickness: 1px;
  text-underline-offset: 2px;
}
a:focus-visible {
  outline: 3px solid #73a6a8;
  outline-offset: 2px;
}
.tag {
  display: inline-block;
  color: #ffffff;
  background: var(--accent-2);
  border-radius: 999px;
  padding: 2px 8px;
  white-space: nowrap;
}
.empty {
  color: var(--muted);
  margin: 0;
}
footer {
  color: var(--muted);
  padding: 0 clamp(18px, 4vw, 48px) 32px;
  font-size: 0.9rem;
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
  <meta name="theme-color" content="#f5f7f3">
  <style>{CSS}</style>
</head>
<body>
  <header>
    <h1>Moth Station Dashboard</h1>
    <p class="subhead">Recent moth observations, all-time station lists, and first-of-season timing across participating iNaturalist stations.</p>
  </header>
  <main>
    <section>
      <h2>Stations</h2>
      <div class="cards">{_station_cards(summaries)}</div>
    </section>

    <section>
      <h2>Recent Observations</h2>
      <div class="table-wrap">{_recent_table(recent)}</div>
    </section>

    <section>
      <h2>{h(year) if year else "Current"} First-Of-Season Pulses</h2>
      <div class="table-wrap">{_pulse_table(pulses, stations)}</div>
    </section>

    <section>
      <h2>All-Time Station Comparison</h2>
      <div class="table-wrap">{_comparison_table(taxa, stations)}</div>
    </section>
  </main>
  <footer>Generated {h(generated_at())}. First-of-season dates use moth session dates, with records before noon assigned to the previous evening.</footer>
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

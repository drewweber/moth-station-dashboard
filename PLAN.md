# Moth Station Dashboard Plan

## Product Goal

Build a semi-live dashboard for comparing moth stations across a local region.
The site should answer two questions every evening:

1. What is happening tonight or in the last few days?
2. Are stations picking up the same first-of-season moths on the same nights?

The dashboard should be useful to station owners, naturalists, and identifiers
without overstating iNaturalist records as absolute biological firsts.

## MVP

- Config-driven station list in `stations.toml`.
- iNaturalist moth observation sync into SQLite.
- Static HTML dashboard in `public/index.html`.
- Station summary cards.
- Recent observation table.
- First-of-season matrix for the active year.
- Same-season spread score for species found at multiple stations.
- All-time station comparison table.

## First-Of-Season Analysis

For every station/species/year:

- normalize records before noon to the previous evening's moth session
- find the first session date at each station
- keep species recorded at two or more stations
- calculate spread in days between earliest and latest station first
- flag tight pulses:
  - `0` days: same night
  - `1-2` days: highly synchronized
  - `3-7` days: same flight pulse
  - `8+` days: staggered or detection-biased

This should become one of the main views, not a secondary statistic.

## Later Phases

- County and state iNaturalist firsts per station.
- "First among tracked stations" flag.
- Expert-ID change feed from recent identifications.
- Weather and moon correlation by station night.
- Nightly pulse view: dates with many shared first-of-season records.
- Station-owner pages with query details and contribution notes.
- Cloudflare Pages or GitHub Pages deployment.
- Manual update trigger for evening checks.

## Record Language

Use careful language:

- "iNaturalist county first", not "county first" unless independently checked.
- "Observed first" for phenology.
- "Uploaded recently" for dashboard activity.
- "Under-documented" or "notable" before calling a moth rare.

## Reuse Strategy

The Kingfisher Hollow iNaturalist pipeline is the model, especially its API,
SQLite, and moth-session-date logic. This repo should stay separate at first.
If the shared logic stabilizes, extract a small reusable package later.


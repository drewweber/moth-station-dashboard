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

## Phase 2: Collaborative Observatory

The next phase should evolve the dashboard from an analytical comparison tool
into a collaborative observatory. The guiding philosophy:

> Reward contribution over competition, and discovery over raw numbers.

The site should lead with the answer to: "What's interesting happening across
our stations right now?" Tables remain important, but the homepage should open
with automatically generated insight cards and a Naturalist Feed.

### Phase 2 Goals

1. Community home dashboard
   - Lead with build-generated insight cards.
   - Surface species first recorded tonight, early emergence, expanding species,
     active stations, widely shared species, newly unique species, long flight
     periods, and surprises compared with historical averages.
2. Rich species pages
   - Phenology by station, year-over-year flight curves, arrival history, peak
     timing, relative abundance, timeline, tracked-station map, photo gallery,
     station leaderboard, and dataset-generated facts.
3. Station profiles
   - Habitat, light setup, station history, accumulation curve, seasonal
     richness, phenology calendar, signature species, frequently unique species,
     and station-associated species.
   - First phase: generate one static page per station with optional owner
     context fields, data-derived narrative, seasonal richness, accumulation
     milestones, signature species, station-unique species, and recent
     observations.
   - Second phase: add weekly station phenology calendars and a "watch next"
     list based on the station's historical records in the next 30 calendar
     days.
4. Community achievements
   - Reward discoveries, coverage milestones, family/taxon specialties,
     seasonal coverage, consistent uploads, strong IDs, and excellent photos.
   - Avoid rewarding raw observation count alone.
5. Community progress
   - Shared species progress against expected regional fauna.
   - Family completion bars and missing-species pages.
6. Collection challenges
   - Rotating, data-derived challenges such as Spring Micros, Hawk Moth Season,
     Complete Every Sphinx, Every Month Challenge, Family Completion, and
     Earliest Emergence Watch.
7. Better trend visualization
   - Phenology ribbons, season progression, accumulation curves, multi-year
     overlays, relative abundance curves, flight distributions, rank abundance,
     station similarity, cluster analysis, and shared-fauna networks.
   - First phase: generate static trend views for phenology ribbons, network
     species accumulation, monthly year overlays, rank abundance, and station
     similarity, plus a reusable `trends.json` data product.
8. Automatic story generation
   - Each build should identify ecological stories without manual curation.
   - Stories become homepage cards and feed items.
9. Community reputation
   - Data-quality contribution score based on consistency, completeness,
     photos, confirmations, breadth, family coverage, and missing seasonal
     records.
10. Intelligent recommendations
    - Station pages should answer "What should I be looking for next?" using
      expected-this-week species, likely missing species, nearby recent finds,
      and historical probability.
11. Collection completion
    - Track station, family, and seasonal completion against county, regional,
      and tracked-network fauna.
12. Delight
    - Random Species of the Day, This Day in History, Biggest Movers, hidden
      gems, rarest recent observation, anniversaries, and data-generated
      "Did you know?" facts.

### Technical Direction

Keep the project a statically generated Python application deployed with
GitHub Actions and Cloudflare Pages.

- Compute new insights during `mothdash render`.
- Emit JSON data files alongside prerendered HTML.
- Prefer build-time data products over server-side infrastructure.
- Use lightweight client-side JavaScript only for filtering and interaction.
- Keep pages pre-rendered and fast.

### Naturalist Feed

The signature feature should be a build-generated feed of 10-20 naturalist-style
headlines based on what is genuinely interesting in the data, such as:

- "The geometrids have arrived two weeks early."
- "Monkey Run recorded its first plume moth of the season."
- "Kingfisher Hollow now leads the network in crambid diversity."
- "Five stations all recorded the same species within 48 hours."
- "Only two expected sphinx moths remain unrecorded this summer."

This gives people a reason to check the site regularly even when they were not
out mothing the night before.

### Deferred: Shared Feed Feedback

The current thumbs-up/down controls save ratings in each visitor's browser and
can copy a concise summary for discussion. A future shared-feedback phase can
add a small Cloudflare Worker endpoint and lightweight shared store so multiple
station owners can rate or comment on feed items. Keep the dashboard itself
static; the Worker should accept only bounded feedback payloads, include basic
abuse protection, and expose a private aggregate/export for feed tuning.

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

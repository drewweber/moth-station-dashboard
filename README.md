# Moth Station Dashboard

Compare moth activity across several iNaturalist-based light stations.

The MVP builds a static dashboard from configured station queries:

- all-time moth lists by station
- recent observations across stations
- first-of-season timing across stations
- same-season spread, so synchronized flight pulses surface quickly
- county/state iNaturalist first flags, first-among-tracked flags, and moths
  currently unique to one station
- a `live.html` page where visitors can turn on a 10-minute iNaturalist check
  for species new since the last build

## Setup

This first version uses only the Python standard library. Python 3.11 or newer
is required because station config is read from TOML.

```sh
python3 -m mothdash build
```

That command syncs enabled stations from iNaturalist into `data/mothdash.db` and
writes `public/index.html`.

Useful commands:

```sh
python3 -m mothdash sync       # update SQLite only
python3 -m mothdash render     # rebuild HTML from existing SQLite
python3 -m mothdash build      # sync, then render
python3 -m mothdash sync --full # clear and resync station observations
python3 -m mothdash check      # report stations with data newer than the cache
```

## Hosting

The dashboard is configured for Cloudflare Pages at:

`https://moth-stations.kingfisher-hollow.com`

The GitHub Actions workflow builds the dashboard and deploys `public/` to the
Cloudflare Pages project named `moth-stations`.

Forks run validation only. iNaturalist polling, Cloudflare credentials, and
production deploys are restricted to the canonical
`drewweber/moth-station-dashboard` repository, so contributors do not need to
configure secrets or a Cloudflare Pages project in their forks.

Scheduled builds use a two-stage workflow to stay within the free tiers: a
small cursor check asks iNaturalist whether an active station has new records,
then dispatches the sync/render/deploy workflow only when data changed. A daily
build remains as a backstop for older records newly added to a station query.

After pushing this repo to GitHub:

1. Create a Cloudflare Pages project named `moth-stations`.
2. Add `moth-stations.kingfisher-hollow.com` as a custom domain on that Pages
   project.
3. Add these GitHub Actions repo secrets:
   - `CLOUDFLARE_API_TOKEN`
   - `CLOUDFLARE_ACCOUNT_ID`
4. Run the `Build and deploy dashboard` workflow once from the Actions tab.

If the Cloudflare Pages project uses a different name, update
`.github/workflows/build.yml`.

## Upcoming-Moth Watchlists

Every station profile includes a **Next two weeks** list. It is intentionally
separate from the station's host-plant targets and its own historical
`Watch next` list:

- it excludes moth species already recorded at that station;
- it uses all public iNaturalist moth observations within the station's
  configured 100 km reference radius, not only the tracked stations;
- it counts records occurring on the next 14 recurring calendar days across
  iNaturalist history, then ranks the unrecorded species by local seasonal
  record count.

The initial cache fill is deliberately comprehensive. It stores counts by
calendar day, so later daily builds reuse the overlapping 13 days and fetch
only the newly entering day. This keeps routine GitHub Actions and iNaturalist
API usage within the project's free-tier design constraints.

Each station needs `regional_watch_lat` and `regional_watch_lng` in
`stations.toml`. These are metadata-only reference points; they do not alter
the station's source observation query. Use the project/place centroid or a
known station coordinate, and override `regional_watch_radius_km` only when a
station needs a different regional reference radius.

## Configure Stations

Edit `stations.toml`. A station is any iNaturalist query representing one moth
station. It can be a project, user plus place, user plus radius, or another
stable iNaturalist observation query.

```toml
[[stations]]
id = "kingfisher"
name = "Kingfisher Hollow"
enabled = true
project_id = 249580
county_place_id = 653
state_place_id = 48
timezone = "America/New_York"
public_location = "Tioga County, NY"
```

Set `active = false` on a station to stop pulling new observations for it (for
example, a station that is no longer running) while keeping its historical
data in the dashboard. It still shows up in the all-time location list,
flagged as inactive. This is separate from `enabled`, which fully removes a
station from every part of the dashboard.

The full site is moth-focused for now. The `[settings]` block uses
`taxon_scope = "moths"`, and the loader translates that semantic scope into the
iNaturalist query needed to retrieve moth observations. Keep station entries
focused on the source query, location, and public metadata rather than raw taxon
exclusion parameters. Future scopes, such as host plants, should be added as
named site-level scopes before they are used by stations.

## Current MVP Limits

This is an intentionally small first pass:

- county/state firsts are planned but not implemented yet
- weather correlation is planned but not implemented yet
- incremental sync follows iNaturalist observation IDs, so use `sync --full`
  after major station-query changes
- first-of-season timing is based on observed date, with records before noon
  assigned to the previous evening's moth session
- county/state first-record context is cached and refreshed gradually so
  scheduled builds do not make thousands of iNaturalist API calls at once
- the live page runs in the visitor's browser, keeps live mode on locally for
  two hours, and checks recent iNaturalist uploads for ten minutes after toggle

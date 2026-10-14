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

Python 3.11 or newer is required because station config is read from TOML.
The core renderer uses the standard library. Install the optional image-build
dependency to generate smaller, licensed WebP photo variants:

```sh
python3 -m pip install -r requirements.txt
```

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
python3 -m mothdash sync --full # atomically replace active-station observations
python3 -m mothdash check      # report stations with data newer than the cache
```

## Page speed and photo assets

The first homepage photo loads eagerly with high priority; other photos stay
lazy. Recent-sighting thumbnails use iNaturalist's smaller source variant when
no optimized local image is available. The homepage's hero and recent-sighting
photos can receive responsive WebP variants, with actual pixel widths and a
linked photo-credit page retaining source links, attribution, license, and
conversion details.

Ordinary `render` remains network-free and reuses available cached variants.
To prepare missing photos while rendering an existing database:

```sh
MOTHDASH_PREPARE_PHOTOS=1 python3 -m mothdash render
```

Deployment builds enable this flag and cache `.cache/photos` separately from
the database. Only known iNaturalist photo URLs with suitable cached licensing
and attribution metadata are eligible; missing-license and no-derivatives
images stay upstream. Download or decoding failures also keep the original
image usable. Pillow is not required for cache-only rendering.

Build-cost ceiling: at most 20 eligible source photos per build, with at most
20 new download attempts, a 5 MiB limit per source, and a shared 60-second
preparation budget (plus an in-flight operation's five-second timeout).
Successful encodes produce at most two variants per source, each capped at
5 MiB. Only current-source derived files are retained in the persistent cache;
ordinary photos are much smaller than these safety limits. This adds no
iNaturalist API calls, scheduled runs, or Pages deployments. It adds at most
100 MiB of source-image transfer and 200 MiB of encoded assets/cache per cold
build; warm-cache builds do no photo downloading. All output is static and
requires no paid image-transformation service.

The archive initially renders at most 100 flagged records. Filtering, sorting,
and “Show more” load the complete static JSON dataset once, then build only the
requested rows. A full static table remains available without JavaScript.
Calendar and species-comparison views have dedicated static pages, preserving
their full data without parsing all views when the archive opens. Station
selection, scientific counts, sync cadence, and iNaturalist API calls are
unchanged.

Browser regression check (requires Node, Playwright, and Chrome):

```sh
node tests/archive_browser.mjs
```

Set `PLAYWRIGHT_MODULE` to an absolute Playwright module path if it is not
installed in the default Node resolution path. Unit checks remain
`python3 -m unittest discover -s tests -v`.

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
build also reconciles older records whose identification or taxonomic rank
changed after upload. Records deleted from iNaturalist or moved outside a
station's project/place/radius cannot appear in that update feed, so the first
successful build after 30 days automatically performs an atomic full rebuild
of active stations. This uses the existing daily deployment rather than adding
another scheduled run. A maintainer can also select **full_rebuild** when
manually dispatching the build workflow.

The full-rebuild interval is configured with `full_sync_interval_days` in
`stations.toml`. As of August 2026, the active queries contain about 26,600
observations, or roughly 140 observation pages. At the client's sequential
one-request-per-second pacing, the monthly observation pass adds about 2.5
minutes; it does not add another Pages deployment. Inactive stations retain
their frozen history and are never queried by either incremental or full sync.

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

## Predicted Next 10 Moths

Every station profile includes a **Predicted next 10 moths** list. It is intentionally
separate from the station's host-plant targets and its own historical
`Watch next` list:

- it excludes moth species already recorded at that station;
- it uses all public iNaturalist moth observations within the station's
  configured 100 km reference radius, not only the tracked stations;
- it counts records occurring on the next 14 recurring calendar days across
  iNaturalist history, weights the nearer week slightly more, and publishes the
  ten unrecorded species with the strongest seasonal evidence after the
  sheet-time adjustment;
- it preserves that seasonal order unless a species has at least four timed
  tracked-source records and no more than half fall from 6 p.m. to 10 a.m.;
  those credibly daytime-weighted taxa move behind otherwise neutral candidates;
- it shows host associations as supporting context without using them to
  reorder the production prediction.

This is a ranked watchlist for likely next new station records, not a guarantee
that all ten will appear on a particular sheet night. Uploaded iNaturalist
records also do not consistently encode survey method. Exact observation time
is therefore a conservative negative signal for daytime-weighted species, not
proof that an individual record was a sheet capture. Validation measures new
tracked-source records and reports the unadjusted seasonal order alongside the
sheet-time production order.

Forecast snapshots record their deployment channel. Only lists issued by a
production build enter the prospective scorecard; local renders and Cloudflare
preview deployments cannot be mistaken for published predictions.

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
- incremental sync follows new observation IDs and separately reconciles older
  records updated by iNaturalist; use `sync --full` immediately after a major
  station-query change instead of waiting for the automatic 30-day backstop
- first-of-season timing is based on observed date, with records before noon
  assigned to the previous evening's moth session
- county/state first-record context is cached and refreshed gradually so
  scheduled builds do not make thousands of iNaturalist API calls at once
- the live page runs in the visitor's browser, keeps live mode on locally for
  two hours, and checks recent iNaturalist uploads for ten minutes after toggle

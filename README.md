# Moth Station Dashboard

Compare moth activity across several iNaturalist-based light stations.

The MVP builds a static dashboard from configured station queries:

- all-time moth lists by station
- recent observations across stations
- first-of-season timing across stations
- same-season spread, so synchronized flight pulses surface quickly

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
```

## Hosting

The dashboard is configured for Cloudflare Pages at:

`https://moth-stations.kingfisher-hollow.com`

The GitHub Actions workflow builds the dashboard and deploys `public/` to the
Cloudflare Pages project named `moth-stations`.

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

By default, every station query is restricted to moths:

- `taxon_id = 47157` for Lepidoptera
- `without_taxon_id = 47224` for butterflies

You can override those values per station if needed.

## Current MVP Limits

This is an intentionally small first pass:

- county/state firsts are planned but not implemented yet
- weather correlation is planned but not implemented yet
- incremental sync follows iNaturalist observation IDs, so use `sync --full`
  after major station-query changes
- first-of-season timing is based on observed date, with records before noon
  assigned to the previous evening's moth session

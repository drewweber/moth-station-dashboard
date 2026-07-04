# Agent Guidance

This repo builds a static moth-station comparison dashboard from iNaturalist
queries.

## Rules

- Keep `stations.toml` readable for non-programmers.
- Do not commit SQLite databases, logs, or generated HTML.
- Preserve the distinction between observed date, upload date, and ID update
  date.
- For moth sessions, records before noon belong to the previous evening.
- Use cautious record language: "iNaturalist county first" unless an external
  source confirms a broader claim.
- Prefer standard-library Python unless a dependency clearly earns its cost.

## Common Commands

```sh
python3 -m compileall mothdash
python3 -m mothdash sync
python3 -m mothdash render
python3 -m mothdash build
```

## Main Files

- `stations.toml`: station definitions
- `mothdash/config.py`: config parser
- `mothdash/inat_api.py`: iNaturalist API client
- `mothdash/db.py`: SQLite schema
- `mothdash/sync.py`: observation ingest
- `mothdash/analysis.py`: station comparison and first-of-season logic
- `mothdash/render.py`: static HTML renderer


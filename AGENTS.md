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
- Keep pull requests narrowly scoped and do not mix behavior changes with
  unrelated cleanup.
- Add or update tests when changing date handling, station selection, species
  counts, first-record logic, or other analysis behavior.
- Never claim a check passed unless you ran it. Record the exact commands and
  results in the pull request description.
- For visible changes, include before/after screenshots at relevant desktop
  and mobile widths.

## Common Commands

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q mothdash
python3 -m mothdash sync
python3 -m mothdash render
python3 -m mothdash build
```

Before opening a pull request, read `CONTRIBUTING.md` and complete the pull
request template. Explain the user-visible behavior, data implications, risks,
and verification clearly enough that a reviewer does not need to reconstruct
the intent from the diff.

## Main Files

- `stations.toml`: station definitions
- `mothdash/config.py`: config parser
- `mothdash/inat_api.py`: iNaturalist API client
- `mothdash/db.py`: SQLite schema
- `mothdash/sync.py`: observation ingest
- `mothdash/analysis.py`: station comparison and first-of-season logic
- `mothdash/render.py`: static HTML renderer

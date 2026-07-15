# Contributing

Station owners and developers can contribute in three ways:

1. Add or edit a station in `stations.toml`.
2. Open an issue with the station query details if they do not want to edit code.
3. Improve dashboard code or docs through a pull request.

## Station Requirements

Each station needs:

- a stable `id`, using lowercase letters, numbers, and hyphens
- a clear display `name`
- an iNaturalist query, such as `project_id`, `user_login`, `place_id`, or
  `lat`/`lng`/`radius`
- county and state place IDs when first-record context is added later

Do not include private exact coordinates for a station unless the owner is
comfortable with them being public in the GitHub repo.

## Working With AI Coding Tools

Claude, Codex, Cursor, Copilot, and other tools are welcome. Keep AI-generated
changes reviewable:

- make small pull requests
- explain the behavior change
- include the command used to test it
- avoid committing `data/mothdash.db` or generated `public/index.html`
- do not rewrite unrelated files

The repository includes `AGENTS.md` and `CLAUDE.md` so different tools can read
the same project guidance.

## Keep Pull Requests Reviewable

Each pull request should make one coherent change. Avoid combining a feature,
large refactor, formatting rewrite, and station-data update in the same PR.

The description should let a reviewer answer these questions without having to
infer intent from the code:

- What changed for a visitor or station owner?
- Why is this the right behavior?
- Which pages, stations, queries, or calculations are affected?
- Could historical counts, current-night results, privacy, or API usage change?
- What exact automated and manual checks were run?
- What remains uncertain or was not tested?

Use the repository pull request template. Do not replace its sections with a
short summary generated from the commit list.

## Data Rules Worth Protecting

- Observed date, upload date, and identification-update date are different.
- Observations before noon belong to the previous evening's moth session.
- A count labeled "species" must include only species-rank taxa. Use "taxa" if
  broader identifications are intentionally included.
- Daily network richness is the union of species across stations, not the sum
  of station counts.
- County and state records must be described as iNaturalist firsts unless a
  broader source supports the claim.
- `active = false` keeps historical data but should stop current syncing and
  live polling. `enabled = false` removes the station from dashboard analysis.
- Exact coordinates and precise live queries must not be made public without
  the station owner's approval.

## Required Local Checks

Before opening a pull request:

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q mothdash
python3 -m mothdash render
```

Run `python3 -m mothdash build` only when network access is available and the
change needs verification against fresh iNaturalist data. State whether the
render used the existing local database, an empty database, or freshly synced
data.

For analysis changes, add focused tests that demonstrate both the expected case
and an important boundary case. For UI changes, inspect the generated page at a
desktop and mobile width and include screenshots in the PR.

If a check cannot be run, leave it unchecked in the PR template and explain
why. An honest gap is safer than an unsupported claim.

## Reviewer-Friendly Descriptions

Prefer concrete statements:

- "Past week now excludes genus-level identifications; 14 fixture observations
  produce 9 unique species."
- "Durfee Hill remains in all-time analysis but is omitted from sync and Live."
- "Checked the calendar at 390 px and 1280 px; the station columns remain
  aligned."

Avoid vague statements such as "improved logic," "fixed styling," or "tests
pass" without explaining what changed and which tests ran.

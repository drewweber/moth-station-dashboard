# Agent Guidance

This repo builds a static moth-station comparison dashboard from iNaturalist
queries.

## Rules

- Keep `stations.toml` readable for non-programmers.
- Keep taxon filtering semantic. The site is currently moth-focused via
  `taxon_scope = "moths"` in `[settings]`; do not make contributors define raw
  taxon exclusions such as butterfly filters in station entries.
- Do not commit SQLite databases, logs, or generated HTML.
- Preserve the distinction between observed date, upload date, and ID update
  date.
- For moth sessions, records before noon belong to the previous evening.
- Use cautious record language: "iNaturalist county first" unless an external
  source confirms a broader claim.
- Prefer standard-library Python unless a dependency clearly earns its cost.
- Keep pull requests narrowly scoped and do not mix behavior changes with
  unrelated cleanup.
- For any non-trivial or long-running pull request, fetch and rebase on current
  `origin/main` at the start of each work session, before pushing new commits,
  and before marking the PR ready for review. Use `git push --force-with-lease`
  after rebasing; do not use a plain force push.
- If a rebase has conflicts, resolve them against current `main` and record the
  conflicted files, behavior decisions, and rerun checks in the PR description.
- Open large or uncertain work as a draft PR early. Split foundation refactors,
  station/query changes, UI changes, and behavior changes into separate PRs
  unless the PR explains why they must ship together.
- Add or update tests when changing date handling, station selection, species
  counts, first-record logic, or other analysis behavior.
- Never claim a check passed unless you ran it. Record the exact commands and
  results in the pull request description.
- For visible changes, include before/after screenshots at relevant desktop
  and mobile widths.
- Keep the main page fast and simple. Treat homepage sections as bounded
  previews, not complete archives.
- Default to a collaborative network metric alongside any station-specific
  metric when the data supports it. Network totals must de-duplicate shared
  species across stations, and labels must make clear whether a value is a
  station count, a sum of observations, or a network-wide species union.
- Put long, complex, or media-rich collections behind a clear "Browse all" or
  "View all" control leading to an expanded view or dedicated static page.
- Do not render large collections of hidden cards or duplicate images into the
  homepage DOM. Prefer compact tables, paginated rendering, or separate JSON
  data products for full collections.
- When a pull request changes the homepage, report generated `index.html` size
  and repeated-item counts before and after the change.
- Keep all routine queries, builds, previews, and production deploys within the
  free tiers of GitHub Actions and Cloudflare Pages. Do not introduce a paid
  service requirement.
- Before increasing sync frequency, scheduled workflow frequency, API query
  volume, build duration, artifact size, or deployment count, estimate and
  document the worst-case usage in the pull request.

## Common Commands

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q mothdash
python3 -m mothdash sync
python3 -m mothdash render
python3 -m mothdash build
```

For active PR branches:

```sh
git fetch origin
git rebase origin/main
python3 -m unittest discover -s tests -v
python3 -m compileall -q mothdash
python3 -m mothdash render
git push --force-with-lease
```

Before opening a pull request, read `CONTRIBUTING.md` and complete the pull
request template. Explain the user-visible behavior, data implications, risks,
and verification clearly enough that a reviewer does not need to reconstruct
the intent from the diff.

## Maintainer PR Review Requests

When the maintainer asks to "review pending PRs" or similar, read
`MAINTAINER.md` and follow the quick PR review workflow there. Inspect open PRs,
classify each as `Merge`, `Comment`, `Request rebase`, `Needs review`, or
`Close/split`, and suggest exact next actions. Do not merge, approve, close,
request changes, or post public comments until the maintainer explicitly
confirms the target PR number and action.

## Main Files

- `stations.toml`: station definitions
- `mothdash/config.py`: config parser
- `mothdash/inat_api.py`: iNaturalist API client
- `mothdash/db.py`: SQLite schema
- `mothdash/sync.py`: observation ingest
- `mothdash/analysis.py`: station comparison and first-of-season logic
- `mothdash/render.py`: static HTML renderer

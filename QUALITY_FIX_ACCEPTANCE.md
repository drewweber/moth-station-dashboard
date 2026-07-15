# Quality Fix Acceptance Criteria

These criteria define completion for the four findings identified in the July
2026 project review. Each fix should be delivered as a focused commit with its
own automated tests.

## 1. Inactive Station Behavior

- A station with `enabled = false` is excluded from syncing, historical
  analysis, generated pages, and Live.
- A station with `enabled = true` and `active = false` remains visible in
  historical station lists, profiles, and all-time analysis.
- An inactive station is not passed to observation sync or first-record API
  refresh logic.
- An inactive station is not emitted as a checkable station in
  `live-snapshot.json`.
- Automated tests demonstrate the historical/live distinction.

## 2. Species and Taxa Semantics

- Any metric or list labeled "species" includes only rows whose iNaturalist
  rank is exactly `species`.
- Station species totals, Last night, Past week, Firsts, Unique, comparison
  tables, and station-derived species lists use the same species-rank rule.
- Observation totals may include broader identifications, but they are not
  silently added to species richness.
- Existing species-only calendars, accumulation curves, profile analyses, and
  Live behavior remain species-only.
- Fixture tests containing species-, genus-, and family-rank rows prove that
  broader identifications do not inflate species counts.

## 3. Current Seven-Night Window

- Past week is anchored to the current moth-session date in the configured
  network timezone, not to the newest cached observation.
- Before the configured noon cutoff, the current moth-session date is the
  previous calendar date; at or after noon, it is the current date.
- The range always covers that session date and the six preceding dates.
- The displayed range remains current when the database is stale or empty.
- When no observations fall in the current range, the page says so and reports
  the latest synced session separately when one exists.
- Automated tests cover before noon, noon, stale data, and a year boundary.

## 4. Firsts Archive Size and Completeness

- The Recent Firsts photo grid contains at most the 12 newest records.
- Older records are not duplicated as hidden photo cards.
- The archive contains every flagged first in a compact table or compact JSON
  data product.
- Opening the archive shows the first 100 records and provides a control to
  reveal more until all records are visible.
- Type and location filters search the complete archive, including records
  beyond the first 100, and show all matching rows.
- Clearing filters restores the paginated archive state.
- "Browse all" never permanently hides records behind an undocumented preview
  limit.
- Renderer tests cover card limits, full archive inclusion, filtering hooks,
  and removal of the old hidden-card duplication.

## Global Completion

- `python3 -m unittest discover -s tests -v` passes.
- `python3 -m compileall -q mothdash` passes.
- A render with the local database passes.
- A render from a clean empty database passes.
- `git diff --check` passes.
- Each implementation is committed separately and nothing is pushed until the
  repository owner confirms.

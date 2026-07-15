## What changed

<!-- Describe the user-visible or contributor-visible behavior. Be specific. -->

## Why

<!-- Explain the problem and why this implementation is appropriate. -->

## Scope and data impact

<!--
List affected pages, stations, queries, calculations, or generated files.
State explicitly whether this changes:
- historical or current-night counts
- species/taxon filtering
- session-date handling
- iNaturalist API usage or caching
- public coordinates, privacy, or Live queries
Use "None" where appropriate.
-->

## Verification

Commands run and results:

```text
# Paste the exact commands and concise results here.
```

- [ ] `python3 -m unittest discover -s tests -v`
- [ ] `python3 -m compileall -q mothdash`
- [ ] `python3 -m mothdash render`
- [ ] I added or updated tests for changed analysis behavior, or explained why no test is needed.
- [ ] I checked the relevant generated page manually.
- [ ] I checked both desktop and mobile layouts for visible changes.

Data used for verification:

<!-- Existing local database, empty database, fixture data, or fresh sync? -->

## Before and after

<!-- For visible changes, attach labeled before/after screenshots. Otherwise write "Not a visible change." -->

## Risks and limitations

<!-- Note edge cases, untested paths, migration/cache concerns, and anything the reviewer should verify. -->

## Change hygiene

- [ ] This PR contains one coherent change.
- [ ] I did not commit generated HTML, SQLite databases, logs, secrets, or unrelated formatting changes.
- [ ] Existing station IDs remain stable unless the PR explicitly documents a migration.
- [ ] Public wording distinguishes iNaturalist firsts from broader historical records.
- [ ] AI-assisted changes were reviewed by the contributor, not submitted without inspection.

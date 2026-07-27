# Moth Station Dashboard Plan

> **Status: archived for future consideration — not authorized for
> implementation.**
>
> Archived on 2026-07-26. This document records a possible scientific and
> technical upgrade path; it is not an active roadmap. Do not create issues,
> change code or configuration, alter public copy, record new validation data,
> publish a preview, or deploy anything on the authority of this document.
> Reactivation requires fresh owner approval after the repository, data,
> services, and evidence have been re-audited.

## Archived Proposal: Scientific Trust and Forecast Validation

### Purpose

Preserve the useful collaborative dashboard and seasonal watchlist while
making every public claim reproducible, appropriately qualified, and supported
by the data actually collected.

The preferred future direction is an observational dashboard with an explicitly
experimental forecast pilot. It is not an abundance, population-monitoring,
habitat-quality, or observer-ranking system.

### Governing Scientific Contract

> The dashboard summarizes public, evidence-backed iNaturalist records from
> configured sources. It supports discovery, identification, survey planning,
> and transparent comparison of recorded timing. Unless standardized sampling
> effort is available, it does not estimate biological absence, abundance,
> population change, habitat quality, emergence, or observer performance.

This contract should control data design, analysis, copy, and interface
decisions if the proposal is reactivated.

The configured sources are heterogeneous. They can represent projects, places,
users, radius searches, or bounding boxes, and they have very different
observer effort, equipment, upload practices, and histories. Use **tracked
source** as the general term. Reserve **station** for a source with a defined,
repeatable sampling location and protocol.

### Audited Forecast Result: Historical Snapshot Only

The following values describe the local cache audited on 2026-07-26. They are
retained as historical evidence and must not be presented as current without a
fresh rebuild and audit.

| Ranking | Hits / issued list slots | Listed-species hit rate |
| --- | ---: | ---: |
| Seasonal | 166 / 781 | 21.3% |
| Seasonal plus host proxy | 122 / 781 | 15.6% |
| Host-prioritized seasonal candidates | 109 / 781 | 14.0% |

The seasonal ranking remained ahead when the overlapping series was divided
into non-overlapping subsets and when casual-grade observations were excluded.
This is a useful exploratory signal, not a validated comparative forecast.

The strongest defensible conclusion is:

> In this one-season tracked-network reconstruction, seasonal ranking ordered
> the seasonally eligible target lists better than the current fauna-inferred
> host-association ranking.

Do not call the listed-species hit rate **accuracy**. The calculation has no
true negatives and does not estimate general predictive accuracy.

### Blocking Scientific Limitations

1. **The current host comparison is not independent.**
   `host-only` begins with the same seasonally eligible candidate pool as the
   seasonal ranking. It tests ordering within that pool, not whether host plants
   independently predict future station records.
2. **The host score does not observe station flora.**
   It infers host-guild similarity from documented hosts of moths already
   recorded at the source. It must not be described as evidence that any host
   plant is locally present.
3. **The retrospective windows are dependent.**
   Fourteen-day outcomes were issued weekly. The 264 reported active
   station-night memberships represent only 144 distinct station/date pairs.
4. **The scored subset is outcome-conditioned.**
   Only 48 of 112 possible source-windows were scored; quiet windows and
   sources without sufficient history were omitted rather than retained as
   explicit eligibility outcomes.
5. **The pooled estimate is unbalanced.**
   Kingfisher Hollow contributed 111 of the seasonal ranking's 166 hits.
   Pooled list slots are therefore not a balanced network estimate.
6. **Historical identification state is not frozen.**
   Upload cutoffs are applied, but the local observation record contains the
   current taxon and quality state. A later identification can leak into an
   earlier reconstruction.
7. **The reconstruction and production forecast are different models.**
   They use different candidate evidence, temporal intervals, and sorting
   rules. The reconstruction is a proxy experiment, not a replay of the
   deployed forecast.
8. **Current forecast snapshots are not publication records.**
   Ordinary rendering writes rows. Records do not prove successful deployment
   and lack sufficient model, data, cache-completeness, and deployment
   provenance.
9. **Incremental sync does not fully reconcile changed records.**
   Following newly created observation IDs does not reliably retrieve later
   identifications or quality changes to existing observations.
10. **Effort and detection are unmeasured.**
    The database does not distinguish no survey, a completed zero-result
    survey, an incomplete upload, and a complete upload. Duration, light type,
    method, weather, and observer effort are also not consistently recorded.

Until these limitations are addressed, comparisons remain exploratory and
descriptive.

### Public-Language Contract

If this proposal is reactivated, use the following language consistently:

| Avoid | Use |
| --- | --- |
| `accuracy` | `top-list hit rate: hits / issued targets` |
| `host-only model` | `fauna-inferred host-guild proxy` |
| `same flight pulse` or `synchronized` | `first tracked records fell within X days` |
| `early emergence` | `earlier first tracked record than in prior tracked years` |
| `relative abundance` | `share of uploaded observations`, explicitly not abundance |
| `richest` or `strongest station` | the exact observed-species or uploaded-record measure |
| `active station` | `source with at least one uploaded species record`, unless effort is logged |
| `rare` or `unique` | `N qualifying records within the defined sources and date range` |
| `county first` | `iNaturalist county first`, unless independently corroborated |

Every statistic should disclose:

- data source and data-as-of time;
- geographic and source universe;
- observation and upload date range;
- taxonomic rank and identification/quality policy;
- numerator, denominator, and exclusions;
- provisional or final status;
- permitted interpretation and important limitations.

### Future Work Packages

No work package below is currently authorized.

#### Phase 0 — Re-audit and Approve the Protocol

- Recheck the current branch, working tree, open pull requests, deployments,
  generated artifacts, database state, API behavior, and service limits.
- Rewrite the active roadmap into:
  - shipped and verified;
  - shipped but requiring scientific correction;
  - approved next work;
  - deferred or research-gated.
- Create a metric dictionary covering the disclosures listed above.
- Confirm whether the product owner still wants a forecast experiment.
- Freeze the prospective protocol before changing forecast behavior.

**Gate:** the owner signs the refreshed protocol and exact implementation
scope. Approval of this archived document alone is insufficient.

#### Phase 1 — Correct Trust, Language, Privacy, and Accessibility

- Apply the public-language contract.
- Label all retrospective evidence as exploratory.
- Surface data-as-of times, identification policy, model version, and
  provisional/final status.
- Distinguish tracked sources from standardized stations.
- Remove or reframe unsupported claims about emergence, synchronization,
  abundance, richness, station strength, rarity, and habitat quality.
- Default to coarse or private locations. Precise public locations require
  affirmative owner consent and must not weaken iNaturalist geoprivacy.
- Require WCAG 2.2 AA, keyboard operation, non-color encodings, chart text or
  table alternatives, reduced-motion support, 200% zoom, and a usable
  320-pixel layout.
- Add no public observer leaderboard, reputation score, competitive completion
  system, or incentive based on brighter lights, longer sampling, or total
  captures.

**Gate:** tests and claim-language audit pass; privacy decisions are recorded;
desktop, mobile, keyboard, and screen-reader checks pass; generated page sizes
do not regress; the owner approves a public preview before production.

#### Phase 2 — Make Prospective Forecasts Reproducible

- Separate pure rendering from an explicit forecast-recording command.
- Make ordinary local rendering incapable of creating scientific records.
- Record at most one idempotent run per source, reference date, and model
  version.
- Mark a run as published only after a successful production deployment.
- Save a frozen candidate universe, features, scores, ranks, exclusions, and:
  - model/version identifier;
  - Git commit;
  - configuration and host-data hashes;
  - source-data cutoff and data-as-of time;
  - candidate-source provenance;
  - environment and deployment identifier/URL;
  - API/cache completeness and fallback state.
- Preserve compact immutable forecast ledgers in durable append-only storage.
  An ephemeral workflow cache is not an evidence archive.
- Never label a partially fetched regional aggregate as complete.
- Use date-bounded reconciliation when adjudicating delayed uploads,
  identification changes, and quality changes.

**Gate:** a successful deployed forecast can be reconstructed byte-for-byte
after deleting the local SQLite cache; failed deployments and local renders
produce no published record.

#### Phase 3 — Establish Survey Effort and Run a Prospective Pilot

For each survey attempt, record:

- sampled or not sampled;
- local evening/session date;
- start/end time or duration;
- sheet, trap, light, and other methods;
- broad lamp specification;
- whether uploads are complete;
- optional broad weather observations;
- protocol version.

The data model must distinguish:

- no survey attempted;
- completed survey with zero qualifying records;
- survey with incomplete uploads;
- completed and uploaded survey.

Confirmatory forecasts should:

- be frozen every other Monday at 12:00 America/New_York;
- cover the next 14 local evening-start dates;
- use non-overlapping windows;
- give every comparison model the same frozen candidate universe;
- require at least three declared survey sessions for the primary analysis;
- retain failed eligibility, quiet, and thin-effort windows in the accounting.

Daily operational lists may continue, but they should remain descriptive and
outside the confirmatory analysis.

Predeclare and version:

1. seeded random ranking;
2. regional-frequency ranking without seasonal timing;
3. seasonal ranking;
4. fauna-inferred host-guild proxy;
5. seasonal plus host-guild proxy.

The sole primary comparison should be seasonal plus host-guild proxy versus
seasonal. Changing features, weights, formulas, candidate rules, or outcome
rules creates a new model version evaluated only on later forecasts.

Define a hit as:

> A public, evidence-bearing, non-captive species-level observation from the
> source, observed during the forecast window, not already present in the
> frozen source history at the forecast cutoff.

Use:

- provisional scoring 30 days after the outcome window closes;
- final scoring after a 90-day upload and identification period;
- identification and Data Quality Assessment state at the final cutoff;
- a research-grade-only sensitivity analysis;
- exclusion of targets with an eventually discovered pre-window record.

**Gate:** synthetic fixtures recover precomputed expected results; post-cutoff
predictor changes cannot alter a frozen forecast; exclusions are fully
reported; and the owner approves the reviewable preview before production.

#### Phase 4 — Evaluate Only After the Evidence Gate

Primary measure:

- per-window Precision@20;
- paired Precision@20 difference between seasonal plus proxy and seasonal.

Secondary measures:

- Precision@5 and Precision@10;
- Recall@20;
- candidate-universe recall;
- nDCG@20;
- rank of successful targets;
- no-target and non-evaluable-window rates;
- results by source and effort stratum.

Report source-macro and issue-window-macro results. Pooled list slots may be
shown only as descriptive context. Estimate uncertainty with a hierarchical
bootstrap or equivalent paired analysis that preserves source and date
dependence. Do not treat list slots or overlapping windows as independent
binomial observations.

Until every condition below is met, the public report must say
**experimental/descriptive**:

- at least 60 independent, effort-qualified source-windows;
- at least five contributing sources;
- two complete flight seasons;
- at least 100 adjudicated new-record outcomes;
- at least 80% simulated power to detect a five-percentage-point
  Precision@20 difference.

A public claim that the combined model performs better additionally requires:

- a paired 95% uncertainty interval entirely above zero;
- an improvement of at least five percentage points;
- the same direction of effect in at least four sources;
- leave-one-source-out analyses that do not reverse the conclusion;
- performance above both random and regional-frequency baselines.

#### Phase 5 — Optional Independent Host Model

Treat an independent host model as a separate research project. Do not start it
without:

- direct, versioned plant inventories for participating stations;
- taxonomically normalized station flora;
- a broad regional moth universe frozen before each forecast;
- one shared candidate universe for every model;
- a seasonal model using only timing evidence;
- a host model using only direct station flora and vetted moth-host
  associations;
- missing host information treated as unknown rather than zero;
- predeclared combined-model rules;
- approved API volume, storage design, and prospective sample-size analysis.

### Explicitly Deferred Features

The following require their own proposal and later owner approval:

- effort-adjusted abundance or population-trend inference;
- weather or moon-effect inference;
- habitat-quality comparisons;
- public observer or station rankings;
- public reputation or competitive completion scores;
- "collect every species" challenges;
- automated expert-identification feeds without a changed-record refresh
  strategy;
- shared feedback infrastructure;
- any server-side or paid-service expansion.

Collaborative features should reward identification quality, complete effort
logs, coverage of genuine survey gaps, careful documentation, and responsible
sampling—not hours of lighting, brightness, catch totals, or observer
competition.

### Stop-Work Conditions

If this proposal is reactivated, stop and return for a decision whenever a
feature:

- requires absence, effort, duration, or individual-count data that are not
  collected;
- treats heterogeneous source queries as equivalent standardized stations;
- implies plant presence without direct plant-inventory evidence;
- treats overlapping windows as independent;
- changes an evaluation model after its forecast cutoff;
- makes novelty or rarity claims without a defined universe and identification
  cutoff;
- exposes precise coordinates without documented consent;
- incentivizes excessive lighting or competitive collecting;
- cannot meet the accessibility, provenance, reproducibility, or free-tier
  constraints.

### Reactivation Checklist

Before any future implementation:

1. Obtain explicit owner approval naming the phases authorized.
2. Recheck `git status -sb`, branch ancestry, all open pull requests, and likely
   file overlap.
3. Refresh current moth and dashboard data where the proposed decision depends
   on current counts or recent observations.
4. Re-run the scientific and architectural audit against the current code.
5. Revalidate the cited scientific standards and iNaturalist policies.
6. Estimate API volume, build time, storage growth, artifact size, and
   deployment frequency.
7. Define the preview branch, verification commands, review gate, and exact
   production authorization.

Recommended initial authorization, if this archive is ever reactivated:

> Authorize Phases 0–3 through a reviewable preview only. Do not deploy
> production changes or begin Phases 4–5 without subsequent owner sign-off.

### Scientific References

- Di Cecco et al. (2021), iNaturalist spatial, temporal, and observer bias:
  <https://academic.oup.com/bioscience/article/71/11/1179/6357804>
- Roberts et al. (2017), blocked validation for structured ecological data:
  <https://doi.org/10.1111/ecog.02881>
- Jonason et al. (2014), weather, timing, and lamp effects in moth light-trap
  sampling: <https://doi.org/10.1371/journal.pone.0092453>
- Johnston et al. (2021), effort and detectability in citizen-science data:
  <https://doi.org/10.1111/ddi.13271>
- Ecological Forecasting Initiative, forecast standards:
  <https://ecoforecast.org/cross-cutting-themes/forecasting-standards/>
- Simonis et al. (2021), ecological forecast evaluation:
  <https://doi.org/10.1002/ecy.3431>
- Natural History Museum HOSTS dataset:
  <https://data.nhm.ac.uk/dataset/hosts>
- iNaturalist Data Quality Assessment:
  <https://help.inaturalist.org/en/support/solutions/articles/151000169936>
- iNaturalist identification process:
  <https://help.inaturalist.org/en/support/solutions/articles/151000194901-how-do-identifications-work->
- iNaturalist geoprivacy:
  <https://www.inaturalist.org/pages/geoprivacy>
- Boyes et al. (2021), ecological effects of artificial light on moths:
  <https://doi.org/10.1126/sciadv.abi8322>

## Historical Planning Material

Everything below this point is retained verbatim so earlier product intent,
handoff notes, and uncommitted work are not lost. It is historical context, not
an active backlog or implementation instruction. Where it conflicts with the
archived proposal above, the archived proposal records the preferred future
direction—but neither section authorizes work.

## Product Goal

Build a semi-live dashboard for comparing moth stations across a local region.
The site should answer two questions every evening:

1. What is happening tonight or in the last few days?
2. Are stations picking up the same first-of-season moths on the same nights?

The dashboard should be useful to station owners, naturalists, and identifiers
without overstating iNaturalist records as absolute biological firsts.

## Handoff: Forecast Validation

This section records the current state of the "Next two weeks" forecasting
work so a future contributor can take it over without reconstructing its
history from commits or page copy.

### Intended Question

The goal is to learn which inputs best place species on a station's next-two-
weeks list before those species are recorded at that station for the first
time. This is a model check, not a count of moths or observations.

The useful outcome is a simple, defensible answer such as: "seasonal timing is
currently more useful than host association for ordering this list." The page
should use plain language and show only the metrics needed to support that
answer.

### What Exists Now

- Station pages have a generated `Next two weeks` list.
- Every build saves the rendered target lists in SQLite so future completed
  periods can be scored exactly as published.
- `forecast-validation.html` is a separate internal page linked from the
  historical dashboard footer.
- The historical backtest freezes observations available by local noon at
  past Monday checkpoints, builds a list of up to 20 species, and checks which
  species were then recorded at that station for the first time during the
  following 14 moth sessions.
- It excludes windows with no species-level station activity and does not use
  records uploaded after the checkpoint.
- The current historical reconstruction uses the synced tracked-station cache,
  not freshly recreated regional iNaturalist queries. This avoids hindsight
  and keeps the build within the free tier, but it is not the same as the
  eventual exact published-list check.

### Important Limitation: "Host-only" Is Not Independent

The current comparison has three ranking variants in `mothdash/analysis.py`:

1. `seasonal-only`: ranks moths using nearby seasonal records.
2. `host-only`: **starts with the same seasonally plausible nearby candidate
   pool**, then orders that pool by host-association score.
3. `host-evidence`: uses seasonal ranking with host association as supporting
   evidence.

Therefore `host-only` does **not** test whether host association can predict
new station species independently of nearby seasonal records. It only tests
whether host association improves the ordering of species that have already
been made seasonally eligible.

The host score is also not a direct station plant inventory. It comes from
`mothdash/data/host_plants.json` and looks for documented host overlap between
a target moth and moths already recorded at the station. It is useful context,
but it should not be described as proof that a host plant is present.

Until the implementation changes, call this variant **"host-prioritized
seasonal candidates"** in user-facing writing, not "host-only."

### Current Result Snapshot

These values are generated from the local cache and will change as data is
synced. On 2026-07-26, the historical comparison contained 48 scored
station-window tests and 264 active station-nights:

| Ranking tested | Species on the list that were later recorded for the first time | List accuracy |
| --- | ---: | ---: |
| Seasonal timing | 166 of 781 | 21% |
| Seasonal timing + host evidence | 122 of 781 | 16% |
| Host-prioritized seasonal candidates | 109 of 781 | 14% |

This supports a narrow conclusion only: **within the current seasonally
filtered candidate pool, seasonal timing is the strongest ranking signal so
far.** It does not establish that host association has no value, nor does it
measure a truly independent host-based model.

The shared `781` is only a fairness denominator: each method received the
same total number of list slots across the same test windows. It should not be
a headline metric on the page.

### Why the Current Report Needs Work

The current preview report repeats denominators, presents the test design as
the main result, uses jargon such as "target coverage," and includes a wide
station table with empty published columns. That makes a straightforward
question hard to read.

A future revision should:

1. Lead with the conclusion and a direct comparison of list accuracy.
2. Explain in one sentence that every method had equally long lists but could
   contain different species because their rankings differ.
3. Put test mechanics, exclusions, and caveats behind a concise `Method`
   disclosure.
4. Show station-level evidence separately and mark thin evidence as limited,
   rather than implying every station comparison is equally reliable.
5. Keep the exact published-list check compact until enough 14-day periods
   have matured to make it useful.

### Decision Needed Before Further Work

Do not make the forecast page more elaborate until the product owner decides
whether a true independent host model is wanted.

If yes, define it explicitly before implementation. A defensible design would
use a broad regional species pool documented before each checkpoint, then let
the host model rank by host association without using date-specific nearby
records. Seasonal-only and combined models should be rebuilt from that same
broad pool. This would test the variables more directly, but is a substantive
analysis change and needs new tests.

If no, retain the existing seasonal candidate pool, rename the current variant
honestly, and simplify the report to answer the narrower ranking question.

### Current Git and Preview Status

- Current work is on `preview/forecast-validation-summary`, not `main`.
- The branch contains `00cbc34 Simplify forecast validation comparison` and
  `3f819b0 Add public dashboard preview workflow`.
- Its public preview is
  `https://preview-forecast-validation.moth-stations.pages.dev/forecast-validation`.
- Nothing from the abandoned report rewrite in this handoff has been edited,
  committed, or deployed.
- Any future visible revision must update this preview branch, run the test
  suite and renderer, and be reviewed at the public preview before production
  deployment.

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

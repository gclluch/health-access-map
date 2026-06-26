# Backlog - open edges & known limitations (agent hand-off)

Pick-up-ready tickets for the work we've deliberately deferred, plus the data-integrity findings
from the 2026-06-24 audit. Each ticket has: **what's wrong**, **why it matters**, **where to look**
(repo paths + external sources), a **suggested approach**, and **acceptance criteria**.

> **Before touching anything that changes scores:** re-baseline, then re-gate. Run
> `python -m pipeline.diagnostics` + `pipeline.verify_bands` + `pipeline.bootstrap_gate`
> (+ `pipeline.validate_subcounty --national` for sub-county claims). Ship only if the north star
> (`drop_care_access` stays below FULL), reliability (>=0.93), and coverage hold, judged against the
> **death-records / ACSC** outcomes, never flu/mammography (the anti-circularity rule). See
> [DECISIONS.md](DECISIONS.md) and [VALIDATION.md](VALIDATION.md).

Severity key: **P1** trust/correctness-visible · **P2** real improvement · **P3** nice-to-have ·
**BLOCKED** needs external data/decision.

---

## A. Data integrity (from the 2026-06-24 audit)

The scoring is sound - percentile-rank + E2SFCA make outliers harmless, no impossible rates, no
sentinels, zero/null-pop ZCTAs are non-scoreable. The gaps are in **display** and in **locking the
invariants**. (Audit method: ad-hoc script over `data/processed/metrics.parquet` - see the chat
log; consider committing it as `pipeline/audit.py`.)

### A1 (P1) - Raw per-capita values shown to users look broken
- **Problem.** `primary_per_1k` is a displayed field, so a user clicking a hospital-campus ZCTA sees
  absurd values: **77555** (UTMB Galveston, pop 2, 908 providers) shows **454,000 per 1,000
  residents**; **80045** (Anschutz Medical Campus, Aurora CO, pop 1,615) shows **1,955**. The
  *score* is unaffected (it uses the E2SFCA reachable value, not this), but the raw number looks like
  a bug and erodes trust.
- **Why it matters.** Trust. The whole project sells itself on honesty; a "454,000" with no caveat
  reads as a broken tool.
- **Where to look.**
  - `pipeline/join_and_score.py`: `primary_per_1k` is computed (~L215) and listed in `RAW_DISPLAY`
    (~L353, the per-ZIP fields served to the detail panel).
  - Frontend render: `frontend/src/components/DetailPanel.tsx` + `frontend/src/lib/measures.ts`
    (labels/formatting for displayed fields).
  - Backend serves it per-ZIP: `backend/data.py` `record()`.
- **Suggested approach.** Don't show raw per-capita for tiny-pop ZCTAs. Options (cheapest first):
  (a) in the frontend, when `population < 1000` (or the new institutional flag, A2), render the
  reachable E2SFCA access instead of `primary_per_1k`, or show "n/a - non-residential ZIP";
  (b) or cap/round the displayed value with a footnote. Keep the raw value in the parquet for
  transparency; only change the *display*.
- **Acceptance.** No detail panel shows a per-capita rate implying >~100 providers/resident without a
  visible caveat; UTMB/Anschutz render sanely.
- **Status (2026-06-24): RESOLVED (was largely a non-issue in the UI).** Audit of the render path
  found the DetailPanel shows the *bounded* `primary_2sfca` (E2SFCA reachable value), never the raw
  `primary_per_1k` - so no user ever saw "454,000". The raw field is still served by the per-ZIP API
  (`record()` dumps the whole row) and kept in the parquet for transparency. The residual risk - a
  non-residential campus rendering with no caveat - is now closed by the A2 `institutional` flag,
  which adds a panel caveat and holds it out of rankings. Locked by the A3 invariant (every
  `primary_per_1k > 1000` ZCTA must be `low_confidence | institutional`).

### A2 (P2) - Medical-campus / institutional ZCTAs aren't flagged
- **Problem.** `low_confidence = population < POPULATION_FLOOR (=1000)` catches 25/26 absurd-per-capita
  ZCTAs, but **80045 slips through** (pop 1,615 > floor) - it shows a sane score *and* an absurd raw
  number with **no caveat**, and can appear in rankings.
- **Why it matters.** A non-residential campus ranked alongside real communities is misleading.
- **Where to look.**
  - `pipeline/config.py`: `POPULATION_FLOOR` (currently 1000).
  - `pipeline/join_and_score.py`: `low_confidence` (~L217), `scoreable` (~L279). The provider counts
    (`providers_primary`, `population`) are already on the frame here.
- **Suggested approach.** Add an `institutional` flag where `providers_primary / population` exceeds a
  threshold (e.g. >5 providers/resident, or providers >> pop), independent of the pop floor. Treat it
  like `low_confidence` (kept out of headline rankings, caveated in the panel). Emit it to
  `metrics.json` slim payload (`_write_slim_json`) and mirror in `frontend/src/lib/types.ts`.
- **Acceptance.** 80045 (and any provider≫pop ZCTA) is flagged and excluded from headline rankings;
  flag count reported in `provenance.json`.
- **Status (2026-06-24): DONE.** Added `institutional = providers_total > population` in
  `join_and_score.py` (a pop-independent bright line - "more registered providers than residents =
  a workplace, not a community"). Flags **66** ZCTAs (18 residential med campuses: Anschutz 80045,
  Houston TMC 77030, Stanford, Yale, U-Mich, VA complexes... + 48 tiny-pop). Chose `providers_total`
  over the suggested `>5 providers/resident` because 80045's ratio is 1.95 - the >5 rule would have
  *missed the one ZCTA the ticket names*. Emitted to slim `metrics.json`, `provenance.json`, and
  `meta.json`; mirrored in `types.ts`; excluded from rankings in both `RankingsList.tsx` and backend
  `data.rankings()`; caveated in `DetailPanel.tsx`. Pure metadata - re-gate confirmed scores
  byte-identical (0 rows changed), north star + reliability + bands all hold.

### A3 (P2) - No data-integrity gate/test locking the invariants
- **Problem.** The audit checks (rates∈[0,1], pctiles∈[0,100], no sentinels, extreme-per-capita ⊆
  flagged, zero-pop non-scoreable) pass *today* but nothing enforces them - a future build could
  silently regress.
- **Where to look.**
  - `pipeline/join_and_score.py` `_validate()` (~L483) already checks coverage + percentile range -
    extend it.
  - `tests/` - add `tests/test_integrity.py` (pattern: `tests/test_acceptance.py` skips when
    `metrics.parquet` is absent, so CI stays green without a data build).
- **Suggested approach.** Add assertions: every `*_rate` ∈ [0,1]; every `*_pctile` ∈ [0,100]; no
  numeric < −100000 (sentinel); `population <= 0 → not scoreable`; every ZCTA with
  `primary_per_1k > 1000` is `low_confidence | institutional`. Wire into `_validate` (build-time
  `die`) **and** a skip-guarded test.
- **Acceptance.** `pytest tests/test_integrity.py` passes on a real build; a deliberately corrupted
  value makes it fail.
- **Status (2026-06-24): DONE.** Added `_validate_integrity()` in `join_and_score.py` (build-time
  `die`) asserting: all `*_pctile`/`*_natpct` in [0,100]; all `*_rate` in [0,1]; no numeric < -1e5
  (sentinel); `population <= 0 => not scoreable`; every `primary_per_1k > 1000` is
  `low_confidence | institutional`. Mirrored by `tests/test_integrity.py` (7 tests, skip-guarded on
  `metrics.parquet`), including a corruption test that proves the guard raises `SystemExit`. All 18
  integrity+backend tests pass; the live build runs the gate clean.

### A4 (P3) - Other audits not yet run
- Duplicate ZCTAs in `metrics.parquet` (backend has a dup-guard in `data.record()`, but the source
  isn't checked); geometry-vs-data join gaps (ZCTAs in `zcta.geojson` but missing data, or vice
  versa); `county_fips` validity on the county joins (`build_geonames.py`, `build_medicaldebt.py`,
  `build_amenable.py`); build-over-build distribution drift (snapshot key quantiles, compare).

---

## B. Statistical / validity edges

### B1 (BLOCKED) - Amenable mortality is county-resolution only
- **Problem.** The §4 gold-standard result (care_access partial r +0.395 vs treatable mortality) is
  **between-county**; treatable mortality has no sub-county source, so it can't confirm fine
  within-county differences (the resolution the tool actually runs at).
- **Why it matters.** Sub-county validity still rests on §3 alone (NY ACSC + national USALEEP).
- **Where to look.** `pipeline/build_amenable.py` (recipe + ICD set), `data/manual/wonder_amenable_county.txt`,
  [VALIDATION.md](VALIDATION.md) §4; sub-county harness `pipeline/validate_subcounty.py`.
- **External.** No free ZIP-level treatable-mortality exists. Would need **restricted-access NCHS
  mortality microdata** (death records geocoded to ZIP/tract; via the NCHS RDC) - a major data-use
  agreement effort. Not headlessly obtainable.
- **Status (2026-06-25): PARTIALLY UNBLOCKED - the premise was too pessimistic.** An exhaustive
  data hunt found multiple **free, no-DUA, headless-fetchable, observed, non-circular sub-county**
  outcomes (the original "no free ZIP-level outcome" was true only for *amenable mortality
  specifically*). Integrated: **Colorado CDPHE tract diabetes ACSC** as a second sub-county
  validation state (`validate_subcounty --colorado`) - composite within-county r **+0.507**,
  care_access **+0.417**, generalizing the NY finding to independent geography + an independent
  outcome (VALIDATION §6a). **FIVE independent sub-county rulers now integrated** (`--all` scorecard):
  NY SPARCS PQI (+0.504), CO CDPHE ACSC (+0.568, pop-weighted via HUD res_ratio), CA ACSC mortality
  age-adjusted (+0.440), **TX DSHS patient-ZIP ACSC inpatient (+0.264)**, CDC national overdose
  (+0.224), + USALEEP LE national (+0.608) - composite within-county r. care_access positive in all;
  `medical_debt`/`shortage` county-constant in all. Texas needed no layout doc (the PUDF is published
  **tab-delimited**) - true preventable-hospitalization at patient ZIP, no crosswalk, largest state.
  **Residual ceiling: only HCUP SID** (a single *national* ACSC panel) is paid/DUA; the free
  state-by-state panel now spans the four largest states. Census/HUD keys at ~/.census_api_key,
  ~/.hud_token (read via env or file; never committed).

### B2 (P2) - Thin sub-score margins not individually replicated out-of-outcome
- **Problem.** Only the *dimension-level* care-access claim got the clean out-of-outcome replication
  (amenable, §4). Individual barriers selected on thin margins - e.g. `medical_debt` (partial-r
  +0.27 vs the standard outcomes) - were **not** re-tested against amenable mortality, so they remain
  "selection-soft" per [VALIDATION.md](VALIDATION.md) §1c (winner's curse).
- **Where to look.** `pipeline/bootstrap_gate.py` `amenable_focus()` (the harness that already
  computes partial-r vs amenable - extend it to loop over each care sub-score), `pipeline/diagnostics.py`
  sub-score block, [VALIDATION.md](VALIDATION.md) §1c.
- **Suggested approach.** For each scored care sub-score, compute partial r(amenable | other
  dimensions) with cluster-bootstrap CIs (re-using `amenable_focus` machinery). Report which survive
  on the *independent* outcome. Optionally apply a Benjamini-Hochberg FDR correction across the
  candidate set to quantify the multiplicity the project currently doesn't correct.
- **Acceptance.** A table of each thin sub-score's amenable partial-r + CI; any that collapse get a
  documented caveat (or are reconsidered).
- **Status (2026-06-24): DONE - all four survive.** Added `bootstrap_gate.amenable_subscores()`:
  partial r(amenable | need, vuln) per *scored* care sub-score, cluster-bootstrap (county) CIs, plus
  a **Benjamini-Hochberg FDR** across the four (also lands the B3 multiplicity fix *for this set*).
  Result: `provider_supply` +0.214, `shortage_designation` +0.185, `insurance` +0.042 (thinnest, CI
  [+0.004,+0.082]), `medical_debt` **+0.441 (strongest)** - all q<=0.05, all CIs exclude 0. The
  §1c "selection-soft" caveat on medical_debt is *retired by evidence* (it was the likely artifact;
  it's the strongest replicator). Written to `gate_ci.json` under `amenable_subscores`; documented
  in VALIDATION §4a + §1c; tested in `test_bootstrap_gate.py`. Between-county only (amenable is
  county-level), so it does not speak to sub-county separation - §3 stays that ruler.

### B3 (P3) - Multiple comparisons never formally corrected
- **Problem.** The input-selection ledger ran dozens of candidates against the same 6 outcomes; no
  FDR/Bonferroni correction (acknowledged in [VALIDATION.md](VALIDATION.md) §1c).
- **External.** Benjamini & Hochberg (1995) FDR; standard `statsmodels.stats.multitest`.
- **Suggested approach.** Reconstruct the candidate-test set from [DECISIONS.md](DECISIONS.md), apply
  BH-FDR, and report which survivors hold at a corrected threshold. Mostly a documentation/honesty
  upgrade; pairs with B2.
- **Status (2026-06-24): PARTIALLY DONE; full reconstruction deemed not faithfully reproducible.**
  B2 shipped a real, reproducible **Benjamini-Hochberg FDR** (`bootstrap_gate._bh_fdr` +
  `amenable_subscores`) across the coherent care-sub-score family vs the independent amenable
  outcome - all four survive q<=0.05. That is the part of B3 that can be done honestly from live
  resamples. Reconstructing the *entire historical* candidate ledger (the dozens of rejected probes
  in DECISIONS.md) and FDR-correcting it is **not faithfully reproducible**: the rejected candidates
  did not all record comparable bootstrap test statistics, so any retro-fitted p-values would be
  invented, not measured - which would be less honest than the current explicit §1c disclosure.
  Recommendation: keep §1c's qualitative disclosure + the B2 corrected family; do NOT manufacture a
  full-ledger p-value table. The reusable `_bh_fdr` helper is in place if a future coherent family
  (e.g. a leave-one-sub-score-out gate) is built with real statistics to correct.

### B4 (inherent) - PLACES disease estimates are SES-conditioned
- **Problem.** CDC PLACES is a small-area *model* partly conditioned on socioeconomic structure, so
  the disease↔poverty correlation partly recovers the model's own assumptions (need & vulnerability
  share variance for a partly-circular reason).
- **Where to look.** `pipeline/build_places.py`; [VALIDATION.md](VALIDATION.md) / [METHODOLOGY.md](METHODOLOGY.md)
  limitations.
- **External.** CDC PLACES methodology (cdc.gov/places). Mitigation would mean a non-modeled disease
  source (e.g. claims-based prevalence) - none free at ZCTA. Document as inherent, not fixable here.

### B5 (causal/actionability) - is the index a lever or just a poverty map?
- **Status (2026-06-25): two of three strategies DONE** (`pipeline.validate_placebo`,
  `pipeline.validate_temporal`; [VALIDATION.md](VALIDATION.md) §7). The negative-control test is a
  clean cross-sectional **null** (index predicts preventable = non-preventable deaths); the NY 2014
  event study is **suggestive** (ACSC fell more in high-baseline-uninsured ZIPs post-expansion, DiD
  -36.5/100k·SD, CI excludes 0, survives dropping 2009) but parallel-trends is imperfect, so not proof.
- **B5a (P2) - cross-state DiD with a non-expansion control.** The NY-only event study has no
  never-treated comparison and NY's pre-ACA waiver muted its shock. A non-expansion state's ZIP ACSC
  panel (TX DSHS PUDF is free but ~700MB/year-quarter; only 2019 is cached) would give a proper
  treated-vs-control DiD. **Where:** extend `validate_temporal._fetch_ny_panel` to a multi-state
  panel; reuse the TX PUDF fetcher in `validate_subcounty._fetch_tx_acsc` across years. KFF publishes
  expansion dates (free). Cost is the multi-year TX downloads, not the method.
- **B5b (P3) - provider-entry within-ZIP panel.** NPPES is monthly; a within-ZIP fixed-effects panel
  of `provider_supply` vs subsequent ACSC would test the supply lever the same way §7b tests the
  affordability lever. **Where:** historical NPPES monthly archives (~1 GB each, the heavy part);
  `pipeline/build_providers.py` for the taxonomy classification to reuse.
- **B5c (P3) - MAUP re-zoning robustness.** Classic "ZCTAs are arbitrary areal units" attack. A true
  re-zoning needs the index rebuilt at tract level, but `care_access` (NPPES E2SFCA) has no
  tract-native form, so only need+vulnerability (PLACES/ACS, both publish at tract) can be re-derived
  and crosswalked back - a *partial* MAUP check. **Where:** `pipeline/build_places.py`,
  `pipeline/build_acs.py` (tract geographies), the existing `zcta_tract_xwalk.parquet`. Honestly
  scope it as partial up front, or it over-promises.

---

## C. Coverage / construct gaps (the 5 A's)

Mapped in [METHODOLOGY.md](METHODOLOGY.md) §9a / [VALIDATION.md](VALIDATION.md). 3 of 5 A's are
well-covered; two are genuine holes, both hard to fill from free data.

### C1 (BLOCKED) - Accommodation & Acceptability barely measured
- **Problem.** *Accommodation* (hours, how care is organized) and *Acceptability* (cultural/linguistic
  fit, trust, will-they-see-*you*) are nearly absent. Every free candidate tried was either collinear
  with the deprivation gradient (collapsed in partial-r) or orthogonal-but-unsigned.
- **Where to look.** [DECISIONS.md](DECISIONS.md) "Rejected" rows (FQHC-hours, ACS Medicaid-coverage,
  NY Medicaid-acceptance scrape); `pipeline/build_fqhc.py` (FQHC presence is the only proxy).
- **External / the only remaining lever.** The **scrape-to-calibrate** heuristic (sample real
  provider Medicaid/new-patient acceptance in a few states, regress on held features, predict
  nationally, gate the predicted column). Real provider-directory scraping (state Medicaid enrolled-
  provider lists, e.g. NY Socrata `keti-qx5t`); CMS NDF assignment flag (near-saturated, weak).
- **Status.** Blocked / research-grade. Tested negatives are logged - read them before retrying.

### C2 (P3) - Straight-line distance, not drive-time
- **Problem.** E2SFCA uses haversine (straight-line) catchments, not road-network travel time.
  Adaptive bandwidth is the analog mitigation, but real isochrones would sharpen `provider_supply`.
- **Where to look.** `pipeline/build_supply.py` (`_e2sfca`, `_e2sfca_adaptive`, `config.ADAPTIVE_*`);
  [DECISIONS.md](DECISIONS.md) "Drive-time E2SFCA" rejected row (deemed infeasible without a
  precomputed matrix).
- **External.** OSRM (project-osrm.org) for routing; or a **precomputed national travel-time matrix**
  (e.g. Urban Institute tract-level OSRM travel times) to avoid building a router. A *build* effort,
  not a download. Sharpens supply; does not expand signal (supply is the weakest care sub-score at
  sub-county resolution anyway - VALIDATION §3).
- **Status.** P3 - low ROI given supply's weak sub-county contribution.

---

## D. Engineering / product

### D1 (P2) - Web payload / cold-load weight (the PMTiles item)
- **Problem.** ~16.7 MB `zcta.geojson` (~4.5 MB gzip) + ~30 MB `metrics.json` are loaded eagerly on
  every cold visit (~45 MB parsed to JS objects + Maps). OOM risk on low-memory mobile; the single
  biggest scalability liability. Mitigated (gzip_static, off-main-thread worker parse, hashed
  immutable assets) but not structurally fixed.
- **Where to look.** `frontend/src/lib/data.ts` + `frontend/src/lib/dataWorker.ts` (eager fetch +
  parse); `pipeline/build_geometry.py` (mapshaper simplify); `frontend/nginx.conf` (gzip_static);
  README "Roadmap / honestly not done yet".
- **Suggested approach.** Two tiers. (a) **Quick win:** trim `metrics.json` - it's already rounded to
  1 decimal; drop columns the map/client never reads, or split into a slim coloring payload +
  on-demand detail. (b) **Structural:** vector tiles - `tippecanoe` → **PMTiles** (protomaps) for the
  geometry, served as range-requested tiles instead of one 16 MB blob. Requires a map-layer refactor
  (deck.gl `MVTLayer` / PMTiles source).
- **External.** tippecanoe (github.com/felt/tippecanoe), PMTiles + protomaps (docs.protomaps.com),
  deck.gl tile layers.
- **Acceptance.** Cold-load transfer for geometry drops from ~16 MB blob to range-requested tiles;
  mobile memory stays bounded.
- **Status (2026-06-24): quick-win DONE; structural still open.** Measured the slim payload before
  cutting: 31.3 MB raw is spread *evenly* across ~30 `_pctile` columns (~3% each, no single hog),
  and **gzip_static already ships it at 3.9 MB over the wire** - so the live concern is parsed-object
  memory, not transfer. Audited every slim column against the frontend's dynamic metric keys
  (`metricValue` reads `m[metric]`; selectable set = composite, recomputed coincidence lens,
  `care_access_resid_pctile`, every dimension/sub-score/outcome `_pctile`). Only **one column was
  genuinely dead**: `access_gap_mult_pctile` - the coincidence lens recomputes client-side in
  `scoring.accessGapMult()` from the 3 dimension percentiles, so the precomputed rank was never
  read. Dropped it from `_write_slim_json` (kept in the parquet for the API/CSV): 36→35 cols, 31.3→
  30.3 MB raw, 3.9→3.75 MB gzip, one fewer field per parsed record. tsc + scoring tests green.
  **The remaining columns are load-bearing** (map-coloring by any dimension/sub-score/outcome +
  client reweighting), so further trimming needs the *structural* split (slim coloring payload +
  on-demand sub-scores) or PMTiles for the 16 MB geometry - that is the real lever and stays open.

### D2 (P3) - CSP needs a real-browser verification
- **Problem.** The Content-Security-Policy added to `frontend/nginx.conf` is scoped to the known
  dependencies (Carto basemap, Google Fonts, MapLibre workers/wasm) but was **not** verified against
  a live basemap render (no headed browser in the build session).
- **Where to look.** `frontend/nginx.conf` (the `Content-Security-Policy` header + the inline
  rationale comment).
- **Suggested approach.** Load the prod build in a real browser, confirm the basemap tiles + fonts +
  map workers all load with no CSP violations in the console; tighten or loosen `connect-src` /
  `img-src` / `worker-src` as needed. If `VITE_SENTRY_DSN` / `VITE_ANALYTICS_URL` point off-origin,
  add them to `connect-src`.
- **Acceptance.** Map renders fully under the CSP with zero console violations.
- **Status (2026-06-25): DONE - and it caught a real prod bug.** Headless Chromium (Playwright,
  already used by the e2e suite) IS a real browser, so the "no headed browser" blocker was wrong.
  Added `frontend/scripts/verify-csp.mjs` + `make verify-csp`: serves the built `dist/` with the
  exact `nginx.conf` CSP + security headers, loads it, and fails on any CSP violation, a blocked
  Carto/fonts request, a missing required origin, or a non-rendered canvas. **It immediately found
  that the policy allowed only `*.basemaps.cartocdn.com` while the basemap `style.json` is served
  from the apex `basemaps.cartocdn.com` (a wildcard does not match the apex) - the live basemap
  would have been CSP-blocked in prod.** Fixed nginx.conf to allow both the apex and the wildcard
  in `img-src` + `connect-src`; re-run is clean (0 violations, basemap + fonts load, canvas paints).
  Wired into `make prod-check` and a non-blocking CI `csp` job (external CDN -> `continue-on-error`).

---

## How to use this doc
- Treat each ticket as a unit of work; update its **Status** as you go and move completed ones into
  [DECISIONS.md](DECISIONS.md) (the permanent ledger) with the result + numbers.
- For anything touching scores (A2, B2), the gate discipline at the top is mandatory.
- Anything marked **BLOCKED** needs external data or a maintainer decision - don't burn cycles trying
  to force it headlessly; the blockers are real (restricted microdata, click-through agreements, no
  free source).

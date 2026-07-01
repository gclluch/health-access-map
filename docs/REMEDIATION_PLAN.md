# Remediation Plan - staff-level review follow-up

Ten tickets from the 2026-06-30 review. Sequenced so the test foundation (T7) lands before any
change that moves a published number. Each ticket: **Objective / Steps / Files / Acceptance /
Effort / Risk / Depends-on**. Effort is for one engineer; frontend (T2,T5,T8) and pipeline
(T1,T3,T4,T6,T7,T9) tracks can run in parallel after T7.

Legend: effort S (<1d), M (1-3d), L (3-5d), XL (>1w).

**Status (2026-06-30): 10 of 10 done.** ✅ T7 (`4dfe789`), T1 (`c5f4178`), T3 (`44e2ac9`), T6 (`843301c`),
T2 (diagnostic `c388903` + gate), T5 (headline decomposition), T4 (MOE band - core already shipping;
provenance decomposition + explicit "tied" added). Phase 3 complete: **T8** (`3c18182`) split the client
`metrics.json` into a columnar first-paint `map_frame.json` + lazy `subscores.json` (first-interactive
gz transfer 5.0 MB → 2.0 MB); **T9** (`ad9021a`) stamps `meta.json` + `deploy-manifest.json` with a
per-payload sha256 + pipeline git SHA + provenance digest; **T10** (`9779841`) collapsed the dead
dynamic-API branch so the static per-ZIP3 shards are the sole prod data path. The coordinated doc pass
(README + `VALIDATION.md` §5/§6d + the in-product methodology panel) is **done** - all Phase-2 framing
(T1/T3/T6) and product (T2/T5/T4) changes are reflected in one consistent published story.

---

## Phase 1 - Foundation (do first; unblocks safe methodology changes)

### T7 - Test the statistical core  [High] [L] [depends: none]
**Objective.** Regression-protect the code that generates every headline statistic. Today
`validate_*`, `bootstrap_gate`, `diagnostics` are verifiable only by running against live data.

**Steps.**
1. `tests/test_validation_stats.py` - unit-test `pearson_corr`, `weighted_corr`, `within_residual`,
   partial-corr against closed-form / numpy-reference values on seeded synthetic arrays. Cover NaN
   masking, the `min_pairs` floor (50 default, 100 in the diagnostics wrappers), zero-variance -> nan.
2. Synthetic fixtures (`tests/factories.py`): seeded generators with *known* structure -
   - correlation panel: `y = a*x + noise`, known r;
   - DiD panel: `rate_it = α_i + γ_t + δ·treat_i·post_t + ε`, known δ;
   - partial-r frame: `y = β1·c + β2·z + ε`, c ⟂ z, known partial.
3. `tests/test_diagnostics.py` - feed a synthetic metrics frame; assert `_corr`, `_mean_r`, and the
   drop-dimension margins move in the known direction (adding a predictive dim raises mean_r).
4. `tests/test_bootstrap_gate.py` - small `n_boot`, fixed seed; assert the cluster-bootstrap CI
   brackets the injected effect and *excludes* 0 under strong signal, *includes* 0 under a null.
5. `tests/test_temporal.py` - assert `_did_coefficient` and `_cluster_bootstrap` recover the injected
   δ within tolerance; `_triple_diff` recovers an injected triple interaction; `_event_study` betas.
6. `tests/test_subcounty.py` - `_score_cols`, `_tract_to_zcta` population-weighting, O/E on synthetic.
7. **Refactor for testability where needed:** split any remaining `fetch+compute` functions into
   `_fetch_*` (network) and a pure `_compute_*(frame)` so the compute path tests without network.
8. Wire all of the above into the CI `pytest` job (no network/data needed -> runs in CI).

**Acceptance.** A deliberately introduced sign flip in `pearson_corr` fails a test; CI exercises the
stat kernels; coverage of the compute functions in `validate_*`/`bootstrap_gate`/`diagnostics`.

---

## Phase 2 - Methodology truth (changes published numbers; needs T7 first)

### T1 - Stop leading with county-broadcast-inflated validity  [High] [M] [depends: T7]
**Objective.** Report validity at the resolution the outcome actually has.

**Problem.** County outcomes (life_expectancy, premature_death, infant_mortality, amenable_mortality,
preventable_hosp) are broadcast to ~33k ZCTAs then correlated at ZCTA level -> replication shrinks
CIs and inflates r. Headline `0.95` reliability and `r=0.503` (N=33176) overstate precision.

**Steps.**
1. Tag each outcome `county`|`zcta` (PLACES-derived flu/mammography are genuinely ZCTA).
2. In `diagnostics.py`/`bootstrap_gate.py`, make the **primary** reported figure for county-origin
   outcomes the **county-collapsed, population-weighted** correlation (already computed: r≈0.547,
   N=3225) and the **state-blocked** CI (`[0.334,0.455]`). Keep ZCTA-broadcast as a clearly-labelled
   "upper bound, inflated by within-county replication" secondary.
3. Relabel split-half 0.95 precisely as **internal reliability**, not "validated against outcomes"
   (it is internal consistency, a different claim).
4. Propagate the corrected framing to README "What it is", `VALIDATION.md §4`, and the in-product
   methodology panel - lead with the conservative numbers.

**Acceptance.** README/methodology lead with county-collapsed r + state-blocked CI; ZCTA-broadcast is
explicitly an upper bound; a gate test asserts the reported headline uses the clustered/collapsed value.

### T3 - Collapse the dimensionality theater; demote county-only sub-scores  [High] [M] [depends: T7; informs T1]
**Objective.** Be honest that the index is ~one factor, and stop county-level rows masquerading as
sub-county dimensions.

**Problem.** PC1 = 76%, ~1.6 effective dims, re-weighting moves ranks by Spearman 0.999. Several
sub-scores (`medical_debt`, `shortage_designation`, FQHC distance, partly `insurance`) are county-level
- the sub-county validator shows them at ~0.000 within-county - so they pad apparent dimensionality
while adding zero sub-county signal.

**Steps.**
1. Add `resolution: county|zcta` to each measure in `taxonomy.py`.
2. Pipeline diagnostic: confirm `corr(additive composite, PC1) > 0.99`; emit it to `provenance.json`.
3. UI: render county-resolution rows under a "context (county-level)" group, excluded from any
   sub-county discrimination claim; keep them visible, not scored as sub-county signal.
4. Decision (run gate both ways, report delta): does `provider_supply` (mean|r| 0.273) and the
   county rows deserve equal dimension weight, or move to context? Pick based on the gate impact.
5. Make the "this is ~one deprivation gradient; sliders are a sensitivity probe" statement primary in
   the methodology panel, not a footnote. Consider offering PC1 (or the geometric-mean lens) as the
   default headline, since it is the only lens that breaks collinearity.

**Acceptance.** Taxonomy carries per-measure resolution; UI separates county-context rows; docs state
effective dimensionality plainly; diagnostic shows composite≈PC1.

### T6 - Reframe the causal lever as inconclusive  [Med] [S] [depends: T7 lightly]
**Objective.** Stop framing a broken-pre-trend DiD as "a step toward causal."

**Problem.** The NY DiD has non-flat pre-trends (2009 spike; parallel-trends = False) and the
cross-state falsification (NY vs TX) already overturns it. "Toward causal" overclaims.

**Steps.**
1. Implement an explicit pre-trends test (joint F on pre-period event-study coefficients); report p.
2. Make the verdict string **data-driven** from that test, not editorial - currently the code prints
   "suggestive lever effect" while also printing `parallel-trends clean = False`.
3. Rewrite `VALIDATION.md §7` + methodology panel: placebo null + falsified lever => "descriptive,
   not a demonstrated causal lever," full stop.

**Acceptance.** No doc/UI text claims movement toward causal; the verdict is computed from the
pre-trend test; §7 reads cleanly as descriptive-only.

### T2 - 2-of-3 dimension comparability  [High] [M] [depends: T7]
**Objective.** Stop co-ranking 2-dim and 3-dim composites as equivalent.

**Problem.** `accessGap` renormalizes weights over present dimensions and ranks 2-dim ZCTAs alongside
3-dim - renormalization matches the *scale*, not the *estimand* (different bias/variance).

**Steps.**
1. Diagnostic first: quantify how many ZCTAs are 2-dim and whether their missingness is MNAR (likely
   rural / low-data -> systematic). Report in `provenance.json`.
2. Headline rankings: default to `n_dims_scored == 3`; expose 2-dim as a separate, flagged tier.
   Backend `rankings` already filters - add the option and set the headline default.
3. Map: keep 2-dim coloured but visually distinct (hatch / reduced saturation) and excluded from the
   "reliable rank band."
4. (Optional, defer) imputation of the missing dimension from the other two (collinearity 0.73 makes
   it predictable) - only if product needs 2-dim ranked; adds model risk, mark imputed.

**Acceptance.** Headline list excludes/visually separates 2-dim; diagnostic reports count + MNAR check.

### T5 - Decompose the headline; reduce single-number misuse  [Med] [L] [depends: none hard; pairs with T3]
**Objective.** Lead with the need/access split, not one conflated number (a 95 can be all-need or
all-no-providers - different interventions).

**Steps.**
1. Detail headline leads with the 3-dimension breakdown; composite becomes secondary "screening
   priority," never "how bad."
2. Add a need-vs-access **quadrant** (or profile chip: need-driven / access-driven / both) -
   `synthesis.ts` already computes the dominant driver; promote it to a primary signal.
3. Copy: the composite is a prioritisation screen, not a verdict.

**Acceptance.** Headline UI leads with the decomposition; a need-driven vs access-driven ZIP are
distinguishable at a glance; composite framed as screening only.

### T4 - Magnitude + ACS MOE propagation into displayed ranks  [Med] [L] [depends: T7]
**Objective.** Show per-ZIP uncertainty; stop implying exact ranks.

**Steps.**
1. Ingest ACS margins of error (the `_M` columns) for key rate measures in `build_acs.py`.
2. Monte-Carlo per ZCTA: sample each measure ~ Normal(est, MOE/1.645), recompute the percentile rank,
   take the 90% interval of the rank. Extend the existing Saisana/rank-uncertainty MC from
   gate-level to **per-ZCTA**, store the band in `metrics.parquet`.
3. UI: detail panel shows "78th, reliable range 70-86" per ZIP; "tied with" when bands overlap; map
   can de-emphasise high-uncertainty ZIPs.

**Acceptance.** Per-ZIP rank interval derived from MOE MC is stored and shown; overlapping bands read
as tied.

---

## Phase 3 - Engineering / systems (independent of Phase 2)

### T8 - Kill the 30 MB JSON client parse  [Med] [L] [depends: none]
**Objective.** Cut cold-load payload + parse cost (hard scale ceiling on mobile/cellular).

**Options (ranked).**
- (b, recommended) Ship a compact **typed-array "map frame"** (zcta ids + the ~5 percentile columns
  the default map needs, as Float32/Int8) for first paint; lazy-load everything else per-ZIP via the
  existing shards (`apiZcta`). The map only needs a few columns × 33k -> tiny.
- (a) Columnar binary (Arrow IPC / Parquet via apache-arrow-js or DuckDB-WASM) - biggest win, most work.
- (c) Quick win first: prune `metrics.json` to client-used columns + reduce numeric precision; rely on
  Netlify brotli. Could halve it in hours; ship as a stopgap before (b).

**Steps.** Define the map-frame schema in the pipeline (`build_*`/join step) -> emit a binary; rewrite
`data.ts`/`dataWorker.ts` to parse typed arrays; keep `metrics.json` only for non-default columns or
drop it. Measure cold-load transfer + TTI on throttled 4G before/after.

**Acceptance.** First-interactive transfer < ~5 MB; TTI improved measurably; drill-down still complete
via shards; e2e + `verify-csp` still pass.

### T9 - Data deploy provenance / governance  [Med] [M] (stopgap) / [XL] (full CI) [depends: none]
**Objective.** Know exactly what data is live; make data deploys reproducible and auditable.

**Steps.**
1. Stamp builds: extend `meta.json` with a content hash per payload + the pipeline git SHA + a
   `provenance.json` digest; expose it at a `/version` route the deployed site serves.
2. Deploy record: emit a `deploy-manifest.json` (payload hashes + timestamp + git SHA) and/or put the
   hashes in the Netlify deploy message so a live deploy is traceable to a data vintage.
3. Lock resolved dataset IDs/vintages per build (they resolve-at-runtime with assertions today) so a
   rebuild is reproducible given stable upstreams.
4. (Optional, XL) Scheduled CI that rebuilds data, runs `make acceptance` + `make gate` +
   `make verify-csp`, and only then deploys - removes the local-machine path. Needs API keys as
   secrets + multi-GB downloads (self-hosted runner likely).

**Acceptance.** The live site exposes its data vintage + content hash; a manifest records what shipped;
rollback is traceable to a vintage.

### T10 - Resolve the dual data path  [Low] [S] (static-only) / [M] (deploy API) [depends: T8 decision]
**Objective.** One data path in prod; remove dead/undeployed complexity (`apiZcta` falls back to
static shards because the FastAPI backend is not deployed; `VITE_API_BASE` is unset).

**Decision.** Static-only (recommended, matches the free-hosting model) **or** actually deploy FastAPI.
- Static-only: drop the API branch from `api.ts`; keep `backend/` clearly labelled dev-only (or remove);
  shards already cover drill-down. If T8 goes DuckDB-WASM the backend becomes fully redundant.
- Deploy API: host on a scale-to-zero free tier, set `VITE_API_BASE`, enable the commented netlify
  `/api` proxy, add the origin to CSP `connect-src`, add uptime monitoring.

**Acceptance.** One prod data path; no dead branch in `api.ts`; README states the deployment model
unambiguously.

---

## Sequencing & roll-up

```
Phase 1:  T7  ─────────────────────────────► (gates Phase 2)
Phase 2:  T1 ─ T3 ─ T6  (truth/framing)  then  T2 ─ T5 (product)  then  T4 (uncertainty)
Phase 3:  T8 ─ T9 ─ T10  (independent; can run alongside Phase 2 on the frontend track)
```

- Coordinate the doc rewrites (README, `VALIDATION.md §4/§7`, methodology panel) into **one** pass
  after T1/T3/T6 land, so the published numbers/claims change exactly once.
- Total ≈ 3-5 focused weeks solo; less if frontend (T2,T5,T8,T10-fe) and pipeline (T1,T3,T4,T6,T7,T9)
  run in parallel.
- Highest leverage: **T7** (everything else is only trustworthy once the stats core is tested).

---

## Detailed execution plans (2026-06-30 refresh) - remaining six tickets

Code-anchored, grounded in the current tree. Tracks parallelize: **pipeline** (T4-pipeline, T9) and
**frontend** (T2, T5, T8, T10) overlap little and can run in separate worktrees. All Phase-2 tickets
are unblocked (T7 done).

### T2 - 2-of-3 dimension comparability  [M]  [deps: T7 ✓]  ✅ DONE
**Done.** (1) `selection_diag._two_dim_mechanism` characterizes the missingness as MNAR (764 partial /
2.3%, all missing health_need, median pop 43 vs 2930, 83.5% low-confidence, composite d +0.27) →
`selection` block in provenance. (2) `data.rankings(min_dims=3)` + `main.get_rankings` gate the
headline to 3-of-3, composite-family only (`_COMPOSITE_FAMILY`). (3) `RankingsList` drops partial from
the headline band on composite lenses; (4) `MapView` desaturates partial ZCTAs (alpha 80 vs 158) and
`Legend` carries a "partial score (2 of 3)" chip; the `DetailPanel` banner already warned. (5) tests:
backend `test_rankings_excludes_partial_dims_by_default` / `_partial_gate_is_composite_only`, frontend
`types.test.ts`. **Decision:** silent headline exclusion (matches `institutional`/`low_confidence`); no
ranked partial tier - partial ZCTAs stay map-visible + clickable. Imputation deferred (model risk).

**Original plan.** `join_and_score.py:266-275` renormalizes weights over present dims, so a 2-dim score is
co-ranked with a 3-dim one - same scale, different estimand (bias/variance). `n_dims_scored` already
exists (`join_and_score.py:286-291`); the DetailPanel banner already warns (`DetailPanel.tsx:584-589`).
1. **Diagnostic first** (`selection_diag.py`): count 2-dim scoreable ZCTAs; test MNAR (cross-tab vs
   population / rurality / state). Emit a `two_dim` block to provenance + meta - the evidence for the UI call.
2. **Backend** (`data.py:rankings`, `main.py:get_rankings`): add `min_dims` param beside
   `include_low_confidence`; headline defaults to `n_dims_scored == 3`.
3. **Frontend** (`RankingsList.tsx`, `store.ts`): headline excludes 2-dim; flagged "partial" tier toggle.
4. **Map** (`MapView.tsx`, `Legend.tsx`): 2-dim ZCTAs hatched / desaturated, out of the reliable band.
5. **Tests:** backend `rankings(min_dims=3)` excludes 2-dim; pipeline MNAR diagnostic on a synthetic frame.
**Accept.** Headline excludes/separates 2-dim; diagnostic reports count + MNAR. **Risk:** low (additive).
**Defer:** imputing the missing dim (model risk).

### T5 - Decompose the headline; reduce single-number misuse  [L]  [pairs with T3 ✓]  ✅ DONE
**Done.** (1) `synthesis.profile(m)` → `need-driven | access-driven | both`, decided on the percentile
gap between the need side (health_need + social_vulnerability) and the access side (care_access);
`both` distinguishes the compounding (both-high) from the no-dominant-lever case. (2) `DetailPanel`
leads the body with a color-coded `ProfileChip` (violet need / blue access / amber both) + one-line
lever blurb, ABOVE the composite. (3) the composite number is reframed: label "screening priority"
(was "disadvantage rank") + "a prioritization screen, not a verdict" copy; `DriversSection` breakdown
unchanged below. (4) tests: `synthesis.test.ts` profile cases incl. same-composite need-vs-access
divergence. Verified in-browser on 02301 Brockton (need-driven) vs 76054 Hurst (access-driven) -
distinguishable at a glance. **Deferred:** the optional "color by profile" map lens (step 3) - adds a
metric column; not needed for the acceptance.

**Original plan.** A 95 can be all-need or all-no-providers - different interventions. `synthesis.ts` already
computes the dominant driver; `DriversSection.tsx` renders share bars. T5 promotes the split.
1. **Headline reorder** (`DetailPanel.tsx:591-660`): lead with the 3-dim breakdown / `DriversSection`;
   demote the composite number to a secondary "screening priority."
2. **Profile chip** (`synthesis.ts` → `profile(m)`: `need-driven | access-driven | both`): primary,
   color-coded, near the headline (high-need × high-barrier quadrant logic).
3. **(Optional)** "color by profile" map lens (`MetricSelect.tsx`).
4. **Copy pass:** composite = prioritization screen, not a verdict.
5. **Tests:** extend `synthesis.test.ts` (need-driven vs access-driven fixtures → distinct profiles).
**Accept.** Headline leads with decomposition; profiles distinguishable at a glance. **Risk:** medium -
reshapes the most-viewed surface; verify with Playwright on contrasting ZIPs.

### T4 - ACS MOE → per-ZIP rank intervals  [L]  [deps: T7 ✓]  ✅ DONE (core was already shipping)
**Finding.** The MOE→per-ZIP-rank-band the plan describes was already built, shipping, AND SE-calibrated:
`build_acs._proportion_se` computes real per-rate SEs from published MOEs → summarized into
`acs_input_cv` → `_rank_uncertainty`/`_noise_sigma` propagate it into `access_gap_rank_lo/hi` (shown as
"Reliable range") → `verify_bands.gate3_calibration` already does the exact per-member SE-resample MC
("rate + N(0,1)·se", re-percentile member→sub-score→dim) and asserts the injected σ matches within
±20%. A separate `access_gap_moe_lo/hi` band would be redundant with (and risk contradicting) the
shipped combined band; the plan's own step 3 recommends one combined "reliable range" (which exists).
**Done (additive only, per the scope decision).** (1) `_rank_band_decomposition` (join_and_score) splits
the shipped band into re-weighting vs ACS/PLACES measurement-error shares → `rank_band` block in
provenance (low-conf measurement contribution ≈16.4 pts vs ≈3.0 high-conf - auditable, not asserted);
`_rank_uncertainty` gained an `add_noise` flag to isolate the weight-only band. (2) `CompareTray` now flags
overlapping reliable ranges as explicitly **"Statistically tied"** (was implicit in the footnote). (3) tests:
`tests/test_rank_band.py` (measurement noise only widens; share monotone in input noise). Verified
in-browser on 91201 Glendale ≈ 91401 Van Nuys (overlapping bands → tied). **Not done (deferred):** a
separate stored measurement-only per-ZIP band (redundant); the existing combined band is the reliable range.

**Original plan.** `build_acs.py` ALREADY computes per-ZCTA SEs (`_moe`, `_proportion_se`, `ACS_MOE_Z=1.645`) for
shrinkage; a weight-based band already ships (`_rank_uncertainty` → `access_gap_rank_lo/hi`). T4 adds the
measurement-error band.
1. **Persist SEs** (`build_acs.py`): surface `_SE` columns for the key scored rates into the joined frame.
2. **Per-ZCTA MC** (extend `join_and_score._rank_uncertainty`): B≈500 draws ~ Normal(est, SE), re-rank
   composite, store the 5-95 rank interval (`access_gap_moe_lo/hi`) in parquet + slim JSON.
3. **Decision:** combine MOE⊕weight into one "reliable range" (recommended), store both for provenance.
4. **UI** (`DetailPanel.tsx:ComparisonFrame`): "78th, range 70-86"; "tied with" on overlap.
5. **Tests:** high-SE ZCTA → wider band than low-SE (monotone in SE).
**Accept.** Per-ZIP MOE interval stored + shown; overlapping bands read as tied. **Risk:** medium -
MC×33k×B re-rank runtime (vectorize, cap B); band must not contradict the weight band. Coordinate cols w/ T8.

### T8 - Kill the 30 MB JSON client parse  [L]  [independent]  ✅ DONE (`3c18182`)
**Done.** Two-tier columnar payload: `_write_map_frame` emits `map_frame.json` (18 first-paint cols,
struct-of-arrays, int-quantized pctiles); `_write_subscores` emits `subscores.json` (14 sub-score
lenses + life-expectancy), fetched lazily by `store.ensureSubscoreColumns()` on first sub-score lens
select and merged onto the `SlimMetric` records - the store API is unchanged so map/rankings/legend are
untouched. `data.ts`/`dataWorker.ts` reconstruct records via `framesToRecords`; `metrics.json` removed.
Measured first-interactive gz transfer 5.0 MB → 2.0 MB (map frame 0.72 MB vs old 3.75 MB), sub-scores
0.60 MB deferred off the cold path. Fixture/CSP/Dockerfile/gitignore updated; new tests
`data.test.ts`/`store.test.ts`/`lazy-subscores.spec.ts`/`test_slim_payload.py`; e2e + verify-csp green.
Decision: static-only shard drill-down unaffected; binary blob deferred (columnar JSON captured the win).
**Sizes (verified 2026-06-30 build):** `metrics.json` **30 MB** (33,791 records × 36 cols),
`zcta_overview.geojson` **7.2 MB**, `zcta/` drill-down shards **135 MB total** (~150 KB per zip3).
**Recon corrections (the original notes below were stale - re-verified):**
- The parse is **already off-main-thread**: `data.ts:loadViaWorker` runs in `dataWorker.ts`, falling back to
  `loadOnMainThread`. So the problem is the **30 MB transfer + parse memory/time on cellular**, NOT a blocked
  UI thread. Frame the win as transfer bytes + TTI, not jank.
- Drill-down shards **already exist and lazy-load**: `api.ts:loadShard` fetches `/zcta/{zip3}.json` per click
  (static path, no backend). The DetailPanel's deepest measures already come from this `rec`, not the slim metric.
- **CONSTRAINT (the trap):** the map can color by **any** metric in `ALL_METRICS` (`types.ts`), which includes the
  **14 sub-score `_pctile` columns** (`MetricSelect`). `MapView`/`Legend`/`RankingsList` read them straight off the
  in-memory slim `metrics` map (`metricValue → m[metric]`). So sub-score columns **cannot be naively dropped** -
  doing so breaks every sub-score map/legend lens. They must be lazy-loaded *as map columns*, not just per-ZIP.

**Plan.**
1. **Baseline** transfer (brotli) + TTI on throttled 4G; record in provenance/PR.
2. **(c) stopgap, ship first (~hours):** in `_write_slim_json`, quantize the percentile columns (`*_pctile`,
   tier, band lo/hi) to integers (they're 0-100; already `round(1)`) - Int saves bytes + parses faster; keep
   geography/flags. Lean on Netlify brotli. Measure. Expect a modest (~20-35%) cut, not the headline win.
3. **(b) the real win - two-tier payload:**
   - Emit a compact **map frame** (sibling to `_write_slim_json`) = first-paint columns only: `zcta5` + the 3
     dimension pctiles + `access_gap_pctile`/`within_state`/`resid`/`tier` + flags (`scoreable`,`low_confidence`,
     `institutional`,`n_dims_scored`) + label strings (`city`,`state`,`county_name`,`population`). As JSON-of-typed-
     arrays or a binary blob (Int16 pctiles, Int8 flags). This is what the default map + rankings + legend need.
   - Move the **14 sub-score `_pctile` columns** into a **separate columnar payload** (`subscores.json`/`.bin`)
     fetched lazily the first time a sub-score map metric is selected (extend the store: `ensureSubscoreColumns()`
     merges them into the `metrics` map). The DetailPanel drill-down already uses shards, so per-ZIP detail is
     unaffected.
   - Rewrite `data.ts`/`dataWorker.ts` to parse the map frame; **keep the store API (`SlimMetric` map) unchanged**
     so `MapView`/`RankingsList`/`Legend`/`scoring.ts` don't change. Sub-score columns arrive later and are merged.
4. **Verify:** `e2e/smoke.spec.ts` + `compare.spec.ts` + `make verify-csp` (worker-src/script-src `'self'` - keep
   the binary same-origin, no CDN worker); measure transfer + TTI before/after.
**Accept.** First-interactive transfer < ~5 MB; TTI improved on 4G; sub-score lenses + drill-down still work; e2e +
verify-csp green. **Risk:** med-high (core load path). Do (c) first as a safe stopgap; land (b) behind it.
**Coordinate:** T4 (don't bloat the frame - band lo/hi stay in the frame; the `rank_band` provenance block is build-
side only) and T10 (the static shard path is the prod path).

**Original (stale) notes:** ~~recon found no worker file~~ (wrong - `dataWorker.ts` exists); ~~prune to client-used
columns~~ (most slim cols ARE client-used; the sub-score cols need lazy *column* loading, not deletion).

### T9 - Data deploy provenance / governance  [M stopgap / L full]  [independent]  ✅ DONE (`ad9021a`)
**Done.** `_write_public_meta` now stamps a `build` block into `meta.json` (frontend-fetched): the
pipeline git SHA (`git rev-parse HEAD`, or `HAM_BUILD_SHA` for CI), a streamed sha256 per shipped
payload (`map_frame.json`, `subscores.json`, `zcta_overview.geojson`, `zcta.pmtiles`), and the
`provenance.json` digest. Also emits `deploy-manifest.json` (served static) as the ops record of what
shipped. The freshness badge tooltip surfaces the short build SHA. Test:
`test_public_meta_stamps_build_hashes_and_manifest` (hashes present + content-change flips the hash).
Deferred (optional/XL): the `/version` backend route (T10 is static-only) and scheduled rebuild CI.
**Why.** No way to know what data is live or to reproduce a build. `meta.json` (`_write_public_meta`) today carries
`generated` + `vintages` + counts, but **no content hash and no git SHA**; `backend/main.py` only has `version="1.0.0"`.
1. **Stamp** (`join_and_score._write_public_meta`): add a sha256 per shipped payload (`metrics.json`, the new map
   frame, `zcta_overview.geojson`, `zcta.pmtiles`), the pipeline **git SHA** (`git rev-parse HEAD`, or a build env
   var so it works in CI), and a `provenance.json` digest. Write these into `meta.json` (already frontend-fetched
   by `store.ts`) and surface a small "data vintage + build" line in the methodology panel / footer.
2. **`/version`:** the `meta.json` above IS the static version doc; optionally add a `backend/main.py` `/version`
   route returning the same dict (only if T10 deploys the API - otherwise skip).
3. **Deploy record:** emit `deploy-manifest.json` (payload hashes + timestamp + SHA) and/or put the short SHA +
   hashes in the Netlify deploy message so a live deploy is traceable to a data vintage.
4. **Lock** resolved dataset IDs/vintages per build (`config.PLACES_DATASET_ID` etc. resolve-at-runtime with
   assertions today) so a rebuild is reproducible given stable upstreams.
5. **(Optional, L)** scheduled CI: rebuild → `make acceptance`/`gate`/`verify-csp` → deploy (needs API keys as
   secrets + multi-GB downloads → self-hosted runner). Defer.
**Accept.** Live site exposes vintage + content hash; a manifest records what shipped; rollback is traceable to a
vintage. **Risk:** low (additive). **Note:** `data/processed/*` + `frontend/public/metrics.json` are **gitignored**
(built locally), which is exactly why the stamp matters - the live bytes are otherwise untraceable to a commit.

### T10 - Resolve the dual data path  [S static / M deploy]  [deps: T8 decision]  ✅ DONE (`9779841`)
**Done (static-only).** Removed the `VITE_API_BASE`/`API_BASE` env branch from `api.ts` (+ the env
declaration in `vite-env.d.ts`). `apiZcta` was already shard-backed; `apiCompare` (which had *no* working
prod path - it always hit the down `/api/compare`, the e2e ECONNREFUSED) now enriches best-effort from the
same per-ZIP3 shards, so there is genuinely one prod data path and compare works in prod. `backend/`
labelled dev/test-only in the README + the static-only deploy model stated unambiguously (diagram + a
"Deployment model" note). Test `api.test.ts` guards shards-not-`/api`. Deferred: deploying the FastAPI API.
**Why.** `api.ts` has a dead `VITE_API_BASE` branch (the FastAPI backend is **not deployed**; `VITE_API_BASE` is
unset). `apiZcta` (line ~60: `if (API_BASE) return getJson('/api/zcta/{z}')`) and `apiCompare` always fall through
to the static `/zcta/{zip3}.json` shards. `netlify.toml` has the `/api/*` proxy + the API origin in `connect-src`
**commented out**. So prod is already static-only; the API path is dead weight + a misleading affordance.
- **Static-only (recommended):** delete the `API_BASE` env branch from `api.ts` (the `${API_BASE}` prefix in
  `fetchJsonOnce` + the `if (API_BASE)` in `apiZcta`); keep the shard path as the single prod data path; mark
  `backend/` clearly dev/test-only in the README (the FastAPI app is still exercised by `tests/test_backend.py`,
  so keep it - just label it). Leave the commented netlify `/api` block as documented-but-off, or remove it.
- **Deploy API (alt, only if a live dynamic API is actually wanted):** host on a scale-to-zero free tier, set
  `VITE_API_BASE` at build, enable the netlify `/api` proxy, add the origin to CSP `connect-src`, add uptime
  monitoring. More surface for no current need - **not recommended**.
1. Remove the env branch from `api.ts`. 2. Label `backend/` dev-only in README ("Production & ops"). 3. README
   states the static-only model unambiguously (it currently hedges).
**Accept.** One prod data path; no dead branch in `api.ts`; README unambiguous. **Risk:** low. Do after T8 confirms
the shard path stays the drill-down source (it does, in plan (b) above).

**Sequence (complete):** **T8** (`3c18182`) → **T9** (`ad9021a`) → **T10** (`9779841`), all landed on master.
All three were Phase-3 engineering and touched **no published numbers**. With Phase 1 (T7), Phase 2
(T1/T2/T3/T4/T5/T6) + the coordinated doc pass already done, **all 10 remediation tickets are complete.**

# Remediation Plan - staff-level review follow-up

Ten tickets from the 2026-06-30 review. Sequenced so the test foundation (T7) lands before any
change that moves a published number. Each ticket: **Objective / Steps / Files / Acceptance /
Effort / Risk / Depends-on**. Effort is for one engineer; frontend (T2,T5,T8) and pipeline
(T1,T3,T4,T6,T7,T9) tracks can run in parallel after T7.

Legend: effort S (<1d), M (1-3d), L (3-5d), XL (>1w).

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

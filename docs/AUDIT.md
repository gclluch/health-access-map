# Full-repository audit

Two-lens critical audit of every tracked file (153 files), conducted by seven parallel deep-audit passes.
Each file was read line-by-line under both lenses:

- **ENG** - staff software engineer (system design, best practices, stdlib/pandas/numpy idioms, runtime & memory, correctness, security, reproducibility).
- **STAT** - PhD statistician / econometrician / population-health data scientist (scoring math, weighting, missing data, small-area estimation, causal inference, multiplicity).

Findings are verified against the actual code. `UNVERIFIED` marks a suspicion that could not be confirmed within scope.
116 findings total. Severity: CRITICAL / HIGH / MEDIUM / LOW.

---

## Progress & handoff (last updated by remediation pass 2)

**30 findings fixed and verified so far.** Verification: frontend `tsc --noEmit` clean + 48 vitest tests pass (4 new); Python 130 tests pass. Nothing committed yet.

Pass-2 additions (safe component/a11y): §6.9 CompareTray severity word (non-hue CVD cue) · §6.10 Tip `aria-haspopup`/`aria-expanded` · §6.7 DetailPanel resize-drag listeners cleaned up on unmount (`pointercancel` + teardown ref) · §6.1 (partial) store `hover` no-op-write guard.

Pass-3 (user-decided): **§5.6 → make `profile()` weight-aware** (now takes weights, reads from store in ProfileChip; +1 test proving it responds to re-weighting). **§3.2 → ship UNWEIGHTED anchored preset** (`validate.py` `weights` = unweighted corr; pop-weighted kept as `weights_popw` sensitivity). ⚠️ **`weights.json` on disk is still the old pop-weighted build** - it regenerates only on the next `validate.build()` run (needs `metrics.parquet`); until then the frontend ships stale presets. Also stale: `docs/VALIDATION.md:757` still names `weights_unweighted` (renamed to `weights_popw`) - fold into the §7.2/§7.3 doc-drift cleanup.

Pass-4 (code done, **browser-verified** at localhost:5173): **§6.1 MapView field selectors** (whole-store destructure → per-field selectors) - app renders, hover tooltip + accent border track the cursor, no console errors. **§6.5 methodology modal marks background `inert`** (ref-toggled wrapper in App.tsx; modal moved outside it) - JS-confirmed: dialog open & not inert, map behind IS inert, no horizontal overflow; Esc closes and inert clears. §5.6 profile chip also confirmed rendering live.

Still open: **§6.2 MapView hover highlight** - the fill recompute is already isolated from hover (`getFillColor` keyed on `[metric,weights,scale]`), so the residual cost is line-buffer re-uploads. The audit's fix (deck.gl `autoHighlight`) changes the hover look from an accent *border* to a fill *tint* - a design call, left for a decision + browser. **§6.13** shared quantile selector - bundle with it.

Pass-5 (bug caught in live review + doc-drift): **synthesize() "roughly equally" bug** - it compared only the top two dimension shares, so a near-tied pair over a trailing third (40/37/23) mislabeled as "driven roughly equally"; now emits "driven mainly by X and Y" unless all three shares are within 10 points (+2 tests, verified live). **Doc-drift §7.2/§7.13/§7.18/§7.20**: RATIONALE dental/maternity/telehealth are scored (not "not yet in"); RATIONALE §12 safety-net marked superseded/unscored with the shipped `safetynet_barrier` definition; RATIONALE §10 weights 60/20/21→60/19/21 (sum 100); README HPSA reworded (it's a scored input, hence not an independent anchor); VALIDATION.md updated to unweighted presets + `weights_popw` rename; new `test_taxonomy_counts_match_docs` guards 14 sub-scores / 12 scored / 3 dims.

### Manual verify (localhost:5173, ~60s) for pass-4
1. Hover across many ZIPs fast → no new jank; tooltip + accent border still track the cursor.
2. Drag the weight sliders → map recolors; open Compare tray, add/remove ZIPs → map unaffected.
3. Open "How to read this" → Tab stays trapped in the dialog; VoiceOver (Ctrl+Opt+arrows) can't reach the map/rankings behind it; Esc closes and focus returns.
4. Confirm no layout shift when the modal opens (the new wrapper div is static/zero-size).

### DONE ✅
- **Tier 1 (all 6):** §2.7 `is False` dead check · §5.3 colors empty-domain crash · §1.2 state-from-`county_fips` (+ new `FIPS_STATE`/`fips_to_state` in `zip_states.py`) · §5.4 worker timeout · §4.14 backend cache key · §6.11 life-expectancy format.
- **Frontend logic:** §5.2 `buildScoreIndex` now excludes institutional/low-confidence/2-of-3-partial · §5.9 new tests for `buildScoreIndex`+`percentileOf` · §5.8 `ensureSubscoreColumns` immutable merge + column validation · §5.10 `framesToRecords` boundary validation.
- **Backend/infra:** §4.4 CI Python 3.12 · §4.7 CI payload stub names · §4.11 netlify `Permissions-Policy` · §4.3 `verify-csp.mjs --static` netlify↔nginx drift check + **merge-gating** CI step · §4.2 nginx `real_ip` (rate-limit keys real client IP behind Caddy) · §4.12 CORS `allow_headers` · §4.13 `record` cache `maxsize=None` · §4.15 ASCII-digit ZIP guard · §4.18 404 echoes normalized ZIP.
- **Pipeline/stats:** §3.14/§7.6 bootstrap p-value plus-one floor (feeds BH-FDR) · §1.8 deleted dead `config.DEFAULT_WEIGHTS` · §1.12 `diagnostics.py` double `_member_pctile` compute.

Pass-6 (executed against the FULL LOCAL national data - it was present all along; earlier "no data" was a wrong assumption):
- **§1.1 percentile universe** - MEASURED on real data, then **rejected**: fixing it moves the composite by max 0.11 pctile pts (0 rows >1pt), no correctness content → not worth an invasive core-scoring refactor. No change shipped.
- **§2.1 dual_share** - confirmed **unscored** (not in taxonomy) → skipped.
- **§2.3 NP/PA classification** - **fixed + rebuilt + kept** (user-approved). 42,666 psychiatric NPs reclassified primary→mental in `build_providers.py`; rebuilt providers→supply→join→metrics.parquet + payloads. Composite moves <1pt but the `mental_2sfca`/`primary_2sfca` sub-scores are now factually correct. 131 tests pass, face validity holds. Backup of pre-change metrics in scratchpad.
- **§3.1 spatial CIs** - **implemented + verified** in `validate_temporal.py` + `validate_fqhc_lever.py`: `_cluster_bootstrap`/`_bootstrap` generalized to block by any unit; new county-block CI reported beside the ZIP CI and now drives the verdict (a lever needs BOTH to exclude 0). Measured widening: temporal DiD [-60.3,-11.3]→[-78.6,-4.2]; FQHC lever [-71.7,+2.2]→[-74.1,+10.5] (the borderline case is now clearly null under honest spatial inference). ⚠️ VALIDATION.md §7 hardcoded CIs are now stale vs these wider county-block numbers - regenerate that section from `gate_ci.json`/the validator output on the next doc pass.

### DEFERRED - needs a decision or data build (do NOT guess)
- **§3.2 default weighting scheme** (pop-weighted correlation vs unweighted) - product/statistical judgment call.
- **§3.1 spatial clustering on causal CIs** - substantial; verify against a real build.
- **§1.1 percentile universe unification** & **§2.1 dual_share suppression** & **§2.3 NP/PA classification** - real changes but need a data build to verify; do not ship blind.
- **§7.1 CI builds a data slice** - highest-leverage remaining item; unblocks every data-gated test. Needs a small committed fixture or `make data-ca` in CI.
- **§4.9 nginx non-root** - requires coordinated `nginx-unprivileged` + port change across `frontend/Dockerfile` + `nginx.conf` (`listen 8080`) + `Caddyfile` (`web:8080`) + compose; must be container-tested, not just edited.
- **§4.1/§4.5/§4.6 dependency pinning** - needs a controlled lock regeneration (a backend-only pinned lock), then point Dockerfile + CI at it. Don't fabricate versions.

### Handoff to next agent
Remaining open items (browser-verify or decision-gated):
- **§6.2 + §6.1 (rest)** MapView perf (HIGH): switch whole-store `useStore()` to field selectors, and move hover highlight to deck.gl GPU `autoHighlight` instead of the 33k-feature `updateTrigger`. The store-side no-op hover guard is already done (pass 2); this is the remaining, riskier half. **Verify with the Playwright/browser tooling** - the one place to watch for regressions.
- **§6.5** MethodologyPanel: set `inert`/`aria-hidden` on the app root while the modal is open. Needs a small portal refactor (dialog currently renders inside `#root`, so `#root` can't be inerted as-is) + browser verification.
- **§6.13** lift the duplicated `buildQuantile` (Legend + MapView) into one memoized store selector - low risk but touches MapView; bundle with the §6.2 work.
- **§5.6** synthesis `profile()` vs `synthesize()` weighting contradiction - needs a one-line policy decision (make `profile` weight-aware, or label it weight-independent) before coding.
- **§7.9/§7.10** backend tests assert `status in (200,404)` / object identity - tighten once §7.1 lands (they're data-gated).

Then tackle the DEFERRED items with the user's decisions in hand. Run `cd frontend && npx tsc --noEmit && npx vitest run` and `python -m pytest tests -q` after each wave. Nothing has been committed - the user commits explicitly.

---

## Overall verdict

The codebase is unusually disciplined and self-aware (planted-answer test oracles for the hard math, honest uncertainty messaging, colorblind-safe scale, docs that disclose the "is it just a poverty map?" problem). Defects cluster in three places: (a) a few real mechanical bugs, (b) statistical-consistency seams where two parts compute the "same" number on different universes, and (c) integrity drift where docs/provenance/CI claim guarantees the code does not deliver.

---

## Cross-cutting themes (recurred across independent passes)

1. **No proven server↔client parity** for the shipped composite - map/rankings color from a client recompute; the "parity" test is Python-vs-Python.
2. **"Same" percentile on different universes** - server ranks dimensions on all-non-null but composite on scoreable-only; client percentile pool includes areas the app elsewhere excludes.
3. **Guards don't run where it counts** - CI never builds data, so every acceptance/integrity/scientific test skips; prod + CI install unpinned deps; CI Python 3.11 vs prod 3.12.
4. **Preset weights are a researcher degree-of-freedom** framed as "recovered signal."
5. **Causal CIs too narrow** - cluster only at ZIP, ignoring spatial autocorrelation.
6. **Doc-vs-code drift** - README/RATIONALE describe a superseded taxonomy.

---

## 1. Pipeline core / scoring
`join_and_score.py`, `build_supply.py`, `config.py`, `common.py`, `taxonomy.py`, `run.py`, `preflight.py`, `diagnostics.py`, `selection_diag.py`, `zip_states.py`

**Health:** Disciplined, self-documenting scoring code; the SVI-style hierarchical percentile method is sound. Defects are subtle statistical-consistency and provenance issues, not crashes.

1. **HIGH · STAT · join_and_score.py:227-234,300-314 vs :343** - Member/sub/dimension percentiles ranked over all non-null rows, but the composite is re-ranked over scoreable-only, so the composite mixes dimension percentiles defined on a larger universe than it is ranked on. 615 non-scoreable ZCTAs carry `care_access_pctile` but only 108 carry `health_need_pctile` → asymmetric dilution across dimensions. *Fix:* rank every hierarchy level within `df.loc[scoreable]`, broadcast back.
2. **HIGH · ENG/STAT · join_and_score.py:240, zip_states.py:56** - `state` (drives `access_gap_pctile_within_state` and the UI state filter) derived from the ZIP3 dominant-state heuristic, not the authoritative `county_fips[:2]`. ZIP3 prefixes straddling a state line rank in the wrong state. *Fix:* derive `state` from `county_fips[:2]`; keep ZIP3 map as fallback.
3. **MEDIUM · STAT/ENG · join_and_score.py:319-325,420; taxonomy.py:253** - Shipped composite uses hardcoded `DIMENSION_WEIGHTS = 0.35/0.30/0.35` but `build()` logs "dimension weights derived by pipeline/validate.py (multi-anchor)"; validate.py runs after join and never feeds derived weights into the default composite. *Fix:* consume derived weights, or correct the log to say the default is a theory prior.
4. **MEDIUM · STAT · taxonomy.py:28-253 + join_and_score.py:311-325** - `health_need` and `social_vulnerability` dimension percentiles are ~0.73 correlated (participation ratio ~1.6); the additive composite effectively double-weights deprivation vs `care_access`. Acknowledged in-code via residual lens. *Fix:* collapse need+vulnerability to one latent or orthogonalize before weighting; keep surfacing `care_access_resid_pctile`.
5. **MEDIUM · STAT · build_supply.py:96-99** - `primary_shortage` compares `1/A_i` (inverse Gaussian-decayed E2SFCA accessibility) to HRSA `3500:1`, but `1/A_i` is not an actual people-per-provider ratio. *Fix:* compute a genuine catchment ratio, or relabel as "E2SFCA-derived shortage proxy."
6. **MEDIUM · STAT · join_and_score.py:288-305** - Sub-scores are a `skipna` mean; any member with <100 non-null values dropped globally with no completeness penalty; ZCTAs re-weighted onto present members silently. *Fix:* emit a build-time warning and record per-ZCTA member completeness.
7. **MEDIUM · STAT · taxonomy.py:32-249 + join_and_score.py:311-314** - Each dimension = equal-weighted mean of its sub-scores regardless of measure count; 11 chronic-disease measures share what 4 behavioral-risk measures share. Defensible (mirrors SVI themes) but an implicit weighting decision not surfaced. *Fix:* document explicitly, or offer measure-count weighting as sensitivity.
8. **MEDIUM · ENG · config.py:198** - `DEFAULT_WEIGHTS = {disease/supply/econ}` is dead/stale: keys don't match live `DIMENSION_WEIGHTS` and no pipeline module imports it. *Fix:* delete.
9. **MEDIUM · STAT · join_and_score.py:110-111** - Reliable-range band samples `uniform(0.15,0.55)` renormalized (expected ~0.333 each), centered on equal weighting, not the shipped `0.35/0.30/0.35` point estimate. *Fix:* draw weights centered on the actual default (Dirichlet), or document as equal-weight-centered sensitivity.
10. **MEDIUM · STAT · join_and_score.py:366** - Multiplicative lens floors `frac` at 0.01, so the best-access ~1% of ZCTAs collapse to the same `log(0.01)` floor, compressing the lower tail. *Fix:* lower the floor (e.g. 0.5/100) or use `log1p` regularization tied to 1/n.
11. **LOW · STAT · join_and_score.py:349-350** - `groupby("state", dropna=False)` lumps every null-state ZCTA into one pseudo-state and ranks them together. *Fix:* set within-state percentile to NaN where state is null.
12. **LOW · ENG · diagnostics.py:135** - `_member_pctile` invoked twice per member (filter + value), doubling percentile computation over ~50 measures × 33k rows. *Fix:* compute once and reuse.
13. **LOW · ENG · build_supply.py:92-96** - Fixed-catchment shortage uses `query_radius` (16km) with a Python list comprehension, O(sum of neighbors), can balloon in dense metros; contradicts "milliseconds" docstring. *Fix:* vectorize like `_e2sfca_adaptive` or cap neighbor counts.
14. **LOW/UNVERIFIED · STAT · build_supply.py:79-80** - Step-1 pooling uses each neighbor's adaptive bandwidth while step-2 uses the ZCTA's own bandwidth; same physical distance gets two different decay weights by direction. *Fix:* confirm against McGrail & Humphreys (2009); use one consistent bandwidth per pair if symmetric weight intended.

---

## 2. Pipeline data builders
`build_acs`, `build_amenable`, `build_broadband`, `build_fqhc`, `build_fqhc_openings`, `build_gazetteer`, `build_geometry`, `build_geonames`, `build_hpsa`, `build_lifeexp`, `build_medicaldebt`, `build_outcomes`, `build_places`, `build_providers`, `build_provider_capacity`, `build_sud_mh_supply`, `build_trends`, `build_shards`, `build_pmtiles`

**Health:** Generally disciplined (`norm_zcta`, sentinel scrubbing, EB shrinkage, explicit floors). Risk concentrates in claims-/ZIP-keyed supply stages plus a few silent-partial-failure and inert-validation paths.

1. **HIGH · STAT · build_provider_capacity.py:87,98** - `dual_share = SUM(Bene_Dual_Cnt)/SUM(Tot_Benes)` biased downward: CMS suppresses `Bene_Dual_Cnt` for 1-10 duals, `TRY_CAST` turns blanks to NULLs dropped from the numerator while denominators stay; worst in small/rural/low-dual ZIPs (geographically correlated). *Fix:* restrict ratio to non-suppressed rows, or interval-model suppressed cells.
2. **MEDIUM · STAT · build_providers.py:151 / build_provider_capacity.py:83 / build_sud_mh_supply.py:64** - A mailing/practice ZIP is stored in a column named `zcta5` and joined to ACS ZCTA data as identical; ZIP≠ZCTA and PO-box ZIPs have no ZCTA → silent mis-association/drop. *Fix:* run a ZIP→ZCTA crosswalk before aggregation, or rename and document the approximation + unmatched loss rate.
3. **MEDIUM · STAT · build_providers.py:60-66** - Every NP/PA forced to `primary_care` before any specialization check; psychiatric NPs/surgical PAs counted as PCPs → `providers_primary` inflated, `providers_mental` undercounted. *Fix:* inspect specialization for NP/PA rows before the blanket assignment.
4. **MEDIUM · STAT/ENG · build_sud_mh_supply.py:30-35,63** - Capability flags are substring probes over a stringified JSON blob; `accepts_uninsured` keys on `"free"`, matching "smoke-free", "drug-free", etc., and probes hit JSON field names too. *Fix:* parse the `services` structure; drop/tighten the bare `"free"` token.
5. **MEDIUM · ENG · build_acs.py:289-296,224-225** - An SVI table fetch that raises is caught and merely logged; `_fetch_svi_rates` can return `None` and the build continues, silently dropping that dimension → non-deterministic composite between runs. *Fix:* route SVI fetches through `_census_get` retry and hard-fail if any scored SVI table is missing.
6. **MEDIUM · STAT · build_fqhc_openings.py:56,89** - `first_open_year` = min added-to-scope over currently-active sites only, but `newly_served` = "first FQHC ever"; a ZCTA whose earlier FQHC closed then reopened is mislabeled `newly_served`, contaminating the event-study treatment group. *Fix:* derive first-ever presence from full site history (incl. inactive), or caveat and quantify.
7. **MEDIUM · ENG · build_fqhc_openings.py:117** - `if df[...].between(1960,2030).all() is False:` compares a NumPy bool to the `False` singleton by identity → always False → range check never fires. *Fix:* `if not df[...].between(1960,2030).all():`
8. **MEDIUM · STAT · build_hpsa.py:51-55** - County-MAX HPSA score broadcast to every ZCTA; non-designated counties filled 0, conflating "assessed, no shortage" / "averaged away" / "not assessed." *Fix:* retain a designation-count/coverage indicator so 0 vs unassessed is recoverable.
9. **LOW/MEDIUM · STAT · build_acs.py:41-45** - `_proportion_se` always uses the additive ACS ratio formula even for subset proportions (poverty, uninsured) where Census prescribes the subtractive proportion formula → SEs overestimated, EB shrinkage under-applied, CV bands too wide. Documented as intentional-conservative. *Fix:* use subtractive formula with fallback when radicand negative.
10. **LOW/MEDIUM · ENG · build_broadband.py:43-44** - `B28002_013` hard-indexed with no label assertion (contrary to build_acs discipline); a future vintage renumber computes a wrong rate that still passes `[0,1]`. *Fix:* assert member label from `variables.json`.
11. **LOW/MEDIUM · ENG · build_broadband.py:38-40 / build_trends.py:43-44** - Single request, `die` on any non-200, bypassing `_census_get` retry/backoff. *Fix:* reuse the retrying helper.
12. **LOW · STAT · build_lifeexp.py:54-56** - ZCTA life expectancy = straight pop-weighted mean of tract e(0); LE is nonlinear in age-specific mortality and this is not age-standardized. Documented approximation. *Fix:* aggregate age-specific mortality then recompute, or weight by a standard population.
13. **LOW · ENG · build_gazetteer.py:26-30** - Pre-download HEAD gate treats any status ≥400 as "vintage unavailable," skipping servers that reject HEAD (405/403) but serve GET. *Fix:* fall back to a ranged GET.
14. **LOW · STAT · build_provider_capacity.py:98 (+ SUD/MH/providers)** - Capacity rows carry no de-dup guarantee across ZIP formats and inherit CMS ≤11 suppression dropping smallest/rural NPIs. *Fix:* emit a suppressed-row/coverage indicator per ZIP.
15. **LOW · ENG · build_geometry.py:52-60** - `_detect_field` returns the first `TIGER_ZCTA_FIELDS` entry found as a plain substring anywhere in mapshaper `-info` output (fields, values, layer names concatenated). *Fix:* parse the structured field list / `-info` JSON.

*Note:* several stages depend on `common.download_file`'s resume path (out of scope) which may concatenate a full body onto a partial if a server ignores `Range` and replies 200 - worth a look.

---

## 3. Pipeline validation / causal
`validate`, `validate_acceptability`, `validate_fqhc_lever`, `validate_fqhc_power`, `validate_placebo`, `validate_subcounty`, `validate_temporal`, `validation_stats`, `bootstrap_gate`, `regate_amenable`, `verify_bands`

**Verdict:** Unusually self-aware and broadly defensible - the strongest causal claims are correctly hedged (temporal DiD labeled descriptive-only and self-falsified; FQHC event study called "borderline"), hand-rolled Callaway-Sant'Anna and cluster bootstraps broadly correct, multiplicity/spatial pseudo-replication explicitly addressed. Weaknesses are inference-tightness, not fabricated positives.

1. **HIGH · STAT · validate_temporal.py:165-182 & validate_fqhc_lever.py:198-222** - Causal event studies cluster the bootstrap only on individual ZIP series, treating neighboring ZIPs as independent; health geography is spatially autocorrelated and treatment spatially clustered → CIs too narrow. `bootstrap_gate.spatial_sensitivity` makes exactly this correction for the cross-sectional claim but the two causal studies never do. *Fix:* add a county/region-block bootstrap variant beside the ZIP-cluster CI.
2. **HIGH · STAT · validate.py:89-97,286-290,320 (mirrored subcounty.py:182-195)** - Shipped anchored preset weights (`weights.json`) ∝ pop-weighted dimension-outcome correlation, justified as "recovery of attenuated signal ... fits nothing." Pop-weighting does not disattenuate; it changes the estimand to "the correlation where people live" and up-weights urban counties; consistently raises care-access → researcher-DoF favoring the hypothesis. *Fix:* ship unweighted-correlation preset as default; present pop-weighted as labeled sensitivity, or justify with a genuine EIV model.
3. **HIGH · STAT · validate_fqhc_power.py:154-188,265-267** - Go/no-go power gate simulates a homogeneous-effect TWFE DiD but the study runs the less-efficient Callaway-Sant'Anna not-yet-treated estimator; MDE understated → "GREEN-LIGHT" optimistic (actual estimate landed borderline). *Fix:* simulate the actual CS(g,t) estimator, or inflate MDE by the CS/TWFE efficiency ratio.
4. **HIGH · STAT · bootstrap_gate.py:306-322 + across all validate_* scripts** - BH-FDR applied only within the scored care sub-score family; dozens of "CI excludes 0 / diff>0" decisions across the suite (7 anchors × dims in validate, 5 states + 2 rulers in subcounty, placebo, acceptability, temporal, fqhc) with no global multiplicity control. *Fix:* register confirmatory claims up front; one FDR/hierarchical correction across the confirmatory set.
5. **MEDIUM/HIGH · STAT · validate.py:122-143,349-354** - `disattenuated_r = obs / sqrt(rel_index·ro)` uses an outcome reliability `ro` the docstring calls a conservative (downward-biased) lower bound; a smaller `ro` inflates the disattenuated r upward, so "conservative" is backwards for the headline. Also mixes unweighted split-half `rel_index` with pop-weighted `obs`/`ro`. *Fix:* use a defensible reliability (not a known lower bound), or report as an upper bound; keep weighting consistent.
6. **MEDIUM · STAT · validate_fqhc_lever.py:302-323 (esp. 308)** - FQHC parallel-trends verdict is an eyeballed `clean = pre_rms < |ATT|/2`, the exact ad-hoc rule `validate_temporal._pre_trends_test` was upgraded away from (to a joint Wald test). Two causal studies inconsistent; the flag has no sampling distribution. *Fix:* port the joint-Wald pre-trend test into `validate_fqhc_lever`.
7. **MEDIUM · STAT · validate_temporal.py:338-370 & validate_subcounty.py:95-107** - Cross-state triple-diff compares NY SPARCS AHRQ PQI_90 vs a TX simplified-Billings ICD-prefix ACSC flag - two different outcome definitions; a null triple-diff could reflect construct/scale mismatch rather than true absence of the lever. *Fix:* harmonize the ACSC definition, or standardize each state's outcome within-state before pooling and note residual construct risk.
8. **MEDIUM · ENG/STAT · validate_temporal.py:127-136** - `_twoway_demean` applies the within transform once; exact only for balanced panels. For the unbalanced NY panel it leaves residual FE correlation and biases event-study betas; the triple-diff correctly uses iterated projections. *Fix:* use iterated `_demean2` for the event study too, or assert balance.
9. **MEDIUM · ENG/STAT · bootstrap_gate.py:65-66,429** - `_mean_r`/`_mean_abs_r` average correlations with `np.nanmean`; `_corr` returns NaN when a resample has <100 valid pairs, so the contributing outcome set varies across replicates → the resampled composite mean-r is not a fixed estimand. Averaging raw Pearson (not Fisher-z) is mildly biased. *Fix:* fix the outcome set per replicate; average in Fisher-z.
10. **MEDIUM · STAT · validate.py:146-181,320-321** - Preset weights = floor + proportional-to-univariate-correlation, chosen specifically because the multivariate NNLS collapses care-access; presented alongside R²/CV diagnostics as if a fitted model. *Fix:* keep as an explicitly normative preset, separated from fitted-model diagnostics.
11. **MEDIUM · STAT · validate_fqhc_lever.py:182-188,166-176** - `overall_att` is a cohort-size-weighted average over all e≥0; cohort composition changes across event times (composition-change pitfall CS warn about). *Fix:* lead with the balanced (e≤4) aggregation; treat full-horizon as secondary.
12. **LOW/MEDIUM · STAT · validate_placebo.py:69-79 & validate_subcounty.py:438-446** - Age adjustment is a single linear `polyfit(age65, y, 1)`; if age-mortality is nonlinear (plausible, and age is a suppressor in CA), residual age confounding remains. *Fix:* use a spline/age-bins control and report sensitivity.
13. **LOW/MEDIUM · STAT · validate.py:146-154,191** - Dimension scores clipped at 0 before weighting, so a genuinely wrong-signed dimension is floored to the 5% minimum rather than surfaced. *Fix:* report the raw signed correlation prominently even when floored.
14. **LOW/MEDIUM · ENG · validate_fqhc_power.py:111** - Noise decomposition `var_z ~ a + b·(1/pop)` fit with ordinary `polyfit`, but the response is a per-ZIP variance estimate (heteroskedastic, sampling var ∝ var²) dominated by small-pop ZIPs. *Fix:* fit with weights ∝ ZIP-years (or on log-variance); report MDE sensitivity to `a`.
15. **LOW/MEDIUM · ENG/STAT · validate_temporal.py:154-162,320-335** - Point estimates from `lstsq` with no cluster-robust analytic SE at all; all uncertainty delegated to the bootstrap with no cross-check. *Fix:* log the fraction of skipped/failed resamples; cross-check one CI against a cluster-robust analytic SE.
16. **LOW/MEDIUM · STAT · validate_subcounty.py:176-180,348-394** - Within-county validation reports only point correlations with an arbitrary `|r|<0.01 => "0 resolution"` cutoff and no CI; the "positive within-county r across 5 states" scorecard is a vote-count with no inference. *Fix:* attach cluster-bootstrap CIs to the headline within-county rs.
17. **LOW · ENG · validate_subcounty.py:632-639** - `run_all` wraps each source in a blanket `except Exception` recording `error` and continuing; a silently failing fetch drops out of the "5 states + 2 national" evidence base without the reader noticing the denominator changed. *Fix:* distinguish "ran, weak signal" from "failed to run"; fail loudly on unexpected exception types.
18. **LOW · ENG · validate_fqhc_lever.py:326-336** - `_gate_band` reads scenario N's from `SCENARIOS` but compares against hardcoded 240/110 thresholds not derived from them → labels drift if `SCENARIOS` retuned. *Fix:* derive thresholds from `scen_n`.
19. **LOW · ENG/STAT · validate_acceptability.py:48-62** - Partial-r bootstrap drops NaN degenerate resamples silently via `nanpercentile`; reported CI conditional on non-degenerate resamples with no count; single uncorrected test. *Fix:* report retained-resample count; fold into the multiplicity family.
20. **LOW · STAT · validate.py:100-119** - Split-half reliability averages Pearson r over 200 splits then Spearman-Brown-corrects the mean r (should correct each split then average), and uses raw (not Fisher-z) averaging → small bias propagating into every disattenuated r. *Fix:* Spearman-Brown each split then average, in Fisher-z.

*Note:* the `uninsured_2012` pre-treatment barrier cache (`ny_acs2012_uninsured.parquet`, actually nationwide) has **no builder in the repo** - an unversioned manual artifact, a reproducibility gap.

---

## 4. Backend + infra + config
`backend/main.py`, `backend/data.py`, Dockerfiles, `nginx.conf`, `Caddyfile`, compose files, `Makefile`, `netlify.toml`, `ci.yml`, env examples, requirements, `verify-csp.mjs`

**Health:** No committed secrets, injection, or path-traversal; small validated read-only API. Risk cluster is reproducibility/parity drift.

1. **HIGH · backend/Dockerfile:14-15** - Prod image installs floating ranges from `requirements.txt`, never `requirements.lock`; a later rebuild silently pulls newer majors. *Fix:* install from a pinned lock.
2. **HIGH · frontend/nginx.conf:2,59-66** - `limit_req_zone $binary_remote_addr` behind Caddy with no `real_ip` config → key resolves to Caddy's single IP → global throttle or useless per-client limit. *Fix:* add `set_real_ip_from`/`real_ip_header X-Forwarded-For`.
3. **HIGH · ci.yml:72-92 + netlify.toml:36-41** - CSP job is `continue-on-error: true` (never gates) and `verify-csp.mjs` only parses `nginx.conf`, never `netlify.toml` (the documented primary deploy); Netlify CSP already drifted (missing `Permissions-Policy`). *Fix:* verify the netlify.toml policy and make the diff merge-gating.
4. **MEDIUM · ci.yml:21 vs backend/Dockerfile:4** - CI tests on Python 3.11; prod is 3.12. *Fix:* pin CI to 3.12.
5. **MEDIUM · Makefile:28-34** - `make setup` overwrites `requirements.lock` with `pip freeze` from each dev's machine; lock is non-authoritative and never installed from. *Fix:* generate lock in a controlled job; install from it everywhere.
6. **MEDIUM · ci.yml:23** - CI installs floating `requirements.txt`; green CI does not attest the deployed set. *Fix:* install from lock.
7. **MEDIUM · ci.yml:48-51** - Build-payload stub seeds stale `metrics.json`/`zcta_overview.geojson`; current contract is `map_frame.json`+`subscores.json`+`zcta.pmtiles`, so a payload-name regression passes CI. *Fix:* update the stub to current filenames.
8. **MEDIUM · backend/Dockerfile:4,9-11 (+ frontend)** - Mutable base tags + `apt-get upgrade -y` make images non-reproducible. *Fix:* pin base images by digest; drop the blanket upgrade.
9. **MEDIUM · frontend/Dockerfile:22-25** - Final nginx stage has no `USER`; master runs as root. *Fix:* use `nginxinc/nginx-unprivileged` or a high port + non-root USER.
10. **MEDIUM · backend/Dockerfile:24** - `COPY data/processed/metrics.parquet` bakes the dataset into a layer (bloat, staleness, cache-busting). *Fix:* mount as a read-only volume.
11. **MEDIUM · netlify.toml:36-42** - Header block omits `Permissions-Policy` present in nginx → Netlify ships a weaker header set. *Fix:* add the identical header, cover with #3.
12. **LOW · backend/main.py:51-57** - CORS `allow_headers=["*"]` broader than the GET-only API needs. *Fix:* restrict to `["content-type"]`.
13. **LOW · backend/data.py:76-84** - `record` `lru_cache(maxsize=4096)` vs ~33k rows → thrash. *Fix:* size to row count or drop.
14. **LOW · backend/data.py:87-94** - `rankings` cached on raw `state` but uppercases inside → `ca`/`Ca`/`CA` = 3 entries. *Fix:* normalize before the cache boundary.
15. **LOW · backend/main.py:60-67** - `_norm_zcta` accepts Unicode digits (`str.isdigit`, `\d`). *Fix:* `str.isascii() and str.isdigit()` or `re.ASCII`.
16. **LOW · nginx.conf:23** - CSP retains `style-src 'unsafe-inline'`. Documented, low-risk. *Fix:* move to hashed/nonce styles long-term.
17. **LOW · backend/main.py:83-97 / netlify.toml** - No app-level rate limiting; on the split-deploy path the API is unthrottled. *Fix:* add a lightweight app-level limiter (slowapi).
18. **LOW · backend/main.py:79** - 404 detail reflects raw un-normalized `zcta5`. JSON-encoded (not XSS) but echoes input. *Fix:* echo the normalized value or a fixed message.

*Note (not a finding):* no committed credentials - env examples hold placeholders, `.env` gitignored, `CENSUS_API_KEY` read from environment.

---

## 5. Frontend logic (lib + store)
`scoring`, `synthesis`, `colors`, `csv`, `data`, `format`, `api`, `types`, `geo`, `measures`, `observability`, `dataWorker`, `testFactory`, `store`, `public/weights.json`

**Health:** Core numerics readable and mostly correct, but the client-recomputed composite is the sole map/ranking value with no proven parity to the server's `access_gap_score`, and `buildScoreIndex` includes areas the data model says are held out of rankings.

1. **HIGH · STAT · scoring.ts:77-82 + types.ts:264** - The map/ranking composite is always the client recompute `accessGap`; the server's `access_gap_score`/`_pctile`/`tier`/`rank_lo/hi` are never used to color/rank, and nothing asserts they agree at default weights. *Fix:* parity test asserting `accessGap(m, DEFAULT_WEIGHTS)` reproduces `m.access_gap_score` within tolerance; display server value at default weights, switch to recompute only when weights differ.
2. **HIGH · STAT · scoring.ts:87-94** - `buildScoreIndex` percentile denominator includes every `scoreable` area with no exclusion of `institutional`, `isPartialScore`, or `low_confidence` → the live national rank is computed against a contaminated pool the app elsewhere excludes. *Fix:* filter to `scoreable && !institutional && !isPartialScore`.
3. **HIGH · ENG · colors.ts:41-51** - `buildQuantile([])` → empty-domain scale → `scale(value)` returns undefined → `parseColor(undefined).match` throws; the whole choropleth renders throw when a lazy sub-score lens is all-null before merge. *Fix:* short-circuit empty domain, or treat non-string scale output as `NO_DATA_RGB`.
4. **MEDIUM · ENG · data.ts:61-82** - `loadViaWorker` has no timeout; a worker that fetches but never posts leaves `loadData()` pending forever. *Fix:* race against a timeout that terminates and falls back to main thread.
5. **MEDIUM · STAT · scoring.ts:33-40 + format.ts:16-23 + synthesis.ts:4-5** - `accessGap` is a mean of correlated percentiles (CLT-compressed toward 50), but `severity()` (20-pt bands) and `band()` (66/33) assume uniform percentile input; nothing enforces consumers pass the `percentileOf`-converted value. *Fix:* route every composite→band/severity call through `percentileOf(buildScoreIndex(...))`; test that severity receives a uniform percentile.
6. **MEDIUM · STAT · synthesis.ts:24-57 vs 60-87** - `profile()` uses unweighted dimension percentiles; `synthesize()`'s "driven mostly by..." uses weighted contributions → contradictory narratives in one panel. *Fix:* make `profile` weight-aware, or label it explicitly weight-independent.
7. **MEDIUM · ENG · dataWorker.ts:31 + data.ts:64-75** - Worker returns ~33k reconstructed objects + full overview GeoJSON via structured clone (copy, not transfer); clone cost can rival the JSON.parse it offloads. *Fix:* keep the columnar frame as typed arrays and transfer buffers.
8. **MEDIUM · ENG · store.ts:240-248** - `ensureSubscoreColumns` mutates existing rows in place then swaps the Map (memoized consumers see stale data) and indexes `s[col][i]` with no existence/length check (a missing column throws, dropping the whole merge to error). *Fix:* build new row objects; guard/validate each column array.
9. **MEDIUM · TEST · scoring.test.ts** - `buildScoreIndex` and `percentileOf` (the live re-weighting rank core) have zero tests. *Fix:* add tests for tie group, min, max, empty; and for `buildScoreIndex` exclusion rules.
10. **LOW/MEDIUM · ENG · data.ts:35-48** - `framesToRecords` trusts `frame.n` and column lengths; a truncated column silently yields records with `undefined` fields. *Fix:* validate every expected column exists and `length===n`; throw a clear error.
11. **LOW · STAT · scoring.ts:53-57** - `accessGapMult` clipping asymmetric (top exact, bottom floored at 0.01) → a genuine 0-rank dimension scored as 1st-percentile. Documented rationale (avoid log(0)); acceptable.
12. **LOW · ENG · scoring.ts:97-100** - `percentileOf` via `bisectLeft` gives fraction strictly below → min area always 0th, worst area never 100th. Cosmetic. *Fix:* `(bisectRight-0.5)/n` if inclusive reading wanted.
13. **LOW · ENG · types.ts:44 + data.ts:46** - `SlimMetric` index signature + `rec as unknown as SlimMetric` defeat field-level typing → typo'd percentile columns compile clean, become silent runtime null. *Fix:* drop the blanket index signature; use a typed Record + keyof accessor.
14. **LOW · ENG · geo.ts:4-19** - `centroid` = unweighted vertex mean (includes ring-closing dupes and holes); can land outside concave/multipolygon ZCTAs. Acceptable as a cheap label point. *Fix:* polylabel / area-weighted centroid if precision matters.

*Test map:* geo/measures/observability/dataWorker/testFactory have no test files; store only covers `ensureSubscoreColumns` (`load`/bounds/`locateMe`/`syncUrl` untested).

---

## 6. Frontend components / app shell
`App`, `main`, `MapView`, `DetailPanel`, `DriversSection`, `CompareTray`, `RankingsList`, `WeightSliders`, `MetricSelect`, `Legend`, `MethodologyPanel`, `SearchBox`, `TopControls`, `SiteCredits`, `Caret`, `Tip`, configs

**Health:** Unusually mature - error boundaries, honest uncertainty messaging, keyboard/focus handling, XSS-escaped tooltips, colorblind-safe cividis, disciplined effect cleanup. Main defects are MapView render/repaint perf under hover, a few AT/CSP gaps, and one visual-hierarchy overstatement of precision.

1. **HIGH · MapView.tsx:82-83** - `useStore()` with no selector subscribes to the whole store; deck `onHover` fires continuously → MapView re-renders on every pointer move (plus every Toast/weight-drag/compare change). *Fix:* select only needed fields with `shallow`; drop no-op hover writes in the store.
2. **HIGH · MapView.tsx:176-178,199-202,249-251** - `updateTriggers.getLineColor/Width = [selectedZcta, hoveredZcta]` and `hoveredZcta` in the layer memo dep → each hover change rebuilds the layer and re-runs line accessors over all ~33k features. *Fix:* deck.gl GPU `autoHighlight`/`highlightColor` or a thin dedicated highlight sublayer.
3. **MEDIUM · SearchBox.tsx:40-44** - Validation error `<div>` has no `role="alert"`/`aria-live`; input has no `aria-invalid`/`aria-describedby` → screen readers get no feedback. *Fix:* add `role="alert"` + wire aria attributes.
4. **MEDIUM · index.html:12-17 vs MapView.tsx:44-46** - MapView comment says prod CSP is `'self'`, but index.html hard-loads Google Fonts and the basemap loads from `basemaps.cartocdn.com`; if locked to `'self'` these break in the deployed build only. UNVERIFIED whether allowlisted. *Fix:* self-host fonts or explicitly allow the CDNs.
5. **MEDIUM · MethodologyPanel.tsx:219-232** - Modal has a Tab focus-trap but never sets `aria-hidden`/`inert` on the rest of the app → AT can still read the map behind it. *Fix:* mark app root `inert` while open.
6. **MEDIUM · DetailPanel.tsx:686-704** - Headline renders a precise integer percentile at 34px in a severity color while the reliability caveat is small graphite text → dominant signal is a sharp number the data can't support at that resolution. *Fix:* show a band/tier at headline weight, or attach the reliable range to the big number.
7. **LOW · DetailPanel.tsx:492-509** - Drag-resize `window` listeners removed only on `pointerup`; if the panel unmounts mid-drag they persist and fire on an unmounted component. *Fix:* `setPointerCapture` and/or move drag lifecycle into a `useEffect` with teardown.
8. **LOW · WeightSliders.tsx:50-56** - "Throttled" commit is actually a debounce (`clearTimeout`+`setTimeout`), so a slow continuous drag never commits until motion stops. *Fix:* real leading+trailing throttle, or fix the comment.
9. **LOW · CompareTray.tsx:153-160** - National-rank severity conveyed by hue alone (no severity word), unlike DetailPanel. *Fix:* add the severity word/glyph.
10. **LOW · Tip.tsx:38-50,62-82** - `role="button"` triggers lack `aria-haspopup`/`aria-expanded`; tip force-dismissed on any scroll → keyboard user loses it. *Fix:* add aria attrs; reposition (not dismiss) pinned/focused tips.
11. **LOW · DetailPanel.tsx:782-783** - `life_expectancy` rendered unformatted. *Fix:* `toFixed(1)`.
12. **LOW · MethodologyPanel.tsx:202-217** - Focus-trap `querySelectorAll` matches focusables inside collapsed `<details>`, which aren't focusable → Tab-wrap can no-op. UNVERIFIED across browsers. *Fix:* filter to visible (offsetParent-non-null) elements.
13. **LOW · Legend.tsx:33-62 & MapView.tsx:93-100** - Two independent quantile scales built from identical ~33k inputs each render; duplicated O(n) work + drift risk. *Fix:* lift into a shared memoized store selector.
14. **LOW · MapView.tsx:129-144** - Fly/fit effects silently no-op if `mapRef.current` is null when the target changes; latent gap for future deep-link entry points. *Fix:* re-apply pending target in `onLoad`.
15. **LOW · vitest.config.ts:8** - `environment:'node'` precludes DOM/component tests; all 15 components ride on the Playwright smoke suite. Scope note.

---

## 7. Tests + docs
Python tests, e2e specs, README + docs/*

**Verdict - test rigor:** The pure-kernel layer is genuinely strong (planted-answer oracles for CS-ATT, DiD/triple-diff, pre-trends Wald, cluster bootstrap, BH-FDR, partial-r, Fay-Herriot, E2SFCA, columnar payload - real, deterministic, catch actual regressions). The gap is at the seams: every integration/acceptance/face-validity/CI-shape test is `skipif`-gated on a data build, so CI runs green while the scientific-claim guards never execute.
**Verdict - doc honesty:** On "is it just a poverty map?" the docs are unusually honest. The problem is staleness/drift and unlocked hardcoded numbers.

1. **HIGH · ENG · test_acceptance.py:20, test_integrity.py:21, test_backend.py:16, test_bootstrap_gate.py:12, test_selection_diag.py:12, test_subcounty_sources.py** - All `skipif(not METRICS.exists())`; README:236 says CI is "pytest (pipeline+backend)" but every statistically-meaningful assertion no-ops without `metrics.parquet`, which CI never builds. *Fix:* build a small committed real slice (or `make data-ca`) in CI, or fail loudly if the suite is universally skipped.
2. **HIGH · STAT · README.md:212, RATIONALE.md §9/§12 vs taxonomy.py** - README "HPSA out of v1" contradicts `taxonomy.py:168` `shortage_designation` scored; RATIONALE presents safety-net as a scored decisive fix vs `taxonomy.py:188` `scored=False`; RATIONALE "telehealth not yet in" vs `taxonomy.py:135` `digital_access` scored. *Fix:* refresh the docs to the shipped 12-scored/2-unscored model, or mark them historical.
3. **MEDIUM · STAT · VALIDATION.md §3-§6** - Dozens of hardcoded correlations with no regression lock; internal inconsistencies exist (overdose N `21,366` vs `21,376`; §7f ATT CI `[-71.7,+2.2]` vs `[-71.9,+1.1]`). *Fix:* generate headline tables from committed JSON artifacts, or test a few load-bearing numbers against `data/processed/*.json`.
4. **MEDIUM · ENG · test_acceptance.py:87,116,138** - "server↔client parity" test re-implements the TS `accessGap` in Python; `scoring.ts` is never run → a consistent TS-vs-server divergence is not caught. *Fix:* rename to "composite-formula regression," or drive real parity via shared fixtures.
5. **MEDIUM · ENG · test_acceptance.py:151-156** - Only face-validity direction test (Beverly Hills < South LA) is guarded `if "90210" in d.index and "90011" in d.index` → passes vacuously on any non-CA build. *Fix:* anchor ZIPs guaranteed present; assert presence.
6. **MEDIUM · STAT · bootstrap_gate.py:375,380** - `p_one = mean(a<=0)` can be exactly 0 at finite `n_boot`, fed to BH as an exact p → `q=0.000`, anti-conservative for thin survivors. *Fix:* `(1+#{≤0})/(1+n_boot)` floor; disclose these are bootstrap tail probabilities.
7. **MEDIUM · ENG · make-fixture.mjs:42-43** - CI e2e fixture sets `access_gap_pctile` to the raw composite (not a 0-100 rank) and `care_access_resid_pctile` to the same composite (should be a residual); sub-scores made perfectly collinear → the lens smoke test colors with a non-residual. *Fix:* rank fixture values into 0-100; derive resid from an actual residualization.
8. **MEDIUM · ENG · join_and_score._effective_dimensions/_dimension_correlations/_access_beyond_deprivation** - The "~1.6 effective dimensions / PC1=76%" headline and residual lens have no CI-runnable planted-matrix oracle. *Fix:* add synthetic tests (known covariance→known IPR; planted collinearity→known residual orthogonality).
9. **MEDIUM · ENG · test_backend.py:54,62-64** - "Not found" tests assert `status_code in (200,404)` → cannot detect the bug they name. *Fix:* assert 404 for a known-absent ZIP, 200 for a known-present one.
10. **MEDIUM · ENG · test_backend.py:113-117** - `test_rankings_is_cached` asserts object identity (`is`), an implementation detail. *Fix:* assert `cache_info().hits` increments + content equality.
11. **LOW/MEDIUM · ENG · test_acceptance.py:212-219** - `test_validate_idempotent` calls `validate.build()` twice, overwriting the committed `frontend/public/weights.json` in the working tree. *Fix:* monkeypatch `WEIGHTS` to a tmp path.
12. **LOW/MEDIUM · ENG · test_bootstrap_gate.py:32** - Hard-asserts national-scope `care_access` ci95>0 regardless of build scope and at only `n_boot=80`. *Fix:* read scope from provenance; gate the positivity assertion to national, or raise `n_boot`.
13. **LOW · STAT · RATIONALE.md:171 vs METHODOLOGY.md:118** - Two inconsistent definitions of the safety-net sub-score (E2SFCA capacity-weighted vs `FQHC-distance-pctile × poverty`); now unscored. *Fix:* collapse to the shipped definition and note unscoring.
14. **LOW · ENG · test_causal_validation.py** - Estimators tested on synthetic panels, but the real fetch/parse/join (`_build_panel`, `_state_panel`, `_build_frame`) only exercised by cache-shape tests that skip when caches absent. *Fix:* add a tiny synthetic-CSV fixture for the parse/join path.
15. **LOW · ENG · test_acceptance.py:104-113** - `test_dimensions_reproducible_from_subscores` imports the same `_pct` it validates → can only catch a stale parquet, not a wrong aggregation. *Fix:* state the narrower guarantee, or pin against a hand-computed example.
16. **LOW · ENG · compare.spec.ts:21** - `click({force:true})` bypasses the actionability check that would catch a covering overlay. *Fix:* wait for map idle then click normally, force only on timeout.
17. **LOW · STAT · test_causal_validation.py:238-250** - `_resid_age` test asserts de-correlation with age but never orthogonality to the county factor. *Fix:* also assert per-county residual means ≈ 0.
18. **LOW · STAT · RATIONALE.md:135** - §10 weights sum to 101% (60/20/21). *Fix:* make the rounded triple sum to 100.
19. **LOW · ENG · test_integrity.py:56-72** - `test_extreme_per_capita_is_flagged` / institutional tests no-op on slices lacking the trigger rows. *Fix:* include a synthetic corrupted row so the flag path always runs.
20. **LOW · STAT · README.md:15, METHODOLOGY §2** - "≈50 measures / 14 sub-scores" counts asserted nowhere. *Fix:* one-line test asserting `len(subscore_specs())==14` and scored count==12.

---

## Recommended order of operations

1. **Now:** Tier-1 mechanical bugs (§2.7 `is False`, §5.3 colors crash, §1.2 state-from-ZIP3, §5.4 worker timeout, §4.14 cache key, §6.11 life-expectancy format).
2. **This week:** make CI build a small real data slice so the guards run (§7.1); pin deps + align Python version (§4.1/4.4/4.5/4.6).
3. **Decisions needed:** default weighting scheme (§3.2), spatial clustering on causal CIs (§3.1), reconcile docs to shipped taxonomy (§7.2).

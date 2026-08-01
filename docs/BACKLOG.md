# Backlog - open edges & known limitations

Pick-up-ready tickets for the work we've deliberately deferred, plus the data-integrity findings
from the 2026-06-24 audit. Each ticket has: **what's wrong**, **why it matters**, **where to look**
(repo paths + external sources), a **suggested approach**, and **acceptance criteria**.

> **Before touching anything that changes scores:** re-baseline, then re-gate. Run
> `python -m pipeline.diagnostics` + `pipeline.verify_bands` + `pipeline.bootstrap_gate`
> (+ `pipeline.research.validate_subcounty --national` for sub-county claims). Ship only if the north star
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
- **Status (2026-08-01): DONE - three of the four had already shipped with A3 and the ticket was
  never updated.** Duplicate ZCTAs (`_validate_integrity` check 6 + `test_no_duplicate_zctas`),
  `county_fips` validity (check 7 + `test_county_fips_valid`) and the drift fingerprint
  (`_score_quantiles` → `provenance.score.score_quantiles`, p5/p25/p50/p75/p95 of the raw composite
  among scoreable ZCTAs) were all in place. Only the **geometry-vs-data join gap** was unmeasured:
  run against the national build it is **exactly 1:1 - 33,791 geometry features, 33,791 metrics
  rows, zero on either side** - which is what the left-join-onto-geometry design predicts but
  nothing checked. Now locked by `test_geometry_and_data_cover_the_same_zctas`, guarded on the real
  build (the committed 802-row slice cannot match a national geometry).

---

## B. Statistical / validity edges

### B1 (BLOCKED) - Amenable mortality is county-resolution only
- **Problem.** The §4 gold-standard result (care_access partial r +0.419 vs treatable mortality) is
  **between-county**; treatable mortality has no sub-county source, so it can't confirm fine
  within-county differences (the resolution the tool actually runs at).
- **Why it matters.** Sub-county validity still rests on §3 alone (NY ACSC + national USALEEP).
- **Where to look.** `pipeline/build_amenable.py` (recipe + ICD set), `data/manual/wonder_amenable_county.txt`,
  [VALIDATION.md](VALIDATION.md) §4; sub-county harness `pipeline/research/validate_subcounty.py`.
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
  (+0.229), + USALEEP LE national (+0.612) - composite within-county r. care_access positive in all;
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
- **Status (2026-06-25): two of three strategies DONE** (`pipeline.research.validate_placebo`,
  `pipeline.research.validate_temporal`; [VALIDATION.md](VALIDATION.md) §7). The negative-control test is a
  clean cross-sectional **null** (index predicts preventable = non-preventable deaths); the NY 2014
  event study is **suggestive** (ACSC fell more in high-baseline-uninsured ZIPs post-expansion, DiD
  -36.5/100k·SD, CI excludes 0, survives dropping 2009) but parallel-trends is imperfect, so not proof.
- **B5a (P2) - cross-state DiD with a non-expansion control.** The NY-only event study has no
  never-treated comparison and NY's pre-ACA waiver muted its shock. A non-expansion state's ZIP ACSC
  panel (TX DSHS PUDF is free but ~700MB/year-quarter; only 2019 is cached) would give a proper
  treated-vs-control DiD. **Where:** extend `validate_temporal._fetch_ny_panel` to a multi-state
  panel; reuse the TX PUDF fetcher in `validate_subcounty._fetch_tx_acsc` across years. KFF publishes
  expansion dates (free). Cost is the multi-year TX downloads, not the method.
- **B5e (built 2026-07-02) - APTC-cliff first stage.** The enhanced-premium-tax-credit expiry
  (end-2025) is a national affordability shock; `pipeline/research/validate_aptc_cliff.py` builds the
  ZIP-level first stage from the CMS 2025/2026 OEP ZIP PUFs (cached `data/raw/oep_zip_202[56].zip`;
  output `data/processed/aptc_cliff_zip.parquet`, 15,254 analyzable ZIPs, 31 FFM states).
  Result: enrollment change mean **−8.5%** (median −9.6%, aggregate −6.7%); the drop is larger
  where the access gap is worse (within-county r −0.113) and where 2025 APTC share was higher
  (within-county r **−0.169**; cross-sectional dose-response is weak, −0.05). Caveats: 3,913
  suppression-censored ZIPs dropped (censors the largest drops), FFM states only, ZIP≈ZCTA join.
  Usable as an affordability-sensitivity layer now; outcome effects (ACSC) arrive with a data lag -
  revisit as a §7-style event study when 2026+ state ACSC panels publish.
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
- **B5d (P2) - staggered FQHC New Access Point event study. BUILT and CLOSED - verdict NULL, BOUNDED.**
  The full study is done and documented in `docs/VALIDATION.md` §7f (`make fqhc-lever`). Three new
  read-only pieces, never feed the composite: `pipeline/research/build_fqhc_openings.py` (HRSA `Site Added to
  Scope` → per-ZCTA first-open year → `data/processed/fqhc_openings.parquet`), `pipeline/research/validate_fqhc_lever.py`
  (hand-rolled Callaway-Sant'Anna group-time ATT, within-state controls, NY+TX, + spillover/placebo/loose
  robustness, + a Sant'Anna-Zhao doubly-robust conditional variant), and `validate_subcounty._fetch_tx_year`
  extended to annual TX PUDF 2011-2019. Planted-effect unit tests in `tests/test_causal_validation.py`:
  3 for the CS estimator (recovers a staggered effect, differences out a common trend, exposes a
  treated-only pre-trend) and 2 for the DR variant (recovers an effect the unconditional estimator
  misses by >2x under selection-on-observables; agrees with it under random selection). Suite green.

  The verdict arrived in three stages, and only the last one stands:

  | stage | overall ATT | CI | read |
  |---|---|---|---|
  | unconditional, ZIP-cluster CI | −35.5/100k | [−71.7, +2.2] | "borderline - a powered almost" |
  | unconditional, county-block CI | −35.5/100k | [−74.1, +10.5] | ZIP-cluster CI was too narrow (ACSC is spatially autocorrelated); the borderline is already null |
  | **doubly-robust conditional (final)** | **−4.3/100k** | **[−38.0, +35.4]** | the near-miss was observable *siting* |

  **Final result:** pooled NY+TX, 259 newly-served treated (≈ the gate's powered 277 scenario). HRSA
  sites clinics where ACSC is high *and rising*, and the panel measures both; conditioning each ATT(g,t)
  on pre-window ACSC level + slope, poverty and log pop removes roughly +31 of the −35.5. Per Ding & Li
  (2019) bracketing, the unconditional and conditional estimates bound the truth from either side, so
  **the supply effect lies in [−35.5, −4.3]/100k with both ends indistinguishable from zero** - benefits
  larger than ~3% of the ~1,300/100k baseline are ruled out at 95%. The supply arm therefore lands where
  the affordability arm did (§7e): **no demonstrated lever**, but as a well-identified bound rather than
  an ambiguous near-miss.

  **Do not reopen this as a near-miss.** The `−35.5 / [−71.7, +2.2]` figure is superseded twice over and
  survives only as the first row of the table above. Any future extension is an attempt to tighten an
  already-bounded null, not to rescue a borderline - see **B5f** for why that changed the calculus.
  The original plan follows for the record.

- **B5f (P3) - Missouri replication + harmonized three-state pool. PRE-REGISTERED, then SHELVED
  before any data (2026-08-01). Never run.** Pre-registration and closeout: `docs/PREREG_B5f.md`.
  The plan was a MOPHIMS/MICA ZIP-level preventable-hospitalization panel for Missouri, a standalone
  Callaway-Sant'Anna replication, and a harmonized NY+TX+MO pool. **Gate 0 passed** (the 2015-and-Prior
  module does expose ZIP geography, giving a continuous 2001-2022 annual ZIP panel), and resolving it
  surfaced a real **2015/16 ICD-9→ICD-10 definitional break** between the two MICA modules, which is
  pre-registered in §8a and enforced in code.

  **Shelved because its premise was already stale.** `PREREG_B5f.md` §0 motivates the whole exercise
  from B5d as a near-significant borderline (−35.5, [−71.7, +2.2]) needing ~+22 treated ZCTAs to cross.
  Both the spatial-inference update and the doubly-robust re-estimate had already landed on `master`
  (see B5d above): the honest CI is [−74.1, +10.5] and the conditional point estimate is −4.3. There is
  no borderline left to rescue, so the pre-registration's purpose - preventing a marginal positive from
  being reverse-engineered into significance - no longer applies. Missouri's remaining value is a wide,
  zero-crossing corroboration of an already-bounded null (§2 predicted 35-50 treated ZCTAs), which does
  not change the published conclusion, and it cannot add N to the NY+TX estimator because its condition
  definitions differ.

  **What exists:** `pipeline/research/build_mo_acsc.py` (Playwright MICA extractor) and `tests/test_mo_acsc.py`
  (24 browser-free parsing tests). No Missouri counts were ever extracted. The parsing path is sound;
  **the browser path has two unfixed defects** recorded in `PREREG_B5f.md` §7 - `_counties()` reads the
  wrong `<select>` before the geography cascade, and the scrape requests "Counts and Rates" while the
  parser assumes one column per year. Fix both before any future run.

  **Reopen only if** the paid panels are bought (Florida ~$1,100 / Oklahoma ~$550, both confirmed
  5-digit patient ZIP) - those add N to the *existing* estimator, which free-state replication cannot.
  That is a spend decision, not an analysis decision.

- **B5d (P2) - staggered FQHC New Access Point event study.** The sharpest free-data shot at a
  *positive* causal lever: HRSA awards New Access Point (NAP) grants in waves, each opening a dated,
  located FQHC site - a discrete shock to the **supply / safety-net arm** of `care_access` (the arm
  §7b/§7e never tested; the ACA work tested affordability). Staggered timing → a Callaway & Sant'Anna
  (2021) group-time ATT / event study, using **not-yet-treated + never-treated** ZIPs as controls -
  which avoids the forbidden-comparison sign-flip that two-way FE suffers under heterogeneous timing
  (Goodman-Bacon 2021; de Chaisemartin & D'Haultfœuille 2020). Outcome = ZIP ACSC, reusing the
  state panels (NY/TX/CO/CA). **Treatment timing turned out to be already in hand**: the cached
  `data/raw/hrsa_fqhc_sites.csv` carries **`Site Added to Scope this Date`** per site (the
  new-access-point opening event), so a `ZIP x year -> first FQHC opened` panel is a groupby, not a
  download - `build_fqhc.py` just never surfaced the date column. The B5d.0 gate below already used it
  to ground the treated-N; remaining build lift is wiring those cohorts to the state ACSC panels + the
  Callaway-Sant'Anna estimator, not data hunting.

  - **B5d.0 (the go/no-go gate) - DONE, verdict GREEN-LIGHT** (`pipeline/research/validate_fqhc_power.py`,
    `python -m pipeline.research.validate_fqhc_power`; run 2026-06-26). A Monte-Carlo power analysis on the
    REAL noise floor before any treatment-panel assembly. **Result:** the design is well-powered.
    - *Noise floor (real NY SPARCS panel, decomposed):* residual variance = an **irreducible
      heterogeneity floor sqrt(a)=191/100k** + a sampling term b/pop; AR(1) rho=0.32; baseline
      1,278/100k. Lever 3 (pop-weighting, §7d) cuts the effective SD 28% (319->231) but **barely moves
      the MDE** - because WLS can only beat the sampling term, never the floor, and pop-weighting even
      concentrates weight on big ZIPs that carry the full floor. So lever 3 is NOT the unlock.
    - *Treated-N (real HRSA count) IS the binding lever, and it is large.* "Site Added to Scope"
      openings (active, geocoded, 2012-2019) over the four panel states: 1,685 openings -> 874 unique
      ZCTAs -> **555 NEWLY-served ZCTAs** (no prior site = the clean new-access-point treatment), 8
      staggered cohorts of 51-100/yr (CA 243, TX 142, NY 135, CO 35). The earlier 40-150 guesses were
      ~10x too low.
    - *Verdict:* central design (n_treated=350 after ~37% outcome-coverage attrition, pop-weighted)
      **MDE = 4%**, below the 5% plausible-band midpoint - detects the LIKELY FQHC effect at >=80%
      power (power 0.91 at 4%, 0.96 at 5%). Even the pessimistic 200-ZIP / 8-yr design reaches MDE 5%.
      Underpowered ONLY if the true effect sits near the 2% floor. **=> proceed to the full B5d build.**
    - *Method retained below for the record (and to re-run with refined assumptions):*
    - *Noise floor (free, in hand):* residual SD + within-ZIP AR(1) of ZIP ACSC after two-way
      demeaning, estimated directly from the existing `validate_temporal._fetch_ny_panel()` (+ the TX/CO
      panels via `validate_subcounty`). This is the variance the estimator actually fights.
    - *Dose / dilution:* plausible per-capita ACSC reduction from one new FQHC × catchment penetration
      (treated fraction = new-FQHC patients / ZIP pop); parameterize as a range and report the
      **minimum detectable effect (MDE)** at 80% power, not a single guess. Anchor the effect range to
      the FQHC→preventable-hospitalization literature.
    - *Design dimensions:* number of treated ZIPs × cohorts is the binding constraint - only the 4
      state panels have the outcome, so simulate over realized per-state NAP award *counts* (rough HRSA
      tallies, no geocoding yet) × treatment years × panel length × control pool.
    - *Estimator in the loop:* simulate the CS group-time ATT + aggregation with the project-standard
      ZIP-cluster bootstrap, so the MDE reflects the real inference spec, not an i.i.d. approximation.
    - *Add spillover:* a catchment-leakage parameter (treated clinic serves neighboring control ZIPs)
      that attenuates the treated fraction - SUTVA is violated by construction, so bound its cost.
    - **Decision rule:** if MDE > the plausible effect range → underpowered-by-construction → **don't
      build B5d**; ship the negative result itself (an honest, citable "the free-data supply lever is
      underpowered at ZIP resolution" finding, in `docs/VALIDATION.md` §7). If MDE < plausible effect →
      green-light the HRSA NAP panel assembly and the full study. Either branch is a real deliverable.
    - **Effort:** small - one simulation module (~few hundred lines), reuses the existing panel +
      bootstrap; no heavy downloads. This is the cheap insurance against sinking the multi-year-download
      effort into a study that can't detect anything.

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
- **Status (2026-06-25): the scrape-to-calibrate lever was RUN, and it COLLAPSES.**
  `pipeline/research/validate_acceptability.py` (`make acceptability`) pulled the full NY Medicaid-enrolled
  provider directory (Socrata `keti-qx5t`, ~1.1M rows), built a per-ZIP **acceptance rate** =
  Medicaid-enrolled primary-care NPIs / all local NPPES primary-care providers, and tested it
  against the independent NY SPARCS PQI_90 ACSC O/E outcome with a county-cluster bootstrap.
  Result over 1,103 NY ZIPs: **raw corr +0.047 (near-zero, wrong sign); partial r controlling for
  need+vuln+care_access = +0.040, 95% CI [-0.037, +0.125]** - includes 0 and points the wrong way.
  So Medicaid-acceptance density adds NO protective signal beyond supply + the deprivation gradient
  (it mostly re-expresses provider supply, already captured by care_access). This confirms the prior
  qualitative C1 finding with a measured number. **Keep BLOCKED.** The remaining untried angle is
  *Accommodation* (hours / after-hours / appointment availability), for which no free national ZIP
  source exists. Re-run any time with `make acceptability`; NY-only, no DUA.

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

### D1 (P2) - Web payload / cold-load weight (the PMTiles item) — RESOLVED
- **Problem (original).** ~16.7 MB `zcta.geojson` (~4.5 MB gzip) + ~30 MB `metrics.json` were loaded
  eagerly on every cold visit (~45 MB parsed to JS objects + Maps). OOM risk on low-memory mobile; the
  single biggest scalability liability. Mitigated (gzip_static, off-main-thread worker parse, hashed
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
  client reweighting).
- **Status (2026-06, `perf/mobile-and-bundle`): structural fix DONE.** The 16 MB single-blob geometry
  is gone — geometry is now **hybrid**: a small heavily-simplified `zcta_overview.geojson` for the
  national choropleth at z<6 plus range-requested **PMTiles** vector tiles (`zcta.pmtiles`,
  tippecanoe) at z>=6, wired through `frontend/src/lib/data.ts` / `dataWorker.ts` / `store.ts` /
  `MapView.tsx` and built by `pipeline/build_pmtiles.py`. `zcta.geojson` is now an unshipped pipeline
  intermediate (input to tiling), not a payload. Cold-load geometry and resident memory are bounded;
  the remaining slim-`metrics.json` split into a coloring payload + on-demand sub-scores is the only
  optional follow-up left.

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

---

## E. Backend / API (from the 2026-08-01 static-analysis sweep)

Found by running a Python AST analyser (`py-ast-mcp`, `dead_code` + `find_errors`) over
`pipeline/` — 43 files, 500 definitions. The scoring code came back **clean: zero unreferenced
private symbols.** The findings are all in constants and in the API layer.

### E1 (P1) - `RAW_DISPLAY` has never been wired up; the per-ZIP API returns the entire row

- **Problem.** `pipeline/join_and_score.py:430` defines `RAW_DISPLAY` with the comment
  *"everything the detail panel shows; served per-ZIP via the API"*. **It is not.** No line in
  `pipeline/`, `backend/`, `tests/` or `frontend/` reads the name. `git log -S RAW_DISPLAY`
  returns only the initial commit `62d4143` - it has been dead since the project's first commit.

  Meanwhile `backend/data.py:85` `record()` returns
  `{k: _clean(v) for k, v in row.to_dict().items()}` - **every column of `metrics.parquet`**,
  not the intended display subset. So the whitelist was designed, and then never applied.

- **Why it matters.** Three separate consequences, in increasing severity:

  1. *Payload.* `/api/zcta/{zcta5}` ships every internal column - percentile scratch columns,
     intermediate sub-score inputs, flags - where the client consumes roughly 6 fields read
     directly in `DetailPanel.tsx` plus ~57 driven by `measures.ts`. The response is several
     times larger than the UI needs, on the one endpoint the detail panel hits per click.
  2. *Coupling.* Every column added to the frame silently becomes public API surface. There is
     no typed contract for this response in `frontend/src/lib/types.ts`, so nothing catches it.
  3. *Memory - the real one.* `record()` is decorated `@lru_cache(maxsize=None)`. The key space
     is ~33k ZCTAs and each cached value is a full-width Python dict. A warmed cache (a crawler,
     a scripted scan, or simply time) therefore accumulates a second, *fatter* copy of the whole
     frame as Python objects, on top of the ~60 MB pandas frame. `DEPLOY.md` specifies a
     **minimum 1 vCPU / 1 GB RAM VPS**. This is an unbounded-growth path on a box sized with no
     headroom for it.

- **Where to look.**
  - `pipeline/join_and_score.py:430` (`RAW_DISPLAY`) - and note `SUBSCORE_COLS` immediately above
    it, which *is* used, so the pattern was clearly intended.
  - `backend/data.py:78-85` (`record()`), `backend/main.py:77-83` (the route).
  - `frontend/src/components/DetailPanel.tsx`, `frontend/src/lib/measures.ts` (the real consumer set).

- **Suggested approach.** Cheapest first, and do them in this order:
  1. Bound the cache. `maxsize=None` -> a real bound (e.g. 4096). One-line, removes the OOM path
     immediately, independent of everything below.
  2. Emit `RAW_DISPLAY` from `join_and_score` into a small JSON/meta artifact, and have
     `record()` project onto it. Keep serving the full row behind an explicit
     `?full=1` for debugging so nothing is lost.
  3. Mirror the projected shape as a type in `types.ts` so the contract stops being implicit.
  - **Derive the whitelist from the code, not by hand** - union the `measures.ts` cols with the
    fields `DetailPanel` reads, and diff against `RAW_DISPLAY` before trusting it. It was written
    at commit 1 and has never been exercised, so it is very likely stale.

- **Acceptance.** `record()` returns only whitelisted fields; the detail panel renders with no
  missing values across a sample of ZIPs including a `low_confidence` and an `institutional` one;
  cache is bounded; a test asserts the response key set equals the whitelist.

- **MEASURED (2026-08-01)**, against `tests/fixtures/metrics_slice.parquet` (802 rows x **181 cols**,
  the real column set) with the suite un-skipped by copying the slice to `data/processed/metrics.parquet`:

  | quantity | measured |
  |---|---|
  | columns returned per `/api/zcta/{zcta5}` | **181** |
  | JSON bytes per record | ~5.5 KB |
  | deep `sys.getsizeof` of one cached row dict | **22,829 bytes** |
  | unbounded cache, fully warmed (33k ZCTAs) | **718 MB** |
  | bounded at 4096 (shipped fix) | **89 MB** |
  | pandas frame itself, scaled to 33k | 56 MB |

  Against the `DEPLOY.md` floor of **1 GB RAM**: frame (56 MB) + fully-warmed cache (718 MB) +
  interpreter + FastAPI/uvicorn does not fit. The bound takes the cache term from 718 MB to 89 MB.
  The frontend consumes roughly 60 of the 181 columns, so the projection in step 2 is worth
  roughly a further 3x on payload - but the cache bound is what removes the OOM, and it is shipped.

- **RESOLVED 2026-08-01. Step 1 shipped; steps 2-3 declined; `RAW_DISPLAY` deleted.**
  - Step 1 (bound the cache) is in `backend/data.py` at `maxsize=4096`. That is what closed the OOM,
    and it is the whole of the severity here.
  - Steps 2-3 (whitelist projection + `types.ts` mirror) are **not being done.** They buy ~3x on the
    payload of one endpoint that is already fast, and cost a generated meta artifact, a `?full=1`
    debug escape hatch, and a hand-maintained type mirror - three new things to keep in sync to make
    a non-problem smaller. Revisit only if the detail-panel payload shows up in a real measurement.
  - `RAW_DISPLAY` itself is **deleted** (`pipeline/join_and_score.py`), along with the now-orphaned
    `CONTEXT_ACS` / `CONTEXT_PLACES` import. It had been dead since the project's first commit while
    its comment claimed to describe the live API response - the discrepancy that made this finding
    look like a contract violation rather than the memory issue it actually was. A constant nothing
    reads cannot document anything; deleting it is the fix.

- **Do NOT** treat this as a scoring change. It touches display and transport only - `metrics.parquet`
  is unchanged, so no re-baseline or re-gate is required.

### E2 (P3) - dead constants

Confirmed unreferenced across the entire repo (`*.py`, `*.ts`, `*.tsx`, `*.json`, `Makefile`, docs):

| symbol | location | note |
|---|---|---|
| `ACS_BASE_SUBJECT` | `config.py:80` | ACS *subject*-table endpoint; the pipeline uses detailed tables |
| `ACS_VARS_SUBJECT` | `config.py:82` | same lineage |
| `ACS_UNINSURED_GROUP` | `config.py:90` | `B27001`; insurance now sourced elsewhere |
| `BASEMAP_STYLE` | `config.py:209` | unused in Python, but `MapView.tsx:17` says *"Mirrors pipeline/config.py BASEMAP_STYLE"* - a stated mirror of a constant nothing reads, so the two can drift silently |
| `XWALK_CACHE` | `validate_subcounty.py:59` | duplicates the literal in `common.py:166`; `_xwalk()` delegates to `common.load_zcta_tract_xwalk()`, so this copy is never read and can drift from the real cache path |

- **Suggested approach.** Delete the three ACS constants and `XWALK_CACHE`. For `BASEMAP_STYLE`,
  either delete it and drop the "mirrors" comment in `MapView.tsx`, or genuinely emit it into
  `meta.json` so the frontend reads one source of truth. Don't leave it as a comment-only contract.
- **Acceptance.** `py-ast-mcp dead_code pipeline/` reports zero unreferenced symbols.

- **RESOLVED 2026-08-01 - all five deleted.** The three ACS constants and `XWALK_CACHE` went as
  suggested. `BASEMAP_STYLE` was **deleted rather than emitted into `meta.json`**: the frontend is
  the only consumer, so routing a URL that has never changed through a generated artifact and a
  fetch adds a build step and a failure mode to sync one string to itself. The `MapView.tsx` comment
  no longer claims to mirror anything - it now states that the frontend holds the sole definition.
  `RAW_DISPLAY` (E1) was deleted in the same pass.

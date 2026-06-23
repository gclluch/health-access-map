# Roadmap: strengthen the access signal (gated, verify-after-each-layer)

> **STATUS (2026-06-23):** **Layers A, B DONE; Layer C: C1/C2/C1-redux gate-failed (not scored),
> C3 + C5 SHIPPED (the two wins).** C3's variable/adaptive catchment doubled provider_supply's
> clean-outcome signal (+0.13 → +0.265, FULL 0.479 → 0.486). **C5 added HRSA HPSA as its own
> `shortage_designation` sub-score (FULL 0.486 → 0.492, agreement → 0.495).** C4 (Medicaid
> acceptance) researched - no free national file. Earlier baseline notes below are pre-C3/C5.
>
> **Original status:** Branch `feat/composite-validation-uncertainty`. **Layers A and B
> are DONE.** Layer A (`aa21461`) flipped the north star: `drop_care_access` is now *below* FULL
> (care access ADDS signal). Layer B propagated ACS measurement noise into the rank bands -
> low-confidence ZCTAs now get visibly wider 5-95 bands (median ≈27 vs ≈10 for high-confidence),
> calibrated to an independent input-resample. **Layer C is open.** Two harnesses gate the work:
> `python -m pipeline.diagnostics` (point-score signal) and `python -m pipeline.verify_bands`
> (the band gates); **run both first to re-baseline** before any C work.

The composite is a strong *deprivation* gradient whose *care-access* dimension was its
weakest link - originally **dropping care_access improved outcome agreement** (0.445 → 0.456),
because `provider_supply` is confounded, `safetynet_access` was wrong-signed, and `household`
was near-signal-less. Layer A fixed the latter two. This roadmap fixes the rest, cheapest-first,
with a mandatory verification gate after every layer. No layer ships unless it passes its gate.

Recommended order: **A (model fixes) → B (uncertainty) → C (capacity data)** - rising cost,
falling certainty. A and B are self-contained; C is multi-step and partly shared with the
supply-enrichment stream (coordinate via COORDINATION.md).

---

## 0. The verification harness (run after EVERY layer)

Build once: `pipeline/diagnostics.py` reading `metrics.parquet` + the 6 independent outcomes
(life_expectancy, preventable_hosp, premature_death, infant_mortality, flu_vaccination,
mammography). Orient each higher = worse (negate LE / flu / mammography). It prints five
checks; a layer **passes only if all five hold**.

| # | Check | Pass criterion |
|---|---|---|
| 1 | **North star - dimension marginal value.** Composite mean-r vs 6 outcomes, FULL vs drop-each-dimension. | `drop_care_access` mean-r **decreases** vs the pre-layer run (care access becoming a net-positive contributor). Goal state: dropping care access *hurts* (drop_care_access < FULL). |
| 2 | **Changed-component sign & strength.** For each sub-score/measure touched: signed r vs each outcome + mean\|r\|. | Signs correct (higher barrier → worse outcome; positive r). mean\|r\| **≥** its pre-layer value. |
| 3 | **Composite outcome agreement.** Composite mean-r vs 6 outcomes. | **≥** pre-layer baseline (no regression). |
| 4 | **Internal reliability.** Split-half Spearman-Brown (overall + low-pop). | **≥ 0.93** overall; low-pop not down >0.01. |
| 5 | **Coverage & contracts.** scoreable count; percentile/rate ranges. | scoreable within ±1%; all percentiles ∈[0,100]; rates ∈[0,1]. |

**Baselines to beat (post-Layer-A, the current build):** FULL mean-r **0.479**;
drop_care_access **0.469** (already < FULL → care access ADDS signal; keep it that way);
composite_mean_r 0.479; split-half 0.955 / low-pop 0.939; scoreable 33176. Care sub-score
mean\|r\|: provider_supply **0.17** (still weak - Layer C target), safetynet **0.233** (fixed),
insurance 0.34, preventive 0.27. (Pre-Layer-A baseline was FULL 0.445 / drop_care_access 0.456.)

**Rollback rule:** if check 1 or 3 regresses, revert or retune the layer before proceeding -
exactly as state→county shrinkage was retuned when state-level dropped LE validity.

---

## Layer A - cheap model fixes (taxonomy/scoring only) ✅ DONE (commit aa21461)

Two wrong components were actively subtracting signal. Both were config/scoring edits, no new
data. **Result: FULL 0.445→0.479, drop_care_access 0.456→0.469 (flipped to net-positive).**
A1 removed `household` (all 3 members failed; limited-English wrong-signed −0.25 vs infant
mortality). A2 reframed FQHC to `safetynet_barrier = FQHC-distance-pctile × poverty` in
`join_and_score.py` (verified it adds signal beyond poverty; sub-score 0.118→0.233). Details below.

### A1. Reclassify the `household` sub-score
**Problem:** age65_rate / age17_rate are demographic *context*, not access barriers - at the
area level they're near-signal-less and partly wrong-signed (retirement areas read "vulnerable"
but have good access). limited_english_rate *is* a real barrier (Acceptability axis).
**Change (`pipeline/taxonomy.py`):** remove `household` as a vulnerability sub-score; move
`limited_english_rate` into `socioeconomic` (or a slim "language access" sub-score); demote
`age65_rate`/`age17_rate` to `CONTEXT_ACS` (median_age/pct_under5 already live there).
**Verify (harness):** social_vulnerability mean\|r\| should rise; composite mean-r ≥ baseline;
care-access north-star unaffected (sanity). If limited_english alone underperforms as its own
sub-score, fold it into socioeconomic and re-run.

### A2. Fix or remove the FQHC `safetynet_access` wrong-sign
**Problem:** FQHCs are *placed* in high-need areas, so raw "FQHC access" is highest where need
is highest → the "low safety-net access" barrier reads wrong-signed (−0.21 vs LE).
**Change - try in order, gated:**
1. **Need-relative reframe (preferred), in `join_and_score.py` from existing columns:** define
   the barrier as unmet safety-net need = high uninsured/poverty **AND** poor FQHC access, e.g.
   `safetynet_barrier = pctile( uninsured_rate_pctile − fqhc_access_pctile )` clipped, or a
   need-weighted FQHC shortfall using `nearest_fqhc_km` × `uninsured_rate`. Re-rank.
2. If the reframe still doesn't flip positive, **remove `safetynet_access` from the composite**
   (keep it as a displayed/diagnostic layer only) pending an E2SFCA redesign in the supply
   stream (coordinate - that touches build_fqhc/build_supply).
**Verify (harness):** safetynet sub-score signed r must become **positive** vs ≥4 of 6 outcomes;
composite mean-r ≥ baseline; **drop_care_access north-star must improve** (this is the main win).

**Layer A exit gate:** all 5 checks pass AND drop_care_access mean-r has fallen from 0.456.

---

## Layer B - put input noise into the rank bands ✅ DONE

Before B, `access_gap_rank_lo/hi` captured only *weighting* sensitivity, so they were ~flat
across reliability (low-conf ≈10 vs high-conf ≈9, ratio 1.15×). Layer B propagates ACS
**measurement noise** into the bands, so the band now answers "how precisely can we place this
ZCTA" honestly. **Result: low-conf median band ≈27 vs high-conf ≈10 (ratio 2.66×); overall
median ≈13 - matching `docs/COMPOSITE-EVALUATION.md`'s independent ~10-15pt comparability
threshold.** Point scores are unchanged (composite mean-r 0.479, reliability 0.955/0.939,
scoreable 33176 all hold). New gate harness: `python -m pipeline.verify_bands`.

### B1. Persist per-ZCTA input uncertainty ✅
**`pipeline/build_acs.py`:** `_apply_shrinkage` now emits a per-ZCTA `acs_input_cv` (mean of
**raw** SE/estimate across the scored rates, clipped [0,2]) into acs.parquet before dropping
the `<rate>_se` columns. Uses the *raw* published SE, not the post-shrinkage posterior SD -
see the gate-2 note below for why. `HAM_SE_DEBUG=1` additionally dumps per-rate raw SEs to a
gitignored `acs_se_debug.parquet` that the gate-3 calibration resamples from (no re-fetch).

### B2. Two-source Monte-Carlo in `_rank_uncertainty` ✅
**`pipeline/join_and_score.py`:** each Monte-Carlo draw now perturbs weights (15-55%) AND each
ACS-derived dimension percentile by σ_z = SCALE·share_dim·clip(cv−cv_floor, 0, cap), cv_floor =
the national-median CV (so well-measured ZCTAs get zero added noise and keep their weighting-
only width). `share_dim` = the per-dimension ACS-noise propagation share (social_vulnerability
1.0, care_access 0.60 - both *measured* by gate 3, not guessed; health_need is PLACES → 0).
SCALE=36 is calibrated so the injected σ lands within ±20% of the gate-3 input resample.

### B3 (optional, larger; NOT done). Pull PLACES confidence intervals for the health_need /
preventive members and fold their noise in the same way (health_need currently carries no
measurement-noise term).

**Verify (`pipeline/verify_bands.py`, dedicated - not the standard harness):**
- **Gate 1 - Differentiation:** ✅ low-conf median band ≥1.6× high-conf. Result **2.66×** (27.0 vs 10.1).
- **Gate 2 - Shrinkage visible: DROPPED (reframed).** The original plan ("low-conf bands *narrower*
  with shrinkage ON, using the post-shrinkage effective SE √γ·SE that feeds B2") is statistically
  incoherent here: EB shrinkage drives γ→0 for the noisiest ZCTAs, collapsing their posterior
  variance *below* well-measured ones, which **inverts** Gate 1 (empirically: effective-SE CV
  ratio low/high = 0.52, vs raw-SE CV ratio 3.12). Gates 1 and 2 cannot both hold via the
  posterior-SD route. Decision: the bands use the **raw** input CV (honest "how precisely do we
  measure this ZCTA"); shrinkage's value is a *point-estimate* improvement, already proven and
  gated in Layer 0 (it improved 3/4 independent outcomes). We do not double-credit it in the band.
- **Gate 3 - Calibration:** ✅ the injected σ(cv) matches an independent member-input resample
  (perturb each ACS rate by its published SE, propagate member→sub-score→dimension percentile)
  within ±20% per ACS dimension. Result: social_vulnerability inj/emp **0.93**, care_access **1.15**.
- **Standard harness checks 3-5** still hold (point scores unchanged): ✅ composite 0.479,
  reliability 0.955/0.939, scoreable 33176.

**Layer B exit gate (MET):** low-conf bands clearly wider than high-conf (gate 1); injection
calibrated to the input resample (gate 3); point scores unregressed. Gate 2 retired as above.

---

## Layer C - capacity / realized-access data (the big lift; do last)

The bottleneck is the **input**: NPPES counts registrations, not capacity/acceptance/use. Each
sub-layer adds one data source and is gated independently. Several touch build_providers/
build_supply (supply-enrichment stream) - coordinate, don't clobber.

### C1. Realized utilization as a care-access INPUT (highest impact)

> **RESULT (2026-06-21): ATTEMPTED, FAILED THE GATE, BACKED OUT (kept as merged context, not
> scored).** Built `build_utilization.py` from the **CMS Medicare Geographic Variation PUF**
> (county-level, 2024): `BENES_EM_PCT` / `BENES_TESTS_PCT` / `BENES_OP_PCT` ("% of FFS benes
> with a visit"), mapped county→ZCTA via `geonames.county_fips`, as a `realized_access`
> sub-score. Across all 6 outcomes it *looked* like a win (FULL 0.479→0.487, sub-score
> mean|r| 0.247). **But that lift was circular:** the only strong correlations were with
> flu (+0.66) and mammography (+0.54) - themselves validation outcomes, and mechanically the
> same construct ("engaged with healthcare"). Against the **independent death-records
> outcomes** it carries ~no signal (**life_expectancy r = −0.00**, premature_death +0.21,
> infant_mortality +0.03, preventable_hosp −0.05). The honest north star (composite mean-r vs
> the clean mortality/ACSC outcomes only, dropping flu+mammo) **regressed 0.4796 → 0.4695**.
> Root causes: Medicare visit-rates are **saturated** (~90% median), **need-endogenous** (sick
> areas use more care, not less), and **65+/disabled only**. Raw visit-rates are the wrong
> instrument. A future C1 needs *condition-specific quality-of-care* rates (e.g. HbA1c testing
> *among diabetics*, diabetic eye exams) from the **Dartmouth Atlas / CMS MMD**, which measure
> realized access conditional on need - not raw use. The stage + data remain for that work and
> for display; they are deliberately not in the composite.

**Data:** CMS Mapping Medicare Disparities and/or Dartmouth Atlas - county/ZIP service-use rates
(annual wellness visit, diabetic HbA1c/eye-exam, etc.). **Guard against circularity:** flu &
mammography are already *validation outcomes*; do NOT also use them as inputs. Use *different*
utilization measures as the input, and validate against the held-out mortality/ACSC outcomes.
**Change:** new stage `build_utilization.py` → county→ZCTA crosswalk (reuse geonames) → a new
`realized_access` sub-score under care_access in `taxonomy.py`.
**Verify (harness, emphasis on north star):** `realized_access` signed r positive vs held-out
outcomes; care_access mean\|r\| rises; **drop_care_access must now HURT** (care access finally a
net-positive contributor). If it doesn't, the utilization measure chosen is too proxy-distant -
try another before shipping.

### C2. Capacity-weight NPPES NPIs (shared with supply stream)

> **RESULT (2026-06-21): ATTEMPTED, FAILED THE GATE, NOT SCORED (columns kept as diagnostics).**
> Built a per-NPI Medicare-activity weight `w = benes/(benes+K)` (K=128 median benes) from the
> **CMS Medicare Physician & Other Practitioners by-Provider PUF** (1.24M individual NPIs),
> joined in the `build_providers` DuckDB pass, summed per ZCTA for primary + mental (scoped:
> Medicare doesn't validly cover dental/OB/peds). E2SFCA'd into `primary_2sfca_cap` /
> `mental_2sfca_cap`. **Offline gate vs the clean outcomes: provider_supply mean signed-r
> 0.132 (count) → 0.129 (capacity) - a non-win.** premature_death nudged up (+0.249→+0.264)
> but infant_mortality dropped (+0.246→+0.237, the pediatrician-zeroing predicted by the
> Medicare population mismatch), netting flat-to-worse. Conclusion: provider_supply's weakness
> is **not** dormant registrations - it is the spatial/urbanicity confound (→ C3) plus the
> intrinsic weak ecological link of supply to mortality. Capacity columns remain for diagnostics
> and possible reuse under C3; deliberately not in the composite.

**Data:** CMS Medicare Provider Utilization & Payment (claims volume per NPI) or HRSA Area Health
Resource Files FTE counts. **Change (build_providers/build_supply - coordinate):** weight each NPI
by activity (claims volume, or FTE) before the E2SFCA, so dormant/low-volume NPIs count less.
**Verify:** capacity-weighted `provider_supply` signed r vs outcomes must beat raw-count supply's
current ~0 vs mortality (target: clearly positive vs premature death / ACSC). Compare side-by-side
(keep both columns during evaluation); ship only if the weighted version wins on the harness.

### C3. Drive-time catchment (shared with supply stream)

> **RESULT (2026-06-21): SHIPPED - the first Layer-C win.** True OSRM drive-time was
> infeasible here, so we used its most-cited feasible analog: a **variable/adaptive catchment**
> (McGrail & Humphreys 2009). Each ZCTA's Gaussian bandwidth = distance to the 30th-nearest
> centroid, clipped to [8, 60] km (median 36) - small in cities, wide in sparse rural areas,
> directly removing the fixed-radius urbanicity artifact. **All five gate checks pass:**
> provider_supply mean|r| **0.173 → 0.273**; vs the clean death-records/ACSC outcomes its signed
> r **roughly doubled, +0.13 → +0.265** (premature_death +0.37, infant_mortality +0.39,
> life_expectancy ~0 → **+0.16**, preventable_hosp ~0 → +0.14 - all now correctly signed and
> non-circular); FULL composite 0.479 → 0.486; composite agreement 0.479 → 0.488; split-half
> 0.956 (held); scoreable unchanged. The HRSA 3,500:1 shortage flag is now computed from a fixed
> 16 km service area (the adaptive catchment is for the scored percentile, not an absolute
> benchmark). `config.ADAPTIVE_CATCHMENT` toggles it. This is the lever the whole project needed:
> the access dimension's weakest link is now solid, and supply finally tracks all-cause mortality.

**Data:** OSRM road-network routing (open-source) or a precomputed ZCTA-centroid travel-time
matrix. **Change (build_supply - coordinate):** replace the 16 km straight-line catchment with
drive-time isochrones in the E2SFCA.
**Verify (the confound test):** re-run the density-stratified supply-vs-outcome correlation
(`validate.py` `supply_density_confound`). Today the sign flips across population quintiles
(−0.10 rural → +0.09 urban). Pass: the sign is **consistent** across quintiles (the urbanicity
artifact is gone). Plus standard harness.

### C4. Medicaid / new-patient acceptance (stretch / research)
**Data:** state Medicaid provider directories or a national acceptance proxy - the Acceptability
axis NPPES omits entirely. Research feasibility first; likely partial coverage. **Verify:** as C2.

> **RESEARCHED (2026-06-23): no free national file exists.** Medicaid-accepting / accepting-new-
> patients data lives only in fragmented per-state directories and restricted T-MSIS (DUA required).
> The closest free proxy is the CMS Doctors & Clinicians NDF `ind_assgn`/`grp_assgn`
> (accepts-Medicare-assignment) flag - but that is near-saturated nationally (~96%), so low variance
> = low expected signal. Deprioritized; not built.

### C5. HRSA HPSA shortage designation ✅ SHIPPED (2026-06-23) - the second Layer-C win

> **RESULT: SHIPPED as its own `shortage_designation` sub-score under care_access.** Primary-care
> HPSA "HPSA Score" (0-26, higher = worse), max per county, county→ZCTA via geonames, 0 for
> non-designated (`build_hpsa.py`, free daily CSV from data.hrsa.gov). **Near-orthogonal to our
> E2SFCA density (corr 0.05)** yet clean signed-r **+0.20** on its own (premature_death +0.28,
> life_exp +0.17, infant_mort +0.22, preventable_hosp +0.13) and **+0.19 partial controlling for
> existing supply** - genuinely additive, not a duplicate count. **FULL 0.486 → 0.492, composite
> agreement 0.488 → 0.495**; drop_care_access holds at 0.469 so care-access margin widens to
> +0.023; split-half 0.943 (≥0.93 gate; dipped from 0.956 as expected for a coarse orthogonal
> input, low-pop rose to 0.944); scoreable unchanged; band gates re-pass after retuning
> `_ACS_SHARE[care_access]` 0.60 → 0.47 (the new no-ACS-noise sub-score diluted care_access's ACS
> share). **Kept SEPARATE, not folded into provider_supply** - at corr 0.05 the averaging-then-
> rerank inside provider_supply washes out its distinct signal (folded gave only FULL 0.488).
>
> **Negatives gate-tested at the same time (don't re-run):** mental-health HPSA (+0.09) and dental
> HPSA (+0.12) are subsumed by PC-HPSA (corr 0.59/0.75, partial-r ≈ −0.05 beyond it); the MUA/IMU
> index is wrong-signed at ZCTA (−0.04, its elderly term makes retirement areas read "served").
> Dartmouth diabetic process measures (the predicted C1-redux) carry +0.04 clean - rejected.

**Layer C exit gate (the whole point of the project):** with C1-C3 in, the north-star flips -
`drop_care_access` mean-r is **below** FULL, i.e. the access dimension finally *adds* outcome
signal instead of subtracting it. That is the definition of done for "make this an access tool."

### C6. Digital / telehealth access ✅ SHIPPED (2026-06-23)

> **RESULT: SHIPPED as `digital_access` sub-score under social_vulnerability** (ACS B28002
> no-internet rate, `build_broadband.py`). The telehealth analog of the no-vehicle transport
> barrier. Solo clean signed-r **+0.25** (premature_death +0.35, infant_mort +0.31, life_exp
> +0.23), non-circular. **A reliability/completeness add, NOT a signal win:** in care_access it
> *regressed* the composite (collinear with provider supply, corr 0.33); in social_vulnerability
> it holds agreement at 0.495 and lifts split-half **0.943 → 0.955**. Placement lesson: put a
> non-circular-but-collinear measure where it completes a dimension without diluting a distinct
> sub-score. Band `_ACS_SHARE` re-verified (social_vuln inj/emp 1.11, still PASS).

---

## What's been mapped but NOT yet built - the access-dimension audit (2026-06-23)

A full literature + dataset sweep (4 research streams: spatial methods, existing indices, untapped
datasets) mapped every access dimension vs what we have. The empirically-derived **pre-screen rule**
from this session's probes: *a candidate is a SIGNAL win only if ZCTA-native AND non-circular AND
orthogonal to what's already scored.* County-level → dilutes to ~0 (Dartmouth +0.04). Collinear →
reliability-only (broadband). Redundant with need+supply → fails (cardiology −0.06). **Raw
facility-COUNT access → wrong-signed** (pharmacy −0.17: facilities cluster in dense high-need urban
areas - the same confound that forced the FQHC `desert × poverty` reframe).

### Queue, ranked by data accessibility (resume here)
| Item | Data access | Pre-screen | Next action |
|---|---|---|---|
| ~~HCAHPS / ED-timeliness / hospital quality~~ | free CMS CSV (IDs `dgck-syfz`, `yv7e-xc69`, `xubh-q36u`) | **REJECTED (2026-06-23)** - the "rate" pre-screen was wrong; see below | documented negative - do not re-run |
| **SAMHSA behavioral facilities** | free (OTP CSV, FindTreatment.gov JSON API) | probe as **distance-to-nearest desert**, NOT count | **probe FIRST next window** |
| Hospital/ER/OB beds (CMS POS / HIFLD) | flaky (JS pages, NASA mirror frozen Aug 2025) | raw count predicted wrong-signed | only via `desert × need` reframe; low yield |
| Pharmacy (NPPES Entity 2) | on disk | **REJECTED −0.17** wrong-signed | documented negative - do not re-run |
| AHRF county FTE | free zip | county-level → predicted dilution | skip unless desperate |
| SACData transit | tract-level Dataverse | *spatial* → predicted collinear w/ supply | skip unless desperate |

### REJECTED 2026-06-23: hospital quality / ED-timeliness / HCAHPS (CMS Care Compare)
Probed all of CMS Care Compare's hospital measures (`xubh-q36u` general info, `yv7e-xc69` timely
& effective care, `dgck-syfz` HCAHPS), mapped hospital→ZCTA by Gaussian catchment (bw 40 km, max
120 km) over gazetteer centroids - full coverage (~33k ZCTAs). Tested against the clean
death-records/ACSC outcomes (candidate oriented higher = worse):

| Candidate (hospital-level) | mean clean-r | Note |
|---|---|---|
| `OP_18b` median ED wait | **−0.148** | **wrong-signed** - the ED-crowding urban confound (long waits in dense cities w/ better outcomes; corr −0.45 w/ supply). The roadmap's "a rate is immune to the clustering confound" pre-screen was **wrong**: a *throughput* rate carries its own urbanicity confound. |
| `OP_22` left-without-being-seen | +0.034 | dead |
| `OP_18c` admitted ED time | −0.018 | dead |
| `H_STAR_RATING` HCAHPS patient experience | −0.024 | dead / wrong-signed on infant mort (rural critical-access hospitals score *higher* on experience) |
| **Hospital overall star (1-5)** | **+0.228** | strong raw signal - but see below |

The overall star looked like a win (raw +0.228, comparable to provider_supply 0.273) but **collapsed
to +0.075 partial-r** controlling for the already-scored gradient (supply + shortage + care_access +
health_need + social_vuln). It is NOT orthogonal (corr 0.28 w/ health_need, 0.23 w/ supply - poor
areas have worse hospitals AND worse outcomes; we already score the poverty). Worse, the surviving
partial signal **concentrates on the two circularity-adjacent outcomes** (premature_death +0.14,
preventable_hosp +0.12 - which mechanically overlap the star's 30-day-mortality / readmission
components) while the two cleanest of-area outcomes collapse (life_exp −0.00, infant_mort +0.04 -
infant mortality is **not even in** the star rating). Since the star's *access-process* components
(ED timeliness, patient experience) all probe dead on their own, the +0.075 IS the mortality
component - i.e. outcome-adjacent, which the methodology keeps out of the composite. **Same shape as
the cardiology-mismatch negative (raw +0.273 → partial −0.06): a measure collinear with the
deprivation gradient, not a new access axis.** Rejected on the probe (no build), like Dartmouth C1-redux.

*New pre-screen rule:* "it's a rate, not a count" does NOT clear the clustering confound. ED
throughput and facility utilization rates carry urbanicity confounds of their own; only the
orthogonality + partial-r test (vs the FULL scored gradient) is decisive.

### Real data gaps (NO free national data) → minimal-scrape heuristic plan
Method discipline: **scrape to CALIBRATE a national model, never to fill coverage** (partial scrape =
urban bias = the artifact that kills a national composite). Sample stratified → regress on features we
already hold → predict nationally → validate on held-out scraped ZCTAs → gate the *predicted* column.

- **Accommodation (hours / after-hours).** Free footholds first: (1) FQHC file already carries
  operating hours - we ignore them; build hours-weighted safety-net availability. (2) urgent-care NPIs
  (NPPES Entity 2, taxonomy `261QU0200X`) already on disk, as a desert measure. Minimal scrape: Google
  Places free tier (~6-11k Place Details/mo with `opening_hours`), ~500 ZCTAs stratified by urbanicity
  × need → "extended-hours rate" → regress on density/type-mix/urbanicity → predict → gate.
- **Acceptability (Medicaid acceptance).** Free footholds: FQHC/RHC density + county dual-eligible rate
  + CMS NDF active-billing flag. Minimal scrape: 4-5 large diverse states publish downloadable
  Medicaid-enrolled-provider files (NY/CA/TX/OH/FL) → ZCTA "% NPIs Medicaid-enrolled" → regress on FQHC
  density + poverty + provider-mix + dual rate → predict other 45 states → validate on held-out state →
  gate. Skip language concordance (ACS limited-English is known wrong-signed here, Layer A1).

### Methods worth gate-testing (no new data)
BFCA (removes E2SFCA's 3-8× supply/demand inflation, conservation property, unit-testable);
gravity model (drops the catchment-cutoff artifact; E2SFCA is its binary special case); free
drive-time matrix (Urban Institute national tract OSRM, replaces haversine). NOT worth it: KD2SFCA
(redundant - we already use Gaussian decay), national GTFS (urban-biased), SDA-2SFCA (need-weights
demand → reproduces the double-count we gated out), ML/kriging/GNN (not used as access indices).

---

## One-glance sequence

1. Build `pipeline/diagnostics.py` (the harness) + capture baselines. 
2. **Layer A** (household reclass, FQHC reframe/remove) → gate → commit.
3. **Layer B** (persist ACS CV, two-source bands, calibration) → gate → commit.
4. **Layer C1** (realized utilization input) → gate → commit. **C2/C3** (capacity weight,
   drive-time - with supply stream) → gate each → commit. **C4** (acceptance) research.
5. Final: confirm `drop_care_access < FULL`. Re-run the full evaluation (`docs/COMPOSITE-EVALUATION.md`).

Every arrow is gated on the harness. Anything that regresses checks 1 or 3 is reverted or retuned,
never shipped - the same evidence discipline that turned state-shrinkage (a regression) into
county-shrinkage (a win).

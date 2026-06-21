# Composite Enhancement - Research & Empirical Findings

Research note (2026-06-21) on how to make the Access Gap composite more accurate and
representative of the *need-access gap*. Combines a literature review of established
indices with statistics run on the live national build (`metrics.parquet`, 33,181
scoreable ZCTAs). Numbers are reproducible from `/tmp/analysis.py` + `/tmp/analysis2.py`.

> **One-line finding:** "Care access collapses to ~5%" is **not** a collinearity bug -
> it is a category error. We are tuning a *gap* construct against an *all-cause health
> outcome* that care access barely moves. The fix is the validation target, not the
> regularizer.

---

## 1. The headline result: the weight collapse is not statistical instability

The standing story was: dimensions are collinear → NNLS is unstable → care access gets
starved → fix it with ridge/elastic-net. **The data refutes this.**

| Diagnostic | Value | Implication |
|---|---|---|
| Dimension VIFs | 1.23 - 1.57 | **Low.** No multicollinearity problem in the classic sense. |
| PC1 of the 3 dimensions | 61% of variance | ~2 effective axes; mild redundancy, not severe. |
| NNLS weights vs (-LE) | need 79.2 / vuln 20.8 / **access 0.0** | access pinned to zero. |
| Ridge λ=1 / 10 / 100 | access **0.0** at every λ | **Regularization does NOT rescue access.** |
| Partial r(-LE, access \| need, vuln) | **-0.074** | access carries ~zero independent signal vs LE (slightly wrong-signed). |
| Partial r(-LE, need \| vuln, access) | +0.493 | need carries almost all the independent signal. |

Ridge cannot recover a weight for a predictor whose *partial* correlation with the target
is ~0. There is no shared signal being misallocated - there is no signal. The collapse is
**real, not an artifact**, *given this outcome*.

---

## 2. Why care access has no signal vs life expectancy - decomposed

Breaking the care-access dimension into its four sub-scores and correlating each against
life expectancy (the only PLACES-independent outcome we hold) is the key diagnostic:

| Care sub-score | r(LE, sub-score) | Read |
|---|---|---|
| `provider_supply_pctile` (2SFCA) | **-0.011** | zero signal |
| `safetynet_access_pctile` (FQHC 2SFCA) | **+0.210** | **wrong sign** (FQHC deserts sit in *higher*-LE areas) |
| `insurance_pctile` | -0.391 | real signal, correct sign |
| `preventive_use_pctile` | -0.329 | real signal, correct sign |

The dimension averages a genuinely predictive pair (insurance, preventive use) with a
**confounded/null pair (the two spatial-supply 2SFCA scores)**. The supply scores cancel
the signal the others carry, so the whole dimension nets to ~0 against LE.

**The confound is urbanicity.** Splitting `provider_supply` vs LE by population quintile:

| Pop quintile | r(LE, supply barrier) |
|---|---|
| p1 (most rural) | +0.013 |
| p2 | -0.053 |
| p3 | -0.118 |
| p4 | -0.171 |
| p5 (most urban) | -0.131 |

Rural ZCTAs read as low-supply (16 km catchment is urban-calibrated) but are not
correspondingly low-LE, so pooling rural + urban cancels the relationship to ~0. The
2SFCA supply percentile is entangled with density.

**Consequence for the sibling session's work** (adding dental + OB/GYN 2SFCA): more
spatial-supply percentiles add more of exactly the signal that all-cause LE cannot see.
They are worth adding, but only an *access-sensitive* outcome will validate them
(maternity supply → infant mortality; primary/dental → ACSC hospitalizations). Validated
against LE they will keep reading as ~0.

---

## 3. The deeper problem: LE is a *need* outcome, not an *access* outcome

Testing composite forms against (-LE):

| Score form | r(-LE) |
|---|---|
| `need` alone | **+0.606** |
| additive 35/30/35 composite | +0.531 |
| `need × access` (multiplicative gap) | +0.441 |
| `need × access × vuln` | +0.462 |

**Need alone beats every composite.** Any weight on access or vulnerability *reduces* the
fit to LE. This is definitional, not a flaw in those dimensions: area-level all-cause life
expectancy is overwhelmingly explained by disease/behavior burden (the ~10-20% of health
outcomes attributable to clinical care is swamped). Optimizing a composite against LE will
*always* converge to "just use health need."

This is exactly why the field's outcome-anchored access indices **do not** use all-cause
mortality:

- **IHME HAQ Index** validates against **amenable/treatable mortality** (Nolte-McKee
  causes) - deaths that timely effective care should prevent - precisely so that disease
  mix doesn't drown the care signal. Convergent validity vs health spending r=0.88, UHC
  index r=0.83.
- **Social Deprivation Index (Robert Graham Center)** validates against **ambulatory-care-
  sensitive (ACSC) hospitalizations** + age-adjusted/infant mortality, at ZCTA/PCSA.
- **County Health Rankings** deliberately **refuses** to set construct weights by
  outcome-regression (circularity; "no one correct set of weights"); uses expert weights.
- **OECD/JRC Handbook on Composite Indicators:** "weights are essentially value
  judgements"; use the outcome as a *concurrent-validity check*, never as the objective
  function.

---

## 4. Recommendations, ranked by leverage

### Tier 1 - changes the conclusion

1. **Stop deriving/validating weights from all-cause life expectancy.** Demote the
   life-expectancy preset to a *concurrent-validity check*, not a weighting source. The
   76/20/5 "empirical" weights are an artifact of the outcome choice and should not be
   presented as "data-driven truth" for an access gap.

2. **Acquire access-sensitive outcomes and validate against them:**
   - **Amenable/treatable mortality** - CDC WONDER Underlying Cause of Death + OECD/Eurostat
     2019 ICD-10 list. County-level; pool years for small-count suppression.
   - **ACSC / preventable hospitalizations (AHRQ PQI 90/91/92)** - CMS Mapping Medicare
     Disparities; County Health Rankings "Preventable Hospital Stays". County-level.
   - **Infant mortality** - CDC WONDER Linked Birth/Infant Death - the natural validator
     for the new OB/GYN maternity-supply layer.
   These are administrative-records based and fully independent of PLACES/BRFSS. Expect
   the care-access dimension to show a real, correctly-signed weight against these.

3. **Keep supply in the composite; surface the confound as a diagnostic, don't strip it.**
   (Decision, 2026-06-21: supply stays a full member of care access; the metric is being
   actively enhanced.) `validate.py` now reports the per-sub-score signed correlations and
   the density-stratified supply confound so the *enhancement* work is targeted - e.g.
   provider supply tracks infant mortality (+0.37) but is ~0 vs life expectancy, and the
   FQHC safety-net sub-score reads wrong-signed (clinics sit in high-need areas). Optional
   future refinements (not removals): a need-adjusted or density-residualized supply
   *variant* alongside the raw score, and benchmark-referenced shortage (HPSA 3,500:1,
   distance-to-nearest) as an absolute companion to the relative percentile.

   Note on weighting: the outcome-anchored presets weight each dimension by its
   **univariate correlation** with the outcome (care access stays visible at 14-20%), not
   by multivariate regression (which floors it at ~5% via collinearity). Regression is
   reported only as a diagnostic.

### Tier 2 - more signal from the same data

4. **Shrink the noisy inputs (Fay-Herriot / empirical Bayes).** ✅ DONE (2026-06-21).
   `build_acs.py` now pulls ACS margins of error, computes a per-rate SE, and EB-shrinks the
   13 social/economic rates toward the **county** mean (state fallback) with
   `γᵢ = τ²/(τ²+SEᵢ²)`, `SEᵢ = MOE/1.645`. County target matters: shrinking to the *state*
   degraded life-expectancy correlation (0.523→0.485, over-smoothing real sub-state signal);
   the **county** target improved 3 of 4 independent outcomes vs raw (premature death
   0.493→0.549, infant mortality 0.398→0.438, ACSC 0.228→0.240; LE 0.523→0.497). Lesson: for
   a percentile-rank composite the gain is modest - ranking is already noise-robust - and the
   shrinkage target must be fine-grained or it costs more signal than it saves.

5. **Prune within-dimension redundancy - more measures ≠ more signal.** Cronbach's α and
   PC1 share within sub-scores:

   | Sub-score | α | PC1 share | Read |
   |---|---|---|---|
   | disability (7 items) | 0.917 | 81% | ~one latent factor; 7 items over-count it |
   | chronic disease (11 items) | 0.901 | 66% | highly redundant |
   | preventive use (6 items) | 0.776 | 57% | genuine spread - keep |

   α > 0.9 signals redundancy. Replacing the disease/disability averages with a single
   **factor score** noise-filters them and stops a redundant cluster dominating by item
   count. (Modest effect on the composite, but it is the honest representation.)

6. **Frame the gap multiplicatively: `Need × UnmetSupply`** (optionally × vulnerability).
   It will not improve LE fit (§3 shows it shouldn't), but it is the correct "unmet need"
   construct (Penchansky-Thomas access-as-fit; HRSA IMU; 2SFCA is itself a supply/demand
   ratio) and structurally avoids the additive double-counting. The additive sum scores
   "high need, fine access" the same as "low need, terrible access" - the multiplicative
   form only lights up where need and barriers coincide, which is the targeting goal.

### Tier 3 - defensibility / most ambitious

7. **Adopt HAQ's frontier-gap framing as the flagship "Access Gap."** Build a context
   index (income, education, % uninsured - things you don't want to *credit* as access),
   risk-standardize the access-sensitive outcomes against the national population mix, fit
   the best-achievable frontier of outcome vs context (free-disposal hull + LOESS on
   bootstraps), and define **Access Gap = distance below the frontier**. This isolates
   ZCTAs underperforming peers *at the same socioeconomic level* - the cleanest separation
   of "access" from "burden," and the most publishable framing.

8. **Decorrelate the composite (Mahalanobis / ZCA whitening)** so it counts each dimension
   net of shared variance. Lower priority - VIFs are only 1.2-1.6, so the double-counting
   is mild - but it is the textbook answer to the stated "dimensions double-count" caveat.

9. **Report ranking robustness (Saisana-style sensitivity analysis)** over weighting /
   normalization / aggregation choices instead of claiming one weight set is correct.
   Turns "trust our weights" into "here is how stable the rankings are."

---

## 5. Direct answers to the posed questions

- **Do we need to regress on something other than life expectancy?** Yes, decisively.
  Proven empirically: vs LE, `need` alone (r=0.606) beats every composite, and care
  access has partial r ≈ 0. LE is a need/disease outcome; it structurally cannot license
  an access weight. Use amenable mortality + ACSC hospitalizations.

- **How do we strengthen the non-health-need signal?** The signal is already there in
  insurance + preventive use (r ≈ -0.39, -0.33 vs LE, correct sign); it is being diluted
  by density-confounded 2SFCA supply scores. Separate them, validate supply against an
  access-sensitive outcome, and consider benchmark-referenced (absolute) supply.

- **Are we squeezing all we can out of the datasets?** We are *over*-extracting redundant
  within-dimension items (disability and disease are each ~one factor) while *under*-
  extracting three real levers: (a) denoising the 31% low-confidence ZCTAs (shrinkage),
  (b) the one independent outcome family that would actually validate the access
  dimension (amenable mortality / ACSC), (c) calibrated, density-corrected supply.

- **Can we reason purely statistically about strengthening signal?** The single highest-
  leverage statistical act is **changing the objective**, not the estimator - no
  regularizer recovers a zero partial correlation. After that: input shrinkage (more
  precision per ZCTA), factor scores (less redundancy), and a multiplicative construct
  (correct interaction) are the levers that add information rather than reshuffle it.

---

## 6. Sources

HAQ Index: GBD 2016 (PMC5986687), GBD 2015 Barber et al. (PMC5528124), Nolte & McKee
(PMC261807). HRSA IMU/HPSA: HRSA SDMS Manual; 42 CFR Part 5. CDC SVI: ATSDR SVI 2022 docs.
ADI: Singh 2003 (PMC1447923); Petterson critique (Health Affairs 2023). SDI: Butler et al.
HSR 2013 (PMC3626349). County Health Rankings: PMC4415342. AHRQ PQI: qualityindicators.ahrq.gov.
California HPI: Public Health Reports 2019 (PMC6598140). Methods: OECD/JRC Handbook on
Constructing Composite Indicators 2008; Kessy/Lewin/Strimmer 2018 (whitening); Fay-Herriot
(Datta & Ghosh 2012; Census SAIPE); James-Stein (Efron & Hastie CASI ch.7); elastic-net
(Zou & Hastie 2005); Saisana/Saltelli/Tarantola 2005 (sensitivity); Penchansky & Thomas 1981;
Luo & Qi 2009 (E2SFCA).

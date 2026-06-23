# Methodology - the Access Gap composite, end to end

This is the authoritative "follow the logic" document: every major design **choice**, the
**empirical or theoretical reason** for it, and the **decision log** of what we tried and
rejected. It is written for a future human or agent who needs to understand *why the model
is the way it is* before changing it. Read this first; the detailed docs below go deeper.

| Doc | What it covers |
|---|---|
| **METHODOLOGY.md** (this) | the cohesive logic + decision log + how to extend safely |
| `PRIMER.md` | data-source dictionary (every input, vintage, caveat) and the field list |
| `RATIONALE.md` | per-formula math + published precedent, including the v1 history |
| `ROADMAP-ACCESS-SIGNAL.md` | the gated layer log (A/B/C) with per-layer gate results |
| `COMPOSITE-ENHANCEMENT.md` | the "why care access reads ~5%" research note |
| `COMPOSITE-EVALUATION.md` | OECD/JRC evaluation: is it meaningful, can you compare ZIPs |
| `uncertainty-research.md` | small-area uncertainty literature behind the rank bands |

---

## 1. What we measure, and the one idea that drives everything

The **Access Gap** is a national, ZIP-level (ZCTA) **relative index of health-care-access
disadvantage**: where do populations have the most health *need* meeting the most *barriers*
to getting care. It is a **gap construct**, not an outcome predictor and not a raw supply count.

The governing idea: **access is not supply.** A provider you cannot afford, reach, or
communicate with is not accessible. This is the **5 A's of access** (Penchansky & Thomas 1981:
Availability, Accessibility, Affordability, Accommodation, Acceptability) and Andersen's
Behavioral Model (predisposing / enabling / need). It is why the model has three dimensions,
not just a provider count:

```
ACCESS GAP  =  weighted percentile blend of
   HEALTH NEED            (how much care is needed)
   SOCIAL VULNERABILITY   (enabling barriers: afford / reach / communicate)
   BARRIERS TO CARE       (availability + affordability of care itself)
```

Outcomes (mortality, life expectancy) are deliberately **NOT** in the composite - they are the
*result* of poor access, not a driver of it. They are used only to *validate* the index (§6).
This is the County Health Rankings stance (factors are ranked separately from outcomes).

---

## 2. Architecture and the percentile backbone

**Hierarchy:** 3 dimensions -> 11 sub-scores -> ~50 measures (`pipeline/taxonomy.py` is the
single source of truth; the frontend mirrors it in `lib/types.ts`).

**Every node is a national percentile rank (0-100), re-ranked at each level.** This is the
**CDC/ATSDR SVI method**: orient each measure so higher = worse, percentile-rank it, average the
available members into a sub-score, **re-rank**; average sub-scores into a dimension, **re-rank**;
weight dimensions into the composite, then report the composite's own percentile.

- **Why percentiles, not z-scores:** the raw inputs are differently-scaled and heavily
  right-skewed (one ZCTA has 454,000 providers per 1,000 residents - a hospital campus with ~2
  residents). Percentile rank is ordinal, so it is immune to outliers. SVI uses percentiles for
  exactly this reason.
- **Why re-rank at each level:** keeps every node a clean, uniform 0-100 "higher = worse,"
  so a sub-score percentile and a dimension percentile mean the same thing.
- **Orientation (`dir` in taxonomy):** `+1` higher = worse (disease, poverty); `-1` higher =
  better (income, provider access, preventive-care use), negated before ranking.
- **Missing data:** a sub-score is the mean of its *available* members; a ZCTA with too few
  inputs is flagged non-scoreable and rendered gray rather than guessed.

**Reading a number:** `pctile = P` means "worse than P% of U.S. ZIP areas on this measure."
Leaf measures are shown as their **raw value** (e.g. mammography 53.6%) **and** their national
percentile, so the two are never confused.

---

## 3. The three dimensions

### Health need (disease, behavior, mental/social, disability)
Four sub-scores from **CDC PLACES** (model-based small-area estimates): chronic disease,
behavioral risk, mental & social distress, disability. Precedent: standardize-then-combine
composite indices. Caveat: PLACES is partly SES-conditioned, so disease/poverty correlation
partly recovers the model's own assumptions (`COMPOSITE-ENHANCEMENT.md`).

### Social vulnerability (the enabling barriers) - why it is access, not a descriptor
Three sub-scores from **Census ACS** + PLACES SDOH: socioeconomic deprivation, housing &
transport barriers, unmet social needs. **This is access, not decoration:** affordability
(income), accessibility (transportation), acceptability (language) are the *enabling* axis of
the 5 A's, and the federal **Medically Underserved Area** formula itself uses % poverty + %
elderly alongside provider supply. Proof it is not a mere descriptor: we *do* carry pure
descriptors (median age, % minority) and score them **zero**.

### Barriers to care (availability + affordability of care)
Four sub-scores: **low provider supply** (spatial, §4), **unmet safety-net need** (FQHC desert
x poverty, §4), **lack of insurance** (ACS + PLACES), **low preventive-care use** (PLACES
checkups/screenings - realized engagement).

---

## 4. Spatial supply - the most-engineered piece

NPPES counts provider *registrations* (an NPI is not an FTE, says nothing about Medicaid
acceptance). We turn that into reachable access:

1. **Provider types (NUCC taxonomy):** primary care, mental health, **dental**, **maternity
   (OB/GYN)** - each E2SFCA'd separately, so "supply" spans the care spectrum and surfaces
   dental deserts (~6.6k ZCTAs) and maternity-care deserts (~15.8k with no OB access).
2. **E2SFCA (Luo & Qi 2009):** floating catchment with Gaussian distance decay - a clinic 2 km
   away counts far more than one at the edge. Fixes the ZIP-containment artifact (a residential
   ZIP next to a hospital ZIP no longer reads as starved).
3. **Variable / adaptive catchment (McGrail & Humphreys 2009) - the access-signal win.** Each
   ZCTA's Gaussian bandwidth = distance to its 30th-nearest centroid, clipped to [8, 60] km:
   small in cities, wide in sparse rural. This replaced a single fixed 16 km radius, whose
   urbanicity artifact left rural supply mis-signed. The fix **roughly doubled** supply's
   correlation with independent mortality (clean-outcome signed-r +0.13 -> +0.265; supply now
   tracks life expectancy, which it provably did not before). This was the lever the whole
   project needed - the weakness was *spatial*, not the input data (see §8). Toggle constants in
   `config.ADAPTIVE_*`.
4. **HRSA 3,500:1 shortage flag** is computed from a **fixed 16 km** catchment, on purpose: an
   absolute pop-to-provider benchmark needs a fixed, interpretable service area, whereas the
   adaptive catchment drives the *relative* scored percentile.
5. **Safety net (HRSA FQHC):** FQHCs serve everyone on a sliding scale - the access point for
   the uninsured/Medicaid. We use **nearest-FQHC distance** and **site count in catchment**, and
   score `safetynet_barrier = FQHC-distance-percentile x poverty` (the *need-relative* form; raw
   FQHC access is wrong-signed because clinics are deliberately sited where need is highest).

---

## 5. Weights

Default **35 / 30 / 35** (need / vulnerability / access) is a **conceptual value judgment**, as
in County Health Rankings (which sets expert weights and says so). Need and barriers - the two
sides of the gap - sit slightly above vulnerability; all near-equal. **The sliders expose the
trade-off rather than hiding it.**

`pipeline/validate.py` also derives **outcome-anchored** weight presets: each weights the
dimensions by how strongly they correlate with an independent outcome. Across every outcome and
method, **care access lands modest** - it is collinear with need (~0.5), and area outcomes are
disease-dominated. That is a true finding about outcomes, **not** proof access is irrelevant
(`COMPOSITE-ENHANCEMENT.md`: it is a category error to tune a *gap* against an all-cause outcome
that care access barely moves). Care access is kept meaningful by deliberate choice because it
is the **actionable lever** - exactly as CHR weights clinical care at 20%.

---

## 6. Validation - the gate that governs every change

We validate against **6 independent outcomes** (CMS claims + NCHS vital records, **never**
BRFSS/PLACES): preventable (ACSC) hospitalizations, premature death, infant mortality, flu
vaccination, mammography, and USALEEP life expectancy. They are shown as separate map layers,
never in the composite.

**Two harnesses gate all composite work** (run BOTH first to re-baseline):
- `python -m pipeline.diagnostics` - the **north star**: composite mean-r vs the 6 outcomes,
  FULL vs drop-each-dimension; per-sub-score mean|r|; split-half reliability; coverage.
- `python -m pipeline.verify_bands` - the rank-uncertainty band gates.

**A change ships only if it passes the gate** (north star does not regress, reliability holds,
coverage holds). Current state: FULL mean-r **0.492**; `drop_care_access` 0.469 (**below** FULL,
so care access *adds* signal - margin now +0.023); composite agreement **0.495**; split-half
**0.943**; provider_supply mean|r| **0.273**, plus the new **shortage_designation** (HPSA)
sub-score (clean signed-r +0.20). (Pre-HPSA: FULL 0.486 / agreement 0.488 / split-half 0.956.)

### The cardinal anti-circularity rule
Flu vaccination and mammography are **healthcare-engagement** measures *and* validation
outcomes. Any candidate input that is also "did you engage with healthcare" will correlate with
them **mechanically**. Therefore: **judge new inputs against the death-records / ACSC outcomes
(life expectancy, premature death, infant mortality, preventable hosp), not the engagement
ones.** This rule is what caught Layer C1 (§8).

---

## 7. Uncertainty and comparability

- **Small-area noise:** low-population ZCTAs have wide ACS margins of error. We apply
  empirical-Bayes (**Fay-Herriot**) shrinkage to the social/economic rates - each ZCTA is pulled
  toward its county mean in proportion to its own noise. Noisiest ZCTAs are flagged
  low-confidence and kept out of headline rankings.
- **Rank bands:** each scoreable ZCTA carries a 5-95 national-rank band (Saisana/OECD
  sensitivity) from (a) plausible re-weighting and (b) ACS measurement noise. A ZCTA's rank moves
  ~+/-6 pts under reweighting and ~+/-4 from noise.
- **Honest resolution:** internally reliable (split-half 0.95), but two ZIPs differ reliably
  only by ~10-15 percentile points - about **7-10 tiers, not 33,000 ranks**. The UI shows
  deciles + a reliable range, not a false integer leaderboard (`COMPOSITE-EVALUATION.md`).

---

## 8. Decision log - what we tried, kept, and rejected (the stream of logic)

The access dimension was the project's weakest link: originally **dropping care access
*improved* outcome agreement** (it was subtracting signal). The fix was pursued cheapest-first,
gated after every step. This is the reasoning trail.

### Kept (passed the gate)
- **HRSA primary-care HPSA as its own `shortage_designation` sub-score (Layer C5)** - an
  official shortage designation that is **near-orthogonal to our E2SFCA density (corr ~0.05)**
  yet tracks independent mortality on its own (clean signed-r **+0.20**: premature_death +0.28,
  life_exp +0.17, infant_mort +0.22, preventable_hosp +0.13). It encodes need + travel +
  safety-net distance a raw provider count cannot see. **Kept as a separate sub-score, not
  folded into provider_supply** - at corr 0.05 the averaging-then-rerank inside provider_supply
  partially washes out its distinct signal (folded: FULL 0.488; separate: FULL **0.492**,
  agreement **0.495**). County-level (max HPSA score per county → ZCTA), free daily CSV from
  data.hrsa.gov (`build_hpsa.py`). *Lesson: an official designation can out-signal a modeled
  density precisely because it is built from different evidence.*
- **Hierarchical percentile model** (SVI method) - skew-robust, interpretable. §2.
- **E2SFCA with adaptive catchment (C3)** - the win: provider_supply mean|r| 0.173 -> 0.273,
  clean-outcome r +0.13 -> +0.265. §4. *Lesson: the supply weakness was the spatial confound
  (fixed radius), not the input data.*
- **Provider-type breadth** (dental, maternity) - surfaces real, distinct deserts. §4.
- **FQHC reframe to desert x poverty (Layer A2)** - the raw FQHC-access score was wrong-signed
  (clinics cluster in high-need areas); the need-relative form is correctly signed and adds
  signal beyond poverty alone. Sub-score signed-r 0.118 -> 0.233.
- **Drop the `household` sub-score (Layer A1)** - age-65+/age-17 are demographic *context*
  (retirement areas read "vulnerable" but have good access); limited-English is wrong-signed vs
  infant mortality (the immigrant-health paradox). All three demoted to context, never scored.
- **Measurement-noise rank bands (Layer B)** - low-confidence ZCTAs now get visibly wider bands.

### Rejected (failed the gate - kept as documented negatives so nobody re-runs them)
- **Condition-specific quality-of-care / "realized access conditional on need" (C1-redux)** -
  the lever §10 *predicted* would be strongest. Tested **Dartmouth Atlas** county-level diabetic
  process measures (HbA1c testing + eye exam *among diabetics*, 2019). **Clean-outcome signed-r
  +0.036** (vs provider_supply +0.265) - life expectancy even faintly wrong-signed. *Weaker than
  the raw-visit-rate C1 it was meant to replace.* Root cause: HbA1c testing is ~85-90% saturated
  among diabetics (little geographic variance), county-level (diluted across ZCTAs), 2019 vintage.
  The "conditional on need" denominator did **not** rescue it. Probed before any build (the right
  move). Blood-lipid testing was retired from HEDIS in 2015 so only 2 measures survive to 2019.
- **Mental-health / dental HPSA, and the MUA/IMU index** - tested alongside PC-HPSA. MH-HPSA
  (+0.09) and DH-HPSA (+0.12) are highly correlated with PC-HPSA (0.59 / 0.75) and add **~0
  beyond it** (partial-r ≈ −0.05). The MUA Index of Medical Underservice is **wrong-signed at
  ZCTA level** (−0.04) - its elderly-% term makes retirement areas read "served." Only PC-HPSA
  ships.
- **Realized utilization (C1)** - CMS Medicare visit-rates (% with an E&M visit, etc.) as a
  "low realized use = barrier" sub-score. *Looked* like a win across all 6 outcomes, **but it
  was circular**: its only strong correlations were with flu (+0.66) and mammography (+0.54),
  which are engagement outcomes; against life expectancy r = **-0.00**, and the clean-outcome
  north star **regressed** 0.480 -> 0.470. Medicare visit-rates are saturated (~90%),
  need-endogenous (sick areas use more care), and 65+-only. **This is why the anti-circularity
  rule (§6) exists.**
- **Capacity-weight NPIs by Medicare claims volume (C2)** - down-weight dormant registrations
  via `w = benes/(benes+K)`. A **wash** vs clean outcomes (provider_supply 0.132 -> 0.129):
  premature-death nudged up but infant-mortality dropped (Medicare doesn't cover pediatricians,
  so weighting zeroed them). Confirmed the weakness was *not* dormant registrations.
- **Need-adjusted supply** - demand weighted by disease burden. Computed historically but never
  scored: it double-counts health need, which is already its own dimension.
- **Demand-matched specialist supply (e.g. CHD ↔ cardiology mismatch)** - the intuitive
  "heart disease prevalent but no cardiologists" idea. Tested empirically (2026-06-23): scanned
  NPPES for 30k cardiologists, E2SFCA'd them on the adaptive catchment, defined mismatch =
  CHD-need-percentile − cardiology-supply-percentile. The mismatch is **real in the world**
  (cardiologists are scarcer where CHD is high, r = −0.30) and its raw clean-outcome r is a
  strong **+0.273** - but it **collapses to −0.06 once you control for CHD prevalence and
  primary supply**, both already scored (CHD in health_need, supply in care_access). The
  mismatch is just `need − supply`, a linear combination the additive composite already sums;
  cardiology supply is 0.80 collinear with primary supply, so the specialty breakout adds
  ~nothing. *This is the specialist-specific proof of the double-counting trap above: the
  weighted sum already rewards "high need AND low supply." Don't add explicit mismatch terms.*
- **Empirical (pure-regression) weights** - NNLS regression of dimensions on an outcome floors
  care access at ~5%. Offered only as a labeled diagnostic preset, never the default, because it
  optimizes "predict this outcome" rather than "measure the access gap" (§5).

*Meta-lesson for §8:* two of three Layer-C input-data attempts failed; the one structural
attempt (catchment shape) won. **The care-access signal was not fixable by better supply/use
input data - the lever was spatial.**

---

## 9. Honest limitations
- **Relative, not absolute** - a 95 means "worse than 95% of ZIPs," not "objectively bad."
- **Modeled disease** (PLACES) is partly SES-conditioned, so need/vulnerability share variance.
- **Collinear dimensions** (~0.5) - the weighted sum double-counts shared variance; the sliders
  make that explicit.
- **NPPES registrations** over-count active capacity and ignore Medicaid/new-patient acceptance
  (FQHC presence is our best available proxy for acceptability).
- **Different vintages/universes** - NPPES (this month), ACS 5-yr (centered ~2-3 yrs back),
  PLACES (a BRFSS year, adults 18+). See `provenance.json`.

---

## 10. For future agents - how to extend without breaking it

1. **Re-baseline first.** Run `pipeline.diagnostics` + `pipeline.verify_bands` and record the
   numbers before touching anything.
2. **Add a measure/sub-score in `pipeline/taxonomy.py`** (source + members + `dir`), produce its
   column in a build stage, register the stage in `pipeline/run.py` (and `OPTIONAL_STAGES` in
   `join_and_score.py` if it should merge gracefully). The frontend mirror is `lib/types.ts` +
   `lib/measures.ts`.
3. **Gate it.** Re-run the harness. Ship only if the north star does not regress, reliability
   holds (>=0.93 overall), and coverage holds. **Validate against the death-records/ACSC
   outcomes, never flu/mammography** (the anti-circularity rule).
4. **If it fails, back it out** but leave a documented negative (taxonomy comment + roadmap/this
   doc), so the next agent does not repeat it. C1 and C2 are the template.
5. **Outcomes stay out of the composite.** They validate; they never score.
6. **Pipeline is the source of truth, the backend just serves it.** `data/` and the big payloads
   are gitignored and reproducible via the staged build (`python -m pipeline.run`).

**C1-redux (condition-specific quality-of-care) has now been tested and REJECTED** - Dartmouth
diabetic process measures carry no clean signal (+0.04; see the decision log above). The lever
that worked instead was **HPSA shortage designation (C5)** - an *official* shortage signal, not
a modeled rate.

The strongest remaining levers are now structural/data, in rough ROI order:
1. **Drive-time E2SFCA** - replace the straight-line adaptive catchment with true OSRM road-network
   isochrones. A *build* (run routing over provider coords), not a download. Most likely to sharpen
   provider_supply further, especially rural. (See ROADMAP C3's straight-line analog.)
2. **ZIP/sub-county HPSA resolution** - the current HPSA score is county-max; the file also carries
   population-group and address-level designations. A finer geographic assignment could lift the
   +0.20 shortage signal.
3. **PLACES measurement-noise bands (Layer B3)** - health_need carries no measurement-noise term;
   folding PLACES CIs in would complete the uncertainty model (honesty, not point-signal).
4. **Acceptability (Medicaid / new-patient acceptance)** - the axis NPPES omits. No free national
   file exists (only the CMS NDF Medicare-assignment flag, near-saturated); a real slog. Lowest ROI.

# Methodology - the Access Gap composite, end to end

This is the authoritative "follow the logic" document: every major design **choice**, the
**empirical or theoretical reason** for it, and the **decision log** of what we tried and
rejected. It is written for a future human or agent who needs to understand *why the model
is the way it is* before changing it. Read this first; the detailed docs below go deeper.

| Doc | What it covers |
|---|---|
| **METHODOLOGY.md** (this) | the cohesive logic + how to extend safely |
| `PRIMER.md` | data-source dictionary (every input, vintage, caveat) and the field list |
| `RATIONALE.md` | per-formula math + published precedent (incl. the multiplicative lens) |
| `DECISIONS.md` | compact ledger: every lever tried, kept, or rejected (don't re-run these) |
| `VALIDATION.md` | how the index is validated: outcomes, sub-county gate, comparability, uncertainty |

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
partly recovers the model's own assumptions (`VALIDATION.md`).

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
method, **care access lands modest** - it is collinear with need (~0.58), and area outcomes are
disease-dominated. That is a true finding about outcomes, **not** proof access is irrelevant
(`VALIDATION.md`: it is a category error to tune a *gap* against an all-cause outcome
that care access barely moves). Care access is kept meaningful by deliberate choice because it
is the **actionable lever** - exactly as CHR weights clinical care at 20%.

---

## 6. Validation - the gate that governs every change

We validate against **6 independent outcomes** (CMS claims + NCHS vital records, **never**
BRFSS/PLACES): preventable (ACSC) hospitalizations, premature death, infant mortality, flu
vaccination, mammography, and USALEEP life expectancy. They are shown as separate map layers,
never in the composite.

**Three harnesses gate all composite work** (run first to re-baseline):
- `python -m pipeline.diagnostics` - the **north star**: composite mean-r vs the 6 outcomes,
  FULL vs drop-each-dimension; per-sub-score mean|r|; split-half reliability; coverage.
- `python -m pipeline.verify_bands` - the rank-uncertainty band gates.
- `python -m pipeline.validate_subcounty --national` - the **sub-county gate**: within-county
  (county fixed-effect) correlation vs NY SPARCS ZIP-ACSC + national USALEEP. ~25% of the
  composite's variance is *within* county and invisible to the two county-level harnesses above;
  this is the only check that sees it. It caught the `safetynet_access` resolution-dependent
  wrong-sign (correct between counties, wrong within) that the county gate passed. See VALIDATION.md.

**A change ships only if it passes the gate** (north star does not regress, reliability holds,
coverage holds, no sub-county wrong-sign). Current state: FULL mean-r **0.510**; `drop_care_access`
0.467 (**below** FULL, so care access *adds* signal, margin **+0.043**); composite agreement
**0.514** (ZCTA-broadcast; the matched-resolution **county-collapsed** point is **0.546**, since 5
of 6 outcomes are county-level - see VALIDATION.md §1a; gate margins use the cluster bootstrap, not
this point); clean (non-circular) composite-r **0.547**; split-half **0.954**; bands ALL PASS;
composite within-county (national) **0.599**. Care sub-scores: **medical_debt** mean|r| **0.40**
(the strongest - affordability barrier, survives partial-r +0.27, **but county-level: within-county
r = 0.000, scored on construct grounds not sub-county signal - VALIDATION.md §3**), insurance 0.34,
provider_supply 0.273, **shortage_designation** (HPSA) 0.20. These thin margins are **not
multiple-comparisons corrected** (VALIDATION.md §1c). Two care items are computed +
displayed but **unscored**: `safetynet_access` (wrong-signed within counties) and `preventive_use`
(realized utilization - a mediator/outcome, not a barrier). The arc this session: dropped the
`preventive_use` mediator (clean-r 0.501→0.516) and added the `medical_debt` barrier (→0.547),
lifting FULL from 0.492. See VALIDATION.md + DECISIONS.md.

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
  sensitivity) from (a) plausible re-weighting, (b) ACS measurement noise (excess over the
  well-measured baseline - widens low-pop ZCTAs), and (c) PLACES measurement noise (Layer B3 - a
  near-uniform irreducible modeling-uncertainty floor on the disease/health_need estimates),
  combined in quadrature. A ZCTA's rank moves ~+/-6 pts under reweighting and ~+/-4 from noise.
  - **What is calibrated vs chosen (read before trusting the widths to the point):** the band
    *magnitude* is not free-tuned to a target - the noise-injection scale is calibrated so the
    injected σ matches an **independent member-input resample** (perturb each rate by its published
    SE, propagate to the dimension percentile), and `pipeline.verify_bands` gate 3 fails unless
    injected/empirical ∈ [0.8, 1.2] per ACS dimension. What *is* a judgment call - researcher
    degrees of freedom the gate does not pin down - is the band's *shape*: the median-CV floor
    (which ZCTAs get zero added noise), the excess cap, the decision to floor-subtract ACS but not
    PLACES, and the per-dimension propagation shares. These move *which* ZCTAs widen and by how
    much relative to each other, even though the overall level is anchored. So trust the bands as
    a calibrated order-of-magnitude ("~10-15 pts, low-pop wider"), not as exact per-ZCTA intervals.
- **Honest resolution:** internally reliable (split-half 0.95), but two ZIPs differ reliably
  only by ~10-15 percentile points - about **7-10 tiers, not 33,000 ranks**. The UI shows
  deciles + a reliable range, not a false integer leaderboard (`VALIDATION.md`).

---

## 8. Decision log - pointer

The access dimension was the project's weakest link: originally **dropping care access
*improved* outcome agreement** (it was subtracting signal). It was fixed cheapest-first, gated
after every step - the adaptive catchment (C3) was the structural win that roughly doubled
supply's clean-outcome correlation (+0.13 -> +0.265); HPSA (C5) added an orthogonal official-
shortage signal; the FQHC reframe and `household` removal fixed two wrong-signed pieces.

**The full ledger - every lever tried, kept, or rejected, with its numbers and root cause -
now lives in [`DECISIONS.md`](DECISIONS.md)** (the single source so completed work isn't
re-litigated here). *Meta-lesson:* the care-access signal was not fixable by better supply/use
input data - the lever was spatial (catchment shape) and structural, not more data.

## 9. Honest limitations
- **Relative, not absolute** - a 95 means "worse than 95% of ZIPs," not "objectively bad."
- **Modeled disease** (PLACES) is partly SES-conditioned, so need/vulnerability share variance.
- **Strongly collinear dimensions** (need↔vulnerability **0.74**, need↔access 0.58,
  vulnerability↔access 0.63; PC1 = 77% of dimension variance, **~1.6 effective dimensions**) -
  the weighted sum double-counts shared variance, and because the axes move together,
  re-weighting barely moves ranks (Spearman ~0.999). The sliders are therefore a **sensitivity
  probe**, not a control that meaningfully rewrites the map - stated as such in-product.
- **NPPES registrations** over-count active capacity and ignore Medicaid/new-patient acceptance
  (FQHC presence is our best available proxy for acceptability).
- **Different vintages/universes** - NPPES (this month), ACS 5-yr (centered ~2-3 yrs back),
  PLACES (a BRFSS year, adults 18+). See `provenance.json`.

### 9a. Coverage against the 5 A's of access (the construct lens - what we measure vs miss)
A full crawl (2026-06-23) mapped every component to Penchansky & Thomas's 5 A's. This is the
honest "what are we still missing," separate from the signal question:

| Axis (5 A's) | Covered by | Status |
|---|---|---|
| **Availability** (enough providers) | provider_supply (E2SFCA × 4 types), shortage_designation (HPSA) | **Strong** - the most-engineered piece |
| **Accessibility** (can physically reach) | adaptive catchment, no_vehicle (ACS), digital_access (telehealth) | **Good** - missing only true drive-time (infeasible; circuity's capturable part is a per-stratum rescale percentiles absorb) |
| **Affordability** (can pay) | insurance (uninsured), socioeconomic (income/poverty), safetynet (FQHC desert × poverty) | **Good** on cost; **missing Medicaid/new-patient acceptance** (no free national file) |
| **Accommodation** (hours, how care is organized) | — | **GAP**. FQHC operating-hours tested: orthogonal but too weak (§8). ED-timeliness wrong-signed. No usable free signal. |
| **Acceptability** (cultural/linguistic fit, trust) | — | **GAP**. limited-English is wrong-signed (immigrant-health paradox); no free provider language/race-concordance data. FQHC presence is the only proxy. |

**Bottom line:** 3 of 5 A's are well-covered; **Accommodation and Acceptability are genuine
construct gaps**, and both are *unfillable from free national data* - every free candidate is
either collinear with the captured deprivation gradient (collapses in partial-r) or, where
orthogonal, too weak to survive dimensional dilution. Closing them needs the **scrape-to-calibrate**
heuristic (sample → regress on held features → predict nationally → gate the predicted column;
specced in DECISIONS.md), the only remaining lever that could add genuinely new signal.

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

**The spatial-signal ceiling is reached (2026-06-23).** Three further probes - hospital quality
(Care Compare), SUD/behavioral desert (SAMHSA/NPPES), and sub-county HPSA - all failed the same way
every earlier one did: collinear with the poverty/rural/supply gradient already scored, so raw signal
collapses in partial-r. No remaining free spatial dataset is orthogonal to that gradient. The
remaining levers are therefore **completeness/structural, not signal** (in rough ROI order):
1. ~~**PLACES measurement-noise bands (Layer B3)**~~ ✅ **SHIPPED 2026-06-23** - health_need's
   measurement noise (previously σ=0 in the bands) is now parsed from PLACES 95% CIs into a
   `places_input_cv`, injected in quadrature with the ACS term and calibrated to a member-input
   resample (gate 3 health_need inj/emp 0.97). Point scores unchanged; the uncertainty model is now
   complete across all three dimensions. See DECISIONS.md Layer B3.
2. **Drive-time E2SFCA** - replace the straight-line adaptive catchment with true OSRM road-network
   isochrones. A *build* (routing over provider coords), not a download; deemed infeasible at C3,
   revisit only with a precomputed travel-time matrix (e.g. Urban Institute national tract OSRM).
   Sharpens provider_supply; does not expand signal.
3. **Acceptability (Medicaid / new-patient acceptance)** - the axis NPPES omits. No free national
   file exists (only the CMS NDF Medicare-assignment flag, near-saturated); needs the scrape-to-
   calibrate heuristic in DECISIONS.md. A real slog. Lowest ROI.
~~ZIP/sub-county HPSA resolution~~ - tested 2026-06-23, a wash (0.991 correlated with county-max).

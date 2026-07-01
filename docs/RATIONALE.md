# Scoring rationale & precedent

This document explains **how each number is computed, what it means, and the published
precedent it follows.** The guiding principle: lean on established public-health
indexing methods (CDC SVI, Area Deprivation Index, County Health Rankings, HRSA HPSA,
2SFCA) rather than invent anything novel. Where the tool bends from best practice, it
says so.

> **Note on versions.** §1 (the percentile backbone) and §8-13 (access theory, the honest
> scoring evaluation, weights, the E2SFCA supply upgrade, safety-net, and the multiplicative
> lens) describe the **current hierarchical model** - 3 dimensions → 14 sub-scores
> (12 scored + 2 displayed-only) → ~50 measures. §2 is a short appendix recording the original **v1** 3-component scoring (disease /
> supply / econ) for history. See [`METHODOLOGY.md`](METHODOLOGY.md) and
> [`PRIMER.md`](PRIMER.md) for the current structure.

---

## 1. The backbone: percentile ranking

Every component is reduced to a **national percentile rank (0-100)** before being
combined.

**Why.** The raw inputs are on different scales and are heavily right-skewed (provider
density, income). A z-score composite would let a handful of outliers dominate (one ZIP
has 454,000 providers per 1,000 residents - a hospital campus with ~2 residents). A
**percentile rank is ordinal, so it is immune to outliers** and produces a single,
interpretable scale.

**Precedent.** The **CDC/ATSDR Social Vulnerability Index (SVI)** is built exactly this
way: percentile-rank each variable, sum into themes, then percentile-rank the result.
The skew-robustness argument is the documented reason SVI uses percentiles.

**What a percentile means (read this once):**

> `pctile = P` means **"this area scores higher than P% of all U.S. ZIP areas on this
> measure."**

So a disease-burden percentile of **5** = *healthier* than 95% of areas (very low
burden). A provider-supply percentile of **5** = fewer providers per resident than 95%
of areas (starved).

---

## 2. Appendix - the superseded v1 model

The original **v1** Access Gap was a 3-component weighted sum - **disease burden 0.40 / supply
gap 0.35 / economic vulnerability 0.25** - each component standardized then percentile-ranked
(standardize-then-combine, the construction of deprivation indices and the Human Development
Index; supply gap = 100 - provider-density percentile, on the HRSA HPSA ratio precedent). It was
replaced by the current **hierarchical SVI-method model** (§1, §8-13 here +
[`METHODOLOGY.md`](METHODOLOGY.md)): 3 dimensions -> 14 sub-scores (12 scored + 2 displayed-only) -> ~50 measures at default
weights 35 / 30 / 35. The hierarchical model fixed v1's two weak spots - flat ZIP-containment
supply (now E2SFCA + adaptive catchment, §11) and a thin economic axis (now the full
social-vulnerability dimension, §8). The percentile backbone (§1) and precedents (SVI, ADI, CHR,
2SFCA) carry over unchanged; see [`PRIMER.md`](PRIMER.md) for the current per-dimension inputs.

## 8. Why each dimension belongs in an *access* gap (not just a descriptor)

A reasonable objection: "social vulnerability describes a population - it isn't access."
The response, grounded in access theory:

**Access ≠ supply.** A provider you can't afford, reach, or communicate with is not
accessible. The canonical definitions make vulnerability part of access:
- **Penchansky & Thomas's 5 A's of access** - Availability, Accessibility, **Affordability**,
  Accommodation, **Acceptability**. Our *Barriers to care* covers Availability + part of
  Affordability (uninsured); **social vulnerability covers the rest** - Affordability
  (income/poverty), Accessibility (transportation/no-vehicle), Acceptability (language).
- **Andersen's Behavioral Model** - care use is driven by *need*, *enabling resources*
  (income, insurance, transport, education), and *predisposing factors*. Social
  vulnerability *is* the enabling-resources axis.

**Precedent:** the federal **Medically Underserved Area** formula (HRSA's IMU) is built from
provider ratio, infant mortality, **% below poverty**, and **% age 65+** - i.e. the US
government's own underservice score puts socioeconomic vulnerability co-equal with supply.

**Proof it's not a passive descriptor:** we *have* descriptors - median age, % people of color,
% under-5 - and we score them **zero** (context only). Social vulnerability is scored
because its components *causally impede getting care* (cost-related avoidance, missed
visits from no transport, language under-use), not merely correlate with disadvantage.

**On uninsured vs under-insured:** uninsured is measured directly (in *Barriers to care*).
Under-insurance (coverage you still can't afford to use) has no clean national ZCTA source;
**income/poverty in social vulnerability is the proxy** for that affordability barrier.

The three dimensions thus map to: *Health need* (demand) · *Social vulnerability* (the
demand-side enabling resources / affordability of access) · *Barriers to care* (supply +
coverage availability). This makes the score **realized/effective access**, not just spatial.

## 9. Honest scoring evaluation - gaps, redundancies, inspiration

**What comprehensive indices do (and what we borrowed):**
| Index | Idea we took |
|---|---|
| CDC/ATSDR **SVI** | percentile-rank → theme → composite (our backbone) |
| **Area Deprivation Index** (Singh 2003) | a rich SES deprivation set; factor-weighted |
| **County Health Rankings** | dimension structure + *transparent expert weights*; separates **outcomes** from **factors** |
| **Healthy Places Index** | weights derived **empirically** by regressing domains on **life expectancy** |
| **HRSA IMU/MUA** | poverty + elderly + supply as the underservice formula |

**Gaps (missing from the picture):**
- **Outcomes layer (shipped).** CHR ranks outcomes (mortality/life-expectancy) separately
  from factors; we now do too - **CDC USALEEP life expectancy** is loaded as an independent
  outcome (from death records, not BRFSS), shown in the panel, colorable on the map, and used
  to derive the empirical weights and a validation anchor (composite ↔ fair/poor health ~0.85).
  It is **not** in the access-gap composite (outcomes are the result, not a driver). *Backlog:*
  preventable-hospitalization / infant-mortality outcomes; a newer-vintage life-expectancy source.
- **Under-insurance** not measured (only uninsured); income proxies it.
- **Other supply types** - pharmacy (deserts) not yet in (dental and maternity/OB are scored in `provider_supply`; broadband/telehealth is the scored `digital_access` sub-score).
- **No empirical weights** - we use conceptual weights (see §10); HPI-style life-expectancy
  regression is the principled upgrade.

**Redundancies (disclosed, mostly intentional):**
- **Poverty is counted ~twice** - it conditions PLACES disease estimates (health need) *and*
  drives social vulnerability (need↔vulnerability dimension correlation **0.73**). The sliders + reported
  correlations are the honest resolution; a PCA/factor composite would formally de-dup.
- **Two transportation measures** - `no_vehicle` (structural asset) and `lacktrpt` (PLACES
  experienced barrier). Related but distinct (you can own a car and still lack reliable
  transport); kept on purpose, not an error.
- **Uninsured measured twice** - ACS uninsured + PLACES adults-18-64; cross-validating, minor.

## 10. On the weights (why 35 / 30 / 35)

The default dimension weights are a **conceptual value judgment, not an empirical fact** -
exactly the stance County Health Rankings takes. The reasoning:
- The tool's thesis is *"high need meeting low access."* So **Health need (35%)** and
  **Barriers to care (35%)** - the two sides of that gap - are weighted slightly above
  **Social vulnerability (30%)**, which is the modifier of how acutely need+supply translate
  into unmet care.
- They're kept **near-equal** deliberately: there's no defensible basis for privileging one
  contested axis, and equal-ish weighting is the most honest default.
- **The sliders are the real answer.** Because the weights are a judgment, they're exposed
  and explorable - your weighting, not ours.
- **Empirical alternative (shipped - the "Data-driven" preset).** Following the Healthy
  Places Index, we derive weights by **non-negative least-squares regression (NNLS; Lawson &
  Hanson 1974) of the three dimensions on CDC USALEEP life expectancy** (5% floor, normalized to 100). The result:
  **~60% health need / 19% social vulnerability / 21% care access** (R²≈0.39, n≈31k). This is
  itself a finding: at the *area* level, disease burden predicts mortality far more than the
  other axes (~3x health need over care access) - and it's partly tautological (PLACES disease
  ≈ death). Notably the data-driven care-access weight lands at **~21%, almost exactly County
  Health Rankings' 20% clinical-care weight** - independent corroboration of that expert choice.
  Both weightings are offered; the conceptual near-equal default stands as a value judgment, the
  data-driven preset is one click away, and the honest takeaway is that "what predicts
  (all-cause) mortality" ≠ "the access gap."
- **Anchored to the *right* outcome, the data-driven weight rises.** Re-deriving the same NNLS
  against **treatable (amenable) mortality** instead of all-cause LE gives **~66% need / 5% / 29%
  care access at R²≈0.61** (`weights.json`) - care access nearly **+50% heavier** than the LE-anchored
  ~21%, and the fit jumps 0.39 → 0.61. The "data nearly zeros access" intuition was an artifact of the
  all-cause ruler; against the access-sensitive outcome the empirical weight lands close to the
  conceptual default. See [VALIDATION](VALIDATION.md) §4.

## 11. Supply, enhanced - E2SFCA, and the "need-adjusted?" question

Supply uses **E2SFCA** (Luo & Qi 2009) - the 2SFCA spatial-accessibility method (Luo & Wang
2003) **plus Gaussian distance decay**, so a clinic 2 km away counts far more than
one at the 16 km edge. More realistic than the binary catchment.

**"Need-adjusted?"** - weighting demand by morbidity (sicker populations stretch each
provider further) is legitimate (demand-weighted SFCA), and it's computed and stored
(`primary_2sfca_needadj`). But it is **deliberately not the scored value**: health need is
already its own 35% dimension, so need-adjusting supply would **double-count need**. We keep
the scored supply un-need-adjusted and surface the need-adjusted variant for transparency.

## 12. Safety-net access - the supply-side validity fix

The deepest flaw in any provider-density metric is that it's **provider-agnostic**: it counts
a cash-only concierge physician identically to a community clinic that serves everyone. For
the uninsured/Medicaid populations this tool is about, that's the difference between *theoretical*
and *real* access - it's the **Acceptability** "A" (will they see *you*) on the supply side, the
analog to why we include social vulnerability on the demand side (§8).

> **Status (superseded).** This section records the original bipartite-E2SFCA safety-net design.
> It was later reframed to `safetynet_barrier` = FQHC-distance percentile × poverty and is now
> **displayed but not scored** (`scored=False`): the reframed form is correctly signed *between*
> counties but wrong-signed *within* counties in ~85% of states, so dropping it from the composite
> lifts sub-county accuracy. See `pipeline/taxonomy.py` (`safetynet_access`), VALIDATION.md, and
> DECISIONS.md. The narrative below is kept for the reasoning; the shipped state is unscored.

We address it with a **safety-net access** sub-score: bipartite **E2SFCA** over ~18,000 HRSA
**FQHC** sites (mandated sliding-fee clinics), capacity-weighted by operating hours. This is the
single most decisive thing we can add to the access dimension's *validity* - more than travel-time
precision (the academic "next step," which improves the *measure* but not *what's measured*), and
more than provider-type breadth (dental/OB/ER - valuable, but breadth not validity). True
Medicaid-acceptance data has no clean national ZCTA source; FQHC presence is the authoritative
stand-in.

**What it revealed:** FQHCs are deliberately sited in underserved areas, so high-need places like
the Mississippi Delta now correctly read as having a *functioning safety net* even where private
provider density is low - a signal the raw count was blind to. Conversely, **~37% of ZCTAs have no
FQHC within 16 km** (true safety-net deserts). *Caveat:* presence ≠ unlimited capacity, sliding-fee
≠ free, and hours are a rough capacity proxy. *Backlog (validity, in priority order):* network
travel-time E2SFCA; dental/maternity/ER provider types; claims-based active-provider FTEs.

## 13. Alternative aggregation - the multiplicative (geometric) lens

The default `access_gap_score` is a weighted **arithmetic** mean of the three dimension
percentiles - **fully compensatory**: a surplus in one dimension fully offsets a deficit in
another, so it scores "high need / fine access" the same as "low need / terrible access" (both
land mid-scale). For a *targeting* tool that is a category error - the gap should light up only
where need **and** barriers **coincide**.

`access_gap_mult` is the weighted **geometric** mean of the same percentiles with the same
weights (frac clipped to [0.01, 1] so a 0-rank dimension can't zero the product; renormalized
over present dims). This is the OECD/JRC Handbook's **non-compensatory** aggregation: a deficit
in one dimension can no longer be fully bought back by a surplus in another.

**Precedent.** OECD/JRC Handbook (geometric vs linear aggregation); Penchansky-Thomas
access-as-fit; HRSA IMU (itself a supply/demand product). **Gated as a construct, not a signal:**
it tracks outcomes ~identically to the additive default (clean mean-r 0.500 vs 0.502, rank corr
0.994, identical coverage) but down-weights one-dimensional highs (need-only / barrier-only) by
~4-5 percentile points while preserving coincidence-highs. It is therefore gated on construct
validity + no-outcome-regression, **not** on an outcome-r lift (the additive form is the one that
maximizes outcome correlation, so gating on outcome-r would wrongly reject a correct construct).

**Shipped as a selectable lens, not the default** (the user owns the compensability assumption,
as they own the weights). It is live in the Color-by + Rankings menus (`COMPOSITE_MULT_METRIC`
in the frontend), recomputed **client-side** from the three stored dimension percentiles
(`scoring.accessGapMult()`) — so the precomputed `access_gap_mult_pctile` was dropped from the
slim `map_frame.json` payload (kept in the parquet for the API/CSV). See [VALIDATION.md](VALIDATION.md)
for the gate detail and [DECISIONS.md](DECISIONS.md) (lens toggle DONE; slim-payload trim, D1).

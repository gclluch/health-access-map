# Scoring rationale & precedent

This document explains **how each number is computed, what it means, and the published
precedent it follows.** The guiding principle: lean on established public-health
indexing methods (CDC SVI, Area Deprivation Index, County Health Rankings, HRSA HPSA,
2SFCA) rather than invent anything novel. Where the tool bends from best practice, it
says so.

> **Note on versions.** §1 (the percentile backbone) and §8-11 (access theory, the honest
> scoring evaluation, weights, and the E2SFCA supply upgrade) describe the **current
> hierarchical model**. §2-7 document the original **v1** 3-component scoring (disease /
> supply / econ) for history; the percentile method and precedents still hold, but the model
> is now 3 dimensions → 11 sub-scores → ~50 measures. See [`PRIMER.md`](PRIMER.md) for the
> current structure.

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

## 2. Disease burden

```
for each of {diabetes, COPD, coronary heart disease, asthma, depression} crude prevalence %:
    z = (value − national_mean) / national_std        # standardize
disease_index   = mean(the 5 z-scores, skipping any missing)
disease_burden_pctile = national_percentile_rank(disease_index) × 100
```

**Why standardize first.** The five conditions have very different baselines (depression
~20%, diabetes ~11%, CHD ~6%). Averaging raw percentages would let the common conditions
dominate the "burden" signal. Z-scoring puts each on a common footing so each contributes
equally, *then* the percentile maps to the shared 0-100 scale.

**Precedent.** Standardize-then-combine is the standard construction for composite indices
(deprivation indices; the classic Human Development Index method).

**Meaning.** `disease_burden_pctile = 85` → this area's combined chronic-disease burden is
higher than 85% of U.S. ZIP areas.

**Caveat.** Crude (not age-adjusted) prevalence, so an old population reads high-burden
partly *because* it is old. Median age is shown alongside for context.

---

## 3. Provider supply  →  supply gap

```
primary_per_1k = providers_primary ÷ (population / 1000)
provider_supply_pctile = national_percentile_rank(primary_per_1k) × 100   # higher = better
supply_gap = 100 − provider_supply_pctile
```

**Why a per-capita ratio.** Provider-to-population density is *the* canonical
health-workforce access metric. Primary care is the front door to the system.

**Precedent.** **HRSA's Health Professional Shortage Area (HPSA)** designation scores
population-to-provider ratios directly; WHO uses provider-density thresholds; "primary care
physicians per 100,000" is a standard workforce statistic.

**Meaning.**
- `provider_supply_pctile = 87` → better supplied than 87% of areas.
- `supply_gap = 100 − 87 = 13` → a small gap. **A supply gap of 4 means supply is better
  than 96% of areas - essentially no shortage. A supply gap of 96 means the area is among
  the worst-supplied 4% in the country.**

**Caveat (the weak link).** Supply is counted by **ZIP containment** - providers registered
*inside* the ZIP, over that ZIP's residents. A residential ZIP next to a hospital ZIP reads
near-zero even if a clinic is two miles away. The accepted fix is a spatial catchment (see
§7). Counts are also *registrations*, not active/accepting capacity.

### 3a. Honesty note - this is supply density, not a "gap"

`supply_gap = 100 − supply_pctile` is **just inverted relative density**. It contains **no
need term and no adequacy benchmark**, so it does not measure whether providers are
sufficient to meet local demand. The app therefore labels this layer **"low provider
supply,"** and reserves the word *gap* for the composite (which is where supply meets need).
Even the composite is a **relative index**, not a measured provider deficit.

A **real, benchmarked supply gap** would need three things we do not yet have, each with
precedent:

1. **An adequacy ceiling.** HRSA HPSA flags a shortage at a population-to-PCP ratio of
   **3,500:1** (3,000:1 in high-need areas). A true gap = providers needed to reach the
   benchmark minus providers present (`max(0, pop/3500 − providers)`), i.e. "this area needs
   N more PCPs." The detail panel now shows the raw ratio against the 3,500:1 reference so the
   absolute picture is visible.
2. **A need adjustment.** Lower the adequate ratio where disease burden / demand is high
   (HPSA's high-need 3,000:1; or weight the denominator population by expected demand). This
   is what makes it a gap "to meet the needs of the disease prevalence."
3. **A spatial catchment** (2SFCA, §7) so the ratio reflects what residents can reach, not
   what their ZIP happens to contain.

One caution: NPPES counts are cumulative *registrations* and over-count active capacity, so
an absolute ratio against 3,500:1 reads *too optimistic*. Relative ranking partly sidesteps
this (the over-count is roughly uniform); an honest absolute gap needs active-provider data
(e.g. Medicare/Medicaid claims-based FTE), which is the further upgrade.

---

## 4. Economic vulnerability

```
econ_vuln_pctile = mean(
    percentile_rank(poverty_rate),
    percentile_rank(uninsured_rate),
    percentile_rank(−median_income)      # negated: high income = low vulnerability
) × 100
```

**Why these three.** Poverty, income, and insurance are the core socioeconomic /
access-barrier triad. Equal-weighted on a common scale.

**Precedent.** The **Area Deprivation Index** (Singh 2003; Kind et al., UW-Madison) builds a
deprivation composite from income/poverty/housing; the **SVI socioeconomic theme** uses
poverty and income; the uninsured rate is the most direct health-care-access barrier.

**Meaning.** `econ_vuln_pctile = 91` → more economically vulnerable than 91% of U.S. areas.

---

## 5. The composite Access Gap Score

```
access_gap_score = 0.40·disease_burden_pctile
                 + 0.35·supply_gap
                 + 0.25·econ_vuln_pctile         # weights renormalized over present components
```

**Why a weighted sum.** It is the simplest *transparent* aggregation: every point is
traceable to a driver, and the weights are exposed as sliders.

**Why these weights.** They are a **value judgment, not an empirical fact.** That is the
honest reason the sliders exist - the user owns the trade-off.

**Precedent.** **County Health Rankings** (RWJF / UW Population Health Institute) aggregates
health factors with *expert-chosen* weights (30% behaviors, 20% clinical care, 40% social &
economic, 10% environment), explicitly framed as a modeling choice.

**Meaning + an important subtlety.** The score is a 0-100 index where higher = more disease
meeting less supply meeting more vulnerability. The score value is **not itself a
percentile** - the weighted sum is not uniformly distributed (a score of 61 is about the
68th percentile; a score of 75 is about the 90th). So the app reports the *true percentile
of the score* for the "worse access than X% of U.S. ZIPs" statement, computed by ranking the
composite - the same final step CDC SVI performs on its summed index.

**The "what drives the gap" numbers** are the weight-normalized *contributions* of each
driver; they sum to the score. (E.g. a "supply gap" contribution of 5 on a score of 61 means
supply adds 5 of those 61 points.)

---

## 6. What we use vs. what is on the table

The MVP deliberately uses a thin slice of each source. Available but unused:

| Source | Used | Available, not yet used (all precedented) |
|---|---|---|
| CDC PLACES (~40 measures) | 5 chronic conditions | high blood pressure, obesity, high cholesterol, cancer, kidney disease, stroke, arthritis; **prevention** measures (annual checkup, cancer screenings) which are direct *access* signals; poor physical/mental-health days |
| Census ACS / SVI (16 SVI vars) | poverty, uninsured, income | unemployment, no-high-school-diploma, no-vehicle, crowded housing, limited English, disability, age 65+/under-18, single-parent households |
| CMS NPPES | primary care | **mental-health and specialist counts are already computed but excluded from the score**; dentists |
| HRSA HPSA | — | the federal shortage designation (deferred; would serve as an external consistency check) |

So yes - we are leaving a lot on the table. The components are transparent and honest; the
basket is just intentionally small for v1.

---

## 7. If we improve one thing: spatial supply (2SFCA)

The single highest-leverage fix is **not a new dimension - it is repairing the supply
dimension**, which is the one component currently producing artifact-driven values.

Replace ZIP containment with a **Two-Step Floating Catchment Area** measure (Luo & Wang,
2003 - the standard spatial-accessibility method):

1. For each provider location, pool the population within a travel radius (~16 km) and
   compute a provider-to-population ratio for that catchment.
2. For each ZIP, sum the catchment ratios reachable within the radius (optionally
   distance-decay weighted).

Implemented with a `BallTree(metric="haversine")` spatial index over ZIP centroids, this is
milliseconds over 33k points (never all-pairs). It turns supply from *"where the buildings
are"* into *"what a resident can actually reach,"* and it dissolves the many-zeros tie
problem (residential ZIPs stop reading as exactly zero).

If the preference is instead to **add** a dimension, the precedented move is to widen the
economic layer toward the full **CDC SVI variable set** rather than invent new indicators -
adopt an established index, don't reinvent one.

---

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

**Proof it's not a passive descriptor:** we *have* descriptors - median age, % minority,
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
| **Area Deprivation Index** | a rich SES deprivation set; factor-weighted |
| **County Health Rankings** | dimension structure + *transparent expert weights*; separates **outcomes** from **factors** |
| **Healthy Places Index** | weights derived **empirically** by regressing domains on **life expectancy** |
| **HRSA IMU/MUA** | poverty + elderly + supply as the underservice formula |

**Gaps (missing from the picture):**
- **No health-outcomes dimension.** CHR ranks outcomes (mortality/life-expectancy)
  separately; we rank need + access only. *Partial fix shipped:* we now report a validation
  anchor - the composite's correlation with PLACES fair/poor health (~0.85). *Backlog:* a
  true outcomes layer from CDC USALEEP life-expectancy or preventable-mortality.
- **Under-insurance** not measured (only uninsured); income proxies it.
- **Other supply types** - dental, pharmacy (deserts), broadband/telehealth - not yet in.
- **No empirical weights** - we use conceptual weights (see §10); HPI-style life-expectancy
  regression is the principled upgrade.

**Redundancies (disclosed, mostly intentional):**
- **Poverty is counted ~twice** - it conditions PLACES disease estimates (health need) *and*
  drives social vulnerability (dimension correlation ~0.5). The sliders + reported
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
- **Empirical alternative (backlog):** derive weights HPI-style by regressing the three
  dimensions on a health outcome (life expectancy / fair-poor health), which would replace
  the value judgment with a data-driven one. The validation anchor (§9) is the first step.

## 11. Supply, enhanced - E2SFCA, and the "need-adjusted?" question

Shipped the §7 recommendation, then went one better: supply now uses **E2SFCA** (Luo & Qi
2009) - 2SFCA **plus Gaussian distance decay**, so a clinic 2 km away counts far more than
one at the 16 km edge. More realistic than the binary catchment.

**"Need-adjusted?"** - weighting demand by morbidity (sicker populations stretch each
provider further) is legitimate (demand-weighted SFCA), and it's computed and stored
(`primary_2sfca_needadj`). But it is **deliberately not the scored value**: health need is
already its own 35% dimension, so need-adjusting supply would **double-count need**. We keep
the scored supply un-need-adjusted and surface the need-adjusted variant for transparency.

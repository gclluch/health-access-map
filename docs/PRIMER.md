# Care Access Map - Primer

A single resource to get intimately familiar with this project: the purpose, the
problem space, every dataset and field, the metrics and the math behind them, the
jargon, and the domain knowledge. Written to onboard a human or an agent from zero.

> If you read only one thing: the app turns four federal datasets into one
> explorable, drill-down map of **where Americans face the biggest gap between
> health *need* and health-care *access*** - at ZIP-code granularity, with every
> number traceable to its source and honestly caveated.

---

## 1. What this is, and who it's for

**Care Access Map** is a web app: a choropleth (color-shaded) map of the United
States at **ZIP-code-area** granularity. For any ZIP you see a composite **Access
Gap Score** and can drill down through 3 dimensions → 14 sub-scores → ~50 underlying
measures. You can re-weight the score live, rank the worst/best areas by any metric,
search a ZIP, and read every methodological caveat in-app.

**Audience:** analysts, public-health folks, journalists, students, and a portfolio
reviewer. The differentiator is **honesty + transparency**: it tells you exactly how
each number is built and why it might mislead.

**It is an exploratory instrument, not a clinical or policy verdict.** Every score is
a *relative national rank*, not an absolute measure of badness.

---

## 2. The problem space (the landscape)

**Health-care access** = the ability of people to obtain needed health services. It is
shaped by three broad forces, which map directly onto this tool's three dimensions:

1. **Need / burden** - how sick the population is (chronic disease, behavioral risk,
   mental health, disability). Higher need = more demand on the system.
2. **Social vulnerability** - the socioeconomic and material conditions that make care
   harder to get and worse health more likely (poverty, no insurance, no vehicle,
   food/housing insecurity, language barriers). This is the **social determinants of
   health (SDOH)** lens.
3. **Care access (supply)** - whether providers, coverage, and preventive care are
   actually reachable.

An **"access gap"** exists where **high need + high vulnerability meet low access**.
Why is *vulnerability* part of *access*? Because access is realized use, not just supply -
affordability (income), accessibility (transportation), and acceptability (language) are
access dimensions by the standard definition (Penchansky's 5 A's; Andersen's enabling
factors), and the federal Medically-Underserved formula itself uses poverty + elderly
alongside provider supply. (Full argument, the honest scoring evaluation, and the weight
rationale: [`RATIONALE.md`](RATIONALE.md) §8-11.) The core idea is well-trodden:

- The federal government formalizes it as **HPSA / MUA** designations (see glossary).
- Researchers quantify it with **spatial accessibility** methods (2SFCA).
- Equity is quantified with composite indices: **CDC/ATSDR SVI**, the **Area
  Deprivation Index (ADI)**, the **County Health Rankings**.

This project synthesizes those established approaches into one interactive, ZIP-level
instrument - it does not invent new methodology.

**Why ZIP-level?** It's the granularity people intuitively understand ("my ZIP"), and
the level at which PLACES + NPPES are readily available nationally. The honest caveat:
ZIP areas are postal/statistical, not communities, and people cross ZIP lines for care
(which is exactly why supply is measured spatially, not by containment - see §7.3).

---

## 3. The mental model (the hierarchy)

```
ACCESS GAP SCORE  (one 0-100 relative national rank, tunable weights)
├─ HEALTH NEED            (35%)   ── CDC PLACES
│  ├─ Chronic disease            (11 conditions)
│  ├─ Behavioral risk            (smoking, inactivity, drinking, sleep)
│  ├─ Mental & social distress   (depression, poor-mental-health-days, loneliness…)
│  └─ Disability                 (7 disability types)
├─ SOCIAL VULNERABILITY   (30%)   ── Census ACS + CDC PLACES (SDOH)
│  ├─ Socioeconomic              (poverty, income, unemployment, education)
│  ├─ Housing & transport        (no vehicle, crowding, mobile homes, multi-unit)
│  ├─ Unmet social needs         (food/housing/transport/utility insecurity)
│  └─ Digital / telehealth access (no household internet)
└─ BARRIERS TO CARE       (35%)   ── CMS NPPES + HRSA + Census ACS + Urban Institute
   ├─ Low provider supply (spatial) (E2SFCA: primary, mental, dental, maternity/OB)
   ├─ Official provider shortage    (HRSA primary-care HPSA)
   ├─ Lack of insurance             (uninsured: ACS + PLACES)
   ├─ Medical debt burden           (in collections — Urban Institute)
   ├─ Unmet safety-net need*        (FQHC desert × poverty)
   └─ Low preventive-care use*      (checkups, screenings)

* displayed but NOT scored (see §6 and DECISIONS.md). The former "household
  composition" sub-score (age 65+, age 17−, limited English) was dropped — age is
  context and limited-English is wrong-signed vs mortality.
```

Every level is a **0-100 national percentile, and every label is direction-honest:
higher = worse, always** (hence "barriers to care," not "care access"; "low provider
supply," not "provider supply"). See
`docs/diagrams/proposed-model.svg` for the visual.

---

## 4. The universal join key: ZCTA

Everything keys on **`zcta5`** - a **5-character, zero-padded string** (e.g. `01001`,
`90210`).

- **ZIP code** = a USPS *mail-delivery route*, not an area. It can change anytime and
  doesn't tile the map.
- **ZCTA** (ZIP Code Tabulation Area) = the Census Bureau's *areal approximation* of a
  ZIP, built from census blocks. ~33,000 nationally. This is what we actually map and
  join on.
- USPS ZIP ≠ ZCTA exactly. NPPES carries USPS ZIPs; PLACES/ACS use ZCTAs. We do a
  direct 5-digit match (covers the large majority) and accept minor loss.

**The leading-zero trap:** `01001` read as an integer becomes `1001`, silently
dropping ~8% of the Northeast. The pipeline forces string dtype + zero-pad on every
read and asserts `^\d{5}$`.

**Vintage alignment:** ZCTA boundaries changed between the 2010 and 2020 Censuses.
PLACES (2025 release), ACS (2023), and TIGER (2020 cartographic) are all kept on the
**2020 ZCTA** basis so the join doesn't silently mismatch.

---

## 5. The datasets

### 5.1 CDC PLACES — disease, behavior, disability, SDOH
- **What:** model-based estimates of ~40 health measures for every ZCTA.
- **Source:** CDC, `data.cdc.gov`, "PLACES: ZCTA Data (GIS Friendly Format)".
- **How it's made:** **MRP** (multilevel regression with poststratification) applied to
  the **BRFSS** survey (the CDC's annual phone health survey, ~400k respondents), then
  projected onto small areas using demographics. So these are **modeled small-area
  estimates, not raw case counts**.
- **Unit:** `*_CrudePrev` = crude prevalence, a **percentage of adults** (mostly 18+).
- **Critical caveat:** because PLACES borrows strength from socioeconomic structure, its
  disease estimates are *partly predicted from* SES. So a "high disease + high poverty"
  correlation partly recovers the model's own assumptions - not two independent signals.
- **Crude vs age-adjusted:** we use **crude** prevalence (raw % of the population). It
  reflects the local **age mix** - a retirement ZIP reads high-burden because it's old.
  We carry **median age** as context to flag this.

### 5.2 CMS NPPES — providers
- **What:** the National Plan & Provider Enumeration System - the registry of every
  **NPI** (National Provider Identifier) in the US. ~8M records, ~330 columns, ~10 GB.
- **Source:** CMS monthly "Full Replacement" file, `download.cms.gov/nppes`.
- **We keep:** individual providers (Entity Type 1), their practice ZIP, and taxonomy.
- **Classification:** the **NUCC** Provider Taxonomy crosswalk maps each provider's
  taxonomy code to a class. We derive **primary care**, **mental health**, **dental**, and
  **maternity (OB/GYN)** - each run through E2SFCA separately, so the supply sub-score spans
  the spectrum of care types and surfaces **dental deserts** (~6,600 ZCTAs) and
  **maternity-care deserts** (~15,800 ZCTAs with no OB access in catchment).
- **Critical caveats:** an NPI is a *registration*, not a full-time-equivalent clinician.
  It says nothing about whether the provider is active, accepts Medicaid/uninsured, or
  takes new patients. Counts **over-state effective capacity**, especially for the
  underserved. Some ZIPs are billing/institutional addresses (a hospital campus with ~2
  residents shows absurd per-capita density) - which is why we use spatial 2SFCA, not
  raw containment.

### 5.3 Census ACS — economics, society, housing
- **What:** the American Community Survey - the Census Bureau's rolling survey of income,
  poverty, employment, education, housing, demographics.
- **Source:** Census Data API, `api.census.gov`. **5-year** estimates (pooled over 5
  years for small-area reliability), 2023 vintage, at ZCTA.
- **We pull:** median income, poverty, uninsured (group `B27001`), median age, plus
  ~10 **SVI-style** rates (unemployment, education, age structure, limited English,
  vehicles, crowding, housing type) and demographics for context.
- **Critical caveats:** 5-year estimates are *centered ~2-3 years back* in time. Small
  ZCTAs have wide **margins of error (MOE)** - we flag low-population areas. Census uses
  **sentinel negatives** (e.g. `-666666666`) for suppressed values, scrubbed to null.

### 5.2a HRSA FQHC sites — the safety net
- **What:** ~18,000 active Federally Qualified Health Center service-delivery sites (HRSA),
  geocoded, with operating hours.
- **Why it matters:** FQHCs are mandated to serve everyone on a **sliding fee scale** - they
  are the access point for the uninsured/Medicaid. A raw provider count is *provider-agnostic*
  (it counts a concierge doctor like a community clinic); the safety-net layer captures whether
  the people who most need care can actually get it. It's the supply-side answer to "will they
  see *you*" (the Acceptability "A" of access).
- **How we use it:** a **bipartite E2SFCA** (sites = supply, ZCTA centroids = demand, operating
  hours = capacity weight) → a "Low safety-net access" sub-score, plus FQHC sites reachable +
  nearest-FQHC distance in the panel. 37% of ZCTAs have **no FQHC within 16 km** (safety-net deserts).
- **Caveat:** site presence ≠ unlimited capacity; sliding-fee ≠ free; hours are a rough capacity proxy.

### 5.3a CDC USALEEP — life expectancy (the independent outcome)
- **What:** life expectancy at birth for census tracts (2010-2015), from the U.S. Small-area
  Life Expectancy Estimates Project (NCHS + RWJF + NAPHSIS).
- **Why it matters:** it's the **one input derived from death records, not BRFSS/PLACES** -
  genuinely independent of the disease/behavior layers. We use it as a separate **outcome**
  (shown, colorable) and to **derive the empirical weights** (regress dimensions on it).
- **How we use it:** tract life expectancy → ZCTA via a population-weighted (POPPT) crosswalk
  (Census 2010 ZCTA↔tract relationship). It is **never in the access-gap composite** -
  outcomes are the result of poor access, not a driver of it (the County Health Rankings stance).
- **Caveats:** 2010-2015 vintage; covers ~89% of tracts (no Maine/Wisconsin); 2010 tracts/ZCTAs
  mapped onto 2020 ZCTAs.

### 5.4 Census geography — TIGER, Gazetteer, relationship files
- **TIGER cartographic boundary** (`cb_2020_us_zcta520_500k`): the ZCTA polygons,
  simplified (mapshaper, 8%) and reprojected to WGS84 for web rendering. The 2020
  vintage is the *only* one that publishes ZCTA boundaries.
- **Gazetteer**: ZCTA "internal point" lat/lon centroids - the anchor for the 2SFCA
  catchment.
- **ZCTA→County relationship file**: maps each ZCTA to its dominant county (by land
  area) for the human "Coahoma County, Mississippi" labels. City names come from the
  modal NPPES provider city.

### 5.5 Conceptual references (not datasets we ingest, but frameworks we follow)
- **CDC/ATSDR SVI** (Social Vulnerability Index) - the percentile-rank-and-aggregate
  method, and the social-vulnerability variable set.
- **HRSA HPSA** (Health Professional Shortage Area) - the 3,500:1 supply benchmark.
- **Area Deprivation Index (ADI)** - the socioeconomic deprivation composite.
- **County Health Rankings** - the weighted-dimension composite with expert weights.

---

## 6. Every field

Format: **column** — definition — *direction* (`↑worse` = higher value is worse;
`↑better` = higher is better) — unit.

### HEALTH NEED (CDC PLACES, crude % of adults, all `↑worse`)
**Chronic disease:** `diabetes_pct` diabetes · `bphigh_pct` high blood pressure ·
`highchol_pct` high cholesterol · `chd_pct` coronary heart disease · `stroke_pct`
stroke · `copd_pct` chronic obstructive pulmonary disease · `casthma_pct` current
asthma · `cancer_pct` cancer (non-skin) · `obesity_pct` obesity · `arthritis_pct`
arthritis · `teethlost_pct` all natural teeth lost (oral-health proxy).
**Behavioral risk:** `csmoking_pct` current smoking · `lpa_pct` no leisure-time
physical activity · `binge_pct` binge drinking · `sleep_pct` short sleep (<7h).
**Mental & social health:** `depression_pct` depression · `mhlth_pct` ≥14 poor
mental-health days/month · `loneliness_pct` loneliness · `emotionspt_pct` lacks
social/emotional support.
**Disability:** `disability_pct` any · `mobility_pct` · `cognition_pct` ·
`vision_pct` · `hearing_pct` · `selfcare_pct` · `indeplive_pct` independent-living.

### SOCIAL VULNERABILITY (Census ACS rates 0-1 + PLACES SDOH %, all `↑worse` except income)
**Socioeconomic:** `poverty_rate` below federal poverty line · `median_income`
median household income (*↑better*, $) · `unemployment_rate` · `no_hs_diploma_rate`
adults 25+ without a high-school diploma.
**Housing & transport:** `no_vehicle_rate` no vehicle available · `crowding_rate` >1
occupant per room · `mobile_home_rate` · `multi_unit_rate` 10+ unit structures.
**Unmet social needs (PLACES SDOH %):** `foodinsecu_pct` food insecurity ·
`housinsecu_pct` housing insecurity · `lacktrpt_pct` lack of reliable transportation ·
`shututility_pct` utility shut-off threat · `foodstamp_pct` receives SNAP/food stamps.
**Digital / telehealth access:** `no_internet_rate` households with no internet
subscription (ACS B28002) — the telehealth analog of the no-vehicle barrier.

> The former **household composition** sub-score (`age65_rate`, `age17_rate`,
> `limited_english_rate`) is no longer scored — age structure is context and limited
> English is wrong-signed vs mortality (immigrant-health paradox). Those columns remain
> as context (see below).

### CARE ACCESS
**Provider supply (spatial, E2SFCA):** `primary_2sfca` primary-care providers per 1,000
people *reachable within ~16 km* (*↑better*) · `mental_2sfca` mental health · `dental_2sfca`
dental · `ob_2sfca` maternity/OB-GYN. Derived: `primary_people_per_provider` (catchment
people-per-provider) and `primary_shortage` (boolean, true if > HRSA 3,500:1).
**Official provider shortage (HPSA):** `hpsa_pc_score` HRSA primary-care Health
Professional Shortage Area score — an official designation orthogonal to the E2SFCA density.
**Insurance:** `uninsured_rate` (ACS, all ages) · `access2_pct` (PLACES, adults 18-64).
**Medical debt burden:** `medical_debt` share with medical debt in collections (Urban
Institute credit-bureau panel, county-level) — the affordability barrier beyond coverage.
**Safety-net access (displayed, NOT scored):** `safetynet_2sfca` FQHC capacity reachable ·
`fqhc_sites_reachable` · `nearest_fqhc_km`. Scored form `safetynet_barrier` (FQHC desert ×
poverty) is `scored=False` — wrong-signed within counties (see §6 / VALIDATION.md).
**Preventive-care use (PLACES %, `↑better`; displayed, NOT scored):** `checkup_pct`
annual checkup · `dental_pct` dental visit · `cholscreen_pct` cholesterol screening ·
`mammouse_pct` mammography · `colon_screen_pct` colorectal screening · `bpmed_pct`
taking prescribed BP medication. Realized utilization (a mediator), so `scored=False`.

### Context only (shown, never scored — by design)
`median_age`, `pct_minority` (1 − white-non-Hispanic share), `pct_under5`,
`pct_over65_ctx`, `age65_rate`, `age17_rate`, `limited_english_rate` (the former
"household composition" inputs, now context), `medicaid_rate` (Medicaid/means-tested
coverage — a barrier that collapses to the poverty gradient, so shown not scored),
`ghlth_pct` (fair/poor general health), `phlth_pct` (poor physical-health days),
provider raw counts, population, and geography (`city`, `county_name`, `state_name`).

> **Race/ethnicity is context, not scored.** The CDC SVI includes a minority-status
> theme (for disaster planning). We deliberately exclude it from the access-gap score:
> encoding race as "vulnerability" in a health-equity score is easily misread as
> causal. We show demographics for context only.

### The derived percentiles (what the UI mostly shows)
- 14 sub-scores: `chronic_disease_pctile`, `behavioral_risk_pctile`,
  `mental_social_health_pctile`, `disability_pctile`, `socioeconomic_pctile`,
  `housing_transport_pctile`, `social_needs_pctile`, `digital_access_pctile`,
  `provider_supply_pctile`, `shortage_designation_pctile`, `insurance_pctile`,
  `medical_debt_pctile`, plus `safetynet_access_pctile` and `preventive_use_pctile`
  (the last two are computed and displayed but **not scored** — `scored=False`).
- 3 dimensions: `health_need_pctile`, `social_vulnerability_pctile`,
  `care_access_pctile`.
- Composite: `access_gap_score` (the weighted blend) and `access_gap_pctile` (its true
  national rank).

---

## 7. The metrics & the math

### 7.1 Percentile ranking (the backbone)
Every measure is **percentile-ranked nationally**: `pctile(x) = (rank of x / N) × 100`.
- **Meaning:** `pctile = P` → "higher than P% of all U.S. ZIP areas on this measure."
- **Why:** the inputs are wildly different scales and heavily right-skewed (provider
  density, income). Percentile rank is **ordinal**, so it's immune to outliers and gives
  one interpretable 0-100 scale. This is the **CDC SVI** method.
- **Orientation:** before ranking, each measure is oriented so **higher = worse**
  (income and preventive-care-use are negated). So every percentile reads uniformly.

### 7.2 Where z-scores appear
Within a sub-score we average **member percentiles** directly (SVI-style). (An earlier
version z-scored disease measures before averaging; the current model uses percentile
means at every level for consistency and reproducibility.)

### 7.3 2SFCA — the spatial supply metric (Two-Step Floating Catchment Area)
The honest way to measure supply. Containment ("providers inside my ZIP ÷ my
population") is an artifact of where buildings sit. 2SFCA (Luo & Wang, 2003) instead:
- **Step 1:** for each ZCTA *j*, compute `Rj = providers_j ÷ (population pooled over all
  ZCTAs whose centroid is within ~16 km of j)`.
- **Step 2:** for each ZCTA *i*, `accessibility_i = Σ Rj over all j within ~16 km of i`.
- Result: **providers per person reachable**, not just contained. A residential ZIP now
  inherits the supply of the clinic ZIP next door.
- Implemented with a `BallTree(metric="haversine")` spatial index (radius query over
  33k points is milliseconds; never all-pairs O(n²)).
- **Honest naming:** the sub-score is "Provider supply (spatial)" - still a *relative*
  access measure, not itself a need-relative "gap." The real benchmark gap is the
  `primary_shortage` flag (people-per-provider vs **HRSA 3,500:1**).
- **Caveat:** the ~16 km radius is urban-calibrated; rural access operates at a larger
  scale, so rural supply reads somewhat low.

### 7.4 The hierarchy aggregation (re-ranked at each level, SVI-faithful)
```
member_pctile      = percentile_rank(oriented measure)
subscore_pctile    = percentile_rank( mean(member_pctiles) )      # re-ranked
dimension_pctile   = percentile_rank( mean(subscore_pctiles) )    # re-ranked
access_gap_score   = weighted_mean(dimension_pctiles, weights)    # 35/30/35 default
access_gap_pctile  = percentile_rank(access_gap_score)            # the true "rank"
```
Re-ranking at each level keeps every node a clean 0-100 "higher = worse." Missing
members/sub-scores are skipped (the mean is over what's present), so partial data still
yields a score; an area needs ≥2 of 3 dimensions and a population to be "scoreable."

### 7.5 Reading any number (English)
- **A sub-score / dimension of 5** → worse than only 5% of ZIPs on that axis = among the
  *best* 5% (low burden / low vulnerability / good access).
- **of 95** → among the worst 5%.
- **Composite "worse access than 68% of U.S. ZIPs"** → the *true percentile* of the
  composite (the raw 0-100 score value is not itself a percentile, so we rank it - the
  same final step SVI performs).
- **"What drives the gap" numbers** = each dimension's weight-normalized *contribution*;
  they sum to the score.
- **Supply 2SFCA 3.7/1k** → ~3.7 primary-care providers per 1,000 people reachable within
  the catchment. **`primary_shortage = true`** → below the HRSA 1-per-3,500 benchmark.

### 7.6 Why the weights are tunable
The default 35/30/35 dimension weights are a **value judgment, not empirical** (as in
County Health Rankings). The three dimensions are also **strongly collinear**
(need↔vulnerability **0.73**, need↔access 0.59, vulnerability↔access 0.61; ~1.6 effective
dimensions), so a weighted sum double-counts shared variance. The **sliders** make that subjectivity
explicit and explorable rather than hidden - that's the honest resolution.

---

## 8. Glossary (acronyms & jargon)

- **ZCTA** — ZIP Code Tabulation Area; the Census areal version of a ZIP. The join key.
- **ZIP** — USPS Zone Improvement Plan code; a mail route, not an area.
- **PLACES** — CDC's Population Level Analysis and Community Estimates; small-area health
  estimates.
- **BRFSS** — Behavioral Risk Factor Surveillance System; the CDC phone survey PLACES is
  modeled from.
- **MRP** — Multilevel Regression with Poststratification; the small-area modeling method.
- **SDOH** — Social Determinants of Health; non-medical conditions (food, housing,
  transport, income) that shape health.
- **NPPES** — National Plan & Provider Enumeration System; the CMS provider registry.
- **NPI** — National Provider Identifier; a provider's unique id.
- **NUCC** — National Uniform Claim Committee; publishes the provider-taxonomy code set.
- **CMS** — Centers for Medicare & Medicaid Services.
- **ACS** — American Community Survey (Census). **5-year** = pooled for small areas.
- **MOE** — Margin of Error (ACS estimates carry one; large for small areas).
- **CV** — Coefficient of Variation = SE/estimate; a reliability measure.
- **TIGER** — Census Topologically Integrated Geographic Encoding & Referencing; the
  geography files. **Cartographic boundary** = simplified for mapping.
- **Gazetteer** — Census file of place centroids (internal points) + areas.
- **SVI** — CDC/ATSDR Social Vulnerability Index; percentile-rank composite of 16 social
  factors in 4 themes.
- **ADI** — Area Deprivation Index (UW-Madison); socioeconomic deprivation ranking.
- **HRSA** — Health Resources & Services Administration.
- **HPSA** — Health Professional Shortage Area; a federal designation (e.g. primary care
  when population:provider ≥ 3,500:1, or 3,000:1 in high-need areas).
- **MUA/MUP** — Medically Underserved Area/Population; a related HRSA designation.
- **FQHC** — Federally Qualified Health Center; safety-net clinic (not modeled here).
- **2SFCA / E2SFCA** — (Enhanced) Two-Step Floating Catchment Area; spatial-access method.
- **PCP** — Primary Care Provider/Physician.
- **FTE** — Full-Time Equivalent (what an NPI count is *not*).
- **Choropleth** — a map shaded by a data value per area.
- **Crude vs age-adjusted prevalence** — raw % vs standardized to a reference age
  structure (we use crude).
- **Ecological fallacy** — inferring individual facts from area aggregates (a trap).
- **Percentile rank** — position in a distribution, 0-100; ordinal, outlier-robust.
- **cividis** — the perceptually-uniform, colorblind-safe color ramp used for the map.

---

## 9. Domain facts worth knowing

- **The US has no single "access" number.** Access is multi-dimensional; HRSA uses
  several overlapping designations (HPSA, MUA/MUP), each with its own formula. This tool
  is a synthesis, not an official designation.
- **Primary care is the front door.** Provider-to-population ratios for primary care are
  the standard workforce-adequacy metric; ~1 PCP per 1,500-2,000 is often cited as
  adequate, and HRSA flags shortage at 3,500:1.
- **Supply ≠ access ≠ utilization ≠ outcomes.** Having a provider nearby (supply)
  doesn't mean you can get in (access), use them (utilization), or get healthy
  (outcomes). This tool measures *potential* spatial access plus need and vulnerability.
- **The most underserved places** in the US that this model surfaces - Pine Ridge
  (Oglala Lakota County, SD), the Mississippi Delta, the Navajo Nation, Appalachia,
  South Texas colonias - are exactly the regions the health-equity literature flags.
- **Social needs are now measurable.** Recent PLACES releases added SDOH measures (food,
  housing, transport, utility insecurity, loneliness) - a major addition this tool uses.
- **Modeled estimates are powerful but circular.** Small-area models like PLACES make
  national ZIP-level health visible at all, but because they borrow from demographics,
  correlating them against demographics isn't independent confirmation.

---

## 10. Limitations (honest, first-class)

1. **Relative, not absolute.** Every score is a national rank. 95 means "worse than 95%
   of ZIPs," not "objectively bad."
2. **Modeled disease (PLACES).** SES-conditioned; not independent of the vulnerability
   layer. Crude prevalence reflects age mix (median age shown).
3. **Provider supply is spatial access over registrations.** 2SFCA fixes containment, but
   NPPES counts over-state active capacity and ignore Medicaid/new-patient acceptance.
   The HRSA flag is the only benchmark-referenced gap.
4. **Strongly collinear dimensions** (need↔vulnerability **0.73**, need↔access 0.59,
   vulnerability↔access 0.61; ~1.6 effective dimensions). The weighted sum double-counts;
   sliders make it explicit; correlations are reported in `provenance.json`.
5. **Small-area noise.** Low-population ZIPs have wide MOEs; flagged low-confidence and
   excluded from headline rankings; uninhabited ZIPs render gray ("no reliable data").
6. **Vintage/universe skew.** NPPES (this month), ACS (centered ~2-3 yrs back), PLACES
   (a BRFSS year) describe different times and populations (adults 18+, civilian
   noninstitutionalized, total).
7. **Ecological fallacy.** Area patterns are not individual-level facts.
8. **ZIP↔ZCTA + rural catchment.** Direct 5-digit matching drops a few providers; the
   16 km catchment is urban-calibrated, so rural supply reads low.

---

## 11. Precedents this builds on (so you can cite/learn the field)

| This tool | Established method |
|---|---|
| Percentile-rank → sub-score → dimension → composite | **CDC/ATSDR SVI** |
| Social-vulnerability variable set | **SVI**, **Area Deprivation Index** |
| Weighted dimensions with chosen weights | **County Health Rankings** (RWJF/UW) |
| Spatial provider supply | **2SFCA** (Luo & Wang 2003; E2SFCA Luo & Qi 2009) |
| Supply adequacy benchmark | **HRSA HPSA** (3,500:1) |
| Disease/SDOH groupings | **CDC PLACES** categories |
| Small-area estimation | **MRP** on **BRFSS** |

---

## 12. Where things live (code map)

```
pipeline/
  config.py            all volatile URLs/IDs + ACS variable map + 2SFCA params
  taxonomy.py          THE model: dimensions → sub-scores → measures (+ directions)
  common.py            zcta normalization, downloads, percentile helper home
  build_places.py      CDC PLACES → 40 measures
  build_providers.py   CMS NPPES via DuckDB → primary/mental counts + modal city
  build_acs.py         Census ACS → income/poverty/uninsured + SVI rates
  build_geonames.py    ZCTA → county labels
  build_gazetteer.py   ZCTA centroids (for 2SFCA)
  build_supply.py      2SFCA spatial supply (BallTree haversine)
  build_geometry.py    TIGER → simplified WGS84 GeoJSON
  join_and_score.py    the hierarchical scoring engine (percentile, re-ranked)
  run.py               orchestrator (--dev-state, --only, --from, --force)
backend/               FastAPI over the in-memory metrics table (per-ZIP + rankings)
frontend/src/
  lib/types.ts         the MODEL hierarchy + weights (mirrors taxonomy.py)
  lib/scoring.ts       client-side composite recompute (matches the pipeline)
  lib/measures.ts      member measures per sub-score (for the drill-down)
  components/          MapView, DetailPanel (drill-down), RankingsList, Legend, …
docs/
  PRIMER.md            this file
  RATIONALE.md         scoring rationale + precedent
  diagrams/            score-flow.svg, proposed-model.svg
data/processed/
  metrics.parquet      everything (88 cols); served per-ZIP by the API
  map_frame.json       slim first-paint frame (geography + percentiles); loaded by the map
  subscores.json       the 14 sub-score lenses; fetched lazily on sub-score select
  provenance.json      exact dataset ids, vintages, weights, correlations
```

**Reproduce everything:** `make data` (national) or `make data-ca` (fast slice), then
`make api` + `make web`. Every percentile is reproducible from the stored raw columns
(guarded by an acceptance test).

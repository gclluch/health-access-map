# B5f pre-registration - Missouri replication & harmonized Billings pool

**Status: SHELVED 2026-08-01, before any Missouri data was acquired. Never run.** §0's premise
(B5d as a near-significant borderline) was already superseded on `master` when this was written -
B5d is a bounded null. See §7 for the closeout and for two known defects in the extractor.
§1-§6 are preserved unedited as the pre-registered plan.

**Originally: PRE-REGISTERED. Written 2026-08-01, BEFORE any Missouri data was acquired,
extracted, or inspected.** Nothing in this document may be revised after data exists. Any
change made later must be recorded below under "Deviations" with a date and a reason, and the
original text left intact.

---

## 0. Why this document exists

B5d returned overall ATT **-35.5/100k**, 95% CI **[-71.7, +2.2]**, n = 259 newly-served
treated ZCTAs (NY + TX). Implied SE ~ **18.85**.

We subsequently computed that the interval would exclude zero at SE < 18.11 - a variance ratio
of 1.083, i.e. roughly **+22 treated ZCTAs**.

**We now know exactly how much additional N it takes to cross significance.** That knowledge is
corrosive: any state list, specification, or aggregation chosen *after* learning it is open to
the charge that it was reverse-engineered from the desired result. Every causal claim in this
repo so far has been disciplined by measure-first / decide-after rules (see `DECISIONS.md`), and
B5d itself was gated by a power analysis run before the build. This document holds that line.

The commitments below are fixed. Their purpose is that the answer is credible **whichever way it
lands** - and a null here is an equally publishable outcome (see §6).

---

## 1. Gate 0 - the go/no-go that runs before anything else

Missouri MOPHIMS "Preventable Hospitalization MICA" splits into a **2016-and-Forward** module
and a **2015-and-Prior** module. ZIP/ZCTA geography is confirmed selectable in the former and
**unconfirmed** in the latter.

FQHC New Access Point openings in scope run **2012-2019**. An event study needs a pre-period.

**Decision rule, fixed in advance:**

- If the 2015-and-Prior module exposes ZIP/ZCTA -> proceed to §2 and §3 in full.
- If it does NOT -> the usable Missouri pre-period starts 2016, leaving only 2017-2019 opening
  cohorts with any pre-period at all. In that case **abandon the Missouri event study**, record
  the data limitation in `VALIDATION.md` §7, and do NOT substitute a shortened-window design,
  a different outcome, or a different state to rescue it. The null result of the gate is
  itself the deliverable.

No analysis of any kind is run before Gate 0 resolves.

---

## 2. Analysis 1 (replication) - Missouri standalone

Pre-specified, in full:

- **Outcome.** Missouri MICA preventable-hospitalization counts per ZCTA-year, Billings et al.
  (1993) definitions, as published. Conditions taken as the full set MICA exposes: asthma 18-39,
  COPD/asthma 40+, community-acquired pneumonia, diabetes (short-term, long-term, uncontrolled),
  heart failure, hypertension, UTI. We do NOT hand-pick a subset to maximise signal.
- **Denominator.** ZCTA population, same vintage source as the existing pipeline.
- **Treatment.** First FQHC site opened in the ZCTA per HRSA `Site Added to Scope this Date`,
  restricted to **newly-served** ZCTAs (no prior site), identical to B5d. Reuses
  `pipeline/research/build_fqhc_openings.py` unchanged.
- **Estimator.** Callaway & Sant'Anna group-time ATT, not-yet-treated + never-treated controls,
  within-state, identical settings to `pipeline/research/validate_fqhc_lever.py`. No re-tuning.
- **Inference.** ZIP-cluster bootstrap, same spec and same iteration count as B5d.
- **Aggregation.** Overall ATT, population-weighted, as the single headline. Event-time path
  reported but not used as the headline.
- **Suppressed cells.** Censored cells are treated as **missing, never as zero.** Count of
  suppressed ZCTA-years is reported alongside the estimate. If suppression removes >25% of
  treated ZCTA-years, the estimate is reported as unreliable and not used as evidence either way.

**Expectation stated in advance:** Missouri is Colorado-sized. Colorado yielded 35 newly-served
ZCTAs; we expect **35-50** here. NY alone (135) was already underpowered. **Missouri standalone
is expected to produce a wide, zero-crossing interval, and that outcome will NOT be interpreted
as evidence against an effect.** It is a sign and dose-response check only.

**What counts as replication support:** point estimate right-signed (negative) AND monotone in
event time. Nothing else. Significance is not required and will not be claimed.

---

## 3. Analysis 2 (confirmatory) - harmonized Billings three-state pool

This is the only free route that genuinely increases N in a single estimator.

- **Harmonization direction.** NY and TX record-level outcomes are **recomputed under Billings
  et al. definitions** to match Missouri. Missouri is NOT converted to AHRQ PQI (it cannot be -
  only aggregates are published).
- **Pool.** NY + TX + MO, single CS estimator, within-state controls, as in B5d.
- **Pre-committed acknowledgment:** changing the outcome definition changes the point estimate by
  an unknown amount in an unknown direction. We commit now to reporting the harmonized result
  **whatever it shows**, including if it is weaker, wrong-signed, or further from significance
  than the PQI-90 result.
- **Both results are reported side by side.** The original PQI-90 NY+TX estimate remains the
  primary published figure; the harmonized pool is reported as a pre-registered secondary test.
  The harmonized result does not replace or supersede the original.

---

## 4. Required falsification checks

The headline is void unless all three pass. These are gates, not robustness garnish.

1. **Placebo-in-time** - shift treatment dates 3 years earlier; estimated ATT must be
   approximately 0. (B5d returned -3.6; same standard applies.)
2. **Spillover-control drop** - re-estimate excluding control ZCTAs within 10 km of a treated
   site; sign and rough magnitude must survive. (B5d: -39.5 vs -35.5.)
3. **Pre-trend inspection** - event-time coefficients before t=0 reported in full, not
   summarized. B5d's pre-trends were **not fully clean** (residual siting); if the harmonized
   pool is worse, that is disclosed as a limitation, not smoothed over.

**Anti-circularity rule (unchanged, non-negotiable):** never gate on flu or mammography outcomes.
Judged against death-records / ACSC only. See `DECISIONS.md`.

---

## 5. Stopping rule

**One run per analysis.** After results exist:

- No re-specification, no alternative weighting, no state added or dropped, no condition subset
  changed, no event window adjusted.
- No "sensitivity analysis" introduced post hoc that becomes the reported headline.
- Any deviation whatsoever is logged in §7 with date and reason, and the pre-registered result
  is reported alongside it.

---

## 6. What each outcome means - written before we know which one we get

- **Harmonized pool excludes zero, falsification checks pass.** The project's first demonstrated
  free-data access lever, under a pre-committed spec. Reported with the caveat that the outcome
  definition differs from the headline index measure.
- **Harmonized pool crosses zero, right-signed, MO replicates the sign.** A well-powered
  "almost" with independent out-of-sample corroboration. Given the realized effect is **2.78%**
  of baseline, sitting essentially on the 2% floor the B5d.0 power gate named as the
  underpowered boundary, this is the **most likely** outcome and is a legitimate, publishable
  finding - not a failure.
- **Harmonized pool null or wrong-signed.** Reported as a null. Combined with the clean
  cross-sectional negative control (§7 of `VALIDATION.md`) and the overturned temporal signal,
  it closes the supply-lever question honestly. Also publishable.
- **Gate 0 fails.** Missouri is unusable; recorded as a data limitation. No substitute design.

In no branch does the absence of significance trigger a search for a specification that produces it.

---

## 7. Deviations

*(append dated entries below, never edit above this line)*

### 2026-08-01 - B5f SHELVED before any data was acquired. §0's premise was already superseded.

**Nothing in §1-§6 was run. No Missouri counts were extracted. This is a closeout, not a result.**

§0 motivates the whole pre-registration from B5d standing at **−35.5/100k, 95% CI [−71.7, +2.2]**,
and from the corrosive knowledge that ~+22 treated ZCTAs would push the interval off zero. That
framing was **stale when this document was written**, by two changes already on `master`:

1. **Spatial inference** (`VALIDATION.md` §7, "Spatial-inference update"). The causal validators now
   key their verdict on a **county-block** bootstrap rather than the ZIP-cluster one, because ACSC
   geography is spatially autocorrelated and ZIP-clustering treats neighbouring ZIPs as independent.
   The honest CI is [−74.1, +10.5], not [−71.7, +2.2]. The "hair" in §0 is an artifact of the
   too-narrow CI, and the SE arithmetic in §0 is computed on the superseded number.
2. **Doubly-robust conditional re-estimate** (commit `d31245c`, `VALIDATION.md` §7f). Conditioning
   each ATT(g,t) on pre-window ACSC level + slope, poverty and log pop collapses the overall ATT to
   **−4.3/100k**, CI [−38.0, +35.4]. Roughly +31 of the −35.5 was observable siting read back as
   treatment. With Ding & Li (2019) bracketing the effect is bounded in **[−35.5, −4.3]/100k, both
   ends ≈ 0**.

**Why that shelves B5f rather than merely re-scoping it.** This document exists to stop a marginal
positive from being reverse-engineered into significance (§0, §5). There is no longer a marginal
positive to reverse-engineer toward - B5d is a bounded null with an informative upper bound. B5f's
remaining value is corroborating that null from a third state under a *different condition
definition* and a *different vintage*, at the cost of a ~230-query browser scrape plus a harmonized
three-state re-pool. Per §2 the Missouri standalone was already expected to return a wide,
zero-crossing interval at 35-50 treated ZCTAs; a wide null corroborating a bounded null adds
approximately nothing to the published conclusion.

**What the discipline actually bought.** §1's Gate 0 was resolved honestly (PASS, §8), §8a found and
pre-registered a real 2015/16 definitional break before any estimation, and §5's stopping rule is
being honored by *not running* rather than by running and then explaining. Recording a shelve here,
before data exists, is the same commitment as recording a null.

**Reopening conditions.** B5f becomes worth running only if the paid panels in `BACKLOG.md` B5d
(Florida ~$1,100, Oklahoma ~$550, both confirmed 5-digit patient ZIP) are purchased, since those
add N to the *existing* NY+TX estimator rather than standing alone. Free-state replication does not.
That is a spend decision, not an analysis decision.

**Known defects in `pipeline/research/build_mo_acsc.py`, recorded so shelving does not bury them.** The
parsing path is tested (24 cases) and sound; the browser path was never run against the live site
and has two defects found by reading, not by execution. Fix both before any future run:

1. `_counties()` (line 239) reads `page.locator("select").nth(2)` on a freshly-loaded page, i.e.
   *before* Geography = "Zip / ZCTA" has been selected. This module's own docstring (line 11) states
   the pickers cascade and the county list does not exist until geography is chosen, so the default
   all-counties path at line 265 reads the wrong `<select>`. Passing `--counties` explicitly avoids it.
2. `_scrape_one()` selects `Statistics: "Counts and Rates"` (line 315), but `parse_table_csv` and its
   fixtures assume **one column per year** (`Statistics:,Count,Count`). With both statistics there are
   two columns per year, both matching the year regex, so the parser emits two rows per
   `(zcta5, year)` and `combine()`'s `drop_duplicates` silently keeps one - possibly the **rate**
   where a count is intended. Select counts only, or make the parser read the Statistics row and
   keep the count column explicitly.

---

## 8. Gate 0 result - RESOLVED 2026-08-01, verdict PASS

Checked directly in the live MOPHIMS Preventable Hospitalization query builder
(`healthapps.dhss.mo.gov/MoPhims/QueryBuilder?qbc=PHM&q=1&m=1`), before any extraction.

**PASS, and more comfortably than the ticket assumed.**

- The **2015-and-Prior** module *does* expose ZIP geography. The Geography combobox carries
  `option "Zip / ZCTA" value="ZIP"`, and selecting it renders the full ZIP entry UI
  (per-county ZIP picker + manual ZIP entry + add/clear).
- Year coverage in that module: **2001-2015**, single-year selectable, annual.
- Combined with the 2016-and-Forward module (2016-2022), Missouri offers a continuous
  **2001-2022 annual ZIP-level panel** - a far longer pre-period than the 2012-2019 opening
  window requires.

### 8a. NEW ISSUE found during the gate - definitional break at 2015/2016

The two modules do **not** use the same condition list. This was not known when §1-§7 were
written and is recorded here rather than silently absorbed.

- **Upto 2015** (ICD-9 era): Angina, Asthma, Bacterial pneumonia, Cellulitis, Chronic
  obstructive pulmonary, Congenital syphilis, Congestive heart failure, Convulsions,
  Dehydration - volume depletion, ... - the older, broader Billings-style list.
- **2016 Onwards** (ICD-10 era): Asthma in Younger Adults (18-39), COPD or Asthma in Older
  Adults (40+), Community Acquired Pneumonia, Diabetes Long-Term Complications, Diabetes
  Short-Term Complications, Heart Failure, Hypertension, Other Diabetes with Lower-Extremity
  Amputation, Uncontrolled Diabetes, ... - these are **AHRQ PQI condition names**, not Billings.

So the earlier characterisation ("Missouri is Billings throughout") is **wrong for 2016+**. The
break sits at the Oct-2015 ICD-9 -> ICD-10 transition.

**Pre-specified handling, fixed now, before any estimation:**

1. The break is **common to all Missouri ZCTAs in a given year**, so it is absorbed by the
   year fixed effects already in the estimator. No rescaling, no splicing, no imputation.
2. **Pre-committed robustness check:** re-estimate dropping 2015 and 2016 entirely. If the sign
   or rough magnitude does not survive, the Missouri result is reported as
   **contaminated by the definitional break** and is not used as replication evidence.
3. Cohorts first treated in **2015 or 2016** are the ones most exposed to the break. Their
   group-time ATTs are reported separately and are **excluded from the headline aggregate**.
4. Because 2016+ is PQI-named, the harmonization in §3 is **re-scoped**: harmonize NY/TX to the
   *2016-onward* Missouri list where the panel permits, and treat the pre-2016 Billings-era
   Missouri years as a separate, clearly-labelled sensitivity - never pooled with PQI-era rows.

**These four rules are pre-registered. They were written before any Missouri counts were
extracted, and before any estimate existed.**

---

## 9. Implementation - `pipeline/research/build_mo_acsc.py` (added 2026-08-01)

Extractor written to the plan above, before any counts were pulled.

- **Browser-driven (Playwright), not `requests`.** MOPHIMS is stateful ASP.NET WebForms:
  every control change is a `__VIEWSTATE` postback and the geography/county/ZIP pickers
  cascade. A real browser removes that entire class of brittleness.
- **One query per (year_group, county)**, not per cell. Years accumulate into a multiselect
  via `Add=>`, and Main Row=Geography x Main Column=Year returns a whole ZIP x year matrix.
  Total ~115 counties x 2 modules, not ~22,000 queries.
- **Raw CSVs cached** under `data/raw/mo_mica/` so a re-parse never forces a re-scrape, and
  a failed county is skipped and logged rather than killing the run.
- **Suppression handling implements §2 exactly.** `parse_cell` returns a count only if the
  text parses as a number; `*`, `S`, `NR`, `-`, blank all become NA with `censored=True`.
  A literal `0` stays `0` - MOPHIMS emits genuine zeros for low-volume ZIPs, and conflating
  those with suppression in *either* direction would bias the panel.
- **The §8a break is enforced in code, not left to discipline.** Every row carries
  `year_group`, and `load_panel()` **refuses** to return a frame spanning both modules
  unless the caller passes `allow_mixed_definitions=True`. Accidentally pooling the
  Billings-era and PQI-era measures is now a hard error rather than a silent mistake.
- **Tests: `tests/test_mo_acsc.py`, 24 cases, browser-free.** Fixtures reproduce the real
  export shape verified against the live site (Boone County 2022: 65010=42, 65201=292,
  65215=0). Covers suppression-vs-zero in both directions, TOTAL-row rejection, ZIPs
  straddling county lines, malformed input, and the two-module separation.

**Not yet run.** No Missouri counts have been extracted. The plan in §1-§8 is unchanged by
the existence of this code.

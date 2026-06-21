# Reliability & Uncertainty Standards for Small-Area Composite Indices

**Question:** For a ZCTA-level (~33k areas) "Access Gap" composite (percentile-rank of 3 weighted dimensions from ~50 CDC PLACES + ACS + provider-supply measures), what does the field consider the standard for "is a difference between two areas meaningful," and is ZIP/ZCTA-level ranking comparison statistically valid?

**Headline:** The field's leading indices are *unanimous* that small-area composite ranks carry large, spatially-structured uncertainty, that close ranks are not statistically distinguishable, and that ZIP/ZCTA is a non-validated geography that adds error. The methodological gold standard (Saltelli/Saisana/OECD) is to report **confidence intervals on the ranks themselves**, not just point scores. Almost none of the production indices (ADI, SVI, even County Health Rankings) actually publish rank CIs - which is precisely the gap a credible new index can fill.

---

## 1. ADI / Neighborhood Atlas on ZIP/ZCTA use, and the Petterson critique

**ZIP/ZCTA is not validated; block group is the native geography.** The Neighborhood Atlas FAQ states the ADI should only be used at the geography for which it was validated:

> "The ADI should not be used at any levels other than the core Census geographies for which it is validated, specifically the Census block group."

> "Multiple studies demonstrate the substantial loss of exposome measure precision introduced when using 5-digit ZIP code geographies as opposed to core Census geographies."

> ZIP geographies "result in relatively large geographic zones with linkages that can lead to less precise estimates, especially in areas in which concentrated poverty abuts more wealthy regions."

The reasoning is exactly the one relevant to a ZCTA index: ZIP/ZCTA are large administrative zones (not census units) that average together heterogeneous populations, and the averaging is *worst* where poverty borders wealth - i.e., the boundaries that matter most for an access-gap measure.
Source: https://www.neighborhoodatlas.medicine.wisc.edu/faq

**Native geography / scale.** ADI is built and published at the Census **block group** level, as national percentile ranks 1-100. Note a correction to a common premise: the US has **~242,000 block groups** (Petterson's 2020 analytic frame: 242,335 total, 236,136 after inclusion criteria), *not* ~73,000. The ~73,000 figure is the count of census **tracts**. Source: https://pmc.ncbi.nlm.nih.gov/articles/PMC10986280/

**Petterson 2023 critique.** Stephen Petterson, "Deciphering the Neighborhood Atlas Area Deprivation Index: the consequences of not standardizing," *Health Affairs Scholar* 1(5):qxad063, Nov 2023. DOI 10.1093/haschl/qxad063.
- Because the ADI does not standardize its inputs, dollar-scale variables dominate: "Just 2 measures - median income and median home value - account for 98.8% (34.7% + 64.1%) of the unstandardized ADI score." Median home value alone ≈ 64%.
- The published Atlas ADI *is* effectively the unstandardized index ("correlation greater than 0.9999" with Petterson's unstandardized reconstruction).
- **ACS margin-of-error point (the reliability critique):** in block groups in the lowest decile of home ownership, "the mean margin of error for median home values is an astoundingly high $105,418." A variable that drives ~64% of the score is, in many block groups, estimated with an MOE larger than the value itself.
Source: https://academic.oup.com/healthaffairsscholar/article/1/5/qxad063/7342005 · https://pmc.ncbi.nlm.nih.gov/articles/PMC10986280/

**Corroborating peer review.**
- Hannan et al., "The Neighborhood Atlas ADI ... An Overemphasis On Home Value," *Health Affairs* 42(5):702-709, 2023 (DOI 10.1377/hlthaff.2022.01406): in New York State, downstate areas rank as *more* deprived on 13 of 17 non-dollar variables yet *less* deprived overall, because home value dominates.
- Rehkopf & Phillips, *Health Affairs* 42(5):710-711, 2023 (DOI 10.1377/hlthaff.2023.00282): lack of standardization "potentially further disadvantages already disadvantaged communities"; recommends a revised ADI.

**Takeaway for the access composite:** ADI's own authors refuse to endorse ZIP/ZCTA linkage, and the most-cited critique of ADI is *exactly* an ACS-MOE-at-small-area-level reliability argument. Both apply directly to a ZCTA composite.

---

## 2. CDC/ATSDR SVI and uncertainty

**SVI does not propagate ACS error into its rankings, and publishes no confidence intervals or reliability flags on the composite.** (High confidence - the full SVI 2022 Documentation was read end-to-end.)

- The ranking pipeline (EP → EPL → SPL → RPL) operates on **point-estimate percentages only**. ACS margins of error are computed and stored as separate `M_`/`MP_` columns (with correct Census propagation formulas), but they are *never* fed into the percentile ranks. There is no `M_RPL_THEMES` or any CI on a ranking.
- The strongest uncertainty statement in the entire document just *points the user back to the inputs*: "It is important to consider how sampling errors may impact conclusions in any analysis." That is a disclaimer on the input estimates, not a CI on the index.
- The only "flag" is **substantive, not reliability-based**: "Tracts in the top 10%, or the 90th percentile, are given a flag value of 1 to indicate high social vulnerability." This flags high vulnerability, not high uncertainty.
- SVI gives **no test for whether two tracts differ meaningfully.** It does warn about *scale dependence* (US vs. state databases produce different ranks for the same tract) - an internal-consistency caveat, not a sampling-error one.
Source: https://www.atsdr.cdc.gov/place-health/media/pdfs/2024/10/SVI2022Documentation.pdf

**Academic critique of this gap.**
- Tate (2012), "Social vulnerability indices: a comparative assessment using uncertainty and sensitivity analysis," *Natural Hazards* 63:325-347 (DOI 10.1007/s11069-012-0152-2): Monte Carlo simulation turns each unit's "discrete output vulnerability rank ... into a frequency distribution," concluding "the reliability of index rankings is questionable." This is precisely the treatment SVI omits.
- Spielman et al. (2020), *Natural Hazards* 100:417-436 (DOI 10.1007/s11069-019-03820-z): "multiple SoVI-based measurements of the vulnerability of the same place, using the same data, can yield strikingly different results." (Targets Cutter's SoVI, adjacent to CDC SVI - treat as family-level critique.)

**Takeaway:** The most widely-used federal small-area vulnerability index publishes *zero* uncertainty machinery on its ranks. A new index that does so exceeds the de facto government standard - but the *literature* (Tate, Spielman) treats SVI's omission as a known deficiency, not a model to copy.

---

## 3. ACS small-area reliability (Spielman / Folch / Nagle)

**Small-area ACS estimates are unreliable in a large share of areas, and the error is spatially structured (does not cancel out).**

**Core findings (verified verbatim):**
- Spielman, Folch & Nagle (2014), "Patterns and causes of uncertainty in the American Community Survey," *Applied Geography* 46:147-157 (DOI 10.1016/j.apgeog.2013.11.002): "The margins of error on ACS census tract-level data are on average **75 percent larger** than those of the corresponding 2000 long-form estimate." For African-American median household income, "more than 75 percent of all census tracts ... fail to meet the NRC 'reasonable' standard of precision."
- Spielman & Folch (2015), *PLOS ONE* (DOI 10.1371/journal.pone.0115626): "in over **72% of census tracts**, the estimated number of children under 5 in poverty has a margin of error greater than the estimate." Example: a tract with "169 children under 5 in poverty ± 174 children."
- Folch, Arribas-Bel, Koschinsky & Spielman (2016), "Spatial Variation in the Quality of American Community Survey Estimates," *Demography* 53(5):1535-1554 (DOI 10.1007/s13524-016-0499-1): uncertainty is **spatially patterned** - higher in low-income areas and urban cores, lower in suburbs, differing North vs. South. **Critical for an index: the error is correlated with the very deprivation the index measures, so it does not average away.**

**CV / reliability threshold conventions (authoritative):**

| Source | Threshold for "unreliable" | Notes |
|---|---|---|
| **ESRI** (ArcGIS) | CV ≤12% high reliability; 12-40% moderate; **>40% low** | Most-cited operational bands |
| **NRC** | CV ≤10-12% = "reasonable" precision | Strict standard |
| **NCHS legacy** (Healthy People 2010) | **RSE > 30% → suppress** | The "CV>30%" convention you recalled - real but *historical* |
| **NCHS current** (Series 2 No. 175, 2017) | CI-width based (Korn-Graubard), suppress if n<30 | Moved *away* from RSE>30% |
| **County Health Rankings** | **RSE > 20% → flag as unreliable** | Operational cutoff in production today |

The Census Bureau's "Compass" handbook teaches users to compute CV/MOE but mandates no single cutoff; the 12/40 bands are ESRI's, 30% is NCHS legacy, 20% is CHR's.

**Composite-index danger (Spielman & Singleton 2015, *Annals AAG* 105(5)):** few classification methods handle uncertain inputs; zero estimates break MOE handling; and while combining indicators "mitigates some" single-indicator noise, the spatially-structured error means it does *not* cancel. Their recommended fix is **regionalization** - merging small areas into data-driven regions with larger effective sample size and smaller MOE.

**Takeaway:** For a ZCTA index built on ~50 ACS/PLACES measures, expect a meaningful fraction of inputs (especially count-type, subgroup, and poverty variables) to be unreliable in many ZCTAs, and expect that unreliability to concentrate in exactly the high-deprivation areas the index is meant to flag. Use ESRI's >40% (or CHR's RSE>20%) to flag/suppress inputs; cite NRC 10-12% for the strict bar.

---

## 4. Best practice for reporting uncertainty in a ranking

**The gold standard is confidence intervals on the RANKS, derived by Monte Carlo over the discretionary modeling choices.**

- Saisana, Saltelli & Tarantola (2005), "Uncertainty and sensitivity analysis techniques as tools for the quality assessment of composite indicators," *J. Royal Statistical Society A* 168(2):307-323 (DOI 10.1111/j.1467-985X.2005.00350.x): proposes uncertainty + sensitivity analysis specifically for "an assessment of the reliability of countries' rankings." (Note: published title says "quality assessment," not "analysis and validation.")
- OECD/JRC *Handbook on Constructing Composite Indicators* (2008, ISBN 978-92-64-04345-9) makes this an explicit, **required** step (Step 9 of 10: "Robustness and sensitivity") and spells out the reporting format:
  - Vary normalization, weighting, aggregation, indicator inclusion/exclusion, imputation in a Monte Carlo loop; "quantify the overall uncertainty in country rankings as a result of the uncertainties in the model input."
  - **Report each unit as median rank + 5th-95th percentile interval**, not a point rank: "the median (black mark) and the corresponding 5th and 95th percentiles (bounds) of the distribution."
  - Robustness is judged by interval width; if intervals are wide, "it would have to be concluded that [the index] is not a robust measure."
  - **The middle of the table is least reliable:** "The countries with the highest total variance in ranks are the middle-of-the-table countries, while the leaders and laggards ... have low total variance."
Source: https://www.oecd.org/content/dam/oecd/en/publications/reports/2008/08/handbook-on-constructing-composite-indicators-methodology-and-user-guide_g1gh9301/9789264043466-en.pdf

**"Is this difference real?" - the operational tests:**

| Approach | Rule | Where used |
|---|---|---|
| Overlapping CIs on the measure | Two areas differ only if their 95% CIs don't overlap | County Health Rankings |
| Rank-interval overlap (Monte Carlo) | Two areas not distinguishable if 5th-95th rank intervals overlap | OECD Handbook |
| Minimum Detectable Difference (MDD) | Smallest difference that would be significant given variance/n | Regulatory stats (EFSA, Mair 2020) |

**County Health Rankings - the closest production analogue:**
- Reports 95% CIs on the underlying **measures** (not the ranks): "Where possible, we provide the margins of error (95% confidence intervals) for our measure values."
- Operationalizes overlap: "When the error margin ranges ... overlap between two places, we can be less confident that the true population experiences ... are different."
- Flags unreliable inputs at **RSE > 20%**.
- Explicitly warns against over-reading small rank gaps: "close ranks are not necessarily statistically significantly different ... the top-ranked county (#1) is not necessarily significantly healthier than the second-ranked county (#2)"; "rankings ... should be used as a starting point, not an end point."
- **Does NOT publish CIs on the ranks themselves** - an acknowledged gap. Independent work ("How Reliable Are County and Regional Health Rankings?", PMC8335645) estimated rank CIs and found "rank estimates remained imprecise for many counties," widest for middle-ranked and small-population counties, with even top-decile counties re-identified only ~66% of the time.
- As of 2024, CHR **dropped numeric ranks entirely** in favor of 10 grouped "Health Groups" - an institutional admission that precise ranks over-promise.
Sources: http://www.countyhealthrankings.org/ranking-methods · https://pmc.ncbi.nlm.nih.gov/articles/PMC4415342/ · https://pmc.ncbi.nlm.nih.gov/articles/PMC8335645/

**Takeaway:** The mandatory machinery is (1) a Monte Carlo sensitivity analysis over modeling choices producing a **rank distribution** per ZCTA, (2) reporting median rank + 5th-95th interval, and (3) treating overlapping intervals as "not distinguishable." The middle of your distribution will be the least reliable.

---

## 5. Dimensionality - is a ~60% PC1 a problem?

**A dominant first component is generally a feature (evidence of a coherent common gradient), not a defect - but do not over-claim it as proof of uni-dimensionality.**

From the OECD/JRC Handbook (Section 4.3, Box 6):
- PC1 capturing the most variance is the *design objective* of PCA: "the first principal component accounts for the maximum possible proportion of the variance." A ~60% PC1 is strong - well above the Handbook's own worked example (TAI PC1 = 41.9%).
- **Cronbach's alpha** measures internal consistency; threshold "Nunnally (1978) suggests 0.7 as an acceptable reliability threshold" (some accept 0.6, some demand 0.8).
- **Crucial caveat:** "strictly speaking c-alpha is not a measure of uni-dimensionality. A set of individual indicators can have a high alpha and still be multi-dimensional." Alpha (reliability) and PCA (dimensional structure) measure *different* things.
- Factor-retention rules: Kaiser (drop eigenvalue <1.0), Joliffe (<0.70), scree plot, or "keeping enough factors to account for 90% (sometimes 80%) of the variation." There is **no official "PC1 must explain X%" coherence threshold.**

**The debate, with the cautionary tale:**
- *Defense:* Townsend, Carstairs, and the English IMD are deliberately built as single composite scores because deprivation is treated as one gradient to rank/target. If your goal is to rank areas on a general access-gap gradient, one dominant component is exactly what you want.
- *Critique:* Deas, Robson, Wong & Bradford (2003), *Environment and Planning C*, argue a single composite masks the multidimensional nature of deprivation.
- *The cautionary tale (ADI):* Petterson 2023 shows ADI collapses to ~2 raw variables (98.8% of the score), "certainly not the advertised multidimensional measure." And the ADI-3 revision (*Health Services and Outcomes Research Methodology* 2021, DOI 10.1007/s10742-021-00248-6) found the "prior-assumed unidimensional ADI measure fails standard tests of construct validity," revealing three distinct factors.

**Takeaway:** A ~60% PC1 is fine and arguably desirable for an access-*gap* index whose purpose is to rank areas along one disadvantage gradient - *as long as* you frame it honestly as "a strong common gradient" and don't market three independent dimensions that empirically collapse into one. The honest framing: report PC1 % variance, Cronbach's alpha (target ≥0.7), and acknowledge that alpha + dominant PC1 demonstrate *coherence/reliability*, not that your three weighted dimensions are statistically independent. If the three dimensions don't separate, either own the unidimensionality or do an ADI-3-style factor decomposition and report dimensions separately.

---

## 6. Salience / communication to lay users

**Every leading index bins into coarse categories, uses directional plain-language labels, sequential color, and part-to-whole framing - and pairs the rank with action content.**

- **ADI:** dual presentation - national **percentile 1-100** and state **decile 1-10**, both directional ("1 = least disadvantaged, 100/10 = most disadvantaged"). Source: https://sparkmap.org/data-info/area-deprivation-index/
- **SVI:** overall percentile **0-1**, with the part-to-whole explanation "a ranking of 0.85 signifies that 85% of tracts ... are less vulnerable," plus a binary **90th-percentile flag** for targeting.
- **County Health Rankings (2024 redesign):** dropped exact ranks for **10 color-shaded Health Groups**, a least-to-most-healthy continuum dot plot, and per-county "Areas of Strength / Areas to Explore" paired with "What Works for Health" evidence-based strategies - i.e., rank + action.
- **Design research:** frequency / part-to-whole framing beats abstract probability for low-numeracy users (SVI's "85% of tracts" phrasing is the model); sequential colorblind-safe choropleths with ≤7-10 classes (darker = higher); plain-language labels matter most for unfamiliar audiences; predefined categories can mislead if thresholds aren't explained. Production indices generally do *not* display per-area CIs - a recognized gap.

**Takeaway:** Make the ZCTA rank actionable by (a) binning to deciles/quartiles rather than showing raw percentile precision the data can't support, (b) directional plain-language labels, (c) "X% of ZIP areas have better access than this one" framing, (d) sequential colorblind-safe maps, and (e) pairing each area with concrete drivers/actions. Showing uncertainty (even a simple reliability shade or "low confidence" overlay) would *exceed* what ADI/SVI/CHR display and is a differentiator.

---

## Synthesis: what this means for a ZCTA access composite

**Can you claim two ZIPs are comparable?** Only with explicit, quantified caveats. The field's verdict is consistent and adverse on three fronts:

1. **Geography.** ADI's own authors say ZIP/ZCTA linkage is *not validated* and adds error, worst where poverty abuts wealth. ZCTA is not a census unit; it averages heterogeneous populations. You inherit this problem directly.
2. **Input reliability.** ACS small-area estimates are unreliable in a large share of areas (MOE > estimate in 72%+ of tracts for some variables; tract MOEs 75% larger than the old long form), and the error is *spatially correlated with deprivation* - so it concentrates in exactly the high-access-gap ZCTAs you most want to trust, and does not cancel in a composite.
3. **Rank precision.** Even well-funded indices (CHR) warn that adjacent ranks are not statistically distinguishable, and CHR dropped exact ranks in 2024 for this reason. The middle of any ranking is the least reliable (OECD).

So: **two ZCTAs are "comparable" only when their rank uncertainty intervals do not overlap.** A bare statement that ZIP A ranks above ZIP B is not defensible; A's interval clearing B's interval is.

**Mandatory uncertainty machinery (do not ship without):**
- **Monte Carlo sensitivity analysis** over your discretionary choices (weights across the 3 dimensions, normalization, aggregation, indicator inclusion) → a **rank distribution per ZCTA**, reported as **median rank + 5th-95th percentile interval** (Saisana 2005; OECD 2008). This is the single most important addition and is what the production indices lack.
- **Input reliability filtering:** flag/suppress ACS inputs with RSE>20% (CHR) or CV>40% (ESRI); propagate or at least report the dominant MOEs.
- **A "not distinguishable" rule:** overlapping rank intervals (or overlapping measure CIs) = not meaningfully different. State it on the product.
- **Binned presentation** (deciles/quartiles), not raw percentile precision the data can't support.
- **Honest dimensionality framing:** report PC1 % variance and Cronbach's alpha; if ~60% PC1, present as one coherent access-gap gradient, don't over-claim three independent dimensions.

**Nice-to-have (differentiators):**
- Per-ZCTA reliability shading / "low confidence" map overlay (exceeds ADI/SVI/CHR).
- Regionalization of the most uncertain ZCTAs (Spielman & Folch 2015) to shrink MOEs.
- Pairing ranks with drivers/actions (CHR's "What Works") and part-to-whole framing (SVI's "X% of areas are better").

**The opportunity:** ADI, SVI, and CHR all *publish ranks without rank-level confidence intervals*. The literature (Saisana, Saltelli, Tate, the CHR reliability critiques) treats this as a known deficiency. An access-gap index that reports rank intervals and an explicit "not distinguishable" rule would be more methodologically honest than the federal standards it competes with - at the cost of having to tell users that, for many ZCTA pairs, the honest answer is "we can't tell these apart."

---

### Source list
- Neighborhood Atlas FAQ: https://www.neighborhoodatlas.medicine.wisc.edu/faq
- Petterson 2023 (Health Affairs Scholar): https://academic.oup.com/healthaffairsscholar/article/1/5/qxad063/7342005 · https://pmc.ncbi.nlm.nih.gov/articles/PMC10986280/
- Hannan 2023: DOI 10.1377/hlthaff.2022.01406 · Rehkopf & Phillips 2023: DOI 10.1377/hlthaff.2023.00282
- CDC/ATSDR SVI 2022 Documentation: https://www.atsdr.cdc.gov/place-health/media/pdfs/2024/10/SVI2022Documentation.pdf
- Tate 2012 (Natural Hazards): https://link.springer.com/article/10.1007/s11069-012-0152-2
- Spielman et al. 2020 (Natural Hazards): https://link.springer.com/article/10.1007/s11069-019-03820-z
- Spielman, Folch & Nagle 2014 (Applied Geography): https://pmc.ncbi.nlm.nih.gov/articles/PMC4232960/
- Folch et al. 2016 (Demography): https://link.springer.com/article/10.1007/s13524-016-0499-1
- Spielman & Folch 2015 (PLOS ONE): https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0115626
- ESRI ACS reliability bands: https://www.esri.com/arcgis-blog/products/bus-analyst/analytics/examine-data-accuracy-in-arcgis-business-analyst-using-acs-reliability-estimates
- NCHS Data Presentation Standards (2017): https://www.cdc.gov/nchs/data/series/sr_02/sr02_175.pdf
- Saisana, Saltelli & Tarantola 2005 (JRSS A): https://rss.onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-985X.2005.00350.x
- OECD/JRC Handbook 2008: https://www.oecd.org/content/dam/oecd/en/publications/reports/2008/08/handbook-on-constructing-composite-indicators-methodology-and-user-guide_g1gh9301/9789264043466-en.pdf
- County Health Rankings methods: http://www.countyhealthrankings.org/ranking-methods · https://pmc.ncbi.nlm.nih.gov/articles/PMC4415342/
- CHR reliability critique: https://pmc.ncbi.nlm.nih.gov/articles/PMC8335645/
- ADI-3: https://link.springer.com/article/10.1007/s10742-021-00248-6
- Deas & Robson IMD critique: https://journals.sagepub.com/doi/10.1068/c0240
- ADI presentation (SparkMap): https://sparkmap.org/data-info/area-deprivation-index/

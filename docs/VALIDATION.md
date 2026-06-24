# Validation - how we know the index is right (and where it isn't)

How the Access Gap is checked against independent outcomes, what its real resolution is, and
the sub-county gate. Consolidates the former composite-evaluation, uncertainty-research, and
composite-enhancement notes. Decisions live in [DECISIONS.md](DECISIONS.md).

## 1. The outcomes and the anti-circularity rule

Validated against **6 independent outcomes** (CMS claims + NCHS vital records, **never**
BRFSS/PLACES): preventable (ACSC) hospitalizations, premature death, infant mortality, flu
vaccination, mammography (all county, from County Health Rankings), and USALEEP life expectancy
(census-tract, 2010-2015). Outcomes **validate**; they never enter the composite (the County
Health Rankings stance: factors ranked separately from outcomes).

**Cardinal rule:** flu and mammography are healthcare-*engagement* measures *and* outcomes, so
any "did you engage with care" input correlates with them mechanically. **Judge new inputs
against the death-records / ACSC outcomes, never the engagement ones.** This caught the C1
realized-utilization negative ([DECISIONS](DECISIONS.md)).

**Gate harness:** `pipeline.diagnostics` (north star: composite mean-r FULL vs drop-each-
dimension; sub-score mean\|r\|; split-half) + `pipeline.verify_bands` (rank-band gates).
Current: FULL **0.492**, drop_care_access **0.467**, composite **0.495**, split-half **0.955**.

## 2. Why care access reads modest - a category error, not a bug

Tuning a *gap* against an *all-cause* outcome starves care access by construction:

| Score form vs (−life expectancy) | r |
|---|---|
| health_need alone | **+0.606** |
| additive 35/30/35 composite | +0.531 |
| partial r(−LE, care_access \| need, vuln) | **−0.074** (~zero) |

Need alone beats every composite; ridge/regularization cannot recover a predictor whose
*partial* correlation is ~0. This is definitional: area all-cause mortality is overwhelmingly
disease/behavior burden; the ~10-20% attributable to clinical care is swamped. The field's
outcome-anchored access indices therefore validate against **amenable/treatable mortality**
(IHME HAQ) and **ACSC hospitalizations** (Robert Graham Center SDI), not all-cause mortality.
Care access is kept in the composite by deliberate construct choice (it is the actionable
lever, as County Health Rankings weights clinical care 20%), not because it predicts mortality.

**Implication:** the standard gate is need-dominated, so it can only ever show care access as
marginal. The two fixes are the **amenable-mortality** anchor (§4) and **sub-county** validation
(§3) - both change what the ruler can see, rather than adding inputs.

## 3. Sub-county validation - the county-resolution blind spot (`pipeline.validate_subcounty`)

Every access-sensitive outcome is **county-level**, yet **25% of the composite's variance is
within-county** - structurally invisible to the standard gate. So any ZCTA-resolution access
measure cannot be rewarded by a county-flat outcome; the "spatial-signal ceiling" was declared
at county resolution.

**Instrument:** NY SPARCS PQI_90 (overall ACSC composite) by patient ZIP - free Socrata
`5q8c-d6xq`, **observed** (not modeled), 2009-2023. Pooled 2019-2023 → 1,265 ZCTAs / 61
counties. The **within-county** correlation (county mean removed both sides) is the test county
outcomes cannot do; **O/E** = observed/expected is the risk-adjusted (age/sex) form.

| within-county O/E | result | reading |
|---|---|---|
| `access_gap_score` | **+0.48** | the composite resolves real sub-county signal - the ZCTA tool is validated, not a county tool in disguise |
| `care_access` | **+0.31** | its best showing anywhere (vs ~0.27 on any county outcome) - but need still dominates |
| `health_need` | +0.48 | dominates even at sub-county ACSC resolution → the care-access ceiling is **largely real** |
| `shortage_designation` | **−0.00** | county-max HPSA has zero sub-county resolution (reopens the sub-county-HPSA negative) |
| `safetynet_access` | **−0.11** | **wrong-signed within-county** - the FQHC desert×poverty form isn't confound-free at sub-county scale |

**Robustness (NY ex-NYC, 1092 ZCTAs):** both key findings hold - `safetynet` −0.11 (all 3
subsamples −0.11 to −0.13), `hpsa_tractonly` +0.285. `provider_supply` flips −0.16 (NYC) → +0.09
(ex-NYC), the textbook urbanicity confound. A tract-confined HPSA carries +0.275 raw → **+0.089
partial** within-county (small, below ship bar, but nonzero where county-max gives zero).

**National confirmation (USALEEP, `--national`):** NY's ACSC is one state, so the findings are
re-tested nationally against USALEEP life expectancy (tract→ZCTA, all states, independent death
records - need-dominated, but the only *national* sub-county outcome). **21,244 ZCTAs / 2,208
counties**, within-county: `access_gap_score` **+0.583**, `care_access` +0.393, `shortage_
designation` **+0.000**, `safetynet_access` **−0.072**. So the composite resolves sub-county
signal *nationally*, and both structural negatives hold beyond NY. The `safetynet_access`
wrong-sign is wrong-signed within-county in **85% of states** (median −0.084) - a national
property, not an NY/urban artifact. Two independent outcomes (NY ACSC claims + national USALEEP
mortality), same conclusion. *No second open-data ACSC state was needed: MD is county-level, CA
restricted, and only NY publishes statewide ZIP ACSC - USALEEP gives the national check instead.*

**Verdict:** the ceiling is **soft, not hard** - real sub-county signal was hiding below county
resolution - but the magnitude is modest, so the need-dominated conclusion holds.

**The `safetynet_access` sub-score is resolution-dependent (open decision).** It is correctly
signed *between* counties (+0.126 pooled; FQHC deserts genuinely flag underserved rural counties)
but wrong-signed *within* counties (FQHC-distance tracks suburban-ness, not need). Removing it
from the composite is a clean tradeoff: composite within-county +0.583→**+0.601** (national) and
care_access NY within-O/E +0.305→**+0.388**, at the cost of a tiny county-level loss (care_access
mean-r 0.380→0.370; composite 0.504→0.503). Because the tool is **ZCTA-native**, the sub-county
gain arguably outweighs the county loss - but it touches shipped scoring and slightly regresses
the historical county gate, so it is a **judgment call left to the maintainer**, not auto-applied.
Do *not* re-tune the desert×poverty form against the within-county metric (overfitting); the
honest options are keep (county-helpful) or remove (sub-county-helpful).

### Is supply too spatial? The 5 A's coverage + signal audit

Decomposing `care_access` by Penchansky-Thomas access dimension, with county mean|r| vs
sub-county (within-county, national USALEEP) signal:

| care sub-score | 5-A dimension | county mean\|r\| | **within-county r** |
|---|---|---|---|
| provider_supply (2SFCA, spatial) | Availability | 0.263 | **0.076** |
| shortage_designation (HPSA) | Availability | 0.206 | **0.000** |
| insurance | Affordability | 0.313 | **0.474** |
| preventive_use (checkups/screens) | realized access (net of all A's) | 0.200 | **0.464** |
| safetynet (FQHC, **unscored**) | Acceptability proxy | 0.201 | −0.072 |

**Finding: the two *spatial* Availability sub-scores carry ~zero sub-county signal
(provider_supply 0.076, HPSA 0.000), while the *non-spatial* ones carry nearly all of it
(insurance 0.474, preventive_use 0.464).** The most-engineered piece (spatial supply) is the
least productive at the resolution the tool runs. (Enabling A's in social_vulnerability behave
the same: socioeconomic/Affordability within-county +0.524, digital/telehealth +0.356.)

**5 A's coverage (updated):** Availability over-built + weak (spatial); **Affordability strong and
now deepened** - uninsured (coverage) **+ medical-debt burden** (the under-insured / cost-burden
barrier, the first new scored barrier to survive partial-r at +0.27, mean|r| 0.40); Accessibility
decent on the *demand* side (no-vehicle, telehealth), weak on the *supply* side; **Accommodation
absent** (FQHC-hours flat - no signal); **Acceptability absent** (FQHC proxy unscored; real
Medicaid-acceptance data is orthogonal but need-endogenous/unsigned - DECISIONS). **`preventive_use`
was REMOVED from the composite** (it is *realized utilization* - a mediator/Donabedian "process",
not a barrier; `mammouse` was criterion-contaminated with the mammography validator). Removing the
mediator *raised* clean-r (0.501→0.516); adding the medical-debt barrier raised it further (→0.547).
*Implication / lesson: the productive frontier for care_access was not more geography and not
realized-use proxies (mediators) - it was a genuine upstream **affordability** barrier (medical
debt). Spatial supply stays the weakest, least-productive piece.*

## 4. Amenable mortality - the gold-standard anchor (wired, not yet pulled)

`build_amenable.py` encodes the 80-code OECD/Eurostat treatable ICD-10 list and converts a CDC
WONDER county export into the `amenable_mortality_county.csv` that `validate.py` already merges.
It is the one outcome that can legitimately weight care access, and the frontier outcome for a
future frontier-gap construct. **Blocked only on the manual WONDER pull** - county data is not
headlessly fetchable (the WONDER API is national-only). Expected impact is tempered by §3: even
a clean sub-county access outcome left care access modest.

## 5. Comparability and resolution - it's a gradient, not a 33k-rank leaderboard

OECD/JRC evaluation of the live build:

| Test | Result | Reading |
|---|---|---|
| Internal reliability (split-half) | **0.95** | strong; the ~50 measures cohere |
| External validity | r ≈ +0.52 LE, +0.49 premature death, +0.40 infant mort | moderate, correctly signed, ≈ SDI's published validation |
| Plausible-weight rank wobble | ~±6 pts | reasonable weightings barely move ranks (Spearman 0.999) |
| Measurement noise (split-half SE) | ≈2.6 pts; min detectable gap ≈7 | two ZIPs <7 pts apart are within noise |
| Dimensionality | PC1 = 46%; corr(composite, PC1) 0.94 | ~one "general deprivation" gradient under the hood |

**Combined: two ZIPs are reliably different only by ~10-15 percentile points ⇒ ~7-10 tiers, not
33,181 ranks.** The UI leads with **deciles + a 5-95 rank band**, not an integer leaderboard.

**Why this is honest where the field isn't:** ADI/SVI/CHR publish ranks with **no rank-level
confidence interval** - the literature (Saisana/Saltelli/Tarantola; OECD Handbook Step 9) calls
that a deficiency. ACS small-area error is large and *spatially structured* (tract MOEs ~75%
larger than the long form; MOE > estimate in 72%+ of tracts for some counts; Spielman/Folch/
Nagle), concentrated in the poor ZCTAs the index cares about, so it does **not** cancel in a
composite. ADI's own authors say ZIP/ZCTA linkage is "not validated." We ship the rank bands and
an explicit "can't tell these apart" rule the federal indices omit, and shrink the noisy inputs
(Fay-Herriot, §[DECISIONS](DECISIONS.md)).

Key sources: IHME HAQ (GBD 2016, PMC5986687); Robert Graham Center SDI (Butler 2013); OECD/JRC
Handbook 2008; Saisana/Saltelli/Tarantola 2005; Spielman/Folch/Nagle 2014 (Applied Geography);
Petterson 2023 (ADI critique, Health Affairs Scholar); CHR ranking-methods.

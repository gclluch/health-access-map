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
Current: FULL **0.498**, drop_care_access **0.452**, composite **0.503**, split-half **0.953**.

### 1a. Error bars on the gate (`pipeline.bootstrap_gate`) - the margins are no longer naked points

`diagnostics` reports POINT estimates of correlation differences and historically shipped or
killed inputs on margins as small as +0.04 with no uncertainty attached. `pipeline.bootstrap_gate`
puts a 95% CI on every margin, with two deliberate choices that make the interval honest, not
flattering:

- **Cluster bootstrap over county** (`state|county_name`), not ZCTA rows (Efron & Tibshirani
  1993; the clustered/block form follows Cameron, Gelbach & Miller 2008). Five of the six
  outcomes are county-level (CHR), so resampling 33k ZCTAs as if independent treats one county's
  ~11 ZCTAs as 11 independent looks at a single outcome value and understates uncertainty by
  ~√(zctas/county). Resampling whole counties (≈3,225 clusters) respects the true effective N.
- **Paired** FULL-vs-drop differences (same resample each replicate), so the margin CI is the
  distribution of the *paired* difference - far tighter and stricter than differencing two
  independent CIs.

Live result (1,000 replicates, `data/processed/gate_ci.json`):

| margin (FULL − drop) | point | 95% CI | reading |
|---|---|---|---|
| drop **care_access** | **+0.046** | **[0.041, 0.052]** | adds signal in **100%** of resamples - robustly real |
| drop health_need | +0.025 | [0.02, 0.03] | adds signal, robust |
| drop **social_vulnerability** | **−0.016** | **[−0.02, −0.012]** | **mildly redundant** - dropping it *raises* agreement (its variance is largely re-counted by need/access; CI excludes 0) |

So the headline care-access decision survives the stricter ruler (the lever the whole project
chased is not noise). The new finding the point estimate hid: social vulnerability is slightly
*net-negative* on the county-outcome gate - consistent with it being the most collinear
dimension (need↔vulnerability 0.73). It is kept in the composite by construct choice (the 5 A's
enabling axis; it carries real *within-county* signal, +0.568, §3) - but the gate no longer
pretends it adds county-level outcome agreement. **Run `python -m pipeline.bootstrap_gate` after
any scoring change and ship only if the relevant margin CI excludes 0.**

**The headline point r itself is a ZCTA-broadcast number - read its precision, not its decimals.**
The `diagnostics` mean-r (composite **0.503**, etc.) correlates ~33k ZCTAs against outcomes that
are county-level for 5 of 6, broadcast to every ZCTA - so the **effective N is the county count
(~3,225), not the row count**. This does *not* inflate the point magnitude (within-county composite
variance has no outcome to track, so the row-level r is if anything mildly *attenuated*: the
matched-resolution **county-collapsed mean-r is 0.547**, now reported alongside it by
`diagnostics`). What it inflates is **precision** - which is exactly why every ship/kill margin is
gated on the **cluster bootstrap** above (effective N ≈ county count), never on the naked row-level
point. Treat the headline r as good to ~one decimal, with the honest interval coming from
`bootstrap_gate`, not from 33k-row significance.

### 1b. The index is ~1.6 effective dimensions

At the dimension level the correlation matrix (need/vulnerability/access) has eigenvalues
[2.30, 0.44, 0.26]: **PC1 = 76%** of the joint variance, **participation ratio ≈ 1.6 effective
dimensions** (the inverse participation ratio - IPR - a standard spectral measure of effective
dimensionality). The three-dimension framing is a *construct* decomposition (the 5 A's), not a claim
of three statistically independent axes - which is exactly why re-weighting them barely moves
ranks (Spearman ~0.999, ~±6 pts) and why the sliders are framed in-product as a sensitivity
probe, not a control that rewrites the map. Reported live in `provenance.json`
(`score.dimension_correlations`, `score.effective_dimensions`).

**The actionable response** is the **access-beyond-deprivation lens** (`care_access_resid_pctile`):
care_access residualized on need + social_vulnerability and re-ranked, so the map can show the
*structural* access disadvantage **net of** the deprivation gradient. It is near-orthogonal to its
predictors (0.05) by construction, yet the residual still tracks low life expectancy at **+0.135**
(vs +0.476 for raw care_access) - and, against the access-sensitive ruler, tracks **treatable
(amenable) mortality at +0.331** (§4) - i.e. the part of barriers-to-care *not* explained by poverty
is independently outcome-relevant, and markedly more so for the deaths care can actually prevent. A
selectable lens (Color-by / Rankings), not in the composite; recorded in `provenance.json`
`score.access_beyond_deprivation`.

### 1c. Selection bias - the margins are not corrected for multiple comparisons

The input-selection program (the `DECISIONS.md` ledger) tested **dozens of candidate measures and
sub-scores against the same 6 outcomes**, keeping the ones that cleared a thin bar (ship margins as
small as **+0.04**, partial-r ~**+0.27**). This is a garden-of-forking-paths search, and our
statistics do not correct for it:

- The `bootstrap_gate` CIs quantify **sampling noise conditional on the chosen model**. They are
  *not* selection-adjusted - they say nothing about the fact that the winning input was picked from
  many tried against the same outcomes.
- So the surviving effect sizes are **upward-biased** (winner's curse) and the thinnest margins
  (e.g. care-access's **+0.046**, or `medical_debt` clearing partial-r where ~a dozen others did
  not) sit within the noise of the *selection* process, not just the *sampling* process. A +0.04
  margin that "excludes 0" in a paired cluster bootstrap can still be a multiple-comparisons
  artifact.
- Mitigations actually in place (partial honesty, not a fix): the **anti-circularity rule** (judge
  against death-records/ACSC, never flu/mammography) culls the most obvious false positives; the
  **partial-r** bar is stricter than raw-r; and rejected probes are logged so they are not silently
  re-tried. None of these is a multiplicity correction.
- **How to read it:** treat the *direction and rough magnitude* of a surviving input as the
  reliable claim, and the *exact decimal margin* as soft. The honest test for any thin winner is
  **out-of-sample / out-of-outcome replication** - which the amenable-mortality anchor (§4) and the
  sub-county gate (§3) provide, since they change the *ruler* rather than re-fitting against the same
  six outcomes the inputs were selected on. **This test has now been run (§4): care_access replicates
  on treatable mortality at partial r +0.395 - an outcome no input was ever selected against.** So the
  central care-access claim is no longer a within-selection margin; it survives the cleanest available
  out-of-outcome check.
- **The individual sub-scores have now been re-tested too (§4a, BACKLOG B2).** Each *scored* care
  sub-score was put through the same out-of-outcome ruler - partial r vs amenable mortality net of
  need + vulnerability, with a **Benjamini-Hochberg FDR correction across the four candidates** (the
  multiplicity fix §1c had been missing). **All four survive** at q<=0.05 with a CI excluding 0.
  Decisively, `medical_debt` - the margin §1c singled out as possibly a multiple-comparisons artifact
  (partial-r ~+0.27 vs the standard six) - posts the **strongest** independent partial r of the set
  (**+0.441**, q=0.000); `insurance` is the thinnest (**+0.042**, CI [+0.004,+0.082], q=0.014) but
  still clears. So the "thinnest sub-score margins remain selection-soft" caveat is now **retired by
  evidence**, not just asserted: the inputs corroborate on a ruler they were never selected against.

## 2. Why care access reads modest - a category error, not a bug

Tuning a *gap* against an *all-cause* outcome starves care access by construction:

| Score form vs (−life expectancy) | r |
|---|---|
| health_need alone | **+0.606** |
| additive 35/30/35 composite | +0.603 |
| partial r(−LE, care_access \| need, vuln) | **+0.125** (small) |

Need alone nearly matches the full composite; care access's *partial* correlation is **small
(+0.125)** - it carries a modest independent signal even net of need + vulnerability (consistent
with the access-beyond-deprivation lens, §1b, +0.135), but it is **swamped**, not zero. This is
definitional: area all-cause mortality is overwhelmingly disease/behavior burden; the ~10-20%
attributable to clinical care is a small slice. The field's outcome-anchored access indices
therefore validate against **amenable/treatable mortality** (IHME HAQ) and **ACSC
hospitalizations** (Robert Graham Center SDI), not all-cause mortality.
Care access is kept in the composite by deliberate construct choice (it is the actionable lever, as
County Health Rankings weights clinical care 20%) - and, **against the right outcome, it does predict
mortality**: see §4, where care_access's partial r jumps from **+0.125 (all-cause) to +0.395
(treatable)**. The "+0.125 small" above is not care access being weak; it is all-cause LE being the
wrong ruler - precisely the category error this section names.

**Implication:** the standard gate is need-dominated, so it can only ever show care access as
marginal. The two fixes - the **amenable-mortality** anchor (§4) and **sub-county** validation (§3) -
change what the ruler can see rather than adding inputs. **Both have now been run, and the
amenable anchor confirms it**: on the access-sensitive ruler care access is far from marginal
(partial +0.395; §4).

## 3. Sub-county validation - the county-resolution blind spot (`pipeline.validate_subcounty`)

> **Update (HPSA now tract-resolved).** `shortage_designation` (HPSA) was upgraded this build from a
> county-MAX broadcast to census-tract resolution (see `docs/SUBCOUNTY_PLAN.md`), lifting its
> within-county r from **0.000 to ~+0.20** and roughly doubling its outcome-validation signal
> (amenable mortality 0.25→0.49). The "5 A's" table below is corrected, but several later statements
> and computed tables in this section still describe HPSA as "county-constant / 0.000" - those
> **predate the fix** and are stale for HPSA only (`medical_debt` remains the one county-flat scored
> input). Re-run `validate_subcounty` to regenerate the computed tables (§6a, §6b) consistently.

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
| `access_gap_score` | **+0.50** | the composite resolves real sub-county signal - the ZCTA tool is validated, not a county tool in disguise |
| `care_access` | **+0.30** | its best showing anywhere (vs ~0.27 on any county outcome) - but need still dominates |
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
counties**, within-county: `access_gap_score` **+0.608**, `care_access` +0.409, `shortage_
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
mean-r 0.380→0.370; composite 0.504→0.503). *(These are the historical deltas measured when the
removal was decided, on the pre-Fay-Herriot-upgrade build; safetynet is already unscored in the
shipped model - the live national composite within-county is +0.608, above.)* Because the tool is **ZCTA-native**, the sub-county
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
| shortage_designation (HPSA, tract-resolved) | Availability | 0.206 | **+0.246** |
| insurance | Affordability | 0.322 | **0.477** |
| **medical_debt** (Urban Institute, **county-level**) | Affordability | **0.40** | **0.000** |
| preventive_use (checkups/screens) | realized access (net of all A's) | 0.200 | **0.464** |
| safetynet (FQHC, **unscored**) | Acceptability proxy | 0.201 | −0.072 |

**Finding: `provider_supply` (2SFCA) carries ~zero sub-county signal (0.076), while the non-spatial
sub-scores carry most of it (insurance 0.477, preventive_use 0.464). HPSA rose from 0.000 to ~+0.20
(authoritative `validate_subcounty` value +0.246) once it was resolved to the census-tract level
(this build) - the old county-MAX broadcast, not the
designation itself, was hiding its sub-county signal.** The most-engineered piece (spatial 2SFCA
supply) is still the least productive at the resolution the tool runs.

**One county-level scored barrier remains - an honest asymmetry.** After HPSA was resolved to
census tracts (this build), just one *scored* care sub-score is still a county-level input
broadcast county→ZCTA, so its within-county r is **0.000** by construction (`validate_subcounty`
auto-flags it): **`medical_debt`** (Urban Institute credit-bureau; no free sub-county release). It
is the affordability win celebrated in §1/§4 - its entire mean|r| 0.40 and **partial-r +0.27 are a
*county-resolution* result**; it contributes nothing at the tool's native ZCTA resolution. We keep
it *scored* on **construct grounds** (a real, credit-bureau, county-level barrier), not because it
resolves sub-county variance. The distinction from `safetynet` (which was *removed* from scoring)
is that county-flat is **signal-less within county, not wrong-signed** - harmless to carry, whereas
safetynet actively mis-ranked sub-county. A reader comparing two ZCTAs in the same county should
know `medical_debt` gives them the *same* value: the sub-county separation now comes from HPSA,
insurance, the spatial supply terms, and the need/vulnerability dimensions. (Enabling A's in social_vulnerability behave
the same: socioeconomic/Affordability within-county +0.562, digital/telehealth +0.356.)

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

## 4. Amenable mortality - the gold-standard anchor

> A CDC WONDER county export
> (OECD treatable causes, ages 0-74, **age-adjusted**, pooled 2016-2020; committed at
> `data/manual/wonder_amenable_county.txt`, 3,088 counties) is now built into `metrics.parquet`
> as `amenable_mortality` and gated. **Headline: care_access partial r(amenable | health_need,
> social_vulnerability) = +0.395, 95% CI [0.368, 0.43]** (cluster bootstrap over county). Against
> the access-sensitive ruler the field actually validates on, care access carries strong, robust
> signal *net of the entire deprivation gradient* - it was never marginal, just measured against
> the wrong outcome.

All-cause mortality is a *need* outcome, so the standard gate can only ever show care access as
marginal (§2). **Amenable (treatable) mortality** - deaths timely effective care should prevent
(OECD/Eurostat, ages 0-74) - is the access-sensitive ruler the field validates against. The result
(`bootstrap_gate.amenable_focus()`, 3,066 counties / 32,879 ZCTAs):

| care_access vs ... | partial r (\| need, vuln) | reading |
|---|---|---|
| all-cause life expectancy (§2) | **+0.125** | small - "swamped"; the category error |
| **amenable (treatable) mortality** | **+0.395**  CI [0.368, 0.43] | **strong** - tracks treatable death net of deprivation |

Every supporting number moves the same way:
- composite **FULL r vs amenable +0.660** (vs ~0.52 against the all-cause mix - the index tracks
  treatable death far better); care_access **raw r +0.612**; **marginal value +0.062** CI [0.055, 0.072]
  (vs +0.046 on the standard mix).
- the access-beyond-deprivation **residual lens** (care access net of need+vuln, §1b) tracks amenable
  at **+0.331** (vs +0.135 against LE) - the *structural* access signal is independently treatable-death-relevant.
- the **amenable-anchored empirical weights** (`weights.json`) give care_access **~29-31%** (NNLS 28.7%
  / corr-preset 31.2%, R²=0.607) vs ~21% against all-cause LE (R²=0.39): anchoring the data-driven
  weights to the *right* outcome restores care access to ≈ its conceptual default, and fits far better.

**This resolves the project's central question and confirms §2 was right** - care access wasn't
marginal, it was judged by a ruler that structurally can't see it. Swap to the access-sensitive
outcome and the partial-r **triples** (+0.125 → +0.395).

**Why this is among the strongest claims in the repo, not the weakest:**
- **Out-of-outcome replication.** Amenable mortality was **never** part of the input-selection search
  (§1c) - no measure was kept or killed against it. So it is a genuine out-of-sample test of the
  winner's-curse concern, *exactly* the honest check §1c asked for: the thin all-cause margins are
  corroborated by an outcome the inputs were never fitted to.
- **Not circular.** Amenable mortality is a death-records outcome; care_access is *barriers* (supply,
  insurance, debt), not engagement/utilization - the anti-circularity rule (§1) does not apply.

**Honest caveats (read before quoting the decimal):**
- **County resolution.** Treatable mortality is county-level (broadcast to ZCTA), so this validates
  the index *between* counties; it adds nothing at sub-county scale (§3 stays the only sub-county
  check). Effective N is the county count (~3,066) - which is why the focus uses the cluster bootstrap,
  not the 33k-row point.
- **Cause-set composition.** The export uses the OECD-treatable ICD-10 approximation actually selected
  in WONDER (a few ranges slightly broader than the strict list, as `build_amenable.py` documents); a
  +0.395 partial with a [0.368, 0.43] CI is robust to that.
- **Amenable is still partly deprivation-driven** - but the +0.395 is *after* removing need +
  vulnerability, which is the entire point.
- **Kept OUT of the main 6-outcome gate on purpose** (`diagnostics.OUTCOMES`): the standard gate stays
  the conservative all-cause ruler; amenable is reported only here via the focus, so it neither dilutes
  the headline mean-r nor mixes another county-broadcast outcome into it.

**Reproduce / refresh:** the export is committed at `data/manual/wonder_amenable_county.txt` (it is
*not* headlessly fetchable - the WONDER county API is national-only - so it lives in version control,
not `data/raw/`). `build_amenable` prefers it; **`make amenable`** re-runs the whole gate. For a fresher
vintage or the full OECD code set, follow the recipe in `pipeline/build_amenable.py` and overwrite it.

### 4a. Each scored care sub-score, re-tested on the independent ruler (BACKLOG B2)

§4 corroborated the *dimension*. The open edge §1c flagged was the *individual* care sub-scores -
several selected on thin margins against the standard six, never re-checked on an outcome they
weren't fitted to. `bootstrap_gate.amenable_subscores()` closes it: for each **scored** care
sub-score, partial r vs amenable mortality net of need + vulnerability, cluster-bootstrapped over
county, with a **Benjamini-Hochberg FDR correction (Benjamini & Hochberg 1995) across the four** (the
multiplicity fix §1c said was missing). 3,066 counties / 32,879 ZCTAs.

| Scored care sub-score | raw r | partial r \| need,vuln | 95% CI (cluster) | BH q | verdict |
|---|---|---|---|---|---|
| `provider_supply` (2SFCA) | +0.402 | **+0.214** | [+0.181, +0.245] | 0.000 | holds |
| `shortage_designation` (HPSA) | +0.227 | **+0.185** | [+0.145, +0.222] | 0.000 | holds |
| `insurance` (uninsured) | +0.343 | **+0.042** | [+0.004, +0.082] | 0.014 | holds (thinnest) |
| `medical_debt` (Urban Inst.) | +0.612 | **+0.441** | [+0.409, +0.474] | 0.000 | holds (strongest) |

**All four survive** FDR at q<=0.05 with CIs excluding 0 - so every scored barrier independently
tracks treatable death net of the deprivation gradient. The headline reversal: **`medical_debt`,
the margin §1c singled out as the likely winner's-curse artifact (partial-r ~+0.27 vs the standard
six), posts the strongest independent signal of the set (+0.441)** - it is corroborated, not
collapsed. `insurance` is genuinely thin (+0.042) yet still clears. `safetynet_access` and
`preventive_use` are excluded here because they are `scored=False` (not in the composite; the
former is wrong-signed within-county, the latter is utilization not a barrier).

Caveats inherit from §4: this is a **between-county** test (amenable is county-level), so it does not
speak to sub-county separation (§3); and `medical_debt` is itself county-level, so its strong showing
is a clean county-scale result, not a sub-county one. FDR here corrects only this 4-candidate care
set, not the whole historical selection ledger (B3 remains open for the full reconstruction).

## 5. Comparability and resolution - it's a gradient, not a 33k-rank leaderboard

OECD/JRC evaluation of the live build:

| Test | Result | Reading |
|---|---|---|
| Internal reliability (split-half) | **0.95** | strong; the ~50 measures cohere |
| External validity | r ≈ +0.52 LE, +0.49 premature death, +0.40 infant mort | moderate, correctly signed, ≈ SDI's published validation |
| Plausible-weight rank wobble | ~±6 pts | reasonable weightings barely move ranks (Spearman 0.999) |
| Measurement noise (split-half SE) | ≈2.6 pts; min detectable gap ≈7 | two ZIPs <7 pts apart are within noise |
| Dimensionality | PC1 = 46% **across the underlying measures** (cf. **76% at the 3-dimension level**, §1b); corr(composite, PC1) 0.94 | ~one "general deprivation" gradient under the hood |

**Combined: two ZIPs are reliably different only by ~10-15 percentile points ⇒ ~7-10 tiers, not
33,181 ranks.** The UI leads with **deciles + a 5-95 rank band**, not an integer leaderboard. The
band is a Saisana/OECD Monte-Carlo over (1) plausible re-weighting and (2) **ACS/PLACES measurement
noise propagated from the published margins of error** (`ACS_MOE_Z=1.645` → per-rate SE → the rank
MC; calibrated against an independent member-input SE-resample by `pipeline.verify_bands` gate 3,
within ±20%). `provenance.json → rank_band` decomposes the width into its two parts: for
low-confidence ZCTAs the measurement term contributes **≈16.4** of the ≈24.6-pt median band; for
high-confidence ZCTAs only **≈3.0** of ≈10.8 - i.e. the band widens where the data is actually
noisier, not uniformly. When two ZIPs' bands overlap the comparison view marks them **"statistically
tied"** outright (T4), not just footnoted.

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

## 6. Robustness program - answering the hardest statistical critiques

The robustness program addresses five specific statistical weaknesses; the honest results are
below. Two strengthen the project, two are real-but-bounded, one is the known structural ceiling.

### 6a. Sub-county validation across five states + two national rulers (`validate_subcounty --all`)

**The scorecard** - composite + care_access WITHIN-county correlation, each against an INDEPENDENT
outcome (none in the inputs):

| Source | ZCTAs | counties | composite within-r | care_access within-r |
|---|---|---|---|---|
| NY SPARCS PQI (ACSC hospitalizations, O/E) | 1,265 | 61 | **+0.504** | +0.302 |
| CO CDPHE diabetes ACSC (tract) | 293 | 45 | **+0.568** | +0.440 |
| CA ACSC mortality (age-adjusted) | 1,170 | 46 | **+0.440** | +0.324 |
| TX DSHS ACSC inpatient (patient ZIP) | 1,335 | 146 | **+0.264** | +0.157 |
| US CDC overdose mortality (national) | 21,376 | 2,210 | **+0.224** | +0.156 |
| US USALEEP life expectancy (national) | 21,244 | 2,208 | **+0.608** | +0.409 |

Positive within-county composite **and** care_access in **every** independent ruler, across five
states and two national outcomes - the index discriminates *sub-county*, not just between counties.
Three of the five state rulers are true ACSC/preventable-hospitalization outcomes (NY, CO, TX - the
textbook access construct); TX is patient-ZIP so it needs no crosswalk at all. Detail by source below.

The central critique: nearly all validation is county-resolution, so the index's *within-county*
discrimination - its reason to exist over CHR/SVI - rested on one state (NY ACSC, §3). It now has a
**second, geographically independent state against an independent outcome**: Colorado CDPHE
age-adjusted **diabetes ACSC hospitalizations by census tract** (a core AHRQ PQI; in none of the
inputs), crosswalked tract→ZCTA with the **HUD `res_ratio` population weight** (each tract weighted by
the share of the ZIP's residential addresses it holds). 293 CO ZCTAs across 45 multi-ZCTA counties:

| Column | pooled r | **WITHIN-county r** |
|---|---|---|
| `access_gap_score` | +0.565 | **+0.568** |
| `social_vulnerability` | +0.587 | +0.536 |
| `care_access` | +0.399 | **+0.440** |
| `insurance` | +0.443 | +0.437 |
| `provider_supply` | +0.056 | +0.154 |
| `shortage_designation` | +0.148 | ~0.000 |
| `medical_debt` | +0.451 | **~0.000** |
| `safetynet_access` | -0.111 | -0.150 |

The composite resolves real **sub-county** ACSC variance (+0.507) in a state whose data never
trained it, and so does the novel `care_access` construct (+0.440). The structural negatives
**replicate** the NY/national findings: `safetynet_access` is wrong-signed; `shortage_designation`
and `medical_debt` show ~0 within-county resolution because they are **county-constant** - which
independently corroborates the §4a caveat that medical_debt's strong *between*-county signal
(+0.441) buys **zero** sub-county discrimination. (Caveats: one ACSC condition; CO + NY ≠ national.)

**And a NATIONAL sub-county ruler** (`validate_subcounty --overdose`). The data hunt also turned up
the one national, free, observed, sub-county outcome that exists: **CDC NCHS census-tract
drug-overdose mortality** (`4day-mt2f`, pooled 2022-2024, death records, independent of every input),
crosswalked tract→ZCTA. **21,366 ZCTAs across 2,210 counties** - real national coverage:

| Column | pooled r | **WITHIN-county r** |
|---|---|---|
| `access_gap_score` | +0.206 | **+0.224** |
| `health_need` | +0.233 | +0.232 |
| `behavioral_risk` | +0.178 | +0.210 |
| `care_access` | +0.119 | +0.156 |
| `medical_debt` | +0.116 | ~0.000 |

The within-county r (**+0.224**) ≈ the pooled r (+0.206): the index resolves genuine sub-county
structure, confirmed **nationally** against an independent death-records outcome - not just a county
aggregate. The magnitude is modest *and honestly so*: overdose is a specific construct (SUD/harm-
reduction access + deaths of despair), so the **behavioral/mental/need** sub-scores correctly lead,
and the remaining county-constant piece (`medical_debt`; `shortage_designation`/HPSA is now
tract-resolved - see the §3 update) shows ~0 within-county a **third** independent time. This is the strongest available answer to "does it discriminate within
counties": yes, in two states on ACSC and nationally on overdose mortality.

**And a 4th state - California** (`validate_subcounty --california`). CA CHHS publishes observed
ACSC-cause mortality (diabetes/heart/COPD/stroke deaths) by ZIP. Crude rates are age-confounded -
and in CA age is a *suppressor* (older ZIPs are wealthier coastal/retirement areas), so the signal
only emerges after age adjustment (residualize index + rate on `age65_rate` within county). 1,170
CA ZCTAs / 46 counties:

| within-county r | crude | **age-adjusted** |
|---|---|---|
| `access_gap_score` | +0.100 | **+0.440** |
| `social_vulnerability` | +0.138 | +0.485 |
| `care_access` | -0.001 | **+0.324** |
| `insurance` | -0.025 | +0.352 |
| `shortage_designation` / `medical_debt` | ~0 | **~0** (county-constant, a 4th time) |

**And a 5th state - Texas, the cleanest expansion of all** (`validate_subcounty --texas`). The TX
DSHS THCIC Inpatient PUDF gives per-discharge records with the **patient's 5-digit ZIP + principal
ICD-10 diagnosis** - so a TRUE ACSC (preventable-hospitalization) outcome at patient ZIP, needing
**no crosswalk**, in the largest state. (It was thought to need a fixed-length layout doc; in fact
the PUDF is also published **tab-delimited with headers**, so it is fully headless.) We flag a
discharge ACSC if its principal diagnosis is in the AHRQ-PQI-style set (diabetes, COPD/asthma,
pneumonia, CHF, hypertension, UTI, dehydration, angina), pool the 4 quarters of 2019, and rate by
ZCTA population. 1,335 TX ZCTAs / 146 counties:

| Column | pooled r | **WITHIN-county r** |
|---|---|---|
| `access_gap_score` | +0.311 | **+0.264** |
| `chronic_disease` | +0.354 | +0.281 |
| `care_access` | +0.140 | +0.157 |
| `insurance` | +0.217 | +0.162 |
| `shortage_designation` / `medical_debt` | +0.20/-0.11 | **~0** (county-constant, a 5th time) |

So the sub-county claim holds in **five states** - NY + CO + TX on true ACSC hospitalizations, CA on
age-adjusted ACSC mortality, plus national overdose - and the structural negatives
(`medical_debt`/`shortage` county-constant, `safetynet` wrong-signed) replicate in **every one**.
HCUP SID (a single national ACSC panel) stays the paid gold standard, but the free state-by-state
panel now spans the four largest states by population. See [BACKLOG.md](BACKLOG.md) B1.

### 6b. Spatially-honest CIs - the claim survives state blocking (`bootstrap_gate.spatial_sensitivity`)

The county cluster bootstrap fixes within-county pseudo-replication but still treats counties as
spatially independent; health geography is autocorrelated, so those CIs are too narrow. Re-running
the load-bearing claim (care_access partial r vs amenable | need, vuln) under **state blocking**
(whole states resampled - the conservative correction for between-county autocorrelation):

| Blocking | clusters | care_access partial r | 95% CI |
|---|---|---|---|
| county (baseline) | 3,225 | +0.395 | [0.366, 0.426] |
| **state** (spatial) | 52 | +0.395 | **[0.334, 0.455]** |

The interval roughly **doubles in width** - the honest cost of acknowledging spatial dependence -
but **still excludes 0 by a wide margin**. The headline result is not an artifact of treating
counties as independent.

### 6c. Cross-validated weights - the fit is not overfit (`validate._cv_regression`)

The data-driven weights are fit to an outcome, then fit quality was reported on the same outcome
(optimism). Honest **leave-one-state-out CV** (standardize on the training fold only, predict the
held-out state, pool):

| Anchor | in-sample R² | **CV R²** | optimism | weight SD across folds |
|---|---|---|---|---|
| amenable mortality | 0.607 | **0.598** | 0.009 | ≤0.5 pts |
| premature death | 0.515 | 0.505 | 0.010 | ≤1.0 |
| infant mortality | 0.443 | 0.412 | 0.031 | ≤1.9 |
| life expectancy | 0.390 | 0.382 | 0.008 | ≤0.8 |

Optimism is **small** (≤0.03 R², largest for the sparse/noisy outcomes), and the weights are
**stable** (≤2-point swing when any state is removed). The "data-driven" weighting is not noise.

### 6d. Missingness is mostly benign, with two disclosed selection effects (`pipeline.selection_diag`)

- **Scoreability: benign.** The 615 non-scoreable ZCTAs hold **0.000%** of national population
  (they are unpopulated), so they carry no rank to bias.
- **2-of-3 dimension scores (764 ZCTAs, 2.3%): a real, disclosed selection.** They are
  systematically worse-access and higher-mortality than 3-of-3 ZCTAs (Cohen d **+0.27** on the
  composite, **+0.24** on amenable mortality) - their partial composite is *not* missing-at-random.
  The mechanism is MNAR and specific: every one is missing **health need** (no PLACES disease data),
  their median population is **43 vs 2,930** for full scores, and **83.5%** are already
  `low_confidence` (vs 29.4%). A renormalized 2-of-3 score matches the *scale* of a 3-of-3 score but
  not the *estimand*, so co-ranking them is a comparability error. The build flags `n_dims_scored`,
  and (T2) the headline **holds 2-of-3 scores out of the reliable rank band** - backend
  `rankings(min_dims=3)` and the client rankings exclude them on composite-family lenses, the map
  desaturates them, and the detail panel labels the score "partial." They stay visible and
  clickable; they are not silently co-ranked with the full-score majority.
- **Validation-subset selection: a real range restriction.** ZCTAs missing the amenable /
  preventable-hosp outcome are **+0.38 / +0.33 SD worse-access** than those with it, so those
  validation r's are computed on a slightly better-access (truncated) subset - which *attenuates*
  correlations, i.e. the reported r's are if anything conservative. Life expectancy is clean
  (d +0.02, 96% coverage).
- **Member completeness:** every sub-score averages ≥0.90 of its members present (thinnest:
  mental/social health 0.90), so the skipna-mean is not silently averaging over large gaps.

### 6e. Decision-context ranking - within-state, not just a national ladder (point 5)

National percentiles compare a ZCTA to the whole country, but care is allocated **within** state
programs. The build now emits `access_gap_pctile_within_state` (the composite re-ranked within each
state) and the map exposes an "Access gap (within-state rank)" lens. It correlates **0.72** with
the national rank - different enough to matter: a ZCTA can be middling nationally yet worst-in-its-
state, which is the unit a state administrator acts on. (Within-commuting-zone is the natural next
refinement.)

### 6f. B4 bounded - the index's validity barely depends on the circular PLACES dimension

B4 (PLACES disease estimates are SES-conditioned, so `health_need` shares modeled variance with
`social_vulnerability`) is **not fixable** - it is a *non-identification* problem (you cannot separate
the model-induced SES↔disease correlation from the genuine one using the same variables), and the
only true fix (non-modeled sub-county disease) is paywalled. But it can be **bounded**: rebuild the
composite WITHOUT `health_need` (the pure-PLACES dimension; care_access + social_vulnerability are
ACS/NPPES-dominant) and re-correlate against the independent death/hospitalization-records outcomes
(`bootstrap_gate.b4_circularity_bound`):

| Independent outcome | full composite r | no-PLACES composite r | **validity retained** |
|---|---|---|---|
| amenable mortality | +0.660 | +0.606 | **92%** (CI [90%, 93%]) |
| premature death | +0.642 | +0.602 | 94% |
| infant mortality | +0.543 | +0.510 | 94% |
| preventable hosp | +0.342 | +0.305 | 89% |

**~90-94% of the index's external validity survives deleting the entire PLACES dimension.** So the
circularity inflates the *internal-coherence story* (the need↔vulnerability correlation, the
PLACES-general-health anchor) but is **not load-bearing for predictive usefulness** - the index
tracks independent death records nearly as well with PLACES removed. B4 is therefore a bounded,
disclosed limitation, not a hidden dependency. (The PLACES anchor r=0.865 is reported elsewhere only
to *contrast* with these independent rulers, never as validation.)

**Net:** the sub-county claim now holds in **five states** - NY, CO, TX on true ACSC hospitalizations,
CA on age-adjusted ACSC mortality - **and nationally on overdose mortality** (21k ZCTAs, within-county
+0.224); the headline survives spatially-honest CIs; the
weights survive cross-validation; the one genuine selection effect (2-of-3 scores) is quantified and
already flagged. The residual ceiling is narrower than before: no *national ACSC* sub-county panel is
free (HCUP SID is paid), so the strongest access-specific sub-county evidence is state-by-state (NY,
CO), while the national sub-county check rides on overdose mortality - a real but construct-specific
ruler. B4 (PLACES SES-conditioning) is structurally unfixable but now **bounded** (§6f): ≤10% of
external validity depends on the circular dimension.

**Crosswalk refined to population weighting.** The tract→ZCTA crosswalk now uses the **HUD
USPS `res_ratio`** (the share of each ZIP's residential addresses in each tract) instead of crude land
area. This *strengthened* every headline: CO composite within-county **+0.507 → +0.568**, overdose
**+0.202 → +0.224**, care_access likewise - i.e. the area weighting had been *attenuating* the signal
by mis-assigning sparsely-populated rural tracts. The findings are not just robust to the crosswalk
choice; they were understated by the cruder one. (Falls back to area weighting when no HUD token is
present; `validate_subcounty._load_hud_xwalk`.)

**Only the paid national panel remains.** Every free expansion identified has now been integrated -
NY, CO, CA, TX as states and CDC overdose + USALEEP nationally. Texas turned out to need no layout
doc (the PUDF is published tab-delimited). The one thing still out of reach is **HCUP SID**, a
single *national* ACSC panel - paid + DUA, not headless. The free state-by-state panel (now the four
largest states) is the substitute. (California was initially shelved as age-confounded, then
*recovered* once age was properly controlled - see §6a.)

## 7. Causal / actionability frontier - is it a lever, or just a better poverty map?

Every check in §1-§6 is **cross-sectional**: it correlates the index with outcomes at one point in
time. The deepest surviving critique accepts all of it and still says: *your index correlates with
bad outcomes because it is a deprivation gradient - poverty plus disease burden. Correlation at one
instant cannot tell me access is a LEVER: that putting a clinic or coverage where the index is high
would move outcomes. You have a better map of where sick poor people live; I already had that.* This
is a causal/actionability question, and §7 attacks it with the strongest identification strategies
free data allows. The honest answer, after running them all: **the index is a well-validated
*descriptive* map of where access is poor; its *actionability* as a lever is not demonstrated.**

**§7 at a glance - the causal evidence ladder (read top to bottom):**

| Rung | Design | Result | What it means |
|---|---|---|---|
| §7a | Negative control (placebo outcome) | **null** (diff +0.007, CI crosses 0) | cross-sectionally indistinguishable from a poverty map |
| §7b | NY-only event study around 2014 | **inconclusive** (-36.5; joint pre-trends test χ²(4)=9.28, p=0.055 - borderline, point estimates not flat) | not a causal read on its own - high-barrier ZIPs may already be converging |
| §7e | **Cross-state DiD-in-DiD** (NY vs TX control) | **falsified** (triple-diff +10.3, CI crosses 0) | TX never expanded yet declined the same → the §7b hint was secular convergence, not the expansion |
| §7d | Precision-weighting + disattenuation | observed↑ to ceiling ~0.85; **no scored signal added** | the "modest" correlations are a noisy *ruler*, not a weak index |
| §7f | **Staggered FQHC supply-lever event study** (Callaway-Sant'Anna, NY+TX) | **null** (-35.5/100k; ZIP CI [-71.7, +2.2], spatially-honest county-block CI [-74.1, +10.5] - both include 0) | the *supply* arm is right-signed, dose-responsive, robust to spillover, but not distinguishable from 0 once counties (not ZIPs) are the resampling unit; pre-trends not fully clean |
| - | New-data hunt (CMS/SAMHSA/HCRIS) | supply hits the endogeneity wall; the barrier that works is redundant | no free dataset adds new scored signal |

> **Spatial-inference update (supersedes the ZIP-cluster CIs in §7b/§7f below).** The causal
> validators now report a **county-block** bootstrap beside the ZIP-cluster one and key the verdict on
> it, because ACSC geography is spatially autocorrelated and the ZIP-cluster CI treats neighbouring
> ZIPs as independent (too narrow). The honest CIs are wider: **temporal DiD −36.5, county-block CI
> [−78.6, −4.2]** (still excludes 0) and **FQHC overall −35.5, county-block CI [−74.1, +10.5]** (the
> "borderline" is now clearly null). Verdicts are unchanged in direction; the FQHC lever remains "no
> credible effect". The per-horizon and balanced CIs in the prose below are still ZIP-cluster and were
> not re-run - treat the validator output (`validate_temporal`/`validate_fqhc_lever`) as authoritative.

A single-state DiD would have shipped a causal claim (§7b) that the falsification control (§7e)
shows the data does not support; the project reports the null rather than the optimistic read. The two
arms of `care_access` land differently: **affordability** (the ACA coverage shock, §7b/§7e) is a clean,
control-disciplined null; **supply** (the FQHC openings, §7f) is a powered near-miss - the strongest
free-data hint of an actionable lever the project has, still honestly short of demonstrated.

### 7a. Negative control - the index does NOT separate access from deprivation cross-sectionally (`pipeline.validate_placebo`)

A placebo-outcome / negative-control design (Lipsitch, Tchetgen Tchetgen & Cohen 2010) splits
mortality into two buckets that are **both** deprivation-loaded but differ on one axis - whether timely ambulatory care can prevent the death:

- **access-sensitive** (the target): ACSC deaths - diabetes, heart disease, COPD, stroke. Primary
  care, medication, and disease management prevent these.
- **placebo / access-insensitive** (the control): external-cause deaths - unintentional injury,
  homicide, suicide. These track poverty just as hard, but a clinic does not stop a car crash.

If the index were access-specific it would predict the access-sensitive bucket **more** than the
placebo (a positive *differential* r), and that excess would concentrate in `care_access`. CA
ZIP-level vital records, age-adjusted within county (injury skews young, ACSC old):

| index column | r vs ACSC | r vs placebo | **differential** | county-bootstrap 95% CI |
|---|---|---|---|---|
| `access_gap_score` | +0.493 | +0.494 | **-0.001** | [-0.143, +0.097] |
| `care_access` | +0.364 | +0.357 | +0.007 | [-0.126, +0.115] |
| `care_access_resid` (access net of deprivation) | -0.264 | -0.258 | -0.006 | [-0.073, +0.064] |
| `health_need` | +0.469 | +0.508 | -0.039 | [-0.152, +0.051] |

**The differential is a clean null everywhere** - raw care-access, the residualized
access-beyond-deprivation lens, and the composite all predict preventable and non-preventable deaths
*equally*. At ZCTA cross-section the index behaves like a general deprivation/mortality gradient: it
does not flag the deaths timely care could have prevented over the ones it could not. The placebo is
*conservative* (injury includes drug-poisoning, suicide carries a mental-health-access component), so
contamination biases this test **toward** finding access signal - and it still finds none. This does
not overturn the county amenable-mortality partial-r (§4): that is a partial association net of need
at county scale with a curated treatable-mortality list, a different and weaker claim than *differential
prediction*. But it **bounds** the cross-sectional access claim honestly, and it is exactly why the
temporal test below is the better question.

### 7b. Temporal quasi-experiment - inconclusive on its own, then overturned by the cross-state control (`pipeline.validate_temporal`)

Cross-sectional differential prediction is an extremely hard bar (everything bad loads on the same
gradient). A within-unit fixed-effects **event study** around a real access shock escapes it. NY
publishes ACSC hospitalizations (AHRQ PQI_90) by patient ZIP every year 2009-2023; in 2014 the ACA
coverage expansion sharply cut the uninsured rate, **most where it was highest**. The model is a two-way-fixed-effects
event study (DiD: Card & Krueger 1994; two-way-FE / event-study framing: Angrist & Pischke 2009):

`PQI_zt = α_z + γ_t + Σ_k β_k·(barrier_z × 1[year=k]) + ε`  (base year 2013)

- `α_z` (ZIP FE) absorbs **all time-invariant deprivation** - the exact confound that sank §7a. Each
  ZIP is its own control.
- `γ_t` (year FE) absorbs the statewide secular ACSC trend.
- `barrier_z` is the ZIP's standardized **pre-treatment** uninsured rate (ACS 2008-2012, *before* the
  shock). The shipped ACS-2023 rate is post-expansion and endogenous - it correlates only ~0.42 with
  the 2012 rate, because expansion compressed it - so using the true pre-period barrier is essential
  (the contemporary proxy badly mismeasures who faced a high barrier).

Result (1,265 NY ZIPs × 15 years): the **post-2014 coefficients shift negative** (mean -6.8) and the
average post-expansion DiD is **-36.5/100k per +1 SD baseline barrier, ZIP-cluster bootstrap CI
[-60.3, -11.3]** (excludes 0), surviving dropping the one non-flat pre-year (2009): **-30.6**. Read
naively this looks like ACSC falling more, after coverage expanded, in the ZIPs that had been most
uninsured.

**The parallel-trends assumption is tested, not assumed - and it does not clear the bar.** The pre-2014
betas are subjected to an explicit joint Wald test (`_pre_trends_test`: do the pre-period coefficients
jointly equal zero?): **χ²(4) = 9.28, p = 0.055**. That only *barely* fails to reject at 5%, and the
pre-period point estimates are plainly *not flat* (+53.6, +22.6, +35.4, +37.1/100k - a systematic
positive level, RMS 38.8, comparable in size to the DiD itself). So the verdict the validator prints is
computed, not editorial: **INCONCLUSIVE / descriptive only - no causal read.** It is also **one state**,
and NY's pre-ACA childless-adult waiver muddies the shock. Crucially, the cross-state control (§7e)
then **falsifies** the optimistic read outright: Texas, which never expanded Medicaid, shows the same
post-2014 high-barrier decline. The strongest honest claim free data supports is therefore *descriptive*
- the index describes where access is poor - **not** that the access components were shown to move the
outcome. Any "step toward causal" framing is withdrawn.

### 7c. What §7 changes

Cross-sectionally the index cannot be distinguished from a poverty map (§7a). The NY-only event study
(§7b) *appeared* to show the barrier behaving like a lever - but it carried imperfect parallel trends,
and **the cross-state falsification test (§7e) overturns that optimistic read**: Texas, which never
expanded Medicaid, shows the *same* post-2014 high-barrier ACSC decline as New York, so the NY drop was
secular convergence, not the expansion. The honest, control-disciplined conclusion is therefore the
conservative one: **free-data causal identification does not establish an actionable access lever.** The
index is a deprivation-dominated *structural-access* map that is well-validated descriptively (§3-§6)
but whose *actionability* is not demonstrated - and the project says so rather than resting on the
single-state hint. This is the value of building the control: the naive single-state DiD would have
shipped a causal claim the data does not support. But §7e tested only the *affordability* arm; the
**supply arm (§7f below) - a staggered FQHC-opening event study - lands differently: a powered borderline,
right-signed and dose-responsive but just short of significance.** So the sharpened conclusion is not a
flat null but an asymmetry: affordability reads as a clean null, supply as a near-miss; the index's
actionability remains *undemonstrated*, not *disproven*. All temporal validators are standing, read-only,
and never feed the composite. Remaining follow-ups (a provider-entry within-ZIP panel; a MAUP (Openshaw 1984) re-zoning
check) are in [BACKLOG.md](BACKLOG.md).

### 7d. Precision-weighting + disattenuation - the "modest" correlations are partly a noisy-ruler artifact

A statistician's audit of *what would actually raise explanatory power* found that most of the levers
either overfit (outcome-tuned weights), lower resolution (coarser aggregation), or hit the collinearity
ceiling (more predictors). The two that legitimately recover signal both **reduce measurement noise**
rather than fit it - so they are near-guaranteed and change no scores. Both are now reported by the
validators (`validate._wcorr`/`_index_reliability`/`_parallel_forms_reliability`; `validate_subcounty._wcorr`).

**Precision-weighting (WLS).** The unweighted correlation lets a tiny, high-variance area count as much
as a large, precisely-measured one - classic errors-in-variables attenuation. Weighting each unit by
population down-weights the noise and shifts the estimand to *where people actually live*. It corrects
attenuation; it fits nothing. The recovery is real and largest at the resolution the tool runs at:

| ruler | unweighted r | pop-weighted r | recovered |
|---|---|---|---|
| county: amenable mortality | +0.753 | +0.789 | +0.036 |
| county: premature death | +0.710 | +0.778 | +0.068 |
| **NY sub-county: composite (within-county O/E)** | +0.504 | **+0.623** | **+0.119** |
| **NY sub-county: care_access (within-county O/E)** | +0.302 | **+0.442** | **+0.140** |

**Disattenuation - the reliability ceiling.** With index reliability (split-half, Spearman-Brown)
**0.882** and each ruler's reliability estimated by the single-factor triangulation
`rel_i = r(i,j)·r(i,k)/r(j,k)` over the three access-sensitive county rulers, the disattenuated
composite-outcome correlation `r / √(rel_x·rel_y)` shows how much of the gap to 1.0 is recoverable noise:

| ruler | reliability | observed (pop-w) r | disattenuated r |
|---|---|---|---|
| amenable mortality | 0.97 | +0.789 | +0.852 (near ceiling) |
| **preventable_hosp** | **0.25** | +0.435 | **+0.926** |
| premature death | 0.74 | +0.778 | +0.961 |

The headline: **`preventable_hosp` - the "textbook ambulatory-access outcome" - has reliability ~0.25**,
so its weak observed correlation (0.435) is overwhelmingly measurement error in the *ruler*, not a weak
index. (Honest caveat: the triangulation attributes all low inter-correlation to noise; a ruler that
measures a genuinely *distinct* construct - preventable_hosp is Medicare-65+ *hospitalization*, not
death - would also read low. So 0.25 is "reliable variance shared with the mortality factor", a
conservative reliability. Either way, its low r is not evidence against the index.) This relocates the
long-standing "care access reads modest" finding (§2) from *weak index* toward *noisy outcome* - the
modesty is real but smaller than the naked correlations imply.

**What this does and does not change.** The per-ZCTA composite scores never change - precision-weighting
and disattenuation only alter how the index's association with outcomes is *measured*. The anchored
*presets* use the **unweighted** dimension correlations (the shipped default), with the pop-weighted
variant retained beside them as `weights_popw` for transparency. Pop-weighting changes the estimand to
"the correlation where people live" and systematically raises care_access, so it is offered as a labeled
sensitivity, not the default. The unweighted→pop-weighted shift is modest and mixed at county resolution
(e.g. amenable care_access 31.2→28.5; infant mortality moves the other way, 31.5→34.1) - the
large care_access recovery is a *sub-county* phenomenon, not a county-preset one, and the docs say so.
The CV-optimal supervised reweighting at sub-score level was measured and **declined**: it buys only
+0.02 to +0.085 out-of-sample R² and costs the conceptual-weight interpretability the index protects
(`validate._cv_regression` shows the 3-dimension weights are near-optimal, optimism ≤0.03).

**The pruning lever is exhausted.** Removing a component only raises clean-r if
the component was adding noise - which is how `safetynet_access` and `preventive_use` were dropped
historically. Re-running the per-sub-score gate (`bootstrap_gate.amenable_subscores`, BH-FDR q≤0.05)
shows **every** scored care sub-score now HOLDS a positive partial r against amenable mortality:
provider_supply +0.214, shortage_designation +0.185, insurance +0.042, medical_debt +0.441 (all
q≤0.05); and every need/vulnerability sub-score has a solidly positive, correctly-signed mean|r|
(0.20-0.46). There is no failing or wrong-signed component left to prune for a free gain. Combined with
the collinearity ceiling (§1b), the noisy-ruler disattenuation above, and the cross-sectional placebo
null (§7a), the conclusion is that the **internal** levers (pruning, reweighting, noise-correction in
reporting) are now worked to completion; the remaining real gains are **external** - new data
(BACKLOG B5: a non-expansion control state, a provider-entry panel) - not another pass over the same
33k rows.

### 7e. Cross-state falsification - the temporal lever does NOT survive a control (`validate_temporal.run_cross_state`)

The NY-only event study (§7b) had no never-treated comparison, so it could not separate the 2014
expansion from a secular trend in which high-uninsured ZIPs were already converging. The fix is a
**DiD-in-DiD** with a falsification control: **Texas never expanded Medicaid**, so if the high-barrier
post-2014 ACSC decline were the expansion, it should appear in NY (treated) and **not** in TX (control).
We built the TX patient-ZIP ACSC panel from the free DSHS PUDF (2011-2015, ICD-9 era spanning 2014;
1.46M ACSC of 13.4M discharges), used the same pre-2012 uninsured barrier, and estimated a two-way-FE
(ZIP + state×year) event study per state plus the triple interaction `barrier × post × treated`:

| year | NY (treated) β | TX (control) β |
|---|---|---|
| 2011 | +24.7 | +19.2 |
| 2012 | +23.3 | +8.6 |
| 2013 | 0 (base) | 0 (base) |
| 2014 | +0.2 | -1.2 |
| 2015 | -2.4 | -35.2 |

**Triple-diff (barrier × post × NY) = +10.3, ZIP-cluster bootstrap CI [-14.3, +33.8] - null and
wrong-signed.** TX shows the same (in 2015, larger) post-2014 high-barrier decline as NY. So the §7b
"suggestive lever" was the secular convergence common to both states, **not** the Medicaid expansion.
The falsification control did exactly its job: it caught a confound the single-state design could not.

The honest verdict: **free-data causal identification does not support an actionable access lever.** The
optimistic single-state reading is retracted. (Caveats, none of which rescue the claim: TX's 2015 Q4
crosses into ICD-10 and could inflate its decline, but even the pre-transition 2014 shows no NY-vs-TX
divergence; and ACSC is FFS/all-payer-mixed across the two sources, absorbed by the state×year FE.) This
is the strongest free design available and it returns a clean, disciplined null - which, paired with the
descriptive validity of §3-§6, is the accurate place to leave the index: a well-validated map of *where*
access is poor, not a demonstrated lever for *fixing* it. The estimator is unit-tested with a planted
treated-only effect against a common pre-trend (`tests/test_causal_validation.py`).

### 7f. Supply lever - the staggered FQHC opening event study (`pipeline.validate_fqhc_lever`)

Every test above (§7a-§7e) attacked the **affordability** arm of `care_access` - the ACA coverage shock,
which moves who can *pay*. It left the other arm untouched: **supply / safety-net** - whether putting a
clinic *where there was none* moves preventable hospitalizations. HRSA opens Federally Qualified Health
Centers in dated, located waves (New Access Point grants), a **staggered treatment** that §7e's two-state
DiD cannot exploit. The clean treatment is a ZCTA's **first-ever** FQHC opening in 2012-2019 (a 0→1
transition; `build_fqhc_openings.py` derives it from the HRSA `Site Added to Scope` date - 551 such
ZCTAs across the four panel states, matching the power gate's count). Controls are **supply-stable**
ZCTAs (no opening in the window); ZCTAs that already had a clinic and merely gained another are excluded
from both arms.

With many adoption years a two-way-FE DiD is the *wrong* estimator: under heterogeneous, dynamic effects
it contaminates each comparison with forbidden already-treated-vs-newly-treated 2×2s and can flip sign
(Goodman-Bacon 2021). We use the **Callaway & Sant'Anna (2021) group-time ATT** instead, hand-rolled and
unit-tested: for each cohort *g* (opening year) and period *t*,
`ATT(g,t) = [Y_t − Y_{g−1} | cohort g] − [Y_t − Y_{g−1} | not-yet-treated by max(t,g)]`, a universal base
period *g−1*, never using an already-treated ZIP as a control. Comparisons are made **within state**
(NY treated vs NY not-yet, TX vs TX), so state-specific levels, scale and secular shocks difference out -
the equivalent of state×year fixed effects - and the group-time ATTs aggregate to an event-time path
weighted by cohort size. Outcomes: NY SPARCS PQI_90 ACSC/100k by ZIP×year 2009-2023, and the free TX
DSHS PUDF ACSC/100k 2011-2019 (the §7e panel extended to nine annual years). Inference is the project's
ZIP-cluster bootstrap. **This design was pre-registered by a Monte-Carlo power gate** (`validate_fqhc_power`,
BACKLOG B5d.0) *before* any panel assembly: it rated the buildable NY+TX pool (~277 treated) as powered
for the plausible 2-8% effect (MDE 5%) and NY-only (135) as a pilot. **Caveat (corrected):** that MDE
assumed a two-way-FE estimator, but the shipped Callaway-Sant'Anna uses only not-yet-treated comparisons
and is strictly less efficient, so the realized MDE is *larger* than 5%. The null is therefore best read
as **suggestive-but-underpowered** (right-signed, dose-responsive, wide CI), not a cleanly-powered true
null.

**Realized design: 259 newly-served treated ZIPs (NY 125 + TX 134) vs 2,382 supply-stable controls**
(≈ the gate's powered scenario). The event-study path (population-weighted):

| event time *e* (yrs from opening) | ATT /100k | 95% CI | era |
|---|---|---|---|
| −5 … −2 (pre) | +31, +19, +35, +21 | mostly straddle 0 | parallel-trends |
| **0** | −11 | [−35, +16] | post |
| **+2** | −23 | [−61, +14] | post |
| **+4** | −42 | [−87, +5] | post |
| **+6** | −49 | [−108, +11] | post |
| **+10** | −131 | [−269, +3] | post (few cohorts) |

The post path is **monotone and dose-responsive** - ACSC falls further the longer the clinic has been
open. The cohort-weighted **overall ATT is −35.5/100k** (~2.5% of the ~1,300/100k baseline), **95% CI
[−71.7, +2.2]**; restricted to the well-populated horizon (*e*≤4) it is **−25.6/100k, CI [−56.9, +4.8]**.
Both CIs **just barely include zero**. The pre-period is *not* perfectly flat (RMS 26.8/100k, residual
*positive* - the **siting signal**: HRSA opens FQHCs where ACSC is already high and rising), so
`parallel_trends_clean = False`. Pooling TX roughly halved that pre-trend versus the NY-only pilot (RMS
57, overall −40.8, CI [−88, +17]), which on its own is underpowered exactly as the gate predicted.

**Robustness (`run_robustness`).** Three checks, each reported against the headline:

| variant | n_treated | overall ATT | 95% CI | reads |
|---|---|---|---|---|
| headline (clean 0→1) | 259 | −35.5 | [−71.9, +1.1] | the estimate |
| drop controls <10 km (SUTVA) | 259 | **−39.5** | [−73.6, +0.9] | **persists, slightly more negative** - spillover onto near controls was biasing toward 0 |
| placebo-in-time (−3 yr) | 259 | **−3.6** | [−35.1, +23.1] | **≈ 0** - the immediate pre-window is clean; the post-effect is not a near-term pre-trend artifact |
| loose dose (any addition) | 369 | −66.5 | [−96.9, −38.2] | larger & excludes 0, but **more confounded** (repeated investment targets improving areas) - adds power, not clean identification |

The headline survives the spillover check and **passes the placebo-in-time** - the two ways the borderline
result could have been spurious. The loose-dose result is *larger* than the clean dose (the opposite of a
diminishing-returns prediction), which we read not as a stronger lever but as a flag that the looser
treatment folds in more siting endogeneity; the clean 0→1 transition remains the headline precisely
because it is the better-identified one.

**Honest verdict: borderline - a powered "almost", not a demonstrated lever and not a clean null.** The
supply arm is right-signed, dose-responsive, robust to spillover, and clean on the near-term placebo, in
a design the power gate certified - materially stronger than the affordability arm's control-disciplined
null (§7e). But the 95% CI just includes zero and the distant pre-period carries a residual siting trend
the event study cannot fully difference out, so the most we can honestly claim is a **suggestive modest
supply effect (~2-2.5% of baseline ACSC), not statistically conclusive**. This does not overturn §7's
top-line conclusion - the index's actionability is still not *demonstrated* - but it sharpens it: of the
two access arms, affordability reads as a clean null and supply reads as a near-miss worth a future
better-identified design (more states with annual panels; the distance-to-opening dose). Read-only;
never feeds the composite. The CS estimator is unit-tested with a planted staggered effect, a common
trend it must difference out, and a treated-only pre-trend it must expose (`tests/test_causal_validation.py`).

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

- **Cluster bootstrap over county** (`state|county_name`), not ZCTA rows. Five of the six
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
dimensions**. The three-dimension framing is a *construct* decomposition (the 5 A's), not a claim
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
| shortage_designation (HPSA) | Availability | 0.206 | **0.000** |
| insurance | Affordability | 0.322 | **0.477** |
| **medical_debt** (Urban Institute, **county-level**) | Affordability | **0.40** | **0.000** |
| preventive_use (checkups/screens) | realized access (net of all A's) | 0.200 | **0.464** |
| safetynet (FQHC, **unscored**) | Acceptability proxy | 0.201 | −0.072 |

**Finding: the two *spatial* Availability sub-scores carry ~zero sub-county signal
(provider_supply 0.076, HPSA 0.000), while the *non-spatial* ones carry nearly all of it
(insurance 0.477, preventive_use 0.464).** The most-engineered piece (spatial supply) is the
least productive at the resolution the tool runs.

**County-level scored barriers add only county-resolution signal - an honest asymmetry.** Two
*scored* care sub-scores are county-level inputs broadcast county→ZCTA, so their within-county r
is **0.000** by construction (`validate_subcounty` auto-flags both): `shortage_designation` (HPSA)
and **`medical_debt`**. The latter is the affordability win celebrated in §1/§4 - its entire
mean|r| 0.40 and **partial-r +0.27 are a *county-resolution* result**; it contributes nothing at
the tool's native ZCTA resolution, exactly like HPSA. We keep both *scored* on **construct
grounds** (real, official/credit-bureau, county-level barriers), not because they resolve
sub-county variance. The distinction from `safetynet` (which was *removed* from scoring) is that
county-flat is **signal-less within county, not wrong-signed** - harmless to carry, whereas
safetynet actively mis-ranked sub-county. A reader comparing two ZCTAs in the same county should
know HPSA and medical_debt give them the *same* value: the sub-county separation comes entirely
from insurance, the spatial supply terms, and the need/vulnerability dimensions. (Enabling A's in social_vulnerability behave
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

## 4. Amenable mortality - the gold-standard anchor (**RUN - care access validated**)

> **STATUS: VALIDATED against treatable mortality (2026-06-24).** A CDC WONDER county export
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
county, with a **Benjamini-Hochberg FDR correction across the four** (the multiplicity fix §1c said
was missing). 3,066 counties / 32,879 ZCTAs.

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

## 6. Robustness program - answering the hardest statistical critiques (2026-06-25)

A methodologist's review raised five specific weaknesses. Each was implemented and run; the
honest results are below. Two strengthen the project, two are real-but-bounded, one is the
known structural ceiling.

### 6a. Sub-county validation generalized to a second state (`validate_subcounty --colorado`)

The central critique: nearly all validation is county-resolution, so the index's *within-county*
discrimination - its reason to exist over CHR/SVI - rests on one state (NY ACSC, §3). It now has a
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
and the county-constant pieces (`medical_debt`, `shortage_designation`) show ~0 within-county a
**third** independent time. This is the strongest available answer to "does it discriminate within
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

So the sub-county claim now holds in **four states / sources** - NY + CO + CA on ACSC(-mortality)
and nationally on overdose - and the structural negatives (`medical_debt`/`shortage` county-constant,
`safetynet` wrong-signed) replicate in every one. The data hunt also leaves a verified recipe for
the remaining expansion: **TX DSHS PUDF** (true 5-digit patient-ZIP discharge microdata) - blocked
only by a fixed-length layout doc, not a key. HCUP SID (national ACSC) stays the paid gold standard.
See [BACKLOG.md](BACKLOG.md) B1.

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
  This is exactly why the build flags `n_dims_scored` and the UI caveats a 2-of-3 score.
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

**Net:** the sub-county claim now holds in **three states** on ACSC(-mortality) - NY, CO, CA -
**and nationally on overdose mortality** (21k ZCTAs, within-county +0.224); the headline survives
spatially-honest CIs; the
weights survive cross-validation; the one genuine selection effect (2-of-3 scores) is quantified and
already flagged. The residual ceiling is narrower than before: no *national ACSC* sub-county panel is
free (HCUP SID is paid), so the strongest access-specific sub-county evidence is state-by-state (NY,
CO), while the national sub-county check rides on overdose mortality - a real but construct-specific
ruler. B4 (PLACES SES-conditioning) is structurally unfixable but now **bounded** (§6f): ≤10% of
external validity depends on the circular dimension.

**Crosswalk refined to population weighting (DONE).** The tract→ZCTA crosswalk now uses the **HUD
USPS `res_ratio`** (the share of each ZIP's residential addresses in each tract) instead of crude land
area. This *strengthened* every headline: CO composite within-county **+0.507 → +0.568**, overdose
**+0.202 → +0.224**, care_access likewise - i.e. the area weighting had been *attenuating* the signal
by mis-assigning sparsely-populated rural tracts. The findings are not just robust to the crosswalk
choice; they were understated by the cruder one. (Falls back to area weighting when no HUD token is
present; `validate_subcounty._load_hud_xwalk`.)

**Still logged, not done.** A **Texas** 5-digit-patient-ZIP ACSC panel (the biggest single expansion)
needs the fixed-length record layout doc and the S3 listing is disabled - a file gap, not a key gap;
a real recipe for later. (California was initially shelved as age-confounded, then *recovered* once
age was properly controlled - see the 4th-state result in §6a.)

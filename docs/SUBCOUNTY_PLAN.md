# Making the sub-county claim real

Goal: move "sub-county index" from *technically true* (ZCTA-native) to *defensible under a statistician's probe* - both by raising how much of the score genuinely varies within counties, and by proving those within-county rankings against real sub-county outcomes.

## Where it stands today (measured, national build 2026-06-30)

**Structural** - share of composite *weight* on inputs that vary within county:
- sub-county (ZCTA-native) inputs: **82.5%**
- county-flat inputs: **17.5%** - exactly two scored sub-scores, both in `care_access`: `shortage_designation` (HPSA, county-MAX) and `medical_debt` (Urban Institute, county-only).

**Empirical** - share of score *variation* that is within-county (variance decomposition over 3,064 multi-ZIP counties):
| Layer | within-county variance share |
|---|---|
| composite `access_gap_score` | **24.1%** |
| `health_need` (all sub-county inputs) | **31.2%** ← achievable ceiling with current data |
| `care_access` | **7.6%** ← half its scored inputs are county-flat |

Headline you can defend: *"~24% of the score's variation is within-county; health-need resolves best (31%), care-access worst (8%) because two of its inputs are county-level."* Honest, quantified, not overclaimed.

## Lever 1 - tract-level HPSA (raises care_access within-county share)

Feasibility confirmed: `data/raw/hrsa_hpsa_pc.csv` already carries the geography. Of ~20,290 designated rows, **57% (11,632) are `HPSA Component Type Description == "Census Tract"`**; 1,574 are County Subdivision; only 2,240 are genuinely Single County. `pipeline/build_hpsa.py:51` currently does `groupby(county_fips).max()` and discards all of it.

Steps (each with a measure-first gate):
1. **Resolve tract components → tract GEOID.** Risk: `HPSA Component Source Identification Number` is not a clean 11-digit GEOID (e.g. `172999721Q`). Probe whether a clean tract FIPS is derivable (a different column, or a documented HRSA encoding). If not, fall back to `Common Postal Code`/`HPSA Postal Code` (24% filled - direct ZIP) for the rows that carry it.
2. **Map tract → ZCTA** via the existing `zcta_tract_xwalk.parquet` (area/pop-weighted); keep county-MAX only for Single-County / Unknown components (they have no finer geography).
3. **Rebuild** `hpsa → join`; recompute the empirical within-county variance share of `care_access` and the composite.
4. **GATE:** keep it only if within-county `care_access` share rises materially (target: toward health-need's ~31%) AND the sub-county validation (Lever 3) does not degrade. If tract-HPSA is noisy/wrong-signed within county (like `safetynet` was), revert - same discipline that rejected §1.1 and the drive-time E2SFCA.

### Prototype run (2026-06-30) - DO NOT ship the naive versions

Measured against the local national build (`HPSA Geography Identification Number` is the clean 11-digit tract GEOID; area-weighted tract→ZCTA via `zcta_tract_xwalk`):

| Variant | within-county var share | within-county corr vs life-exp (neg=correct) | coverage (>0) |
|---|---|---|---|
| county-max (current) | 0.0% | flat | 91% |
| **pure tract-level** (non-designated tracts = 0) | **38.4%** | **-0.21 ✓** | 9% |
| naive hybrid (tract else county-max fallback) | 4.1% | **+0.07 ✗ WRONG-SIGNED** | 93% |

Findings:
- The tract signal is **real and correctly signed**, but only 9% of ZCTAs sit in a tract-designated shortage (57% of *designations* are Census Tract, but they concentrate in specific low-income pockets).
- **The naive hybrid flips the within-county sign** - backfilling the 91% with county-max mixes two scales (tract-specific score vs county worst-case), so tract-designated pockets read *lower* than their county-max surroundings. Same failure mode as `safetynet`.

Correct build (unresolved - needs a real modeling pass, not a swap):
- Weight by **population**, not tract land area (need tract population in the crosswalk; not currently there).
- Model non-tract designations (11,717 population-group + single-county) properly instead of county-max backfill - a non-designated tract should read **0 shortage**, not its county's worst tract.
- Decide replace-vs-augment: pure-tract (non-designated=0) is correctly signed but drops HPSA's between-county signal (the +0.20 signed-r the audit valued). May need to keep county HPSA for between-county AND add a separate sub-county tract-HPSA - each gated on its own validation.

Bottom line: tract-HPSA is worth doing but is a research task; the quick version is wrong-signed and was not shipped.

## Lever 2 - medical_debt

County-only in the free Urban Institute release; no clean sub-county source. Options: leave (honest county caveat, already documented), or down-weight within `care_access`. Do NOT fabricate sub-county detail. Low priority.

## Lever 3 - prove it (sub-county validation, the real ceiling)

Within-county *inputs* mean nothing without a within-county *outcome* to validate against. Current anchors: NY SPARCS PQI (ZIP-level ACSC), TX PUDF ACSC, USALEEP tract life-expectancy → ZCTA. All genuinely sub-county.

1. **Add state ZIP-level hospital-discharge datasets** as within-county ACSC anchors: CA HCAI (ex-OSHPD) PDD, then FL/NJ/etc. Each new state = an independent within-county falsification test. Highest leverage for the *claim*.
2. **Publish the within-county correlation** of the composite vs tract-LE and vs each state's ACSC as the headline sub-county validity number - now with the county-block CIs added in §3.1 (`validate_temporal`/`validate_fqhc_lever`), so the inference is spatially honest.
3. Wire the `subcore_resolution` tags into a per-ZIP "sub-county resolution fraction" surfaced in the UI/methodology, so the claim is self-documenting.

## Sequence

1. Surface the measured 24.1% / 31.2% / 7.6% numbers in METHODOLOGY/VALIDATION (honest headline - zero new data). **Do first.**
2. Prototype Lever 1 step 1 (tract-component → GEOID); gate on the within-county lift before rebuilding.
3. Lever 3.1 (one new state's discharge data) as the validation payoff.

Everything gates on a measured within-county improvement, not on the change being conceptually nicer.

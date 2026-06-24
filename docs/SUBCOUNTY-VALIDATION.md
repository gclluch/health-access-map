# Sub-county validation - closing the county-resolution blind spot

**Status: SHIPPED harness 2026-06-23 (`python -m pipeline.validate_subcounty`).** NY-only
coverage; a cross-state confirmation (CA HCAI ZIP PQI) is the open follow-up.

## The blind spot this closes

Every access-sensitive outcome in `outcomes.parquet` (ACSC preventable hospitalizations,
premature death, infant mortality) is **county-level**. Measured directly on the live build,
**25.2% of the composite's variance is *within* county** (provider_supply / care_access ~17%;
`shortage_designation` 0% by construction). That entire within-county slice is invisible to
the standard `diagnostics` gate - so any ZCTA-resolution access measure (the adaptive
catchment, HPSA, FQHC desert) literally cannot be rewarded or penalized by a county-flat
outcome. The "spatial-signal ceiling" (ROADMAP §Conclusion) was declared at county resolution.

## The instrument

**NY SPARCS Prevention Quality Indicators by patient ZIP** (AHRQ `PQI_90` overall ACSC
composite, observed + risk-adjusted *expected* rate per 100k, 2009-2023, Socrata `5q8c-d6xq`,
free, **observed not modeled**). PQIs are the textbook ambulatory-care-sensitive outcome, here
at ZIP resolution. Pooled 2019-2023, filtered to obs>0, pop>=1000, >=4 pooled years, multi-ZCTA
counties → **1,265 ZCTAs / 61 counties**. The **within-county** correlation (county mean removed
from both sides) is the test county outcomes cannot do; **O/E** (observed/expected) is the
risk-adjusted form that removes the age/sex-mix confound.

## Results (within-county O/E unless noted)

| Column | pooled-O/E | **WITHIN-O/E** | Read |
|---|---|---|---|
| `access_gap_score` | +0.469 | **+0.482** | **The index resolves real sub-county access signal** the county gate is blind to. |
| `health_need` | +0.515 | +0.484 | Dominates even at sub-county ACSC resolution. |
| `social_vulnerability` | +0.415 | +0.462 | Strong. |
| `disability` (sub) | +0.491 | +0.468 | Strongest single sub-score. |
| `care_access` | +0.318 | **+0.305** | **Its best showing anywhere** - access signal is sharpest against a sub-county, risk-adjusted, access-sensitive outcome. Still modest; need dominates. |
| `insurance` (sub) | +0.268 | +0.357 | Genuine access piece, holds up. |
| `preventive_use` (sub) | +0.379 | +0.388 | Holds up. |
| `provider_supply` (sub) | +0.128 | **+0.065** | Weak even at sub-county (caveat: NY is urban-heavy, low supply variance). |
| `shortage_designation` (sub) | +0.052 | **−0.000** | **Zero sub-county resolution** - county-max HPSA is a county input in ZCTA clothing. |
| `safetynet_access` (sub) | +0.126 | **−0.119** | **Wrong-signed within county** - the A2 desert×poverty reframe fixed the sign at *county* validation resolution, but the FQHC-clustering confound re-emerges at sub-county scale. NY-only; needs cross-state confirmation before acting. |

## What this means (partial Phase-2 fork read, NY-only, pending amenable mortality)

1. **The sub-county-resolution objection is confirmed real** - the composite resolves
   genuine within-county access-sensitive variance (+0.48). The tool is a true ZCTA
   instrument, not a county one in disguise. This is a validation the county gate could
   never give.
2. **But care_access magnitude is mostly a real ceiling, not purely an artifact** - even
   against a clean sub-county ACSC outcome, health_need dominates (+0.48) and care_access is
   modest (+0.31). The resolution fix raises care_access to its best value, but does not flip
   the hierarchy.
3. **Two structural findings the county gate could never surface, both actionable:**
   - `shortage_designation` carries **zero** sub-county information → a tract-level HPSA
     refinement (previously rejected as a "wash" *against county outcomes*) may now be worth
     re-testing *against this sub-county gate*. The wash verdict was resolution-limited.
   - `safetynet_access` is **wrong-signed within-county** → the FQHC desert×poverty form is
     not confound-free at sub-county scale. Re-examine before trusting it as a ZCTA-level
     barrier. Confirm in a second state (CA) first.

## Follow-up probe: re-test sub-county HPSA against THIS gate (2026-06-23)

`shortage_designation` showed **0.000** within-county resolution above (county-max HPSA is
constant within a county). ROADMAP rejected sub-county HPSA as "a wash" - but that test was
run against **county** outcomes (0.991 correlated with county-max), which by construction
cannot see within-county variance. Re-tested here against the sub-county gate:

Built a tract-confined HPSA (11,474 Census-Tract designations confined to overlapping ZCTAs
via the 2010 ZCTA-tract crosswalk; `tract-only` = pure tract designations, no county fallback)
and ran it through the NY PQI within-county test:

| HPSA variant | within-county variance | within-O/E | partial within-O/E* |
|---|---|---|---|
| county-max (shipped) | **0.00** | n/a (constant) | n/a |
| tract + county fallback | 1.79 | +0.073 | - |
| **tract-only** | 16.58 | **+0.275** | **+0.089** |

*partial controls for within-county health_need + social_vulnerability + provider_supply.

**Verdict: the ceiling was soft, not hard.** The county gate was genuinely hiding sub-county
HPSA signal (county-max = 0.00 within-county; tract-only = +0.275 raw). But ~2/3 of it is the
within-county deprivation gradient (tract-HPSA corr +0.38 health_need / +0.44 social_vuln), so
partial-r collapses to **+0.089**. Crucially it does **not** collapse to ~0 or wrong-signed like
every prior rejected probe (hospital-quality +0.075, SUD −0.01, cardiology −0.06) - it keeps a
small, correctly-signed, additive within-county component that county-max provides **zero** of.

So: the "wash" verdict largely **stands** for national county validation, but it was masking a
modest real sub-county signal. +0.089 (NY-only, urban-heavy) is below the project's usual ship
bar, so **do not ship tract-HPSA yet** - but it is direct proof the declared spatial ceiling is
an evaluation artifact at the margin, not a hard floor. Re-test nationally if/when a second-state
or amenable-mortality sub-county anchor lands.

## Robustness: NY ex-NYC (2026-06-23)

CA's ZIP-level PQI is **restricted** (Limited Data Request; only county-level is public), so a
true second-state replication isn't freely available. Instead, re-ran on NY excluding the 5 NYC
boroughs (1092 ZCTAs / 56 counties - the suburban/rural subsample that mirrors national
urbanicity far better than NYC-dominated full NY):

| within-county O/E | NY all | **NY ex-NYC** | NYC only |
|---|---|---|---|
| `safetynet_access` | −0.111 | **−0.111** | −0.127 |
| `hpsa_tractonly` | +0.275 | **+0.285** | +0.296 |
| `care_access` | +0.305 | +0.275 | +0.523 |
| `provider_supply` | +0.065 | +0.087 | −0.161 (urban confound) |

**Both key findings hold.** The safetynet wrong-sign is negative in all three subsamples
(−0.11 to −0.13) - not a NYC artifact, and it survives in the representative ex-NYC subsample.
The sub-county HPSA signal is slightly *stronger* ex-NYC. `provider_supply` flips from −0.16 in
dense NYC to +0.09 ex-NYC, the textbook urbanicity supply confound. This substantially de-risks
the urban-heavy caveat for the two actionable findings, short of a true second state.

**Most actionable: the `safetynet_access` wrong-sign** - a *shipped, scored* sub-score that
contributes a wrong-signed component at sub-county resolution in all 3 subsamples. Re-examine
the FQHC desert×poverty form (or de-weight it) before trusting it as a ZCTA-level barrier.

## Caveats

- **NY only.** Tests sub-county signal *existence*, not national generalization (NY is
  urban-heavy: NYC's five counties dominate, compressing supply variance). Add CA HCAI ZIP
  PQI (manual hcai.ca.gov download → `--extra-csv`, cols `zcta5,obs,exp`) to confirm.
- ZIP ≈ ZCTA join (no crosswalk); PO-box/point ZIPs fall out via the pop>=1000 filter.
- Read-only diagnostic; never feeds the composite.

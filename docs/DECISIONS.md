# Decision ledger - what we tried, kept, and rejected

The compact institutional memory: every lever, its result, and **why**, so nobody re-runs a
dead end. Replaces the old per-layer roadmap (completed work doesn't need a full roadmap). The
narrative logic lives in [METHODOLOGY.md](METHODOLOGY.md); the validation evidence in
[VALIDATION.md](VALIDATION.md).

**Gate for any change:** re-run `pipeline.diagnostics` + `pipeline.verify_bands` (+
`pipeline.validate_subcounty` for sub-county claims). Ship only if the north star
(`drop_care_access` stays below FULL) and reliability (>=0.93) hold, judged against the
**death-records / ACSC** outcomes, never flu/mammography (the anti-circularity rule).

Current baseline: FULL **0.492** / drop_care_access **0.467** (care access adds +0.025) /
composite **0.495** / split-half **0.955** / scoreable **33176**.

## Kept (passed the gate)

| Lever | Effect | Why it worked |
|---|---|---|
| Hierarchical percentile model (SVI method) | the backbone | skew-robust, interpretable, re-ranked per level |
| **E2SFCA + adaptive catchment (C3)** | provider_supply mean\|r\| 0.173→**0.273**; clean-r +0.13→+0.265 | the project's main win - removed the fixed-radius urbanicity confound (structural, not new data) |
| FQHC reframe → desert×poverty (A1/A2) | sub-score 0.118→0.233 | raw FQHC access is wrong-signed (clinics cluster in high-need areas); need-relative form is correctly signed |
| Drop `household` sub-score (A1) | removed wrong-signed members | age structure is context; limited-English wrong-signed vs infant mortality (immigrant-health paradox) |
| Provider-type breadth (dental, OB/GYN) | surfaces real deserts | distinct care axes, distinct deserts |
| **HPSA as own `shortage_designation` (C5)** | FULL 0.486→**0.492**, agreement →0.495 | official designation **orthogonal** to E2SFCA density (corr 0.05); clean +0.20 on its own |
| Digital/telehealth access (C6, broadband) | split-half 0.943→**0.955** | completeness/reliability add (NOT signal - collinear w/ supply); fills the telehealth axis |
| Rank-uncertainty bands (B) + PLACES noise (B3) | honest 5-95 bands | low-conf ZCTAs get visibly wider bands; closes the uncertainty model |
| Fay-Herriot ACS shrinkage | improved 3/4 outcomes | shrink noisy small-area rates to county mean |
| **Multiplicative geometric lens** (this session) | targeting construct, default unchanged | OECD non-compensatory aggregation - need∩barrier coincidence. See [RATIONALE](RATIONALE.md) |

## Rejected (documented negatives - do NOT re-run)

| Lever | Result | Root cause |
|---|---|---|
| Realized utilization C1 (Medicare visit-rates) | regressed 0.480→0.470 | **circular** w/ flu/mammo; LE r=0.00; saturated ~90%, 65+-only, need-endogenous |
| Condition-specific quality C1-redux (Dartmouth diabetic process) | clean +0.036 | HbA1c testing ~85-90% saturated, county-level, 2019 vintage |
| Capacity-weight NPIs by Medicare claims (C2) | wash 0.132→0.129 | weakness wasn't dormant registrations; zeroed pediatricians (Medicare mismatch) |
| Need-adjusted supply | not scored | double-counts health need (already its own dimension) |
| Raw facility-count (pharmacy, NPPES E2) | **−0.17 wrong-signed** | retail clusters in dense high-need urban areas. *Rule: any raw facility COUNT is wrong-signed; must be desert×need, at which point it duplicates safety-net* |
| Hospital quality / ED-wait / HCAHPS (Care Compare) | star raw +0.228 → **partial +0.075** | not orthogonal (corr 0.28 health_need); surviving signal is its 30-day-mortality component (outcome-adjacent). *Rule: "a rate not a count" does NOT clear the clustering confound* |
| SUD / behavioral desert (SAMHSA/NPPES E2) | +0.111 → **partial −0.010** | corr +0.42 w/ provider_supply - the SUD desert IS the rural/supply gradient |
| Demand-matched specialist (cardiology mismatch) | +0.273 → **partial −0.06** | mismatch = need − supply, already summed; cardiology 0.80 collinear w/ primary supply |
| Mental-health / dental HPSA; MUA/IMU index | subsumed / −0.04 | MH/DH-HPSA corr 0.59/0.75 w/ PC-HPSA; MUA elderly term makes retirement areas read "served" |
| Empirical (regression) weights | floors access at ~5% | optimizes "predict mortality" not "measure the gap"; offered only as a labeled diagnostic preset |
| Drive-time E2SFCA | infeasible | no free precomputed provider-reachable matrix; circuity's value is within-rural variance, needs routing. Adaptive catchment is the analog |
| Medicaid / new-patient acceptance (C4) | no data | no free national file; only the near-saturated CMS NDF assignment flag |
| Sub-county HPSA (vs county outcomes) | wash 0.206→0.209 | **REOPENED** - that test was county-resolution-blind. Against the sub-county gate it's tract-only +0.089 additive within-county (small, below ship bar). See [VALIDATION](VALIDATION.md) |
| PM2.5 / ozone (this session) | orthogonal but +0.09-0.12 | first genuinely-orthogonal axis (survives partial-r, mechanism-consistent vs ACSC) but modest, and a **need**-axis not access. Candidate for a `health_need` environmental sub-score, not shipped |

## What's next (open)

1. **Confirm the sub-county findings in a 2nd state** - `safetynet_access` wrong-signed within-county (−0.11, robust ex-NYC) and the tract-HPSA +0.089. CA's ZIP PQI is restricted; needs another open-data state.
2. **Amenable mortality** - `build_amenable.py` is wired; needs the one manual CDC WONDER county pull (API is national-only). Unlocks the frontier-gap construct.
3. **Frontend lens toggle** - `access_gap_mult_pctile` is already in the payload; only the UI control is left.
4. **PM2.5 → `build_environment.py`** only if adopting it for health_need completeness (not an access win).

**Ceiling verdict:** soft, not hard. Sub-county/orthogonal probes each found small (~+0.09) genuinely-additive signal the old county-level, deprivation-collinear gate couldn't see - but the "need-dominated, diminishing-returns" conclusion holds. The productive frontier is completeness + construct + sub-county validation, not new spatial inputs.

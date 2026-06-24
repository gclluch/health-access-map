# Decision ledger - what we tried, kept, and rejected

The compact institutional memory: every lever, its result, and **why**, so nobody re-runs a
dead end. Replaces the old per-layer roadmap (completed work doesn't need a full roadmap). The
narrative logic lives in [METHODOLOGY.md](METHODOLOGY.md); the validation evidence in
[VALIDATION.md](VALIDATION.md).

**Gate for any change:** re-run `pipeline.diagnostics` + `pipeline.verify_bands` +
**`pipeline.bootstrap_gate`** (95% CIs on every margin - ship only if the relevant margin CI
**excludes 0**, not just the point estimate) (+ `pipeline.validate_subcounty` for sub-county
claims). Ship only if the north star (`drop_care_access` stays below FULL) and reliability
(>=0.93) hold, judged against the **death-records / ACSC** outcomes, never flu/mammography
(the anti-circularity rule).

Current baseline: FULL **0.510** / drop_care_access **0.467** (care access adds **+0.043**) /
composite **0.514** / clean-4 **0.547** / split-half **0.954** / bands ALL PASS / scoreable **33176**.
(Up from FULL 0.492 at session start: dropped the mediator `preventive_use`, added the
`medical_debt` affordability barrier - see Kept below.)

## Kept (passed the gate)

| Lever | Effect | Why it worked |
|---|---|---|
| Hierarchical percentile model (SVI method) | the backbone | skew-robust, interpretable, re-ranked per level |
| **E2SFCA + adaptive catchment (C3)** | provider_supply mean\|r\| 0.173→**0.273**; clean-r +0.13→+0.265 | the project's main win - removed the fixed-radius urbanicity confound (structural, not new data) |
| FQHC reframe → desert×poverty (A1/A2) | sub-score 0.118→0.233 (county) | raw FQHC access is wrong-signed (clinics cluster in high-need areas); need-relative form is correctly signed **between** counties... |
| **safetynet_access → unscored** (kept displayed) | composite within-county +0.583→**+0.601**; clean county-r flat 0.502→0.501 | ...but **wrong-signed WITHIN** counties in 85% of states (resolution-dependent). Removed from the composite for a ZCTA-native tool; kept as a displayed sub-score. `scored=False` in taxonomy |
| **preventive_use → unscored** (moved to realized-access layer) | composite clean-r 0.501→**0.516**; care access still adds signal | It is **utilization (a mediator/Donabedian "process"), not a barrier** - and `mammouse_pct` is literally the `mammography` validation outcome (criterion contamination). Removing the mediator *improved* the composite (it had double-counted the PLACES need inputs). `scored=False`; shown as realized access. |
| **medical_debt** (Urban Institute, scored barrier) | composite clean-r 0.519→**0.547**; care_access 0.393→**0.480**; care access marginal value →**+0.043** | **The first new scored barrier to SURVIVE partial-r (+0.27)** vs need+vuln+care_access - an AFFORDABILITY barrier (under-insured / cost-burden) distinct from coverage+poverty (corr ~0.4, not subsumed). Clean signed-r +0.48; strongest care sub-score (mean\|r\| 0.40). County-level (0 sub-county, like HPSA). Free GitHub CSV (`build_medicaldebt.py`). The redemption: replaced the contaminated mediator with a legitimate, stronger barrier. |
| Drop `household` sub-score (A1) | removed wrong-signed members | age structure is context; limited-English wrong-signed vs infant mortality (immigrant-health paradox) |
| Provider-type breadth (dental, OB/GYN) | surfaces real deserts | distinct care axes, distinct deserts |
| **HPSA as own `shortage_designation` (C5)** | FULL 0.486→**0.492**, agreement →0.495 | official designation **orthogonal** to E2SFCA density (corr 0.05); clean +0.20 on its own |
| Digital/telehealth access (C6, broadband) | split-half 0.943→**0.955** | completeness/reliability add (NOT signal - collinear w/ supply); fills the telehealth axis |
| Rank-uncertainty bands (B) + PLACES noise (B3) | honest 5-95 bands | low-conf ZCTAs get visibly wider bands; closes the uncertainty model |
| Fay-Herriot ACS shrinkage | improved 3/4 outcomes | shrink noisy small-area rates to county mean |
| **Multiplicative geometric lens** (this session) | targeting construct, default unchanged | OECD non-compensatory aggregation - need∩barrier coincidence. See [RATIONALE](RATIONALE.md) |
| **Access-beyond-deprivation lens** (`care_access_resid_pctile`) | orthogonal to need/vuln (**0.05**) yet residual still tracks low life expectancy **+0.137** (vs +0.47 raw) | `care_access_pctile` residualized (OLS) on health_need + social_vulnerability, re-ranked. A **selectable diagnostic lens, not in the composite** - isolates *structural* access from the deprivation gradient, the direct answer to the ~1.6-effective-dimensions critique. Proof access is independently outcome-relevant **net of poverty**. Weight-independent (server-computed). |
| **`social_vulnerability` kept despite county-redundancy** (decision, this session) | bootstrap paired margin `drop_social_vulnerability` **−0.008, CI [−0.011,−0.004]** (excludes 0): dropping it slightly *raises* county-outcome agreement | It is the most collinear dimension (need↔vuln **0.74**), so the county-level gate re-counts its variance. **KEPT** by construct (the 5 A's enabling axis) and because it carries the **strongest within-county signal** (+0.524 - the resolution the tool actually runs at). **NOT down-weighted**: tuning the default against an all-cause *county* outcome is the category error the project forbids ([VALIDATION](VALIDATION.md) §2). Recorded with eyes open, not silently. |

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
| **Accommodation** - FQHC operating-hours availability (this session) | no signal | The one free on-disk Accommodation source. Built hours-weighted reachable safety-net (sum / nearest / avg variants). Clean signed-r **+0.005 to +0.046**, within-county ~0, `acc_sum` wrong-signed within-county. The "Operating Hours per Week" field is too flat (median 40, IQR 35-45) to capture real after-hours/weekend variation. Urgent-care NPIs not built (facility-count → predicted wrong-signed, 11GB pass). |
| **Acceptability** - ACS Medicaid-coverage rate (this session) | +0.278 → partial **−0.064** | The non-spatial demand-side proxy. Strong raw signal but **collapses in partial-r** (corr +0.57 socioeconomic, +0.59 health_need) - it is the poverty/deprivation gradient already scored, restated. Surfaced as displayed **context** (not scored). |
| **Acceptability - real Medicaid-acceptance** (NY scrape-to-calibrate template, this session) | orthogonal but **unsigned** | Pulled NY's actual **Medicaid Enrolled Provider Listing** (1.1M providers, `keti-qx5t`) and computed per-ZCTA acceptance = Medicaid-enrolled clinical providers ÷ NPPES providers. **The acceptance ratio IS genuinely orthogonal** to provider supply (corr **+0.06**) and poverty (+0.02) - the new axis we sought. BUT **wrong-signed as a barrier** (−0.09 vs ACSC, −0.11 within-county): acceptance is **need-endogenous** (providers enroll in Medicaid where Medicaid patients are = high-need areas, same trap as FQHCs). Need-relative form (providers per Medicaid enrollee) → +0.027 PQI / +0.003 within-county / **−0.141 partial** (no clean signal). Testing the premise on the cleanest state **killed the multi-state national scrape** before building it. *Conclusion: even real provider-acceptance data does not yield a correctly-signed scored barrier - the access frontier is closed for available data.* |
| PM2.5 environmental burden (CDC tract, this session) | sub-score gate FAIL | The first genuinely-*orthogonal* axis (corr ~0 w/ gradient, survives partial-r +0.119 vs county ACSC, mechanism-consistent). BUT as a `health_need` sub-score it **dilutes** the dimension (0.518→0.511) and regresses the composite (county 0.503→0.501, within-county 0.601→0.597) - its solo clean-r (+0.098) is too weak to survive averaging into 4 strong disease sub-scores. *Same lesson as broadband (C6): orthogonal-but-weak averaged into a strong dimension dilutes, not lifts.* Gated offline before any build; not shipped. (CDC Socrata `vpk8-vfhm`, server-side annual mean.) |

## What's next (open)

1. ~~**Decide `safetynet_access`**~~ ✅ DONE - removed from the composite (`scored=False`), kept displayed. Confirmed wrong-signed *within*-county nationally (85% of states, NY ACSC + national USALEEP); resolution-dependent. Lifted composite within-county +0.583→+0.601, clean county-r flat, north star held. The national check (`validate_subcounty --national`) replaced the need for a 2nd ACSC state (MD county-only, CA restricted).
2. ~~**Amenable mortality**~~ ✅ FULLY WIRED - now an optional outcome in `diagnostics` + `bootstrap_gate`, with the frontier analysis `bootstrap_gate.amenable_focus()` (care-access marginal value + **partial r vs treatable mortality | need,vuln**, cluster-bootstrap CIs; proven correct on synthetic data). Needs only the one manual CDC WONDER county pull (API is national-only); then **`make amenable`** runs the whole re-gate. See [VALIDATION](VALIDATION.md) §4.
3. ~~**Frontend lens toggle**~~ ✅ DONE - both the coincidence lens (`access_gap_mult`) and the new access-beyond-deprivation lens (`care_access_resid_pctile`) are selectable in the Color-by + Rankings menus.
4. **Orthogonalized composite (full)** - the lens orthogonalizes only care_access for display. A fully Gram-Schmidt-orthogonalized *composite* (sequential residualization of all three dimensions) is the bigger, riskier move - it changes the headline score, so it needs its own gate pass. Not started.
5. **PM2.5 → `build_environment.py`** only if adopting it for health_need completeness (not an access win).

**Ceiling verdict:** soft, not hard. Sub-county/orthogonal probes each found small (~+0.09) genuinely-additive signal the old county-level, deprivation-collinear gate couldn't see - but the "need-dominated, diminishing-returns" conclusion holds. The productive frontier is completeness + construct + sub-county validation, not new spatial inputs.

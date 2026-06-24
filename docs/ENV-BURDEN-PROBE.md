# Environmental burden (PM2.5) probe - the first genuinely-orthogonal axis

**Status: PROBED 2026-06-23, borderline-positive, NOT shipped.** A new *risk* axis, not
access - would belong in `health_need`, not `care_access`. Recorded so it isn't re-run blind.

## Why probe it

Every rejected access probe (pharmacy, SUD, hospital-quality, cardiology, sub-county HPSA)
failed the same way: **collinear with the poverty/rural/supply gradient**, so raw signal
collapses in partial-r. Environmental exposure is the one candidate that is *upstream* of and
mechanistically distinct from deprivation - a poor rural tract can have clean air; a
middle-income suburb downwind of a highway/port can have dirty air. So PM2.5 is the cleanest
test of whether the "orthogonality ceiling" is truly hit or just an artifact of testing only
deprivation-collinear measures.

## Data (fully headless - the clean path)

CDC EPHT **Daily Census Tract-Level PM2.5** (data.cdc.gov Socrata `vpk8-vfhm`, 2021-2022),
**server-side aggregated** to an annual tract mean (`$select=ctfips,avg(ds_pm_pred)
$group=ctfips`) - 83,776 tracts, 3.4-18.4 µg/m³. No daily download. (CDC EJI / EPA EJScreen
were both form-gated / offline; this Socrata aggregation is the reliable route. Use the EJI EBM
raw PM2.5/ozone columns only if a tract-level EJI CSV is later obtained - never the EJI/EJScreen
*composite*, which is poverty × demographics by construction.)

## Results

PM2.5 is genuinely **orthogonal** to the scored gradient (corr health_need +0.19, social_vuln
+0.12, care_access −0.02 nationally; **−0.00 with health_need within-county**), and its signal
**survives partial-r** where every deprivation-collinear probe collapsed:

| PM2.5 vs outcome | raw r | partial r (vs need+vuln+access) |
|---|---|---|
| preventable_hosp (county, n=3202) | +0.183 | **+0.119** |
| premature_death (county) | +0.015 | −0.125 (wrong-signed) |
| infant_mortality (county) | −0.006 | −0.080 |
| NY sub-county PQI O/E (n=1207) | +0.091 | **+0.087** |

**Mechanism-consistent:** PM2.5's health effect is cardiopulmonary, so it lands on ACSC /
preventable hospitalization (+0.119) and sub-county ACSC (+0.087) - the respiratory/cardiac
access-sensitive outcomes - while staying ~0 / wrong-signed on infant mortality and all-cause
premature death. That selective pattern is evidence it is real signal, not a gradient artifact.

## Verdict

**The orthogonality ceiling is soft, not hard.** PM2.5 is the first axis found that is both
orthogonal to the deprivation gradient AND retains correctly-signed, mechanism-consistent signal
in partial-r (+0.09-0.12 vs ACSC). But the magnitude is at the margin of the ship bar (comparable
to the sub-county HPSA finding +0.089), and it is a **need/risk** axis (environmental health), not
an access barrier - so it does not address care_access. If added it should be a new
`environmental` sub-score under `health_need` (for completeness + a real orthogonal signal), gated
against the standard harness and re-confirmed once amenable mortality lands. It will NOT lift
care_access and should not be sold as an access win.

*Reusable puller:* `pull_pm.py` (scratchpad) - the Socrata aggregation query; promote to
`build_environment.py` if shipped.

# Coordination - parallel work on the pipeline

Two work streams are touching `pipeline/` in parallel. This file records the ownership
boundary so we don't clobber each other.

## Stream A - Supply / care-access enrichment

**Owns:** `pipeline/build_providers.py`, `pipeline/build_supply.py`, and the provider/
supply constants in `pipeline/config.py`. Also the supply members in `pipeline/taxonomy.py`.

**Doing:** enriching the spatial-supply layer with more provider specialties (dental,
OB-GYN added; more specialties planned), each as an E2SFCA `*_2sfca` column feeding new
`care_access` sub-scores.

## Stream B - Composite validation / weights (this stream)

**Owns:** `pipeline/build_outcomes.py` (new), `pipeline/validate.py` (new), the
weight/validation tail of `pipeline/join_and_score.py`, `frontend/.../MethodologyPanel`,
weight presets, and `docs/COMPOSITE-ENHANCEMENT.md`.

**Doing:** replacing the single life-expectancy-regression weight set with honest,
multi-anchor outcome validation (ACSC preventable hospitalizations, premature death,
optional amenable mortality), exposed as labeled outcome-anchored weight presets.

**Will NOT touch** `build_providers.py`, `build_supply.py`, or `config.py` while Stream A
is active. New constants live inside the new modules.

## The decoupling contract (why this is safe)

- Scoring is generic over `taxonomy.py`: new `*_2sfca` members are absorbed automatically.
- Weights/validation operate at the **3-dimension** level, invariant to how many supply
  sub-scores live inside `care_access`.
- Validation is a **standalone stage** (`pipeline/validate.py`) reading `metrics.parquet`.
  After Stream A rebuilds supply, refresh all weights + validation with one cheap command:
  `python -m pipeline.run --only validate` (no full rebuild). No supply column names are
  hardcoded in Stream B - it reads whatever sub-scores exist.

## Handoff insight for Stream A (from the empirical analysis)

The new dental / OB-GYN 2SFCA scores will validate as **~0 signal against all-cause life
expectancy** - the same way `provider_supply_2sfca` already does (r = -0.01 vs LE;
`safetynet_2sfca` is even wrong-signed at +0.21, a rural/urbanicity confound). That is a
property of the *outcome*, not the supply metric: all-cause LE is a need outcome.

### Update (2026-06-21, Stream B): FQHC safety-net sub-score reframed

Heads-up for Stream A: the scored safety-net barrier no longer uses your `safetynet_2sfca`
E2SFCA column directly - it was **wrong-signed against all 6 independent outcomes** (FQHCs
cluster in high-need areas, so raw "FQHC access" is highest where need is highest). The
composite now scores `safetynet_barrier = FQHC-distance-percentile x poverty` (computed in
`join_and_score.py`), which is correctly signed (mean|r| 0.118 → 0.233) and adds signal
beyond poverty for the access-proximal outcomes. Your `safetynet_2sfca` and the FQHC
distance/sites columns are still built and shown in the detail panel - only the *scored*
barrier changed. If you build a **need-relative E2SFCA** (FQHC capacity per uninsured/poor
person, not per total population), that would be the principled upgrade and we should swap
`safetynet_barrier` for it. Verify any such change with `python -m pipeline.diagnostics`.

### Handoff insight for Stream A (from the empirical analysis)

To validate a supply specialty you need an **access-sensitive** outcome matched to it:
- dental / primary / overall supply  -> ACSC preventable hospitalizations (AHRQ PQI)
- OB-GYN / maternity supply           -> infant mortality
Stream B's `validate.py` provides exactly these anchors + per-sub-score signed
correlations, so once your specialties land, `--only validate` will tell you whether each
one carries real, correctly-signed signal. See `docs/COMPOSITE-ENHANCEMENT.md` §2.

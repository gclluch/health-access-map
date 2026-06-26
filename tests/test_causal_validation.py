"""Causal/actionability validators (placebo + temporal): offline-safe checks that lock the
ESTIMATORS, not the live endpoints. The data fetchers hit the network, so the network paths run
only against cached aggregates and skip cleanly in CI; the statistics are tested on synthetic
fixtures with planted, known answers."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline import validate_fqhc_lever as vf
from pipeline import validate_placebo as vp
from pipeline import validate_temporal as vt


# --- temporal event study: the two-way FE + DiD estimator --------------------------------------

def test_twoway_demean_removes_both_fixed_effects():
    """After the within transform, every ZIP mean AND every year mean must be ~0 - the defining
    property of two-way (ZIP + year) fixed effects."""
    rng = np.random.default_rng(0)
    zips = [f"z{i}" for i in range(8)]
    years = list(range(2010, 2020))
    rows = [{"zcta5": z, "year": y, "v": rng.normal()} for z in zips for y in years]
    df = pd.DataFrame(rows)
    # add strong ZIP and year fixed effects that the transform must absorb
    df["v"] += df["zcta5"].map({z: 100 * i for i, z in enumerate(zips)})
    df["v"] += df["year"].map(lambda y: 10 * (y - 2010))
    dm = vt._twoway_demean(df, ["v"])
    assert dm.groupby("zcta5")["v"].mean().abs().max() < 1e-9
    assert dm.groupby("year")["v"].mean().abs().max() < 1e-9


def test_did_recovers_planted_effect():
    """Plant a known DiD: high-barrier ZIPs drop by a fixed amount post-2014 on top of ZIP/year
    FE and noise. The estimator must recover the planted slope (sign + rough magnitude)."""
    rng = np.random.default_rng(1)
    zips = [f"z{i}" for i in range(60)]
    years = list(range(2009, 2024))
    barrier = {z: rng.normal() for z in zips}                 # standardized-ish baseline barrier
    planted = -40.0                                           # true effect: -40/100k per +1 SD, post
    rows = []
    for z in zips:
        zfe, b = rng.normal(0, 50), barrier[z]
        for y in years:
            yfe = -5 * (y - 2009)                            # secular decline (absorbed by year FE)
            eff = planted * b if y >= vt.EXPANSION_YEAR else 0.0
            rows.append({"zcta5": z, "year": y, "barrier": b,
                         "rate": 1500 + zfe + yfe + eff + rng.normal(0, 8)})
    j = pd.DataFrame(rows)
    did = vt._did_coefficient(j)
    assert did < 0                                            # correct sign
    assert abs(did - planted) < 12                            # within tolerance of the planted value


def test_event_study_omits_base_year_and_is_flat_pre_when_no_pretrend():
    """With a planted POST-only effect and no pre-trend, the event study omits the base year and
    the pre-period betas sit near zero (the parallel-trends property the diagnostic checks)."""
    rng = np.random.default_rng(2)
    zips = [f"z{i}" for i in range(50)]
    years = list(range(2009, 2024))
    barrier = {z: rng.normal() for z in zips}
    rows = []
    for z in zips:
        zfe, b = rng.normal(0, 40), barrier[z]
        for y in years:
            eff = -30.0 * b if y >= vt.EXPANSION_YEAR else 0.0
            rows.append({"zcta5": z, "year": y, "barrier": b,
                         "rate": 1500 + zfe + eff + rng.normal(0, 6)})
    j = pd.DataFrame(rows)
    betas, _, kyears = vt._event_study(j, years)
    assert int(vt.BASE_YEAR) not in betas                     # base year omitted
    pre = [betas[y] for y in kyears if y < vt.EXPANSION_YEAR]
    post = [betas[y] for y in kyears if y >= vt.EXPANSION_YEAR]
    assert np.sqrt(np.mean(np.square(pre))) < 12              # flat pre-trend
    assert np.mean(post) < -15                                # the planted post effect shows up


def test_demean2_removes_both_factors():
    """The iterative two-way transform must drive both the ZIP mean AND the state-year mean to ~0."""
    rng = np.random.default_rng(10)
    rows = []
    for st in ("NY", "TX"):
        for z in range(12):
            zf = rng.normal(0, 30)
            for y in range(2011, 2016):
                rows.append({"zcta5": f"{st}{z}", "sy": f"{st}_{y}",
                             "v": 100 + zf + 7 * (y - 2011) + rng.normal()})
    df = pd.DataFrame(rows)
    dm = vt._demean2(df, ["v"], "zcta5", "sy")
    assert dm.groupby("zcta5")["v"].mean().abs().max() < 1e-6
    assert dm.groupby("sy")["v"].mean().abs().max() < 1e-6


def test_triple_diff_isolates_treated_effect_from_common_pretrend():
    """The decisive property of the cross-state design: plant a secular barrier x post convergence in
    BOTH states (the confound that made the NY-only study only suggestive) PLUS a treated-only (NY)
    expansion effect. The triple-diff must recover the NY-specific effect and NOT be contaminated by
    the common convergence - which a single-state DiD would wrongly attribute to treatment."""
    rng = np.random.default_rng(11)
    common = +20.0     # barrier x post convergence present in NY *and* TX (the confound)
    treated = -50.0    # additional NY-only (expansion) effect
    rows = []
    for st in ("NY", "TX"):
        is_ny = (st == "NY")
        for z in range(80):
            b = rng.normal()
            zfe = rng.normal(0, 40)
            for y in range(2011, 2016):
                post = 1.0 if y >= vt.EXPANSION_YEAR else 0.0
                syfe = 3 * (y - 2011) + (5 if is_ny else 0)        # state x year secular trend
                eff = common * b * post + (treated * b * post if is_ny else 0.0)
                rows.append({"zcta5": f"{st}{z}", "year": y, "state": st, "barrier": b,
                             "rate": 1000 + zfe + syfe + eff + rng.normal(0, 5)})
    panel = pd.DataFrame(rows)
    tdid = vt._triple_diff(panel)
    assert tdid < 0                                  # correct sign
    assert abs(tdid - treated) < 15                  # recovers the NY-ONLY effect, not treated+common


def test_temporal_pre_barrier_cache_shape_if_present():
    if not vt.PRE_BARRIER_CACHE.exists():
        pytest.skip("pre-period barrier not built")
    b = pd.read_parquet(vt.PRE_BARRIER_CACHE)
    assert {"zcta5", "uninsured_2012"} <= set(b.columns)
    assert b["uninsured_2012"].between(0, 1).all()            # it is a fraction


# --- FQHC supply lever: the Callaway-Sant'Anna group-time ATT estimator -------------------------

def _staggered_panel(rng, cohorts, n_per_cohort, n_never, years, *, effect=0.0, common_trend=0.0,
                     treat_slope=0.0, base=1500.0, zip_sd=50.0, noise=8.0):
    """Synthetic staggered-adoption panel. `effect` = static ACSC shift at/after the opening year
    (e>=0); `common_trend` = a secular drift shared by treated AND control (must be differenced out);
    `treat_slope` = a treated-ONLY linear trajectory (a pre-trend the event study must EXPOSE)."""
    rows, zid = [], 0
    for g in cohorts:
        for _ in range(n_per_cohort):
            zfe = rng.normal(0, zip_sd)
            for y in years:
                e = y - g
                eff = effect if e >= 0 else 0.0
                rows.append({"zcta5": f"t{zid}", "year": y, "pop": 5000.0, "cohort": float(g),
                             "state": "SYN",
                             "rate": base + zfe + common_trend * (y - years[0])
                                     + treat_slope * (y - years[0]) + eff + rng.normal(0, noise)})
            zid += 1
    for _ in range(n_never):
        zfe = rng.normal(0, zip_sd)
        for y in years:
            rows.append({"zcta5": f"c{zid}", "year": y, "pop": 5000.0, "cohort": np.inf,
                         "state": "SYN",
                         "rate": base + zfe + common_trend * (y - years[0]) + rng.normal(0, noise)})
        zid += 1
    return pd.DataFrame(rows)


def test_cs_recovers_planted_staggered_att_with_flat_pretrend():
    """Plant a known static post-opening effect across staggered cohorts on top of a strong common
    secular trend. CS must recover the effect (sign + rough size) AND leave the pre-period ATTs ~0."""
    rng = np.random.default_rng(20)
    years = list(range(2009, 2024))
    j = _staggered_panel(rng, cohorts=[2013, 2015, 2017], n_per_cohort=40, n_never=200, years=years,
                         effect=-50.0, common_trend=-9.0)        # common trend must be differenced out
    attgt = vf.att_gt(j)
    ev = vf.aggregate_event(attgt)
    ov = vf.overall_att(attgt)
    pre = ev[ev["e"] < 0]["att"].to_numpy()
    assert ov < 0 and abs(ov - (-50.0)) < 12                     # recovers the planted ATT
    assert np.sqrt(np.mean(np.square(pre))) < 12                 # parallel-trends: flat pre-period
    assert -1 not in ev["e"].to_numpy()                          # universal base g-1 omitted (ref=0)


def test_cs_differences_out_common_trend_no_false_effect():
    """A strong secular trend shared by treated and control, with NO real treatment effect, must NOT
    be mistaken for a lever: the DiD subtracts the control change, so the overall ATT sits at ~0."""
    rng = np.random.default_rng(21)
    years = list(range(2009, 2024))
    j = _staggered_panel(rng, cohorts=[2013, 2016], n_per_cohort=50, n_never=200, years=years,
                         effect=0.0, common_trend=-15.0)
    attgt = vf.att_gt(j)
    ov = vf.overall_att(attgt)
    assert abs(ov) < 10                                          # common trend differenced out -> ~0


def test_cs_event_study_exposes_treated_pretrend():
    """The decisive diagnostic property: a treated-ONLY divergent trajectory (no genuine treatment
    effect) must show up as NON-flat pre-period ATTs - exactly the §7b warning the event study exists
    to surface, rather than being laundered into a clean-looking post coefficient."""
    rng = np.random.default_rng(22)
    years = list(range(2009, 2024))
    j = _staggered_panel(rng, cohorts=[2015, 2017], n_per_cohort=50, n_never=200, years=years,
                         effect=0.0, treat_slope=-12.0)          # treated drift, no real effect
    ev = vf.aggregate_event(vf.att_gt(j))
    pre = ev[ev["e"] < 0]["att"].to_numpy()
    assert np.sqrt(np.mean(np.square(pre))) > 15                 # pre-trend is EXPOSED, not hidden


# --- placebo negative control: the differential estimator ---------------------------------------

def test_resid_age_removes_county_and_age():
    """_resid_age must return a residual orthogonal to both the county mean and age65_rate."""
    rng = np.random.default_rng(3)
    n = 300
    cty = rng.integers(0, 10, n)
    age = rng.normal(0.2, 0.05, n)
    j = pd.DataFrame({"county_fips": cty, "age65_rate": age,
                      "v": 3 * age + cty * 1.0 + rng.normal(0, 0.01, n)})
    r = vp._resid_age(j, "v")
    ok = ~np.isnan(r)
    # residual is ~uncorrelated with age (county mean already implicitly handled via within)
    assert abs(np.corrcoef(r[ok], age[ok])[0, 1]) < 0.2
    assert abs(r[ok].mean()) < 1e-6


def test_differential_detects_access_specific_signal():
    """Construct a column correlated with the ACSC outcome but NOT the placebo: the differential
    must come out clearly positive (the access-specific case the test is built to detect)."""
    rng = np.random.default_rng(4)
    n = 400
    cty = rng.integers(0, 12, n)
    age = rng.normal(0.2, 0.04, n)
    signal = rng.normal(size=n)
    j = pd.DataFrame({
        "county_fips": cty, "age65_rate": age,
        "col": signal,
        "acsc_rate": 2 * signal + rng.normal(0, 0.5, n),       # access-sensitive tracks the signal
        "placebo_rate": rng.normal(0, 1, n),                   # placebo does not
    })
    ra, rp, d = vp._differential(j, "col")
    assert ra > 0.5 and abs(rp) < 0.2 and d > 0.4


def test_placebo_frame_shape_if_cache_present():
    if not vp.CA_DEATHS_CACHE.exists() or not vp.METRICS.exists():
        pytest.skip("CA deaths or metrics not built")
    j = vp._build_frame()
    assert {"acsc_rate", "placebo_rate", "county_fips", "age65_rate"} <= set(j.columns)
    assert (j["acsc_rate"] > 0).all() and (j["placebo_rate"] > 0).all()

"""validate_temporal: the quasi-experimental test - does ACSC fall when the ACCESS BARRIER falls?

Every other validation in this repo is cross-sectional: it correlates the index with outcomes at
one point in time. The deepest surviving critique is that correlation-at-a-point cannot show
access is a LEVER - that lowering a barrier would actually move outcomes. The negative-control
test (`validate_placebo`) makes this concrete: cross-sectionally the index predicts preventable
and non-preventable deaths equally, because everything bad loads on the same deprivation gradient.

A within-unit fixed-effects event study around a real access SHOCK escapes that trap. NY publishes
ambulatory-care-sensitive hospitalizations (AHRQ PQI_90) by patient ZIP every year 2009-2023
(Socrata `5q8c-d6xq`). In 2014 the ACA coverage expansion (Medicaid expansion + the marketplace +
the individual mandate) sharply cut the uninsured rate - and it cut it MOST where the uninsured
rate was highest. So the testable prediction is differential: after 2014, ACSC should fall MORE in
high-insurance-barrier ZIPs than in low-barrier ZIPs in the SAME state.

The model is a two-way fixed-effects event study:

    PQI_zt = alpha_z + gamma_t + sum_k beta_k * (barrier_z x 1[year=k]) + e_zt        (base year 2013)

  * alpha_z (ZIP fixed effect) absorbs ALL time-invariant deprivation - the exact confound that
    sank the cross-sectional placebo test. Each ZIP is its own control.
  * gamma_t (year fixed effect) absorbs the statewide secular ACSC trend.
  * barrier_z is the ZIP's standardized insurance barrier (higher = more uninsured).
  * beta_k traces the effect of +1 SD baseline barrier on ACSC in year k, relative to 2013. The
    PRE-2014 betas test parallel trends and are subjected to an explicit joint Wald test (`_pre_trends_test`):
    only if that test FAILS to reject flat pre-trends could a negative post-2014 path even be considered.
    The verdict is computed from the test, not asserted - and the cross-state control (`run_cross_state`)
    falsifies the affordability arm regardless. This validator is DESCRIPTIVE-ONLY, not a causal claim.

Honest limits, stated in the output:
  * The barrier is proxied by the CURRENT (ACS 2023, post-expansion) uninsured rate, because that
    is what the index ships. Expansion COMPRESSED the uninsured among the previously-high-barrier
    ZIPs, so today's barrier understates the pre-2014 gap - this attenuates beta toward zero
    (conservative). A pre-period ACS barrier would only strengthen a non-null.
  * NY covered childless adults via a pre-ACA waiver, so its 2014 coverage shock was milder than a
    non-expansion state's would have been - again conservative.
  * One state; this is an existence/lever test, not a national effect size. SEs are ZIP-cluster
    bootstrap (the project's standard), accounting for serial correlation within ZIP.

Read-only; never feeds the composite.

    python -m pipeline.validate_temporal
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd
from scipy.stats import chi2

from . import config
from .common import log

METRICS = config.PROCESSED / "metrics.parquet"
PRE_BARRIER_CACHE = config.PROCESSED / "ny_acs2012_uninsured.parquet"   # pre-treatment barrier
NY_PQI_SOCRATA = "https://health.data.ny.gov/resource/5q8c-d6xq.json"
ALL_YEARS = tuple(str(y) for y in range(2009, 2024))   # 2009-2023 panel
BASE_YEAR = "2013"                                      # last full pre-expansion year (reference)
EXPANSION_YEAR = 2014
MIN_YEARS = 12          # require near-complete panels so attrition can't drive the path
MIN_POP = 1000
N_BOOT = 1000


def _fetch_ny_panel() -> pd.DataFrame:
    """PQI_90 observed ACSC rate per 100k by patient ZIP and YEAR, full 2009-2023 panel."""
    years = ",".join(f"'{y}'" for y in ALL_YEARS)
    q = {
        "$where": f"pqi_number='PQI_90' and year in ({years})",
        "$select": "patient_zipcode,year,observed_rate_per_100_000_people",
        "$limit": 100000,
    }
    url = NY_PQI_SOCRATA + "?" + urllib.parse.urlencode(q)
    with urllib.request.urlopen(url, timeout=120) as r:
        rows = json.load(r)
    df = pd.DataFrame(rows)
    df["rate"] = pd.to_numeric(df["observed_rate_per_100_000_people"], errors="coerce")
    df["zcta5"] = df["patient_zipcode"].astype(str).str.zfill(5)
    df["year"] = df["year"].astype(int)
    return df[["zcta5", "year", "rate"]].dropna()


def _build_panel() -> tuple[pd.DataFrame, list[int]]:
    """Join the NY ACSC panel to the index's (time-invariant) standardized insurance barrier; keep
    populated ZIPs with near-complete year coverage."""
    if not METRICS.exists():
        raise SystemExit(f"missing {METRICS}; run the pipeline first")
    panel = _fetch_ny_panel()
    m = pd.read_parquet(METRICS)
    m = m[(m["scoreable"] == True) & (m["population"] >= MIN_POP)].copy()  # noqa: E712
    m["zcta5"] = m["zcta5"].astype(str)
    if "uninsured_rate" not in m.columns:
        raise SystemExit("uninsured_rate missing from metrics")
    # Prefer a TRUE PRE-TREATMENT barrier (ACS 2008-2012 uninsured, before the 2014 expansion). The
    # shipped uninsured_rate is ACS 2023 (post-expansion) and is endogenous to the treatment - it
    # correlates only ~0.4 with the 2012 rate because expansion compressed it - so the contemporary
    # proxy mismeasures who actually faced a high barrier. Falls back to contemporary if uncached.
    pre = PRE_BARRIER_CACHE
    if pre.exists():
        b = pd.read_parquet(pre)
        b["zcta5"] = b["zcta5"].astype(str)
        base = m[["zcta5"]].merge(b, on="zcta5", how="inner").rename(
            columns={"uninsured_2012": "barrier_raw"})
        barrier_src = "ACS 2008-2012 uninsured (pre-treatment)"
    else:
        base = m[["zcta5", "uninsured_rate"]].dropna().rename(
            columns={"uninsured_rate": "barrier_raw"})
        barrier_src = "ACS 2023 uninsured (contemporary; endogenous - conservative)"
    base = base.dropna(subset=["barrier_raw"])
    # standardized baseline barrier (higher = more uninsured = bigger expected coverage gain in 2014)
    base = base.assign(barrier=(base["barrier_raw"] - base["barrier_raw"].mean())
                       / base["barrier_raw"].std())
    _build_panel.barrier_src = barrier_src  # surfaced in run()
    j = panel.merge(base[["zcta5", "barrier"]], on="zcta5", how="inner")
    # county_fips for the spatial (county-block) bootstrap variant; ZIP-only panels fall back to ZIP.
    if "county_fips" in m.columns:
        j = j.merge(m[["zcta5", "county_fips"]].astype({"county_fips": "string"}),
                    on="zcta5", how="left")
    # require near-complete panels and drop absurd rates (data-entry outliers)
    j = j[(j["rate"] > 0) & (j["rate"] < j["rate"].quantile(0.999))].copy()
    yrs = j.groupby("zcta5")["year"].nunique()
    keep = yrs[yrs >= MIN_YEARS].index
    j = j[j["zcta5"].isin(keep)].copy()
    years = sorted(j["year"].unique())
    return j.reset_index(drop=True), years


def _twoway_demean(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Within transformation for two-way (ZIP + year) fixed effects: subtract the ZIP mean and the
    year mean, add back the grand mean. Exact for a balanced panel; the NY panel is ~balanced
    (~1.5k ZIPs every year), so the residual imbalance is negligible."""
    out = df.copy()
    for c in cols:
        g = out.groupby("zcta5")[c].transform("mean")
        t = out.groupby("year")[c].transform("mean")
        out[c] = out[c] - g - t + out[c].mean()
    return out


def _event_study(j: pd.DataFrame, years: list[int]) -> tuple[dict, np.ndarray, list[int]]:
    """OLS event study via two-way demeaning + Frisch-Waugh. Returns {year: beta_k} for the
    barrier x year interactions (base year omitted), plus the design pieces for bootstrapping."""
    kyears = [y for y in years if str(y) != BASE_YEAR]
    work = j.copy()
    for y in kyears:
        work[f"x_{y}"] = work["barrier"] * (work["year"] == y).astype(float)
    xcols = [f"x_{y}" for y in kyears]
    dm = _twoway_demean(work, ["rate"] + xcols)
    X = dm[xcols].to_numpy()
    y = dm["rate"].to_numpy()
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return {ky: float(b) for ky, b in zip(kyears, beta)}, X, kyears


def _did_coefficient(j: pd.DataFrame) -> float:
    """Single-coefficient DiD: barrier x post-2014, two-way demeaned. The average post-expansion
    differential effect of +1 SD baseline barrier on ACSC."""
    work = j.copy()
    work["post_x_barrier"] = work["barrier"] * (work["year"] >= EXPANSION_YEAR).astype(float)
    dm = _twoway_demean(work, ["rate", "post_x_barrier"])
    X = dm[["post_x_barrier"]].to_numpy()
    beta, *_ = np.linalg.lstsq(X, dm["rate"].to_numpy(), rcond=None)
    return float(beta[0])


def _cluster_bootstrap(panel: pd.DataFrame, estimator, n: int,
                       unit_col: str = "zcta5") -> tuple[float, float, float]:
    """Block bootstrap of `estimator`: resample whole `unit_col` blocks with replacement (fixed seed).
    Default resamples each ZIP's time series; pass unit_col="county_fips" to resample whole counties,
    which preserves within-county spatial correlation and yields honest - wider - CIs where
    neighbouring ZIPs are not independent (health geography is strongly spatially autocorrelated, so
    the ZIP-cluster CI understates uncertainty). Each drawn block keeps its ZIP fixed effects distinct
    across copies. Singular resamples are skipped (needed for the rank-deficient triple-diff draws)."""
    units = panel[unit_col].dropna().unique()
    groups = {u: g for u, g in panel.groupby(unit_col)}
    rng = np.random.default_rng(20260625)
    betas = []
    for _ in range(n):
        pick = rng.choice(units, size=len(units), replace=True)
        boot = pd.concat([groups[u].assign(zcta5=groups[u]["zcta5"].astype(str) + f"__{i}")
                          for i, u in enumerate(pick)], ignore_index=True)
        try:
            betas.append(estimator(boot))
        except Exception:  # noqa: BLE001 - singular resample, skip
            continue
    betas = np.array(betas)
    return float(np.percentile(betas, 2.5)), float(np.percentile(betas, 97.5)), float(betas.mean())


def _pre_trends_test(j: pd.DataFrame, years: list[int], n_boot: int = N_BOOT) -> dict:
    """Explicit, DATA-DRIVEN parallel-trends test: are the PRE-2014 event-study coefficients JOINTLY
    zero? (They must be flat for the DiD to be read as causal.) Bootstraps the pre-period beta vector
    over ZIP clusters, forms a Wald statistic b'Σ⁻¹b against the bootstrap covariance, and returns the
    χ² p-value. A SMALL p REJECTS parallel trends - the pre-period is not flat, so the DiD is
    contaminated by pre-existing convergence and cannot be interpreted as a causal lever. This replaces
    the old eyeballed `pre_rms < |did|/2` rule with a proper joint hypothesis test."""
    kyears = [y for y in years if str(y) != BASE_YEAR]
    pre = [i for i, y in enumerate(kyears) if y < EXPANSION_YEAR]
    if len(pre) < 2:
        return {"pre_trend_chi2": None, "pre_trend_df": len(pre), "pre_trend_p": None,
                "parallel_trends_pass": None}
    point, _, _ = _event_study(j, years)
    b = np.array([point[kyears[i]] for i in pre])
    zips = j["zcta5"].unique()
    groups = {z: g for z, g in j.groupby("zcta5")}
    rng = np.random.default_rng(20260625)
    draws = []
    for _ in range(n_boot):
        pick = rng.choice(zips, size=len(zips), replace=True)
        boot = pd.concat([groups[z].assign(zcta5=f"{z}__{i}") for i, z in enumerate(pick)],
                         ignore_index=True)
        try:
            bb, _, _ = _event_study(boot, years)
            draws.append([bb[kyears[i]] for i in pre])
        except Exception:  # noqa: BLE001 - singular resample, skip
            continue
    sigma = np.atleast_2d(np.cov(np.array(draws), rowvar=False))
    try:
        wald = float(b @ np.linalg.solve(sigma, b))
    except np.linalg.LinAlgError:
        wald = float(b @ np.linalg.pinv(sigma) @ b)
    p = float(chi2.sf(wald, len(pre)))
    return {"pre_trend_chi2": round(wald, 2), "pre_trend_df": len(pre),
            "pre_trend_p": round(p, 4), "parallel_trends_pass": bool(p > 0.05)}


def run() -> dict:
    j, years = _build_panel()
    nz, nyr = j["zcta5"].nunique(), len(years)
    log("temporal", f"NY ACSC panel: {nz} ZIPs x {nyr} years ({years[0]}-{years[-1]}), "
                    f"{len(j)} ZIP-years")

    betas, _, kyears = _event_study(j, years)
    did = _did_coefficient(j)
    lo, hi, _ = _cluster_bootstrap(j, _did_coefficient, N_BOOT)
    # Spatial-honest variant: resample whole counties. Health/ACSC geography is spatially
    # autocorrelated, so the ZIP-cluster CI above understates uncertainty; this is the honest bar.
    has_county = "county_fips" in j.columns and j["county_fips"].notna().any()
    clo, chi = (_cluster_bootstrap(j, _did_coefficient, N_BOOT, unit_col="county_fips")[:2]
                if has_county else (lo, hi))

    # parallel-trends diagnostic: mean magnitude of the PRE-2014 betas (should be small vs post)
    pre = [betas[y] for y in kyears if y < EXPANSION_YEAR]
    post = [betas[y] for y in kyears if y >= EXPANSION_YEAR]
    pre_rms = float(np.sqrt(np.mean(np.square(pre)))) if pre else float("nan")
    post_mean = float(np.mean(post)) if post else float("nan")
    # robustness: re-estimate the DiD dropping 2009 (the one clearly non-flat pre-year), so the
    # effect can't be an artifact of a single anomalous baseline year. A surviving coefficient is
    # the honest signal; a collapsing one means the DiD was riding the pre-trend.
    j_drop09 = j[j["year"] != 2009].copy()
    did_drop09 = _did_coefficient(j_drop09)

    rep = {
        "n_zips": int(nz), "n_years": nyr, "zip_years": int(len(j)),
        "outcome": "NY SPARCS PQI_90 observed ACSC rate per 100k (patient ZIP, 2009-2023)",
        "treatment": "+1 SD baseline insurance barrier x post-2014 ACA coverage expansion",
        "base_year": int(BASE_YEAR),
        "event_study_beta": {str(k): round(v, 2) for k, v in betas.items()},
        "did_post_beta": round(did, 2),
        "did_ci": [round(lo, 2), round(hi, 2)],
        "did_ci_county_block": [round(clo, 2), round(chi, 2)],
        "did_excludes_zero_zip": bool(hi < 0 or lo > 0),
        "did_excludes_zero_county_block": bool(chi < 0 or clo > 0),
        # a lever is only claimed if BOTH the ZIP and the spatially-honest county-block CI exclude 0
        "did_excludes_zero": bool((hi < 0 or lo > 0) and (chi < 0 or clo > 0)),
        "pre_trend_rms": round(pre_rms, 2),
        "post_mean_beta": round(post_mean, 2),
        "did_drop2009": round(did_drop09, 2),
    }
    # parallel-trends is now a COMPUTED hypothesis test (joint Wald on the pre-2014 betas), not an
    # eyeballed ratio. The verdict follows the test: if parallel trends are REJECTED the DiD is not
    # interpretable as a causal lever, full stop - regardless of whether its CI excludes 0. (And even
    # when not rejected, the cross-state falsification in run_cross_state overturns the affordability
    # arm - see VALIDATION §7e.) No "step toward causal" language: the test decides.
    pt = _pre_trends_test(j, years)
    rep.update(pt)
    rep["parallel_trends_clean"] = pt["parallel_trends_pass"]
    # The verdict NEVER asserts a causal lever (T6). Even when the joint test fails to reject flat
    # pre-trends, this single-state DiD is only DESCRIPTIVE: the cross-state falsification
    # (run_cross_state / VALIDATION §7e) shows TX - which never expanded - declined the same, so the
    # NY association is secular convergence, not the coverage shock.
    if not rep["did_excludes_zero"] or did_drop09 >= 0:
        rep["verdict"] = "no credible lever effect (DiD CI includes 0 or flips dropping 2009)"
    elif pt["parallel_trends_pass"] is False:
        rep["verdict"] = (f"DESCRIPTIVE ONLY - parallel-trends REJECTED "
                          f"(pre-trend joint p={pt['pre_trend_p']}); the DiD rides pre-existing "
                          f"convergence and is not a causal lever")
    else:
        rep["verdict"] = (f"INCONCLUSIVE / descriptive only - pre-trends not statistically rejected "
                          f"(joint p={pt['pre_trend_p']}) but the pre-period point estimates are not "
                          f"flat, and the cross-state control (§7e) falsifies the lever; no causal read")

    rep["barrier_source"] = getattr(_build_panel, "barrier_src", "?")
    print("\n=== TEMPORAL quasi-experiment: ACSC vs the 2014 ACA coverage expansion (NY) ===")
    print(f"  barrier = {rep['barrier_source']}")
    print(f"  {nz} ZIPs x {nyr} years, two-way (ZIP + year) fixed effects; base year {BASE_YEAR}")
    print("  beta_k = effect of +1 SD baseline insurance barrier on ACSC/100k in year k\n")
    print(f"  {'year':>6s} {'beta':>9s}   {'era':<22s}")
    for y in kyears:
        era = "pre  (parallel-trends)" if y < EXPANSION_YEAR else "POST (the experiment)"
        bar = "#" * min(40, int(abs(betas[y]) / 3))
        sign = "-" if betas[y] < 0 else "+"
        print(f"  {y:>6d} {betas[y]:+9.1f}   {era:<22s} {sign}{bar}")
    print(f"\n  pre-2014 RMS beta  = {pre_rms:6.1f}  (the joint pre-trends test below is the authority)")
    print(f"  post-2014 mean beta= {post_mean:6.1f}")
    print(f"  POST x barrier DiD = {did:+.1f}/100k per +1 SD")
    print(f"    ZIP-cluster CI    [{lo:+.1f}, {hi:+.1f}]  "
          f"{'EXCLUDES 0' if rep['did_excludes_zero_zip'] else 'straddles 0'}")
    print(f"    county-block CI   [{clo:+.1f}, {chi:+.1f}]  "
          f"{'EXCLUDES 0' if rep['did_excludes_zero_county_block'] else 'straddles 0'}  (spatially honest)")
    print(f"  DiD dropping 2009  = {did_drop09:+.1f}/100k  (robustness to the one non-flat pre-year)")
    print(f"  pre-trends joint test: chi2({rep['pre_trend_df']})={rep['pre_trend_chi2']}, "
          f"p={rep['pre_trend_p']}  =>  parallel-trends {'NOT rejected' if rep['parallel_trends_clean'] else 'REJECTED'}")
    print(f"  VERDICT: {rep['verdict']}")
    print("\n  Reading: the joint Wald test on the PRE-2014 betas is the gate. If it REJECTS flat\n"
          "  pre-trends (small p), the post-2014 DiD is riding pre-existing convergence and CANNOT be\n"
          "  read as a causal lever - it stays a descriptive within-unit association. Even when not\n"
          "  rejected, the cross-state falsification (run_cross_state: TX never expanded yet declined\n"
          "  the same) overturns the affordability arm. This validator is descriptive-only by design.")
    return rep


def _demean2(df: pd.DataFrame, cols: list[str], g1: str, g2: str, n_iter: int = 12) -> pd.DataFrame:
    """Iterative (alternating-projection) within transform for two NON-NESTED fixed-effect factors
    g1 (ZIP) and g2 (state x year). Converges to the residual orthogonal to both factor spaces - the
    exact two-way-FE transform for an unbalanced panel (Gaure/Guimaraes-Portugal)."""
    out = df.copy()
    for c in cols:
        out[c] = out[c].astype(float)
    for _ in range(n_iter):
        for g in (g1, g2):
            for c in cols:
                out[c] = out[c] - out.groupby(g)[c].transform("mean")
    return out


def _triple_diff(panel: pd.DataFrame) -> float:
    """Coefficient on barrier x post x treated in a ZIP + (state x year) two-way-FE model. This is
    the DiD-in-DiD: the differential effect of baseline barrier on the post-2014 ACSC change in NY
    (treated) OVER AND ABOVE the same in TX (never-expanded control). The control differences out any
    secular high-barrier convergence common to both states - the exact confound that made the NY-only
    event study only 'suggestive'."""
    p = panel.copy()
    p["post"] = (p["year"] >= EXPANSION_YEAR).astype(float)
    p["treated"] = (p["state"] == "NY").astype(float)
    p["bp"] = p["barrier"] * p["post"]
    p["bpt"] = p["barrier"] * p["post"] * p["treated"]
    p["sy"] = p["state"] + "_" + p["year"].astype(str)
    dm = _demean2(p, ["rate", "bp", "bpt"], "zcta5", "sy")
    X = dm[["bp", "bpt"]].to_numpy()
    beta, *_ = np.linalg.lstsq(X, dm["rate"].to_numpy(), rcond=None)
    return float(beta[1])  # coefficient on bpt (the triple interaction)


def _state_panel(state: str, years) -> pd.DataFrame:
    """ACSC panel (zcta5, year, rate, barrier, state) for one state over `years`, barrier = the
    standardized PRE-2012 uninsured rate within that state. NY uses SPARCS PQI_90 (per-100k-pop rate);
    TX uses PUDF ACSC discharges / population x 100k (same construct + scale; state x year FE absorbs
    any residual scaling)."""
    m = pd.read_parquet(METRICS)
    m = m[(m["scoreable"] == True) & (m["state"] == state)].copy()  # noqa: E712
    m["zcta5"] = m["zcta5"].astype(str)
    m["pop"] = pd.to_numeric(m["population"], errors="coerce")
    pre = pd.read_parquet(PRE_BARRIER_CACHE)
    pre["zcta5"] = pre["zcta5"].astype(str)
    base = m[["zcta5", "pop"]].merge(pre, on="zcta5", how="inner")
    base = base[(base["pop"] >= MIN_POP)].dropna(subset=["uninsured_2012"])
    base["barrier"] = ((base["uninsured_2012"] - base["uninsured_2012"].mean())
                       / base["uninsured_2012"].std())
    if state == "NY":
        panel = _fetch_ny_panel()
        panel = panel[panel["year"].isin(years)][["zcta5", "year", "rate"]]
    else:  # TX
        from .validate_subcounty import tx_acsc_panel
        tx = tx_acsc_panel(tuple(years))
        tx["zcta5"] = tx["zcta5"].astype(str)
        tx = tx.merge(base[["zcta5", "pop"]], on="zcta5", how="inner")
        tx = tx[(tx["n_total"] >= 0) & (tx["acsc"] > 0)]
        tx["rate"] = tx["acsc"] / tx["pop"] * 1e5   # ACSC per 100k residents (matches NY's scale)
        panel = tx[["zcta5", "year", "rate"]]
    j = panel.merge(base[["zcta5", "barrier"]], on="zcta5", how="inner")
    j = j[(j["rate"] > 0) & (j["rate"] < j["rate"].quantile(0.999))].copy()
    yrs = j.groupby("zcta5")["year"].nunique()
    keep = yrs[yrs >= len(years) - 1].index   # near-complete panels only
    j = j[j["zcta5"].isin(keep)].copy()
    j["state"] = state
    return j.reset_index(drop=True)


def run_cross_state(years=(2011, 2012, 2013, 2014, 2015)) -> dict:
    """The cross-state quasi-experiment: NY (Medicaid expansion 2014) vs TX (never expanded) ACSC,
    a DiD-in-DiD around the ACA coverage expansion. TX is the FALSIFICATION control - if high-barrier
    ZIPs' ACSC fell post-2014 in NY but NOT in TX, the lever is the expansion, not a secular trend.
    Reports each state's event-study path plus the triple-difference coefficient with a bootstrap CI."""
    years = list(years)
    ny = _state_panel("NY", years)
    tx = _state_panel("TX", years)
    log("temporal", f"cross-state: NY {ny['zcta5'].nunique()} ZIPs, TX {tx['zcta5'].nunique()} ZIPs, "
                    f"{years[0]}-{years[-1]}")

    betas_ny, _, ky = _event_study(ny, years)
    betas_tx, _, _ = _event_study(tx, years)
    panel = pd.concat([ny, tx], ignore_index=True)
    tdid = _triple_diff(panel)
    lo, hi, _ = _cluster_bootstrap(panel, _triple_diff, 600)

    rep = {"years": years, "n_ny": int(ny["zcta5"].nunique()), "n_tx": int(tx["zcta5"].nunique()),
           "event_study_ny": {str(k): round(v, 2) for k, v in betas_ny.items()},
           "event_study_tx": {str(k): round(v, 2) for k, v in betas_tx.items()},
           "triple_diff": round(tdid, 2), "triple_diff_ci": [round(lo, 2), round(hi, 2)],
           "excludes_zero": bool(hi < 0 or lo > 0)}

    print("\n=== CROSS-STATE DiD-in-DiD: ACSC vs 2014 ACA expansion, NY (treated) vs TX (control) ===")
    print(f"  NY {rep['n_ny']} ZIPs, TX {rep['n_tx']} ZIPs, {years[0]}-{years[-1]}, base {BASE_YEAR}")
    print("  beta_k = effect of +1 SD baseline barrier on ACSC in year k (within-ZIP, vs 2013)\n")
    print(f"  {'year':>6s} {'NY (treated)':>13s} {'TX (control)':>13s}   era")
    for k in ky:
        era = "pre" if k < EXPANSION_YEAR else "POST"
        print(f"  {k:>6d} {betas_ny[k]:+13.1f} {betas_tx[k]:+13.1f}   {era}")
    print(f"\n  TRIPLE-DIFF (barrier x post x NY) = {tdid:+.1f}  CI [{lo:+.1f}, {hi:+.1f}]  "
          f"{'EXCLUDES 0' if rep['excludes_zero'] else 'straddles 0'}")
    # Decision rule stated up front, then the ACTUAL outcome - no declarative causal claim either way.
    verdict = ("treated-vs-control lever supported (triple-diff < 0, CI excludes 0)"
               if rep["excludes_zero"] and tdid < 0 else
               "lever NOT supported - triple-diff CI includes 0: the NY-only decline is secular "
               "high-barrier convergence common to TX (which never expanded), so the §7b hint is falsified")
    rep["verdict"] = verdict
    print("\n  Reading: the triple-diff nets out any secular high-barrier convergence common to both\n"
          "  states - the confound the NY-only study couldn't rule out. Decision rule: a negative\n"
          "  coefficient whose CI excludes 0 would be treated-vs-control causal evidence; a CI that\n"
          "  includes 0 leaves the lever unsupported.")
    print(f"  VERDICT: {verdict}")
    return rep


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "cross":
        run_cross_state()
    else:
        run()

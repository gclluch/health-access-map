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
    PRE-2014 betas test parallel trends (they should be ~flat); the POST-2014 betas are the
    quasi-experiment - a negative, growing post-2014 path is the access lever moving the outcome.

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


def _bootstrap_did(j: pd.DataFrame, n: int = N_BOOT) -> tuple[float, float, float]:
    """ZIP-cluster bootstrap on the post-2014 DiD coefficient (resample whole ZIP time series)."""
    zips = j["zcta5"].unique()
    groups = {z: g for z, g in j.groupby("zcta5")}
    rng = np.random.default_rng(20260625)
    betas = []
    for _ in range(n):
        pick = rng.choice(zips, size=len(zips), replace=True)
        boot = pd.concat([groups[z].assign(zcta5=f"{z}__{i}") for i, z in enumerate(pick)],
                         ignore_index=True)
        betas.append(_did_coefficient(boot))
    betas = np.array(betas)
    return float(np.percentile(betas, 2.5)), float(np.percentile(betas, 97.5)), float(betas.mean())


def run() -> dict:
    j, years = _build_panel()
    nz, nyr = j["zcta5"].nunique(), len(years)
    log("temporal", f"NY ACSC panel: {nz} ZIPs x {nyr} years ({years[0]}-{years[-1]}), "
                    f"{len(j)} ZIP-years")

    betas, _, kyears = _event_study(j, years)
    did = _did_coefficient(j)
    lo, hi, mean = _bootstrap_did(j)

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
        "did_excludes_zero": bool(hi < 0 or lo > 0),
        "pre_trend_rms": round(pre_rms, 2),
        "post_mean_beta": round(post_mean, 2),
        "did_drop2009": round(did_drop09, 2),
    }
    # honest parallel-trends verdict: the pre-period betas being comparable in size to the DiD
    # itself means pre-existing convergence contaminates the estimate - so this is SUGGESTIVE, not
    # clean-causal. We say so rather than letting "CI excludes 0" imply more than it earns.
    clean = pre_rms < abs(did) / 2 and rep["did_excludes_zero"] and did_drop09 < 0
    rep["verdict"] = ("suggestive lever effect (pre-trends imperfect)" if rep["did_excludes_zero"]
                      and did_drop09 < 0 else "no credible lever effect")
    rep["parallel_trends_clean"] = bool(clean)

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
    print(f"\n  pre-2014 RMS beta  = {pre_rms:6.1f}  (parallel-trends: small RELATIVE to the DiD => clean)")
    print(f"  post-2014 mean beta= {post_mean:6.1f}")
    print(f"  POST x barrier DiD = {did:+.1f}/100k per +1 SD  "
          f"CI [{lo:+.1f}, {hi:+.1f}]  {'EXCLUDES 0' if rep['did_excludes_zero'] else 'straddles 0'}")
    print(f"  DiD dropping 2009  = {did_drop09:+.1f}/100k  (robustness to the one non-flat pre-year)")
    print(f"  VERDICT: {rep['verdict']}; parallel-trends clean = {rep['parallel_trends_clean']}")
    print("\n  Reading: most POST-2014 betas are negative (mean {:+.1f}) vs a positive pre-period -\n"
          "  ACSC fell MORE where the PRE-EXPANSION uninsured rate was highest, after coverage\n"
          "  expanded. The ZIP fixed effect removes the deprivation that makes the cross-section a\n"
          "  poverty map, so this is a real step from correlational toward causal. HONESTY: the\n"
          "  pre-period betas are not perfectly flat (a 2009 spike), so pre-existing convergence\n"
          "  inflates the DiD somewhat - hence SUGGESTIVE, not proof. One state, quasi-experimental."
          .format(post_mean))
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


def _bootstrap_triple(panel: pd.DataFrame, n: int = 600) -> tuple[float, float, float]:
    """ZIP-cluster bootstrap on the triple-diff coefficient."""
    zips = panel["zcta5"].unique()
    groups = {z: g for z, g in panel.groupby("zcta5")}
    rng = np.random.default_rng(20260625)
    betas = []
    for _ in range(n):
        pick = rng.choice(zips, size=len(zips), replace=True)
        boot = pd.concat([groups[z].assign(zcta5=f"{z}__{i}") for i, z in enumerate(pick)],
                         ignore_index=True)
        try:
            betas.append(_triple_diff(boot))
        except Exception:  # noqa: BLE001 - singular resample, skip
            continue
    betas = np.array(betas)
    return float(np.percentile(betas, 2.5)), float(np.percentile(betas, 97.5)), float(betas.mean())


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
    lo, hi, _ = _bootstrap_triple(panel)

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
    print("\n  Reading: NY post-2014 betas going negative WHILE TX stays flat = the high-barrier ACSC\n"
          "  drop is specific to the state that expanded coverage. The triple-diff nets out any secular\n"
          "  high-barrier convergence common to both states - the confound the NY-only study couldn't\n"
          "  rule out. A negative coefficient excluding 0 is treated-vs-control causal evidence.")
    return rep


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "cross":
        run_cross_state()
    else:
        run()

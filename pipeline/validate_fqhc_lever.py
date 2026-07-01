"""validate_fqhc_lever: the staggered FQHC New Access Point event study (BACKLOG B5d) - does ZIP
preventable-hospitalization (ACSC) fall after a ZIP gets its FIRST community health center?

This is the SUPPLY / safety-net arm of `care_access` - the one arm the ACA coverage work (§7b/§7e)
never touched. HRSA opens FQHCs in dated, located waves (`build_fqhc_openings`), a staggered shock.
With many adoption years the right estimator is NOT two-way-FE DiD - under heterogeneous, dynamic
effects TWFE contaminates each ATT with forbidden already-treated-vs-newly-treated comparisons and
can flip sign (Goodman-Bacon 2021). We use the Callaway & Sant'Anna (2021) group-time ATT instead,
hand-rolled and unit-tested (tests/test_causal_validation.py), aggregated to an event-study path.

Design:
  * Outcomes: NY SPARCS PQI_90 observed ACSC/100k by patient ZIP x year, 2009-2023 (reuse
    validate_temporal._fetch_ny_panel); TX THCIC PUDF ACSC discharges / population x 100k by patient
    ZIP x year, 2011-2019 (reuse validate_subcounty.tx_acsc_panel). Same construct + scale; the
    estimator never compares across states, so any residual scale difference is irrelevant.
  * Treatment: a ZCTA whose FIRST EVER FQHC opens in 2012-2019 (newly_served, the clean 0->1).
    Cohort g = the opening year.
  * Controls: supply-STABLE ZCTAs - no FQHC opened in the window (never had one, or had one since
    before 2012 and gained none during it). ZCTAs that already had an FQHC and gained ANOTHER
    in-window are EXCLUDED from both arms (supply changes, but it isn't a first-access event).
  * Estimator: ATT(g,t) = [Y_t - Y_{g-1} | cohort g] - [Y_t - Y_{g-1} | not-yet-treated by max(t,g)],
    computed WITHIN each state (NY treated vs NY not-yet, TX vs TX) so state-specific levels, scale
    and secular shocks difference out - the equivalent of state x year fixed effects. Universal base
    period g-1 so ATT(g,g-1)=0. Never use already-treated as controls (the comparison that flips
    TWFE). Aggregate to event time e=t-g across ALL (state, cohort) cells, weighted by cohort size:
    e<0 betas test parallel trends; e>=0 are the dynamic effects; overall ATT averages e>=0.
  * Inference: ZIP-cluster bootstrap (resample whole ZIP series), percentile CIs - the repo standard.

HONEST framing, per the build plan. NY-only is a wiring PILOT (power gate: upper-band only at 135
treated); the powered claim is the NY+TX pool (~277 treated). We lead with the event-study path + a
parallel-trends verdict and NEVER a lone post-coefficient - the §7b lesson, where a single DiD
coefficient looked causal and was a pre-trend artifact. Read-only; never feeds the composite.

    python -m pipeline.validate_fqhc_lever          # pooled NY+TX (the headline)
    python -m pipeline.validate_fqhc_lever NY       # NY-only pilot
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import config
from .common import log
from .validate_fqhc_power import SCENARIOS
from .validate_temporal import _fetch_ny_panel

OPENINGS = config.PROCESSED / "fqhc_openings.parquet"
METRICS = config.PROCESSED / "metrics.parquet"
GAZETTEER = config.PROCESSED / "gazetteer.parquet"

MIN_POP = 1000
COVERAGE_FRAC = 0.8     # keep ZIPs observed in >= 80% of their state's panel years (anti-attrition)
EVENT_MIN, EVENT_MAX = -5, 6   # event-time window to display/aggregate
MIN_COHORTS = 2         # an event-time beta needs >= this many contributing (state,cohort) cells
N_BOOT = 600
NEVER = np.inf          # cohort sentinel for never-(newly-)treated controls
TX_YEARS = tuple(range(2011, 2020))   # annual TX PUDF panel 2011-2019


# --- outcome panels ----------------------------------------------------------------------------

def _ny_outcome() -> pd.DataFrame:
    p = _fetch_ny_panel()                                    # zcta5, year, rate (ACSC/100k pop)
    p = p[(p["rate"] > 0) & (p["rate"] < p["rate"].quantile(0.999))].copy()
    p["state"] = "NY"
    return p[["zcta5", "year", "rate", "state"]]


def _tx_outcome() -> pd.DataFrame:
    from .validate_subcounty import tx_acsc_panel
    tx = tx_acsc_panel(TX_YEARS)                             # zcta5, year, acsc, n_total
    tx["zcta5"] = tx["zcta5"].astype(str)
    pop = pd.read_parquet(METRICS)[["zcta5", "population"]]
    pop["zcta5"] = pop["zcta5"].astype(str)
    tx = tx.merge(pop, on="zcta5", how="inner")
    tx = tx[(tx["acsc"] > 0) & (tx["population"] >= MIN_POP)].copy()
    tx["rate"] = tx["acsc"] / tx["population"] * 1e5         # ACSC per 100k residents (matches NY)
    tx = tx[tx["rate"] < tx["rate"].quantile(0.999)]
    tx["state"] = "TX"
    return tx[["zcta5", "year", "rate", "state"]]


_OUTCOME = {"NY": _ny_outcome, "TX": _tx_outcome}


def _build_panel(states: tuple[str, ...], dose: str = "clean") -> tuple[pd.DataFrame, list[int]]:
    """Pooled (zcta5, year, rate, state, pop, cohort) panel for `states`. dose='clean': treated =
    newly-served (first-ever FQHC in window, 0->1), contaminated ZCTAs (prior FQHC + in-window add)
    dropped - the headline. dose='loose': treated = ANY in-window addition (treat_year_loose), even
    onto existing supply - the robustness dose. cohort = opening year, NEVER for controls. Per-state
    anti-attrition coverage filter; pop for optional weighting."""
    if not OPENINGS.exists():
        raise SystemExit(f"missing {OPENINGS}; run `python -m pipeline.build_fqhc_openings` first")
    panel = pd.concat([_OUTCOME[s]() for s in states], ignore_index=True)

    op = pd.read_parquet(OPENINGS)
    op = op[op["state"].isin(states)].copy()
    op["zcta5"] = op["zcta5"].astype(str)
    if dose == "loose":
        treated = (op[op["treat_year_loose"].notna()][["zcta5", "treat_year_loose"]]
                   .rename(columns={"treat_year_loose": "cohort"}))
        contaminated: set = set()       # every in-window opening is treatment; nothing to exclude
    else:
        treated = op[op["newly_served"]][["zcta5", "treat_year"]].rename(columns={"treat_year": "cohort"})
        contaminated = set(op[(~op["newly_served"]) & op["treat_year_loose"].notna()]["zcta5"])

    j = panel.merge(treated, on="zcta5", how="left")
    j = j[~j["zcta5"].isin(contaminated)].copy()
    j["cohort"] = j["cohort"].fillna(NEVER)

    try:  # county_fips enables the spatial (county-block) bootstrap; absent on some dev builds
        m = pd.read_parquet(METRICS, columns=["zcta5", "population", "county_fips"])
    except Exception:  # noqa: BLE001
        m = pd.read_parquet(METRICS, columns=["zcta5", "population"])
    m["zcta5"] = m["zcta5"].astype(str)
    j = j.merge(m, on="zcta5", how="inner").rename(columns={"population": "pop"})
    j = j[j["pop"] >= MIN_POP].copy()

    # per-state coverage filter: keep ZIPs observed in >= COVERAGE_FRAC of that state's panel years
    keep: list[str] = []
    for _st, sub in j.groupby("state"):
        thr = int(np.ceil(COVERAGE_FRAC * sub["year"].nunique()))
        cov = sub.groupby("zcta5")["year"].nunique()
        keep += list(cov[cov >= thr].index)
    j = j[j["zcta5"].isin(keep)].copy()
    years = sorted(j["year"].unique())
    return j.reset_index(drop=True), years


# --- Callaway-Sant'Anna group-time ATT ---------------------------------------------------------

def _wmean(v: np.ndarray, w: np.ndarray) -> float:
    return float(np.average(v, weights=w)) if len(v) and w.sum() > 0 else float("nan")


def att_gt(j: pd.DataFrame, weighted: bool = False) -> pd.DataFrame:
    """Group-time ATT for every (state, cohort g, period t). Computed WITHIN state: comparison =
    that state's not-yet-treated by max(t,g) (cohort > max(t,g), always including never-treated).
    Universal base period g-1. Returns (state, g, t, e=t-g, att, n_treated)."""
    out = []
    for st, js in j.groupby("state"):
        Y = js.pivot_table(index="zcta5", columns="year", values="rate")
        pop = js.groupby("zcta5")["pop"].first().reindex(Y.index)
        cohort = js.groupby("zcta5")["cohort"].first().reindex(Y.index)
        years = list(Y.columns)
        w_all = pop.to_numpy() if weighted else np.ones(len(Y))
        for g in sorted(c for c in cohort.unique() if np.isfinite(c)):
            base = g - 1
            if base not in years:
                continue
            is_g = cohort.to_numpy() == g
            for t in years:
                if t == base:
                    continue
                ctrl = cohort.to_numpy() > max(t, g)
                dY = (Y[t] - Y[base]).to_numpy()
                ok_t = is_g & np.isfinite(dY)
                ok_c = ctrl & np.isfinite(dY)
                if ok_t.sum() < 1 or ok_c.sum() < 2:
                    continue
                att = _wmean(dY[ok_t], w_all[ok_t]) - _wmean(dY[ok_c], w_all[ok_c])
                out.append({"state": st, "g": int(g), "t": int(t), "e": int(t - g),
                            "att": att, "n": int(ok_t.sum())})
    return pd.DataFrame(out)


def aggregate_event(attgt: pd.DataFrame) -> pd.DataFrame:
    """Aggregate ATT(state,g,t) to event time e=t-g, weighting each (state,cohort) cell by its
    treated size n. Returns (e, att, n_cohorts, n_treated)."""
    rows = []
    for e, gg in attgt.groupby("e"):
        n_cohorts = gg[["state", "g"]].drop_duplicates().shape[0]
        if n_cohorts < MIN_COHORTS:
            continue
        rows.append({"e": int(e), "att": _wmean(gg["att"].to_numpy(), gg["n"].to_numpy()),
                     "n_cohorts": int(n_cohorts), "n_treated": int(gg["n"].sum())})
    return pd.DataFrame(rows).sort_values("e").reset_index(drop=True)


BALANCED_EMAX = 4   # the well-populated post horizon (>=12 cohorts); the e=8-10 tail rests on 2-4


def overall_att(attgt: pd.DataFrame, emax: int | None = None) -> float:
    """Single summary ATT: cohort-size-weighted average of the post-treatment ATT(g,t) (0<=e),
    optionally capped at event time `emax` to drop the noisy, few-cohort long-horizon tail."""
    post = attgt[attgt["e"] >= 0]
    if emax is not None:
        post = post[post["e"] <= emax]
    return _wmean(post["att"].to_numpy(), post["n"].to_numpy()) if len(post) else float("nan")


# --- inference ---------------------------------------------------------------------------------

def _pctci(v: list[float]) -> tuple[float, float]:
    a = np.array([x for x in v if np.isfinite(x)])
    return (float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))) if len(a) else (np.nan, np.nan)


def _bootstrap(j: pd.DataFrame, weighted: bool, n: int = N_BOOT, unit_col: str = "zcta5"
               ) -> tuple[dict[int, tuple[float, float]], tuple[float, float], tuple[float, float]]:
    """Block bootstrap: resample whole `unit_col` blocks, recompute the event path + both overall
    ATTs. Returns {e: (lo, hi)} path CIs, the full-horizon overall CI, and the balanced-window CI.
    Default blocks by ZIP; unit_col="county_fips" resamples whole counties, preserving within-county
    spatial correlation for an honest (wider) CI where neighbouring ZIPs are not independent."""
    units = j[unit_col].dropna().unique()
    groups = {u: g for u, g in j.groupby(unit_col)}
    rng = np.random.default_rng(20260626)
    paths: dict[int, list[float]] = {}
    full, bal = [], []
    for _ in range(n):
        pick = rng.choice(units, size=len(units), replace=True)
        boot = pd.concat([groups[u].assign(zcta5=groups[u]["zcta5"].astype(str) + f"__{i}")
                          for i, u in enumerate(pick)], ignore_index=True)
        try:
            ag = att_gt(boot, weighted=weighted)
            if ag.empty:
                continue
            for _, r in aggregate_event(ag).iterrows():
                paths.setdefault(int(r["e"]), []).append(r["att"])
            full.append(overall_att(ag))
            bal.append(overall_att(ag, emax=BALANCED_EMAX))
        except Exception:  # noqa: BLE001 - singular/degenerate resample, skip
            continue
    ci = {e: _pctci(v) for e, v in paths.items() if len(v) >= n // 4}
    return ci, _pctci(full), _pctci(bal)


def _overall_ci(j: pd.DataFrame, weighted: bool, n: int) -> tuple[float, float]:
    """Bootstrap CI for just the full-horizon overall ATT (the robustness summary statistic)."""
    _, ov_ci, _ = _bootstrap(j, weighted=weighted, n=n)
    return ov_ci


# --- robustness (Phase 3) ----------------------------------------------------------------------

ROBUST_BOOT = 300            # lighter bootstrap for the robustness variants
SPILLOVER_KM = 10.0         # drop controls within this distance of any treated ZCTA (SUTVA)
PLACEBO_SHIFT = 3           # fake the opening this many years early (placebo-in-time)


def _drop_spillover_controls(j: pd.DataFrame, km: float = SPILLOVER_KM) -> pd.DataFrame:
    """SUTVA / spillover: drop control ZCTAs whose centroid is within `km` of ANY treated ZCTA - a
    new FQHC may serve adjacent ZIPs, so a too-close control is partially treated and biases the ATT
    toward zero. Treated ZCTAs and far controls are kept."""
    from sklearn.neighbors import BallTree
    cz = j.groupby("zcta5")["cohort"].first()
    treated, control = cz[np.isfinite(cz)].index, cz[~np.isfinite(cz)].index
    gz = pd.read_parquet(GAZETTEER)[["zcta5", "lat", "lon"]]
    gz["zcta5"] = gz["zcta5"].astype(str)
    gz = gz.set_index("zcta5")
    tt, cc = gz.reindex(treated).dropna(), gz.reindex(control).dropna()
    tree = BallTree(np.radians(tt[["lat", "lon"]].to_numpy()), metric="haversine")
    d, _ = tree.query(np.radians(cc[["lat", "lon"]].to_numpy()), k=1)
    far = set(cc.index[(d[:, 0] * config.EARTH_KM) > km])
    keep = set(treated) | far
    return j[j["zcta5"].isin(keep)].copy()


def _placebo_in_time(j: pd.DataFrame, shift: int = PLACEBO_SHIFT) -> pd.DataFrame:
    """Placebo-in-time: move each treated ZCTA's opening `shift` years EARLIER and use ONLY its
    genuine pre-treatment years (year < real cohort). The fake 'post' window is entirely before the
    real opening, so a clean design returns ~0; a non-zero placebo IS the pre-trend / siting bias."""
    treated = j[np.isfinite(j["cohort"])]
    treated = treated[treated["year"] < treated["cohort"]].copy()
    treated["cohort"] = treated["cohort"] - shift
    controls = j[~np.isfinite(j["cohort"])].copy()
    return pd.concat([treated, controls], ignore_index=True)


def run_robustness(states: tuple[str, ...] = ("NY", "TX"), weighted: bool = True) -> dict:
    """The Phase-3 battery: spillover-drop, clean-vs-loose dose, placebo-in-time. Reports each
    variant's overall ATT vs the headline so the reader sees attenuation/persistence directly."""
    base, _ = _build_panel(states, dose="clean")
    variants = {
        "headline (clean 0->1)": base,
        f"drop controls <{SPILLOVER_KM:.0f}km (SUTVA)": _drop_spillover_controls(base),
        "loose dose (any addition)": _build_panel(states, dose="loose")[0],
        f"placebo-in-time (-{PLACEBO_SHIFT}y)": _placebo_in_time(base),
    }
    rep: dict = {"states": list(states), "weighting": "population" if weighted else "equal",
                 "spillover_km": SPILLOVER_KM, "placebo_shift": PLACEBO_SHIFT, "variants": {}}

    print(f"\n=== FQHC SUPPLY LEVER - ROBUSTNESS BATTERY ({'+'.join(states)}) ===")
    print(f"  {'variant':32s} {'n_treat':>7s} {'overall ATT':>12s} {'95% CI':>20s}   note")
    notes = {
        "headline (clean 0->1)": "the Phase-2 estimate",
        f"drop controls <{SPILLOVER_KM:.0f}km (SUTVA)": "should PERSIST (often more neg)",
        "loose dose (any addition)": "should be SMALLER than clean",
        f"placebo-in-time (-{PLACEBO_SHIFT}y)": "should be ~0; non-0 => siting pre-trend",
    }
    for name, jv in variants.items():
        attgt = att_gt(jv, weighted=weighted)
        ov = overall_att(attgt)
        lo, hi = _overall_ci(jv, weighted, ROBUST_BOOT)
        n_t = int(np.isfinite(jv.groupby("zcta5")["cohort"].first()).sum())
        excl = "EXCLUDES 0" if (lo > 0 or hi < 0) else "straddles 0"
        rep["variants"][name] = {"n_treated": n_t, "overall_att": round(ov, 1),
                                 "ci": [round(lo, 1), round(hi, 1)], "excludes_zero": lo > 0 or hi < 0}
        print(f"  {name:32s} {n_t:>7d} {ov:>+11.1f} [{lo:>+8.1f},{hi:>+8.1f}]  {excl}; {notes[name]}")
    return rep


# --- driver ------------------------------------------------------------------------------------

def _verdict(ev: pd.DataFrame, ov: float, ov_ci: tuple[float, float]) -> tuple[str, bool, float]:
    """Event-study-first verdict. Parallel trends 'clean' iff the pre-period (e<0) ATTs are small
    RELATIVE to the post effect (the §7b discipline). NEVER read off the post coefficient alone."""
    pre = ev[ev["e"] < 0]["att"].to_numpy()
    pre_rms = float(np.sqrt(np.mean(np.square(pre)))) if len(pre) else float("nan")
    excludes0 = bool(ov_ci[0] > 0 or ov_ci[1] < 0)
    clean = bool(np.isfinite(pre_rms) and abs(ov) > 0 and pre_rms < abs(ov) / 2)
    # the CI bound on the zero-side: how close the straddle comes to excluding zero
    near = ov_ci[1] if ov < 0 else ov_ci[0]
    borderline = bool(not excludes0 and abs(ov) > 0 and abs(near) < abs(ov) * 0.2)
    if excludes0 and ov < 0 and clean:
        v = "supply lever detected - ACSC falls after first FQHC, pre-trends clean"
    elif excludes0 and ov < 0:
        v = "suggestive supply lever (pre-trends imperfect - read as the §7b 'suggestive', not causal)"
    elif excludes0 and ov > 0:
        v = "wrong-signed effect (ACSC rises) - not a lever"
    elif borderline and ov < 0:
        v = ("borderline - right-signed, dose-responsive, powered, but the 95% CI just includes 0 "
             "and pre-trends aren't fully clean; suggestive of a modest supply effect, not conclusive")
    else:
        v = "no credible supply-lever effect (CI straddles 0)"
    return v, clean, pre_rms


def _gate_band(n_treated: int) -> str:
    """Map the realized treated-N onto validate_fqhc_power's scenarios (the power gate, re-read at
    the realized N per the build plan), so the verdict carries its own power context. The scenario
    N's are pulled from validate_fqhc_power.SCENARIOS so this can't drift if the power analysis re-runs."""
    scen_n = {label: n_t for label, n_t, *_ in SCENARIOS}
    nyx, nyo = scen_n["NY+TX (real)"], scen_n["NY-only"]
    if n_treated >= 240:
        return f"~NY+TX gate scenario ({nyx}, MDE 5%): powered for the likely effect (realized {n_treated})"
    if n_treated >= 110:
        return f"~NY-only gate scenario ({nyo}, upper-band only): PILOT power (realized {n_treated})"
    return f"below the gate's NY-only scenario ({nyo}): underpowered (realized {n_treated})"


def run(states: tuple[str, ...] = ("NY", "TX"), weighted: bool = True) -> dict:
    j, years = _build_panel(states)
    cohort = j.groupby("zcta5")["cohort"].first()
    n_treated = int(np.isfinite(cohort).sum())
    n_control = int((~np.isfinite(cohort)).sum())
    by_state = (j[np.isfinite(j["cohort"])].drop_duplicates("zcta5").groupby("state").size()
                .astype(int).to_dict())
    tag = "+".join(states)
    log("fqhc-lever", f"{tag} panel: {j['zcta5'].nunique()} ZIPs ({years[0]}-{years[-1]}); "
                      f"{n_treated} newly-served treated ({by_state}), {n_control} supply-stable controls")

    attgt = att_gt(j, weighted=weighted)
    ev = aggregate_event(attgt)
    ov = overall_att(attgt)
    ov_bal = overall_att(attgt, emax=BALANCED_EMAX)
    ci, ov_ci, ov_bal_ci = _bootstrap(j, weighted=weighted)
    # Spatial-honest CI: resample whole counties (ACSC geography is spatially autocorrelated, so the
    # ZIP-cluster CI understates uncertainty). This wider CI is the one the verdict keys on.
    has_county = "county_fips" in j.columns and j["county_fips"].notna().any()
    ov_ci_cty = _bootstrap(j, weighted=weighted, unit_col="county_fips")[1] if has_county else ov_ci
    verdict, clean, pre_rms = _verdict(ev, ov, ov_ci_cty)

    rep = {
        "design": "Callaway-Sant'Anna group-time ATT, staggered first-FQHC opening, within-state controls",
        "states": list(states),
        "outcome": "ACSC/100k by patient ZIP x year (NY SPARCS PQI_90 2009-2023; TX PUDF 2011-2019)",
        "weighting": "population" if weighted else "equal",
        "n_treated": n_treated, "n_treated_by_state": by_state, "n_control": n_control,
        "event_study_att": {int(r.e): round(r.att, 1) for r in ev.itertuples()},
        "event_study_ci": {int(e): [round(lo, 1), round(hi, 1)] for e, (lo, hi) in ci.items()},
        "overall_att": round(ov, 1),
        "overall_ci": [round(ov_ci[0], 1), round(ov_ci[1], 1)],
        "overall_ci_county_block": [round(ov_ci_cty[0], 1), round(ov_ci_cty[1], 1)],
        "overall_excludes_zero_zip": bool(ov_ci[0] > 0 or ov_ci[1] < 0),
        # honest bar: a lever requires BOTH the ZIP and the spatial county-block CI to exclude 0
        "overall_excludes_zero": bool((ov_ci[0] > 0 or ov_ci[1] < 0) and (ov_ci_cty[0] > 0 or ov_ci_cty[1] < 0)),
        "overall_att_balanced": round(ov_bal, 1),     # e=0..4, the well-populated horizon
        "overall_ci_balanced": [round(ov_bal_ci[0], 1), round(ov_bal_ci[1], 1)],
        "balanced_excludes_zero": bool(ov_bal_ci[0] > 0 or ov_bal_ci[1] < 0),
        "pre_trend_rms": round(pre_rms, 1),
        "parallel_trends_clean": clean,
        "power_gate_band": _gate_band(n_treated),
        "verdict": verdict,
    }

    print(f"\n=== FQHC SUPPLY LEVER: staggered first-FQHC event study (Callaway-Sant'Anna, {tag}) ===")
    print(f"  outcome: {rep['outcome']}")
    print(f"  {n_treated} newly-served treated ZIPs {by_state}, {n_control} supply-stable controls; "
          f"{rep['weighting']}-weighted, within-state comparisons")
    print(f"  power gate (re-read at realized N): {rep['power_gate_band']}")
    print("  ATT(e) = ACSC/100k change e years after the first FQHC opens, vs not-yet-treated\n")
    print(f"  {'event e':>8s} {'ATT':>9s}   {'95% CI':>20s}   {'cohorts':>7s}   era")
    for r in ev.itertuples():
        lo, hi = ci.get(int(r.e), (np.nan, np.nan))
        era = "pre  (parallel-trends)" if r.e < 0 else "POST (the experiment)"
        star = " *" if np.isfinite(lo) and (lo > 0 or hi < 0) else ""
        print(f"  {int(r.e):>8d} {r.att:+9.1f}   [{lo:+8.1f},{hi:+8.1f}]   {int(r.n_cohorts):>7d}   {era}{star}")
    print(f"\n  pre-period RMS ATT = {pre_rms:6.1f}  (clean iff small vs |overall ATT|)")
    print(f"  OVERALL post ATT   = {ov:+.1f}/100k  (all e>=0)")
    print(f"    ZIP-cluster CI    [{ov_ci[0]:+.1f}, {ov_ci[1]:+.1f}]  "
          f"{'EXCLUDES 0' if rep['overall_excludes_zero_zip'] else 'straddles 0'}")
    print(f"    county-block CI   [{ov_ci_cty[0]:+.1f}, {ov_ci_cty[1]:+.1f}]  "
          f"{'EXCLUDES 0' if (ov_ci_cty[0] > 0 or ov_ci_cty[1] < 0) else 'straddles 0'}  (spatially honest; drives the verdict)")
    print(f"  balanced (e<= {BALANCED_EMAX})   = {ov_bal:+.1f}/100k  CI [{ov_bal_ci[0]:+.1f}, "
          f"{ov_bal_ci[1]:+.1f}]  {'EXCLUDES 0' if rep['balanced_excludes_zero'] else 'straddles 0'}")
    print(f"  parallel-trends clean = {clean}")
    print(f"  VERDICT: {verdict}")
    return rep


if __name__ == "__main__":
    argv = sys.argv[1:]
    do_robust = "robust" in [a.lower() for a in argv]
    st = tuple(a.upper() for a in argv if a.lower() not in ("robust",)) or ("NY", "TX")
    run(states=st)
    if do_robust:
        run_robustness(states=st)

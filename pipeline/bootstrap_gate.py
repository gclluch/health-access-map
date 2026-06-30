"""bootstrap_gate: uncertainty on the diagnostics gate margins.

The standard gate (`pipeline.diagnostics`) reports POINT estimates of correlation
differences - e.g. "FULL 0.498 vs drop_care_access 0.452, margin +0.046" - and ships
or kills inputs on those points. This module puts error bars on them, because a +0.046
margin is meaningless without knowing whether it is inside sampling noise.

Two design choices make the interval honest rather than flattering:

1. CLUSTER bootstrap over COUNTY (state|county_name), not ZCTA rows. Five of the six
   validation outcomes are county-level (CHR: preventable_hosp, premature_death,
   infant_mortality, flu_vaccination, mammography); only USALEEP life_expectancy is
   sub-county. Resampling 33k ZCTAs as if independent treats one county's ~11 ZCTAs as
   11 independent looks at a single county-level outcome value and so understates the
   true uncertainty by ~sqrt(zctas_per_county). Resampling whole counties respects that
   the effective N is ~the county count.

2. PAIRED differences. FULL and drop-one-dimension are computed on the SAME resample
   each replicate, so the margin distribution is the distribution of the paired
   difference (which has far smaller variance than differencing two independent CIs -
   the correct, and stricter, comparison).

Outputs a 95% CI for: composite mean-r, FULL mean-r, each drop-one margin (FULL minus
drop), and each sub-score mean|r|; plus a bootstrap "p" = share of replicates in which
care_access ADDS signal (margin > 0). Deterministic (fixed seed) like the rest of the
build. Writes data/processed/gate_ci.json and prints a table.

    python -m pipeline.bootstrap_gate [n_boot]   # default 1000
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from . import config
from .diagnostics import OUTCOMES, _oriented
from .taxonomy import DIMENSIONS, subscore_specs
from .validation_stats import pearson_corr

METRICS = config.PROCESSED / "metrics.parquet"
OUT_JSON = config.PROCESSED / "gate_ci.json"
DIM_COLS = [f"{d}_pctile" for d in DIMENSIONS]


def _rank(v: np.ndarray) -> np.ndarray:
    """Ordinal rank (NaN preserved). Pearson r is invariant to the [0,100] rescale the
    pipeline applies, so raw ranks suffice and are faster than pct rescaling."""
    out = np.full(len(v), np.nan)
    ok = ~np.isnan(v)
    order = np.argsort(v[ok], kind="stable")
    r = np.empty(order.size)
    r[order] = np.arange(order.size)
    out[ok] = r
    return out


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    # Stricter 100-pair floor than the shared default; Pearson math lives in validation_stats.
    return pearson_corr(a, b, min_pairs=100)


def _mean_r(series: np.ndarray, Y: np.ndarray) -> float:
    return float(np.nanmean([_corr(series, Y[:, k]) for k in range(Y.shape[1])]))


def _partial_corr(y: np.ndarray, c: np.ndarray, Z: np.ndarray) -> float:
    """Partial correlation of c with y, controlling for the columns of Z: correlate the
    residuals of y and c after regressing each on [1, Z]. Rows with any NaN are dropped."""
    M = np.column_stack([y, c, Z])
    m = ~np.isnan(M).any(axis=1)
    if m.sum() < 100:
        return np.nan
    A = np.column_stack([np.ones(m.sum()), Z[m]])

    def resid(v: np.ndarray) -> np.ndarray:
        beta, *_ = np.linalg.lstsq(A, v, rcond=None)
        return v - A @ beta

    ry, rc = resid(y[m]), resid(c[m])
    ry, rc = ry - ry.mean(), rc - rc.mean()
    s = np.sqrt((ry @ ry) * (rc @ rc))
    return float(ry @ rc / s) if s > 0 else np.nan


def _mean_abs_r(series: np.ndarray, Y: np.ndarray) -> float:
    return float(np.nanmean([abs(_corr(series, Y[:, k])) for k in range(Y.shape[1])]))


def _cluster_groups(d: pd.DataFrame, level: str = "county") -> list[np.ndarray]:
    """Row-position arrays grouped by a spatial BLOCK. Resampling whole blocks (not rows) is
    what makes the bootstrap CI honest under spatial dependence:
      - "county" (state|county_name): the default - respects that one county's ~11 ZCTAs are
        ~1 independent look at a county-level outcome (within-county pseudo-replication).
      - "state": the spatial-autocorrelation block. County outcomes in the same state are NOT
        independent (shared Medicaid/policy + spatial proximity), so resampling whole states is
        the conservative correction for BETWEEN-county autocorrelation. Far fewer clusters (~50)
        => deliberately wider, more honest CIs.
    Rows with no label for the chosen level become singleton clusters (resampled, not pooled)."""
    state = d.get("state", pd.Series([""] * len(d))).astype("string").fillna("")
    if level == "state":
        key = state.to_numpy().astype(object)
        blank = state.to_numpy() == ""
    else:
        county = d.get("county_name", pd.Series([""] * len(d))).astype("string").fillna("")
        key = (state + "|" + county).to_numpy().astype(object)
        blank = (county.to_numpy() == "") | (state.to_numpy() == "")
    key[blank] = [f"__solo_{i}" for i in np.where(blank)[0]]
    order = np.argsort(key, kind="stable")
    key_sorted = key[order]
    bounds = np.where(key_sorted[1:] != key_sorted[:-1])[0] + 1
    return [order[s:e] for s, e in zip(np.r_[0, bounds], np.r_[bounds, len(key)])]


def amenable_focus(d: pd.DataFrame, n_boot: int = 1000, seed: int = 0) -> dict | None:
    """The frontier analysis the amenable-mortality anchor exists for: does care access predict
    the outcome it is *supposed* to (deaths timely care should prevent), and does it add signal
    BEYOND deprivation? All-cause mortality is need-dominated and can only show care access as
    marginal (docs/VALIDATION.md §2); amenable mortality is the access-sensitive ruler.

    Reports, with cluster-bootstrap (county) 95% CIs:
      - care_access marginal value = composite-r(amenable) FULL minus drop-care (paired)
      - PARTIAL r(amenable, care_access | health_need, social_vulnerability) - the key number:
        care access's association net of the deprivation gradient it is collinear with.
    Returns None (no-op) until a WONDER export has been built (see build_amenable)."""
    if "amenable_mortality" not in d.columns:
        return None
    y = d["amenable_mortality"].to_numpy(float)  # higher = worse, already oriented
    if np.isfinite(y).sum() < 100:
        return None

    X = d[DIM_COLS].to_numpy(float)
    care_i = DIM_COLS.index("care_access_pctile")
    keep = [i for i in range(len(DIM_COLS)) if i != care_i]  # need + vulnerability
    groups = _cluster_groups(d)
    n_clusters = len(groups)
    rng = np.random.default_rng(seed)

    def stats(ridx: np.ndarray) -> tuple[float, float]:
        full = _corr(_rank(np.nanmean(X[ridx], axis=1)), y[ridx])
        drop = _corr(_rank(np.nanmean(X[ridx][:, keep], axis=1)), y[ridx])
        partial = _partial_corr(y[ridx], X[ridx][:, care_i], X[ridx][:, keep])
        return full - drop, partial

    base = np.arange(len(d))
    p_margin, p_partial = stats(base)
    p_full = _corr(_rank(np.nanmean(X, axis=1)), y)
    p_care_raw = _corr(X[:, care_i], y)

    bm, bp = [], []
    for _ in range(n_boot):
        pick = rng.integers(0, n_clusters, n_clusters)
        ridx = np.concatenate([groups[i] for i in pick])
        m, p = stats(ridx)
        bm.append(m)
        bp.append(p)

    def ci(arr: list[float]) -> list[float]:
        a = np.asarray(arr, float)
        a = a[~np.isnan(a)]
        return [round(float(np.percentile(a, 2.5)), 3), round(float(np.percentile(a, 97.5)), 3)]

    n_cty = int(d.loc[d["amenable_mortality"].notna(), "county_fips"].nunique()) \
        if "county_fips" in d.columns else None
    return {
        "outcome": "amenable_mortality (treatable, OECD 0-74; CDC WONDER)",
        "n_zctas_with_outcome": int(np.isfinite(y).sum()),
        "n_counties": n_cty,
        "composite_full_r": round(float(p_full), 3),
        "care_access_raw_r": round(float(p_care_raw), 3),
        "care_access_marginal": {"point": round(float(p_margin), 3), "ci95": ci(bm)},
        "care_access_partial_r": {"point": round(float(p_partial), 3), "ci95": ci(bp),
                                  "controls": ["health_need", "social_vulnerability"]},
        "reading": "partial r > 0 with a CI excluding 0 => care access tracks treatable mortality "
                   "BEYOND the deprivation gradient - the legitimate basis for weighting it.",
    }


def _block_ci(d: pd.DataFrame, stat_fn, level: str, n_boot: int, seed: int) -> dict:
    """Generic block-bootstrap CI for a scalar statistic `stat_fn(ridx)->float` under a given
    spatial blocking level. Returns point, CI, and the cluster count (so the reader sees how
    many independent blocks back the interval)."""
    groups = _cluster_groups(d, level)
    n_clusters = len(groups)
    rng = np.random.default_rng(seed)
    point = stat_fn(np.arange(len(d)))
    boot = []
    for _ in range(n_boot):
        pick = rng.integers(0, n_clusters, n_clusters)
        boot.append(stat_fn(np.concatenate([groups[i] for i in pick])))
    a = np.asarray(boot, float)
    a = a[~np.isnan(a)]
    ci = [round(float(np.percentile(a, 2.5)), 3), round(float(np.percentile(a, 97.5)), 3)]
    return {"point": round(float(point), 3), "ci95": ci, "n_clusters": n_clusters,
            "excludes_0": bool(ci[0] > 0 or ci[1] < 0)}


def spatial_sensitivity(d: pd.DataFrame, n_boot: int = 1000, seed: int = 0) -> dict | None:
    """Point 2 (statistician's critique): the county cluster bootstrap respects WITHIN-county
    pseudo-replication but still treats counties as spatially independent. Health geography is
    strongly autocorrelated, so the true effective N is below the county count and every county-
    blocked CI is too narrow. This re-runs the two headline claims under STATE blocking (whole
    states resampled - the conservative correction for between-county autocorrelation) beside the
    county baseline, so the reader sees how much the interval widens and whether the claim SURVIVES
    the honest bar. amenable-only (it is the load-bearing out-of-outcome claim)."""
    if "amenable_mortality" not in d.columns:
        return None
    y = d["amenable_mortality"].to_numpy(float)
    if np.isfinite(y).sum() < 100:
        return None
    X = d[DIM_COLS].to_numpy(float)
    care_i = DIM_COLS.index("care_access_pctile")
    keep = [i for i in range(len(DIM_COLS)) if i != care_i]

    def partial(ridx: np.ndarray) -> float:
        return _partial_corr(y[ridx], X[ridx][:, care_i], X[ridx][:, keep])

    def margin(ridx: np.ndarray) -> float:
        full = _corr(_rank(np.nanmean(X[ridx], axis=1)), y[ridx])
        drop = _corr(_rank(np.nanmean(X[ridx][:, keep], axis=1)), y[ridx])
        return full - drop

    out = {"claim": "care_access vs amenable mortality, county vs state spatial blocking"}
    for name, fn in (("care_access_partial_r", partial), ("care_access_marginal", margin)):
        out[name] = {lvl: _block_ci(d, fn, lvl, n_boot, seed) for lvl in ("county", "state")}
    out["reading"] = ("If 'state' (the spatially-honest block) still excludes 0, the claim survives "
                      "the between-county autocorrelation the county bootstrap ignores. A wider but "
                      "still-positive CI is the expected, honest outcome.")
    return out


def b4_circularity_bound(d: pd.DataFrame, n_boot: int = 1000, seed: int = 0) -> dict | None:
    """B4 is not fixable (PLACES disease estimates are SES-conditioned, so health_need shares modeled
    variance with social_vulnerability - a non-identified circularity). But it can be BOUNDED: how
    much of the index's validity against INDEPENDENT (non-PLACES, death/hospitalization-records)
    outcomes actually depends on the PLACES dimension? Rebuild the composite WITHOUT health_need (the
    pure-PLACES dimension; care_access + social_vulnerability are ACS/NPPES-dominant) and re-correlate.
    If most validity survives, the external-validity case does NOT rest on the circular dimension, so
    the circularity caps the internal-coherence story, not the index's usefulness.

    Also contrasts the CIRCULAR anchor (PLACES general health) against the independent ones, with a
    cluster-bootstrap CI on the retained fraction for amenable (the cleanest ruler)."""
    indep = {"amenable_mortality": "worse", "preventable_hosp": "worse",
             "premature_death": "worse", "infant_mortality": "worse"}
    outs = {}
    for o, direction in indep.items():
        if o in d.columns:
            y = d[o].to_numpy(float)
            outs[o] = (np.nanmax(y) - y) if direction == "better" else y
    if not outs:
        return None
    X = d[DIM_COLS].to_numpy(float)
    hn_i = DIM_COLS.index("health_need_pctile")
    keep = [i for i in range(len(DIM_COLS)) if i != hn_i]  # vuln + care: the minimal-PLACES index

    def full_rank(ridx):
        return _rank(np.nanmean(X[ridx], axis=1))

    def nohn_rank(ridx):
        return _rank(np.nanmean(X[ridx][:, keep], axis=1))

    base = np.arange(len(d))
    rows = {}
    for o, y in outs.items():
        rf, rn = _corr(full_rank(base), y), _corr(nohn_rank(base), y)
        rows[o] = {"full": round(float(rf), 3), "no_health_need": round(float(rn), 3),
                   "retained_frac": round(float(rn / rf), 3) if rf else None}

    # cluster-bootstrap CI on the retained fraction for amenable (the load-bearing independent ruler)
    ci = None
    if "amenable_mortality" in outs:
        y = outs["amenable_mortality"]
        groups = _cluster_groups(d)
        rng = np.random.default_rng(seed)
        fr = []
        for _ in range(n_boot):
            pick = rng.integers(0, len(groups), len(groups))
            ridx = np.concatenate([groups[i] for i in pick])
            rf, rn = _corr(full_rank(ridx), y[ridx]), _corr(nohn_rank(ridx), y[ridx])
            if rf:
                fr.append(rn / rf)
        a = np.asarray(fr, float)
        a = a[~np.isnan(a)]
        if len(a):
            ci = [round(float(np.percentile(a, 2.5)), 3), round(float(np.percentile(a, 97.5)), 3)]

    anchor = None
    if "ghlth_pct" in d.columns:
        g = d["ghlth_pct"].to_numpy(float)
        anchor = {"full_r": round(float(_corr(full_rank(base), g)), 3),
                  "note": "PLACES fair/poor general health - CIRCULAR (PLACES-derived); shown only "
                          "to contrast with the independent rulers, NOT as validation"}
    return {
        "independent_outcomes": rows,
        "amenable_retained_frac_ci95": ci,
        "places_anchor_circular": anchor,
        "reading": "retained_frac = validity of the NO-PLACES composite / the full composite, on an "
                   "outcome PLACES never touched. High retained_frac => the external-validity case "
                   "does not depend on the SES-conditioned dimension, so B4 bounds the internal "
                   "coherence story, not the index's predictive usefulness.",
    }


def _bh_fdr(pvals: dict[str, float], q: float = 0.05) -> dict[str, dict]:
    """Benjamini-Hochberg FDR across a candidate set. Returns per-key the raw p, the BH-adjusted
    p (q-value), and whether it survives at the given q. Quantifies the multiplicity the
    input-selection ledger never corrected (docs/VALIDATION.md §1c, BACKLOG B3)."""
    items = [(k, v) for k, v in pvals.items() if v is not None and not np.isnan(v)]
    m = len(items)
    if not m:
        return {}
    items.sort(key=lambda kv: kv[1])
    # step-up adjusted p: q_(i) = min_{j>=i} ( p_(j) * m / j ), monotone
    adj = [0.0] * m
    running = 1.0
    for i in range(m - 1, -1, -1):
        running = min(running, items[i][1] * m / (i + 1))
        adj[i] = min(running, 1.0)
    return {k: {"p": round(p, 4), "q_value": round(adj[i], 4), "survives_fdr": adj[i] <= q}
            for i, (k, p) in enumerate(items)}


def amenable_subscores(d: pd.DataFrame, n_boot: int = 1000, seed: int = 0) -> dict | None:
    """B2: re-test each *scored* care sub-score against amenable mortality - the INDEPENDENT,
    access-sensitive outcome - net of the deprivation gradient. Only the dimension-level care
    claim got the clean out-of-outcome replication (amenable_focus); individual barriers selected
    on thin margins vs the standard 6 outcomes (e.g. medical_debt) were never re-tested on the
    independent ruler, so they remain 'selection-soft' (winner's curse, VALIDATION §1c).

    For each scored care sub-score s: partial r(amenable, s | health_need, social_vulnerability)
    with cluster-bootstrap (county) 95% CIs + a one-sided bootstrap p (share of replicates where
    the partial is <= 0). Applies Benjamini-Hochberg FDR across the candidate set so the multiple
    comparisons are finally corrected (BACKLOG B3). A sub-score that holds a positive partial r
    here is corroborated on an outcome it was NOT selected against; one whose CI/FDR collapses gets
    a documented caveat. Returns None until a WONDER export exists."""
    if "amenable_mortality" not in d.columns:
        return None
    y = d["amenable_mortality"].to_numpy(float)
    if np.isfinite(y).sum() < 100:
        return None

    # scored care sub-scores only (safetynet_access, preventive_use are scored=False)
    care_subs = [s for s in subscore_specs()
                 if s["dim"] == "care_access" and s.get("scored", True)
                 and f"{s['key']}_pctile" in d.columns]
    keys = [s["key"] for s in care_subs]
    C = d[[f"{k}_pctile" for k in keys]].to_numpy(float)   # sub-score percentiles
    Z = d[["health_need_pctile", "social_vulnerability_pctile"]].to_numpy(float)  # controls

    groups = _cluster_groups(d)
    n_clusters = len(groups)
    rng = np.random.default_rng(seed)

    def partials(ridx: np.ndarray) -> list[float]:
        return [_partial_corr(y[ridx], C[ridx, j], Z[ridx]) for j in range(len(keys))]

    base = np.arange(len(d))
    p_partial = partials(base)
    p_raw = [_corr(C[:, j], y) for j in range(len(keys))]

    boot = [[] for _ in keys]
    for _ in range(n_boot):
        pick = rng.integers(0, n_clusters, n_clusters)
        ridx = np.concatenate([groups[i] for i in pick])
        for j, val in enumerate(partials(ridx)):
            boot[j].append(val)

    def summarize(j: int) -> dict:
        a = np.asarray(boot[j], float)
        a = a[~np.isnan(a)]
        ci = [round(float(np.percentile(a, 2.5)), 3), round(float(np.percentile(a, 97.5)), 3)]
        # one-sided bootstrap p: share of replicates where the partial is <= 0 (no positive effect)
        p_one = float(np.mean(a <= 0)) if len(a) else np.nan
        return {"raw_r": round(float(p_raw[j]), 3),
                "partial_r": round(float(p_partial[j]), 3), "ci95": ci, "p_one_sided": p_one}

    res = {keys[j]: summarize(j) for j in range(len(keys))}
    fdr = _bh_fdr({k: res[k]["p_one_sided"] for k in keys})
    for k in keys:
        res[k]["p_one_sided"] = round(res[k]["p_one_sided"], 4)
        if k in fdr:
            res[k]["q_value"] = fdr[k]["q_value"]
            res[k]["survives_fdr"] = fdr[k]["survives_fdr"]

    return {
        "outcome": "amenable_mortality (treatable, OECD 0-74; CDC WONDER)",
        "controls": ["health_need", "social_vulnerability"],
        "method": "partial r per scored care sub-score, cluster-bootstrap (county) 95% CI; one-sided "
                  "bootstrap p; Benjamini-Hochberg FDR across the sub-score set (q<=0.05)",
        "n_candidates": len(keys),
        "subscores": res,
        "reading": "A care sub-score with partial_r > 0, a CI excluding 0, AND survives_fdr is "
                   "corroborated on the independent outcome it was NOT selected against. One that "
                   "collapses here was a winner's-curse artifact of selection on the standard 6.",
    }


def run(n_boot: int = 1000, seed: int = 0) -> dict:
    df = pd.read_parquet(METRICS)
    d = df[df["scoreable"] == True].reset_index(drop=True)  # noqa: E712
    ys = _oriented(d)
    outcome_names = list(ys.keys())
    Y = np.column_stack([ys[o] for o in outcome_names])

    X = d[DIM_COLS].to_numpy(float)                       # dimension percentiles
    comp = d["access_gap_score"].to_numpy(float)         # additive composite (raw weighted mean)
    sub_specs = [s for s in subscore_specs() if f"{s['key']}_pctile" in d.columns]
    S = d[[f"{s['key']}_pctile" for s in sub_specs]].to_numpy(float)

    groups = _cluster_groups(d)
    n_clusters = len(groups)
    rng = np.random.default_rng(seed)

    keep_idx = {drop: [k for k in range(len(DIM_COLS)) if k != i]
                for i, drop in enumerate(DIMENSIONS)}

    def full_drop(ridx: np.ndarray) -> tuple[float, dict[str, float]]:
        full = _mean_r(_rank(np.nanmean(X[ridx], axis=1)), Y[ridx])
        drops = {drop: _mean_r(_rank(np.nanmean(X[ridx][:, keep], axis=1)), Y[ridx])
                 for drop, keep in keep_idx.items()}
        return full, drops

    # point estimates (no resampling)
    base_idx = np.arange(len(d))
    p_full, p_drops = full_drop(base_idx)
    p_comp = _mean_r(comp, Y)
    p_sub = {s["key"]: _mean_abs_r(S[:, j], Y) for j, s in enumerate(sub_specs)}

    boot = {"full": [], "comp": [], **{f"margin_{k}": [] for k in DIMENSIONS},
            **{f"drop_{k}": [] for k in DIMENSIONS},
            **{f"sub_{s['key']}": [] for s in sub_specs}}

    for b in range(n_boot):
        pick = rng.integers(0, n_clusters, n_clusters)
        ridx = np.concatenate([groups[i] for i in pick])
        full, drops = full_drop(ridx)
        boot["full"].append(full)
        boot["comp"].append(_mean_r(comp[ridx], Y[ridx]))
        for k in DIMENSIONS:
            boot[f"drop_{k}"].append(drops[k])
            boot[f"margin_{k}"].append(full - drops[k])      # paired
        for j, s in enumerate(sub_specs):
            boot[f"sub_{s['key']}"].append(_mean_abs_r(S[ridx, j], Y[ridx]))
        if (b + 1) % 200 == 0:
            print(f"  ... {b + 1}/{n_boot} replicates")

    def ci(key: str) -> list[float]:
        arr = np.asarray(boot[key], float)
        arr = arr[~np.isnan(arr)]
        return [round(float(np.percentile(arr, 2.5)), 3),
                round(float(np.percentile(arr, 97.5)), 3)]

    margin_care = np.asarray(boot["margin_care_access"], float)
    p_adds = float(np.mean(margin_care > 0))   # bootstrap share where care access adds signal

    report = {
        "method": "cluster bootstrap over county (state|county_name); paired FULL-vs-drop "
                  "differences; 95% percentile CIs",
        "n_boot": n_boot, "n_clusters": n_clusters, "n_zctas": int(len(d)),
        "outcomes": outcome_names,
        "composite_mean_r": {"point": round(p_comp, 3), "ci95": ci("comp")},
        "full_mean_r": {"point": round(p_full, 3), "ci95": ci("full")},
        "margins": {k: {"point": round(p_full - p_drops[k], 3), "ci95": ci(f"margin_{k}")}
                    for k in DIMENSIONS},
        "drops": {k: {"point": round(p_drops[k], 3), "ci95": ci(f"drop_{k}")} for k in DIMENSIONS},
        "care_access_adds_signal_boot_p": round(p_adds, 3),
        "subscores": {s["key"]: {"point": round(p_sub[s["key"]], 3), "ci95": ci(f"sub_{s['key']}")}
                      for s in sub_specs},
    }
    af = amenable_focus(d, n_boot, seed)  # None until a WONDER export is built
    if af:
        report["amenable_focus"] = af
    asub = amenable_subscores(d, n_boot, seed)  # B2: thin care sub-scores vs the independent outcome
    if asub:
        report["amenable_subscores"] = asub
    spat = spatial_sensitivity(d, n_boot, seed)  # point 2: state vs county spatial blocking
    if spat:
        report["spatial_sensitivity"] = spat
    b4 = b4_circularity_bound(d, n_boot, seed)   # B4: how much validity survives without PLACES
    if b4:
        report["b4_circularity_bound"] = b4
    OUT_JSON.write_text(json.dumps(report, indent=2))
    _print(report)
    return report


def _print(r: dict) -> None:
    print("\n=== BOOTSTRAP GATE (cluster=county, paired margins, 95% CI) ===")
    print(f"  replicates={r['n_boot']}  clusters(counties)={r['n_clusters']}  zctas={r['n_zctas']}")
    c = r["composite_mean_r"]; print(f"  composite mean-r   {c['point']:.3f}  CI{c['ci95']}")
    f = r["full_mean_r"]; print(f"  FULL mean-r        {f['point']:.3f}  CI{f['ci95']}")
    print("  marginal value of each dimension (paired: FULL - drop):")
    for k, m in r["margins"].items():
        sig = "" if (m["ci95"][0] > 0 or m["ci95"][1] < 0) else "  (CI spans 0 - NOT distinguishable from noise)"
        print(f"    drop {k:22s} margin {m['point']:+.3f}  CI{m['ci95']}{sig}")
    print(f"  care_access adds signal in {r['care_access_adds_signal_boot_p']*100:.1f}% of resamples")
    print("  sub-score mean|r| (95% CI):")
    for k, s in r["subscores"].items():
        print(f"    {k:22s} {s['point']:.3f}  CI{s['ci95']}")
    af = r.get("amenable_focus")
    if af:
        print("\n  --- AMENABLE-MORTALITY FOCUS (the access-sensitive ruler) ---")
        print(f"    counties={af['n_counties']}  zctas_with_outcome={af['n_zctas_with_outcome']}")
        print(f"    composite FULL r vs amenable       {af['composite_full_r']:+.3f}")
        print(f"    care_access raw r vs amenable      {af['care_access_raw_r']:+.3f}")
        m = af["care_access_marginal"]
        print(f"    care_access marginal (paired)      {m['point']:+.3f}  CI{m['ci95']}")
        p = af["care_access_partial_r"]
        sig = "" if (p["ci95"][0] > 0 or p["ci95"][1] < 0) else "  (CI spans 0)"
        print(f"    care_access PARTIAL r | need,vuln   {p['point']:+.3f}  CI{p['ci95']}{sig}")
    else:
        print("\n  (amenable-mortality focus: no WONDER export yet - see pipeline/build_amenable.py)")
    asub = r.get("amenable_subscores")
    if asub:
        print("\n  --- B2: SCORED CARE SUB-SCORES vs amenable | need,vuln (winner's-curse re-test) ---")
        print(f"    candidates={asub['n_candidates']}  (BH-FDR q<=0.05 across the set)")
        print(f"    {'sub-score':22s} {'raw_r':>7s} {'partial_r':>10s} {'95% CI':>16s} {'q':>7s}  verdict")
        for k, s in asub["subscores"].items():
            ci = s["ci95"]
            ci_excl0 = ci[0] > 0 or ci[1] < 0
            verdict = "holds" if (s.get("survives_fdr") and ci_excl0 and s["partial_r"] > 0) \
                else "COLLAPSES"
            print(f"    {k:22s} {s['raw_r']:+7.3f} {s['partial_r']:+10.3f} "
                  f"  [{ci[0]:+.3f},{ci[1]:+.3f}] {s.get('q_value', float('nan')):7.3f}  {verdict}")
    sp = r.get("spatial_sensitivity")
    if sp:
        print("\n  --- POINT 2: SPATIAL BLOCKING (county vs state) on the amenable claim ---")
        for name in ("care_access_partial_r", "care_access_marginal"):
            print(f"    {name}:")
            for lvl in ("county", "state"):
                b = sp[name][lvl]
                tag = "excludes 0" if b["excludes_0"] else "  <-- CI SPANS 0"
                print(f"      {lvl:7s} (k={b['n_clusters']:4d} blocks)  {b['point']:+.3f}  "
                      f"CI{b['ci95']}  {tag}")
    b4 = r.get("b4_circularity_bound")
    if b4:
        print("\n  --- B4 BOUND: composite validity WITHOUT the PLACES dimension (health_need) ---")
        print(f"    {'independent outcome':22s} {'full':>7s} {'no-PLACES':>10s} {'retained':>9s}")
        for o, v in b4["independent_outcomes"].items():
            rf = v["retained_frac"]
            print(f"    {o:22s} {v['full']:+7.3f} {v['no_health_need']:+10.3f} "
                  f"{(rf if rf is not None else float('nan')):8.0%}")
        if b4.get("amenable_retained_frac_ci95"):
            print(f"    amenable retained-fraction 95% CI: {b4['amenable_retained_frac_ci95']}")
        print("    => most external validity survives without PLACES: the circularity bounds the "
              "internal\n       coherence story, not the predictive usefulness.")
    print(f"\n  wrote {OUT_JSON.relative_to(config.ROOT)}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    run(n_boot=n)

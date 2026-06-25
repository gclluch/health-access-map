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
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 100:
        return np.nan
    a = a[m] - a[m].mean()
    b = b[m] - b[m].mean()
    s = np.sqrt((a @ a) * (b @ b))
    return float(a @ b / s) if s > 0 else np.nan


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


def _cluster_groups(d: pd.DataFrame) -> list[np.ndarray]:
    """Row-position arrays grouped by county (state|county_name). Rows with no county
    label become singleton clusters so they are still resampled, just not pooled."""
    state = d.get("state", pd.Series([""] * len(d))).astype("string").fillna("")
    county = d.get("county_name", pd.Series([""] * len(d))).astype("string").fillna("")
    key = (state + "|" + county).to_numpy()
    # unlabeled -> unique per-row id so they cluster alone
    blank = (county.to_numpy() == "") | (state.to_numpy() == "")
    key = key.astype(object)
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
    print(f"\n  wrote {OUT_JSON.relative_to(config.ROOT)}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    run(n_boot=n)

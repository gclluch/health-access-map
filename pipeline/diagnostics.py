"""diagnostics: the verification gate run after every access-signal change.

Reports five checks against the six independent (non-PLACES) outcomes. A change ships
only if it passes; the north-star is the marginal value of the care-access dimension -
today dropping it *improves* outcome agreement (a problem we are fixing). See
docs/DECISIONS.md.

    python -m pipeline.diagnostics
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from .join_and_score import _pct
from .taxonomy import DIMENSIONS, subscore_specs

METRICS = config.PROCESSED / "metrics.parquet"
# outcome -> higher value is "better" (needs flipping to higher = worse) or "worse".
# amenable_mortality is OPTIONAL (manual CDC WONDER pull, see build_amenable): _oriented()
# only includes outcomes actually present, so it auto-joins the gate the moment it lands and
# is a no-op until then. It is the one access-sensitive anchor that can legitimately weight
# care access, so bootstrap_gate.amenable_focus() reports it separately too.
OUTCOMES = {
    "life_expectancy": "better", "flu_vaccination": "better", "mammography": "better",
    "preventable_hosp": "worse", "premature_death": "worse", "infant_mortality": "worse",
    "amenable_mortality": "worse",
}
DIM_COLS = [f"{d}_pctile" for d in DIMENSIONS]


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 100:
        return float("nan")
    a, b = a[m] - a[m].mean(), b[m] - b[m].mean()
    s = np.sqrt((a @ a) * (b @ b))
    return float(a @ b / s) if s > 0 else float("nan")


def _oriented(df: pd.DataFrame) -> dict[str, np.ndarray]:
    out = {}
    for o, direction in OUTCOMES.items():
        if o in df.columns:
            y = df[o].to_numpy(float)
            out[o] = (np.nanmax(y) - y) if direction == "better" else y
    return out


def _mean_r(series: np.ndarray, ys: dict) -> float:
    return float(np.nanmean([_corr(series, y) for y in ys.values()]))


def _county_collapsed_mean_r(d: pd.DataFrame, ys: dict) -> tuple[float, int] | None:
    """Matched-resolution point estimate: collapse the composite to its county mean and correlate
    county-to-county against the (county-level) outcomes. The row-level mean-r treats each county's
    ~11 ZCTAs as independent looks at one outcome value (effective N = county count, not 33k rows);
    this reports the same agreement at the resolution the outcomes actually have."""
    if "county_name" not in d.columns or "state" not in d.columns:
        return None
    # build a frame of the ALREADY-ORIENTED outcomes (ys) + composite, keyed by county, and take
    # county means. ys[o] is higher = worse (flipped in _oriented), so correlation signs are correct.
    frame = pd.DataFrame({"_ckey": (d["state"].astype(str) + "|" + d["county_name"].astype(str)).to_numpy(),
                          "comp": d["access_gap_score"].to_numpy()})
    for o, y in ys.items():
        frame[o] = y
    agg = frame.groupby("_ckey").mean(numeric_only=True).reset_index()
    r = float(np.nanmean([_corr(agg["comp"].to_numpy(), agg[o].to_numpy()) for o in ys]))
    return r, int(agg["_ckey"].nunique())


def run() -> dict:
    df = pd.read_parquet(METRICS)
    d = df[df["scoreable"] == True].reset_index(drop=True)  # noqa: E712
    ys = _oriented(d)
    rng = np.random.default_rng(0)
    report: dict = {}

    # 1. NORTH STAR: composite mean-r vs outcomes, full vs drop-each-dimension
    print("=== 1. NORTH STAR: dimension marginal value (mean r vs 6 outcomes) ===")
    full = _mean_r(_pct(d[DIM_COLS].mean(axis=1)).to_numpy(), ys)
    print(f"  FULL (3 dims):        {full:.3f}")
    drops = {}
    for drop in DIMENSIONS:
        keep = [c for c in DIM_COLS if c != f"{drop}_pctile"]
        r = _mean_r(_pct(d[keep].mean(axis=1)).to_numpy(), ys)
        drops[drop] = r
        flag = "  <-- access ADDS signal" if (drop == "care_access" and r < full) else (
               "  <-- access SUBTRACTS signal" if drop == "care_access" else "")
        print(f"  drop {drop:22s}{r:.3f}{flag}")
    report["north_star"] = {"full": round(full, 3), **{f"drop_{k}": round(v, 3) for k, v in drops.items()}}

    # 2. sub-score sign & strength
    print("\n=== 2. SUB-SCORE signal (mean|r|, and signed r per outcome) ===")
    sub = {}
    for s in subscore_specs():
        col = f"{s['key']}_pctile"
        if col not in d.columns:
            continue
        rs = {o: round(_corr(d[col].to_numpy(), y), 2) for o, y in ys.items()}
        mabs = float(np.nanmean([abs(v) for v in rs.values()]))
        sub[s["key"]] = {"mean_abs_r": round(mabs, 3), "signed": rs}
        wrong = any(v < -0.05 for v in rs.values())
        print(f"  {s['key']:22s} mean|r|={mabs:.3f}{'  (some WRONG-signed)' if wrong else ''}")
    report["subscores"] = sub

    # 3. composite outcome agreement
    print("\n=== 3. COMPOSITE outcome agreement ===")
    comp_r = _mean_r(d["access_gap_score"].to_numpy(), ys)
    print(f"  access_gap_score mean r vs outcomes (ZCTA-broadcast): {comp_r:.3f}")
    report["composite_mean_r"] = round(comp_r, 3)

    # 3b. SAME number at honest resolution. Five of six outcomes are county-level (CHR), so the
    # row-level r above correlates 33k ZCTAs against county values broadcast to every ZCTA - the
    # effective N is the COUNTY count (~3,225), not the row count. Collapsing the composite to its
    # county mean and correlating county-to-county is the matched-resolution point estimate. It is
    # NOT smaller here (within-county composite variance has no outcome to track, mildly attenuating
    # the row-level r), but it is the number whose N is real; the row-level r's *precision* is what's
    # overstated, which is why margins are gated on pipeline.bootstrap_gate's CLUSTER bootstrap, not
    # this point. See docs/VALIDATION.md §1.
    cc = _county_collapsed_mean_r(d, ys)
    if cc is not None:
        print(f"  access_gap_score mean r vs outcomes (county-collapsed, N={cc[1]}): {cc[0]:.3f}")
        report["composite_mean_r_county_collapsed"] = round(cc[0], 3)
        report["n_counties"] = cc[1]

    # 4. internal reliability (split-half)
    print("\n=== 4. INTERNAL reliability (split-half Spearman-Brown) ===")
    from .join_and_score import _member_pctile
    members = [m for s in subscore_specs() for m in s["members"]]
    mp = {m["col"]: _member_pctile(d, m).to_numpy() for m in members if _member_pctile(d, m) is not None}
    Mat = np.column_stack(list(mp.values()))
    pop = d["population"].to_numpy(float)
    med = np.nanmedian(pop)

    def sh(mask=None):
        rr = []
        for _ in range(12):
            idx = rng.permutation(Mat.shape[1]); a, b = idx[:Mat.shape[1] // 2], idx[Mat.shape[1] // 2:]
            ca, cb = np.nanmean(Mat[:, a], 1), np.nanmean(Mat[:, b], 1)
            m = ~(np.isnan(ca) | np.isnan(cb))
            if mask is not None:
                m = m & mask
            r = np.corrcoef(ca[m], cb[m])[0, 1]; rr.append(2 * r / (1 + r))
        return float(np.mean(rr))
    overall, lowpop = sh(), sh(pop < med)
    print(f"  overall={overall:.3f}  low-pop={lowpop:.3f}")
    report["reliability"] = {"overall": round(overall, 3), "low_pop": round(lowpop, 3)}

    # 5. coverage & contracts
    print("\n=== 5. COVERAGE & contracts ===")
    n_score = int(df["scoreable"].sum())
    print(f"  scoreable={n_score}")
    report["scoreable"] = n_score

    print("\n--- gate reminder: care-access fix passes iff drop_care_access FALLS and "
          "composite_mean_r does not regress ---")
    print("--- these are POINT estimates. Run `python -m pipeline.bootstrap_gate` for 95% CIs "
          "on every margin (cluster bootstrap over county, paired); ship only if the margin CI "
          "excludes 0. Current: care_access margin +0.042 CI[0.038,0.048], adds signal in 100% "
          "of resamples; social_vulnerability margin -0.008 CI[-0.011,-0.004] (mildly redundant). ---")
    return report


if __name__ == "__main__":
    run()

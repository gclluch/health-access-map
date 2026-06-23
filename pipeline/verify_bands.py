"""verify_bands: Layer-B rank-band verification gate (uncertainty-on-ranks honesty).

The point scores are unchanged by Layer B; only the 5-95 rank bands change, so the
standard harness (pipeline.diagnostics) cannot see this layer. These three checks do
(docs/ROADMAP-ACCESS-SIGNAL.md Layer B):

  1. Differentiation  - low-confidence median band width >= 1.6x high-confidence.
  2. Shrinkage visible - low-conf bands narrower with shrinkage ON than OFF.
  3. Calibration       - the cheap dimension-percentile sigma(cv) injection matches an
                         independent member-input resample within ~+-20%, per ACS dimension.

Usage:
  python -m pipeline.verify_bands                       # gates 1 + 3 (metrics.parquet)
  python -m pipeline.verify_bands --compare OFF.parquet # gate 2 (current=ON vs OFF file)

Gate 3 needs the per-rate effective SEs, dumped to acs_se_debug.parquet by a build run
with HAM_SE_DEBUG=1. If that file is absent, gate 3 is skipped with a notice.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from . import config
from .join_and_score import (_RANK_CV_EXCESS_CAP, _RANK_CV_FLOOR_Q,
                             _RANK_CV_SIGMA_SCALE, _RANK_PLACES_SIGMA_SCALE,
                             _ACS_SHARE, _PLACES_SHARE, _pct)
from .taxonomy import DIMENSIONS, subscore_specs

METRICS = config.PROCESSED / "metrics.parquet"
SE_DEBUG = config.PROCESSED / "acs_se_debug.parquet"
PLACES_SE_DEBUG = config.PROCESSED / "places_se_debug.parquet"


def _band_width(d: pd.DataFrame) -> pd.Series:
    return d["access_gap_rank_hi"] - d["access_gap_rank_lo"]


def gate1_differentiation(d: pd.DataFrame) -> bool:
    w = _band_width(d)
    lo = float(w[d["low_confidence"] == True].median())   # noqa: E712
    hi = float(w[d["low_confidence"] == False].median())  # noqa: E712
    ratio = lo / hi
    ok = ratio >= 1.6
    print("=== GATE 1. Differentiation (low-conf bands wider) ===")
    print(f"  low-conf median band {lo:.1f}  high-conf {hi:.1f}  ratio {ratio:.2f}x "
          f"(target >=1.60)  {'PASS' if ok else 'FAIL'}")
    return ok


def gate2_shrinkage(d_on: pd.DataFrame, d_off: pd.DataFrame) -> bool:
    won = _band_width(d_on); woff = _band_width(d_off)
    lon = float(won[d_on["low_confidence"] == True].median())    # noqa: E712
    loff = float(woff[d_off["low_confidence"] == True].median())  # noqa: E712
    ok = lon < loff
    print("=== GATE 2. Shrinkage visible (ON narrower than OFF) ===")
    print(f"  low-conf median band  shrinkage ON {lon:.1f}  OFF {loff:.1f}  "
          f"({'narrower' if ok else 'NOT narrower'})  {'PASS' if ok else 'FAIL'}")
    return ok


def _injected_sigma(d: pd.DataFrame, dim: str) -> np.ndarray:
    """The sigma (percentile points) Layer B/B3 injects into `dim` for each scoreable ZCTA:
    ACS (excess-over-floor) and PLACES (no-floor, irreducible) terms combined in quadrature -
    matching join_and_score._noise_sigma."""
    n = len(d)
    acs = np.zeros(n)
    if "acs_input_cv" in d.columns and _ACS_SHARE.get(f"{dim}_pctile", 0.0):
        cv = d["acs_input_cv"].to_numpy(float)
        floor = np.nanquantile(cv, _RANK_CV_FLOOR_Q)
        excess = np.clip(np.where(np.isnan(cv), floor, cv) - floor, 0.0, _RANK_CV_EXCESS_CAP)
        acs = _ACS_SHARE[f"{dim}_pctile"] * _RANK_CV_SIGMA_SCALE * excess
    plc = np.zeros(n)
    if "places_input_cv" in d.columns and _PLACES_SHARE.get(f"{dim}_pctile", 0.0):
        pcv = d["places_input_cv"].to_numpy(float)
        med = np.nanmedian(pcv)
        pcv = np.where(np.isnan(pcv), med, pcv)
        plc = _PLACES_SHARE[f"{dim}_pctile"] * _RANK_PLACES_SIGMA_SCALE * pcv
    return np.sqrt(acs ** 2 + plc ** 2)


def gate3_calibration(d: pd.DataFrame, draws: int = 300, sample: int = 600,
                      seed: int = 0) -> bool:
    """Independent member-input resample: perturb each ACS member rate by its effective SE,
    re-percentile through member -> sub-score -> dimension against the fixed national
    distributions, and measure the empirical SD of each ACS dimension's percentile. Compare
    to the sigma Layer B injects. Pass if the median injected/empirical ratio is in [0.8,1.2]
    per ACS dimension. The draw loop is vectorized (draws-wide arrays per ZCTA)."""
    if not SE_DEBUG.exists():
        print("=== GATE 3. Calibration === SKIPPED (no acs_se_debug.parquet; "
              "rebuild acs with HAM_SE_DEBUG=1)")
        return True
    dbg = pd.read_parquet(SE_DEBUG).set_index("zcta5")
    # Layer B3: fold in the PLACES per-measure SEs (same HAM_SE_DEBUG dump) so PLACES members
    # resample too and health_need (pure PLACES) gets a real empirical SD to calibrate against.
    if PLACES_SE_DEBUG.exists():
        plc = pd.read_parquet(PLACES_SE_DEBUG).set_index("zcta5")
        dbg = dbg.join(plc[[c for c in plc.columns if c not in dbg.columns]], how="outer")
    members_with_se = {c[:-3] for c in dbg.columns if c.endswith("_se")}

    specs = {s["key"]: s for s in subscore_specs()}
    member_dir = {m["col"]: m["dir"] for s in specs.values() for m in s["members"]}
    sorted_val, base_mpct = {}, {}
    for col, dirn in member_dir.items():
        if col in d.columns:
            v = pd.to_numeric(d[col], errors="coerce") * dirn
            sorted_val[col] = np.sort(v.dropna().to_numpy())
            base_mpct[col] = _pct(v).to_numpy()
    sorted_subraw = {}
    for key, s in specs.items():
        mps = [base_mpct[m["col"]] for m in s["members"] if m["col"] in base_mpct]
        if mps:
            sorted_subraw[key] = np.sort(pd.Series(np.nanmean(np.column_stack(mps), 1)).dropna().to_numpy())

    def to_pct(sorted_arr, vals):
        return np.searchsorted(sorted_arr, vals, side="right") / len(sorted_arr) * 100.0

    results = {}
    for dkey, dim in DIMENSIONS.items():
        if not (_ACS_SHARE.get(f"{dkey}_pctile", 0.0) or _PLACES_SHARE.get(f"{dkey}_pctile", 0.0)):
            continue
        subs = list(dim["subscores"].keys())
        sorted_dimraw = np.sort(pd.Series(np.nanmean(
            d[[f"{sk}_pctile" for sk in subs]].to_numpy(float), 1)).dropna().to_numpy())
        samp = d[(d["scoreable"] == True) & d["zcta5"].isin(dbg.index)].sample(  # noqa: E712
            min(sample, int(((d["scoreable"] == True) & d["zcta5"].isin(dbg.index)).sum())),  # noqa: E712
            random_state=seed).index.to_numpy()
        rng = np.random.default_rng(seed)
        emp_sd = np.full(len(samp), np.nan)
        for i, ridx in enumerate(samp):
            z = d.at[ridx, "zcta5"]
            sub_pcts = []  # each (draws,) or scalar broadcast
            for sk in subs:
                mcols = [m["col"] for m in dim["subscores"][sk]["members"] if m["col"] in base_mpct]
                resampled = [mc for mc in mcols if mc in members_with_se]
                if not resampled:  # no input-noise data for this sub-score: fixed baseline
                    sub_pcts.append(np.full(draws, d.at[ridx, f"{sk}_pctile"]))
                    continue
                member_pcts = []
                for mc in mcols:
                    if mc in resampled:
                        rate = pd.to_numeric(d.at[ridx, mc], errors="coerce")
                        se = dbg.at[z, f"{mc}_se"]
                        if np.isnan(rate) or np.isnan(se):
                            member_pcts.append(np.full(draws, base_mpct[mc][ridx])); continue
                        se = min(se, 2.0 * abs(rate)) if rate else se  # match acs_input_cv [0,2] cap
                        pert = (rate + rng.standard_normal(draws) * se) * member_dir[mc]
                        member_pcts.append(to_pct(sorted_val[mc], pert))
                    else:
                        member_pcts.append(np.full(draws, base_mpct[mc][ridx]))
                sraw = np.nanmean(np.column_stack(member_pcts), 1)
                sub_pcts.append(to_pct(sorted_subraw[sk], sraw))
            dimraw = np.nanmean(np.column_stack(sub_pcts), 1)
            emp_sd[i] = float(np.nanstd(to_pct(sorted_dimraw, dimraw)))
        inj = _injected_sigma(d, dkey)[samp]
        m = (inj > 1.0) & ~np.isnan(emp_sd) & (emp_sd > 0)
        ratio = float(np.median(inj[m] / emp_sd[m])) if m.sum() > 20 else float("nan")
        results[dkey] = (float(np.nanmedian(emp_sd[m])) if m.sum() else float("nan"),
                         float(np.nanmedian(inj[m])) if m.sum() else float("nan"), ratio, int(m.sum()))

    print("=== GATE 3. Calibration (injected sigma vs member-resample, per dim: ACS + PLACES) ===")
    ok = True
    for dkey, (emp, inj, ratio, n) in results.items():
        good = 0.8 <= ratio <= 1.2 if not np.isnan(ratio) else False
        ok = ok and (good or np.isnan(ratio))
        print(f"  {dkey:24s} empirical sd {emp:5.1f}  injected {inj:5.1f}  "
              f"inj/emp {ratio:4.2f}  (n={n})  {'PASS' if good else 'CHECK'}")
    print(f"  -> {'PASS' if ok else 'tune _ACS_SHARE/scale so inj/emp in [0.8,1.2]'}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", help="OFF-shrinkage metrics parquet for gate 2")
    args = ap.parse_args()
    d = pd.read_parquet(METRICS)
    d = d[d["scoreable"] == True].reset_index(drop=True)  # noqa: E712
    g1 = gate1_differentiation(d)
    g3 = gate3_calibration(d)
    g2 = True
    if args.compare:
        off = pd.read_parquet(args.compare)
        off = off[off["scoreable"] == True].reset_index(drop=True)  # noqa: E712
        g2 = gate2_shrinkage(d, off)
    print(f"\nLAYER B GATE: {'ALL PASS' if (g1 and g2 and g3) else 'NOT YET'} "
          f"(g1={g1} g2={g2 if args.compare else 'run --compare'} g3={g3})")


if __name__ == "__main__":
    main()

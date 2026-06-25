"""selection_diag: is the index's missingness ignorable, or does it bias the ranking?

The composite is a national percentile rank, so any SYSTEMATIC difference between the ZCTAs
that get a (full) score and those that don't biases everyone's rank. This module makes the
missingness auditable instead of assumed-ignorable. Three nested selections, each tested
against an INDEPENDENT outcome (amenable mortality, 99% coverage; USALEEP life expectancy):

  1. Scoreability    - scoreable vs not. (Spoiler: benign - non-scoreable ZCTAs are unpopulated,
                       ~0% of national population, so they carry no rank to bias.)
  2. Dimension completeness - 3-of-3 vs 2-of-3 dimensions. A 2-of-3 composite is built from
                       collinear dimensions; if the 2-of-3 set differs on the outcome, those
                       ranks are biased relative to the 3-of-3 majority.
  3. Validation subset - among scoreable ZCTAs, those WITH vs WITHOUT each validation outcome.
                       If outcome-present ZCTAs differ systematically, every reported validation
                       correlation is computed on a non-representative subset (MAR violated).

Also reports per-sub-score member completeness (a skipna-mean over missing members silently
re-weights the present ones). Read-only; writes a "selection" block to provenance + prints.

    python -m pipeline.selection_diag
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from .common import log, write_provenance
from .taxonomy import DIMENSIONS, subscore_specs

METRICS = config.PROCESSED / "metrics.parquet"
DIM_COLS = [f"{d}_pctile" for d in DIMENSIONS]
# independent outcomes to test selection against (higher = worse already, or flipped here)
OUTCOMES = {"amenable_mortality": "worse", "life_expectancy": "better", "preventable_hosp": "worse"}


def _oriented(df: pd.DataFrame, col: str) -> np.ndarray:
    y = pd.to_numeric(df[col], errors="coerce").to_numpy(float)
    return (np.nanmax(y) - y) if OUTCOMES[col] == "better" else y


def _cohend(a: np.ndarray, b: np.ndarray) -> float | None:
    """Standardized mean difference (group a minus b) - effect size robust to the huge N that
    makes every t-test 'significant'. |d|<0.1 trivial, 0.2 small, 0.5 medium, 0.8 large."""
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    if len(a) < 30 or len(b) < 30:
        return None
    na, nb = len(a), len(b)
    sp = np.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
    return float((a.mean() - b.mean()) / sp) if sp > 0 else None


def _compare(df: pd.DataFrame, mask: np.ndarray, label_in: str, label_out: str) -> dict:
    """Effect sizes between the in-group (mask) and out-group on the composite + every
    independent outcome. A near-zero d means the selection is ignorable for that variable."""
    out: dict = {"n_in": int(mask.sum()), "n_out": int((~mask).sum())}
    comp = pd.to_numeric(df["access_gap_pctile"], errors="coerce").to_numpy(float)
    out["access_gap_pctile_d"] = _round(_cohend(comp[mask], comp[~mask]))
    for o in OUTCOMES:
        if o in df.columns:
            y = _oriented(df, o)
            out[f"{o}_d"] = _round(_cohend(y[mask], y[~mask]))
    out["_legend"] = f"Cohen d = ({label_in}) minus ({label_out}); + => in-group higher/worse"
    return out


def _round(x: float | None) -> float | None:
    return round(x, 3) if x is not None else None


def run() -> dict:
    if not METRICS.exists():
        raise SystemExit(f"missing {METRICS}; run the pipeline first")
    df = pd.read_parquet(METRICS)
    pop = pd.to_numeric(df["population"], errors="coerce")
    sc = df["scoreable"].astype(bool).to_numpy()
    report: dict = {}

    # 1. scoreability selection - quantify the population at stake
    pop_total = float(np.nansum(pop.to_numpy()))
    report["scoreability"] = {
        "n_scoreable": int(sc.sum()), "n_non_scoreable": int((~sc).sum()),
        "non_scoreable_pop_share": round(float(np.nansum(pop.to_numpy()[~sc]) / pop_total), 5),
        "verdict": "benign if pop share ~0 - unpopulated ZCTAs carry no rank to bias",
    }

    # 2. dimension completeness: 3-of-3 vs 2-of-3 (within scoreable)
    nd = pd.to_numeric(df["n_dims_scored"], errors="coerce").to_numpy(float)
    full = sc & (nd >= 3)
    partial = sc & (nd == 2)
    sub = df.copy()
    report["dimension_completeness"] = {
        "n_full_3of3": int(full.sum()), "n_partial_2of3": int(partial.sum()),
        "partial_share": round(float(partial.sum() / sc.sum()), 4),
        **{k: v for k, v in _compare(sub, partial, "2of3", "3of3").items()
           if k not in ("n_in", "n_out")},
    }

    # 3. validation-subset selection: among scoreable, outcome-present vs outcome-absent
    report["validation_subset"] = {}
    for o in OUTCOMES:
        if o not in df.columns:
            continue
        present = sc & pd.to_numeric(df[o], errors="coerce").notna().to_numpy()
        absent = sc & ~pd.to_numeric(df[o], errors="coerce").notna().to_numpy()
        if present.sum() < 30 or absent.sum() < 30:
            report["validation_subset"][o] = {"coverage": round(float(present.sum() / sc.sum()), 3),
                                              "note": "too few absent to test"}
            continue
        comp = pd.to_numeric(df["access_gap_pctile"], errors="coerce").to_numpy(float)
        report["validation_subset"][o] = {
            "coverage_among_scoreable": round(float(present.sum() / sc.sum()), 3),
            "n_absent": int(absent.sum()),
            "access_gap_pctile_d": _round(_cohend(comp[absent], comp[present])),
            "legend": "d = (outcome-ABSENT) minus (outcome-present) composite; "
                      "large |d| => validation r is computed on a non-representative subset",
        }

    # 4. per-sub-score member completeness (skipna re-weights present members silently)
    report["subscore_member_completeness"] = _member_completeness(df, sc)

    write_provenance({"selection": report})
    _print(report)
    return report


def _member_completeness(df: pd.DataFrame, sc: np.ndarray) -> dict:
    """For each sub-score, the mean fraction of its measures that are present (among scoreable
    ZCTAs where the sub-score is defined). A low value = the sub-score routinely averages over
    missing members, so it is a thinner estimate than its members suggest."""
    out = {}
    d = df[sc]
    for spec in subscore_specs():
        cols = [m["col"] for m in spec["members"] if m["col"] in d.columns]
        if not cols:
            continue
        present = d[cols].notna().sum(axis=1)
        defined = present > 0
        if defined.sum() < 30:
            continue
        out[spec["key"]] = {
            "n_members": len(cols),
            "mean_frac_present": round(float((present[defined] / len(cols)).mean()), 3),
            "pct_full": round(float((present[defined] == len(cols)).mean()), 3),
        }
    return out


def _print(r: dict) -> None:
    print("\n=== SELECTION / MISSINGNESS AUDIT ===")
    s = r["scoreability"]
    print(f"1. Scoreability: {s['n_scoreable']} scoreable / {s['n_non_scoreable']} not; "
          f"non-scoreable hold {s['non_scoreable_pop_share']*100:.3f}% of population")
    print(f"   -> {s['verdict']}")
    dc = r["dimension_completeness"]
    print(f"\n2. Dimension completeness: {dc['n_full_3of3']} full (3/3), {dc['n_partial_2of3']} "
          f"partial (2/3, {dc['partial_share']*100:.1f}%)")
    print(f"   effect sizes 2of3 vs 3of3 (Cohen d):")
    for k, v in dc.items():
        if k.endswith("_d") and v is not None:
            flag = "  <-- non-trivial (|d|>=0.2)" if abs(v) >= 0.2 else ""
            print(f"     {k:32s} {v:+.3f}{flag}")
    print(f"\n3. Validation-subset selection (outcome-absent vs present composite):")
    for o, v in r["validation_subset"].items():
        if "access_gap_pctile_d" in v:
            d = v["access_gap_pctile_d"]
            flag = "  <-- subset BIASED (|d|>=0.2)" if (d is not None and abs(d) >= 0.2) else ""
            print(f"     {o:20s} coverage {v['coverage_among_scoreable']*100:5.1f}%  "
                  f"absent-vs-present d {d:+.3f}{flag}" if d is not None
                  else f"     {o:20s} coverage {v['coverage_among_scoreable']*100:5.1f}%")
    print(f"\n4. Sub-score member completeness (mean frac of members present):")
    for k, v in sorted(r["subscore_member_completeness"].items(), key=lambda kv: kv[1]["mean_frac_present"]):
        flag = "  <-- thin (members often missing)" if v["mean_frac_present"] < 0.8 else ""
        print(f"     {k:24s} {v['mean_frac_present']:.2f} present ({v['n_members']} members, "
              f"{v['pct_full']*100:.0f}% full){flag}")


if __name__ == "__main__":
    run()

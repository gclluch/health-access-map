"""validate: honest, multi-anchor validation of the Access Gap composite.

Standalone stage (reads data/processed/metrics.parquet + outcomes.parquet) so it can be
re-run cheaply after the supply layer changes WITHOUT a full rebuild:

    python -m pipeline.run --only validate

It is generic over the model: dimensions come from taxonomy.DIMENSIONS and sub-scores
from the *_pctile columns present, so adding supply specialties needs no edits here.

What it produces:
  - For each independent OUTCOME anchor (ACSC preventable hospitalizations, premature
    death, infant mortality, optional amenable mortality - all county-level; plus
    USALEEP life expectancy at ZCTA level), a set of outcome-anchored dimension weights
    (constrained NNLS + 5% floor, HPI-style), the fit R^2, and each dimension's signed
    correlation with the outcome.
  - Per-sub-score signed correlations with each anchor (exposes which care-access pieces
    actually track outcomes vs. which are confounded - see docs/COMPOSITE-ENHANCEMENT.md).
  - frontend/public/weights.json (default theory weights + the labeled anchored presets +
    diagnostics) and a "validation" block in provenance.json.

KEY HONESTY POINT recorded in the output: all-cause life expectancy is a *need* outcome,
so its anchored weights starve care-access by construction. The access-sensitive anchors
(ACSC, amenable mortality) are the ones that can legitimately weight the care dimension.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import config
from .common import die, log, write_provenance
from .taxonomy import DIMENSION_WEIGHTS, DIMENSIONS

METRICS = config.PROCESSED / "metrics.parquet"
OUTCOMES = config.PROCESSED / "outcomes.parquet"
WEIGHTS_JSON = config.FRONTEND_PUBLIC / "weights.json"

DIM_COLS = [f"{d}_pctile" for d in DIMENSIONS]

# anchor -> (label, scope, direction, caveat). scope "county" outcomes are aggregated up;
# "zcta" used at ZCTA resolution. direction "worse" = higher value is worse (used as-is);
# "better" = higher value is better (flipped to a deficit so every anchor reads higher=worse).
ANCHORS = {
    "preventable_hosp": ("Preventable hospitalizations (ACSC)", "county", "worse",
                         "Medicare 65+ FFS; the textbook ambulatory-access outcome"),
    "amenable_mortality": ("Amenable mortality", "county", "worse",
                           "deaths avoidable with timely care (IHME HAQ gold standard)"),
    "premature_death": ("Premature death (YPLL)", "county", "worse",
                        "broad mortality burden; partly need-driven"),
    "infant_mortality": ("Infant mortality", "county", "worse",
                         "natural validator for maternity (OB-GYN) supply; sparse at county"),
    "flu_vaccination": ("Flu vaccination (Medicare)", "county", "better",
                        "proximal: did people actually receive care? Closer to access than mortality"),
    "mammography": ("Mammography screening (Medicare)", "county", "better",
                    "proximal access/utilization; claims-based, independent of the PLACES model"),
    "life_expectancy": ("Life expectancy", "zcta", "better",
                        "all-cause -> a NEED outcome; starves care-access by construction. "
                        "Validity check only, not a recommended weighting."),
}


def _wmean(frame: pd.DataFrame, value_cols: list[str], by: str, w: str) -> pd.DataFrame:
    """Population-weighted mean of value_cols grouped by `by`, NaN-aware per column.
    All intermediates are built from aligned numpy arrays (fresh default index) so the
    group key never misaligns against a gappy source index."""
    key = frame[by].to_numpy()
    wt = frame[w].to_numpy(float)
    out = {}
    for c in value_cols:
        v = frame[c].to_numpy(float)
        m = ~np.isnan(v) & ~np.isnan(wt) & (wt > 0)
        tmp = pd.DataFrame({by: key, "num": np.where(m, v * wt, 0.0), "den": np.where(m, wt, 0.0)})
        gp = tmp.groupby(by, as_index=True)[["num", "den"]].sum()
        out[c] = gp["num"] / gp["den"].replace(0, np.nan)
    res = pd.DataFrame(out)
    res.index.name = by
    return res.reset_index()


def _corr(a: np.ndarray, b: np.ndarray) -> float | None:
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 100:
        return None
    a, b = a[m] - a[m].mean(), b[m] - b[m].mean()
    denom = np.sqrt((a @ a) * (b @ b))
    return float(a @ b / denom) if denom > 0 else None


def _floor_weights(vals: list[float], floor: float = 5.0) -> dict:
    """Map non-negative dimension scores to weights summing to 100 with a hard `floor`
    per dimension: each gets `floor` points, the rest is split proportionally. Used for
    the correlation-based presets so every dimension (incl. care access) stays visible."""
    v = np.clip(np.asarray(vals, float), 0, None)
    s = v.sum()
    share = v / s if s > 0 else np.full(len(v), 1 / len(v))
    w = floor + (100 - floor * len(v)) * share
    return {d: round(float(x), 1) for d, x in zip(DIMENSIONS, w)}


def _regression(X: np.ndarray, y: np.ndarray) -> dict | None:
    """Constrained NNLS of standardized dimensions on the (oriented) outcome + R^2.
    Reported as a DIAGNOSTIC: under collinearity it routes shared variance to the
    strongest single dimension (health need), so it understates care access - which is
    exactly why the presets use correlation weighting, not this. See COMPOSITE-ENHANCEMENT."""
    try:
        from scipy.optimize import nnls
    except Exception:  # noqa: BLE001
        return None
    m = ~(np.isnan(y) | np.isnan(X).any(axis=1))
    if m.sum() < 200:
        return None
    Xs = (X[m] - X[m].mean(0)) / X[m].std(0)
    yc = y[m] - y[m].mean()
    coef, _ = nnls(Xs, yc)
    if coef.sum() == 0:
        return None
    w = 5.0 + (100 - 5.0 * len(coef)) * coef / coef.sum()
    pred = Xs @ coef
    ss = float((yc ** 2).sum())
    r2 = 1.0 - float(((yc - pred) ** 2).sum()) / ss if ss > 0 else 0.0
    return {
        "regression_weights": {d: round(float(v), 1) for d, v in zip(DIMENSIONS, w)},
        "fit": {"r2": round(r2, 3), "n": int(m.sum())},
    }


def build(dev_state: str | None = None, force: bool = False) -> str:
    if not METRICS.exists():
        die("validate", f"missing {METRICS.name}; run join_and_score first")
    df = pd.read_parquet(METRICS)
    df = df[df["scoreable"] == True].copy()  # noqa: E712
    sub_cols = [c for c in df.columns if c.endswith("_pctile")
                and c not in DIM_COLS and c not in ("access_gap_pctile", "life_expectancy_pctile")]

    # county-level outcomes usually ride in via join (OPTIONAL_STAGES). Merge any that
    # are missing (e.g. validate re-run against an older metrics.parquet), avoiding the
    # duplicate-column suffixing that a blind merge would cause.
    if OUTCOMES.exists():
        out = pd.read_parquet(OUTCOMES)
        out["zcta5"] = out["zcta5"].astype("string")
        new_cols = [c for c in out.columns if c == "zcta5" or c not in df.columns]
        if len(new_cols) > 1:
            df = df.merge(out[new_cols], on="zcta5", how="left")
    avail = [a for a in ANCHORS if a in df.columns]
    if not avail:
        die("validate", "no outcome anchors present (need outcomes.parquet or life_expectancy)")

    # county-aggregated frame (pop-weighted dims + sub-scores + county outcomes)
    county_anchor_cols = [a for a in avail if ANCHORS[a][1] == "county"]
    cval_cols = DIM_COLS + sub_cols + county_anchor_cols
    cty = _wmean(df.dropna(subset=["county_fips"]), cval_cols, by="county_fips", w="population")

    anchors_out: dict = {}
    sub_diag: dict = {a: {} for a in avail}
    for a in avail:
        label, scope, direction, caveat = ANCHORS[a]
        frame = cty if scope == "county" else df
        # orient every anchor higher = worse: flip the "better" (higher=good) outcomes
        y = frame[a].to_numpy(float)
        y = (np.nanmax(y) - y) if direction == "better" else y
        # each dimension's univariate association with the outcome
        dim_corr = {d: _corr(frame[f"{d}_pctile"].to_numpy(float), y) for d in DIMENSIONS}
        if any(r is None for r in dim_corr.values()):
            continue
        reg = _regression(frame[DIM_COLS].to_numpy(float), y)  # diagnostic (may be None)
        anchors_out[a] = {
            "label": label, "scope": scope, "caveat": caveat,
            # PRESET weights: proportional to univariate correlation, 5% floor. Keeps care
            # access visible at its real association strength instead of letting the
            # multivariate regression collapse it via collinearity with health need.
            "weights": _floor_weights([dim_corr[d] for d in DIMENSIONS]),
            "dimension_corr": {d: round(r, 3) for d, r in dim_corr.items()},
            "regression_weights": reg["regression_weights"] if reg else None,
            "fit": reg["fit"] if reg else None,
        }
        for sc in sub_cols:
            r = _corr(frame[sc].to_numpy(float), y)
            if r is not None:
                sub_diag[a][sc[:-7]] = round(r, 3)

    # density-stratified provider-supply confound (evidence that spatial supply is
    # entangled with urbanicity), if both columns exist
    density_diag = _density_confound(df, avail)

    _write_weights(anchors_out, sub_diag)
    write_provenance({"validation": {
        "method": "multi-anchor. Preset weights = univariate correlation of each dimension "
                  "with the outcome (5% floor). regression_weights = constrained NNLS "
                  "(diagnostic; collapses care access via collinearity). County outcomes "
                  "pop-weighted to county level.",
        "anchors": {a: {"label": v["label"], "scope": v["scope"], "weights": v["weights"],
                        "regression_weights": v["regression_weights"], "fit": v["fit"]}
                    for a, v in anchors_out.items()},
        "subscore_correlations": sub_diag,
        "supply_density_confound": density_diag,
        "scope": dev_state or "national",
        "note": "Area outcomes (even ACSC) are disease/need-dominated and care access is "
                "collinear with need, so multivariate regression understates access. The "
                "composite keeps care access at a value-judgment weight by default; the "
                "anchored presets weight by univariate association. See COMPOSITE-ENHANCEMENT.",
    }})
    log("validate", f"anchors: {list(anchors_out)}")
    for a, v in anchors_out.items():
        r2 = v["fit"]["r2"] if v["fit"] else None
        log("validate", f"  {a}: preset(corr)={v['weights']} | regression={v['regression_weights']} R2={r2}")
    log("validate", f"wrote {WEIGHTS_JSON.name}")
    return str(WEIGHTS_JSON)


def _density_confound(df: pd.DataFrame, avail: list[str]) -> dict:
    if "provider_supply_pctile" not in df.columns or "population" not in df.columns:
        return {}
    sub = df.dropna(subset=["provider_supply_pctile", "population"]).copy()
    if len(sub) < 1000:
        return {}
    try:
        sub["q"] = pd.qcut(sub["population"], 5, labels=["q1_rural", "q2", "q3", "q4", "q5_urban"])
    except ValueError:
        return {}
    target = "preventable_hosp" if "preventable_hosp" in avail else (
        "life_expectancy" if "life_expectancy" in avail else None)
    if target is None or target not in sub.columns:
        return {}
    y = sub[target].to_numpy(float)
    sub["_y"] = (np.nanmax(y) - y) if ANCHORS[target][2] == "better" else y
    out = {"outcome": target, "by_population_quintile": {}}
    for q, g in sub.groupby("q", observed=True):
        r = _corr(g["provider_supply_pctile"].to_numpy(float), g["_y"].to_numpy(float))
        if r is not None:
            out["by_population_quintile"][str(q)] = round(r, 3)
    return out


def _write_weights(anchors_out: dict, sub_diag: dict) -> None:
    default_pct = {k: round(v * 100) for k, v in DIMENSION_WEIGHTS.items()}
    payload = {
        "default": default_pct,
        "anchors": {a: {"label": v["label"], "scope": v["scope"], "caveat": v["caveat"],
                        "weights": v["weights"], "regression_weights": v["regression_weights"],
                        "fit": v["fit"], "dimension_corr": v["dimension_corr"]}
                    for a, v in anchors_out.items()},
        "subscore_correlations": sub_diag,
        "note": ("default = conceptual value judgment (theory weights); care access counts "
                 "fully by design. Each anchor's `weights` are proportional to how strongly "
                 "each dimension correlates with that independent outcome (5% floor) - this "
                 "keeps care access visible. `regression_weights` (NNLS) is a diagnostic: it "
                 "collapses care access because area outcomes are need-dominated and the "
                 "dimensions are collinear, not because access doesn't matter."),
    }
    WEIGHTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    WEIGHTS_JSON.write_text(json.dumps(payload, indent=2))


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

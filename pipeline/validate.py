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
    actually track outcomes vs. which are confounded - see docs/VALIDATION.md).
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


def _wcorr(a: np.ndarray, b: np.ndarray, w: np.ndarray) -> float | None:
    """Precision-weighted Pearson. The unweighted `_corr` lets a tiny, noisy county count as much
    as a large, precisely-measured one, which ATTENUATES the association (classifical errors-in-
    variables). Weighting by population down-weights the high-variance small areas and shifts the
    estimand to 'the correlation where people actually live' - the decision-relevant one. A near-
    guaranteed, legitimate recovery of attenuated signal (it corrects measurement noise, fits
    nothing). See docs/VALIDATION.md §7d."""
    a, b, w = np.asarray(a, float), np.asarray(b, float), np.asarray(w, float)
    m = ~(np.isnan(a) | np.isnan(b) | np.isnan(w)) & (w > 0)
    if m.sum() < 100:
        return None
    a, b, w = a[m], b[m], w[m]
    W = w.sum()
    am, bm = (a * w).sum() / W, (b * w).sum() / W
    cov = (w * (a - am) * (b - bm)).sum()
    va, vb = (w * (a - am) ** 2).sum(), (w * (b - bm) ** 2).sum()
    return float(cov / np.sqrt(va * vb)) if va > 0 and vb > 0 else None


def _index_reliability(cty: pd.DataFrame, sub_cols: list[str], n_splits: int = 200) -> float | None:
    """Split-half reliability of the composite as a measurement instrument: randomly halve the
    scored sub-scores, build two half-composites, correlate across counties, Spearman-Brown up to
    full length. Averaged over many random splits. This is the rel_x in the disattenuation."""
    sub = cty[sub_cols].to_numpy(float)
    if sub.shape[1] < 4:
        return None
    rng = np.random.default_rng(7)
    halves = []
    for _ in range(n_splits):
        idx = rng.permutation(sub.shape[1])
        a, b = idx[: len(idx) // 2], idx[len(idx) // 2:]
        ca, cb = np.nanmean(sub[:, a], 1), np.nanmean(sub[:, b], 1)
        r = _corr(ca, cb)
        if r is not None:
            halves.append(r)
    if not halves:
        return None
    rh = float(np.mean(halves))
    return 2 * rh / (1 + rh) if rh > -1 else None


def _parallel_forms_reliability(cty: pd.DataFrame, anchors: list[str], w: np.ndarray) -> dict:
    """Reliability of each outcome ruler via the single-factor (Spearman) triangulation:
    rel_i = r(i,j)*r(i,k)/r(j,k), using the pop-weighted pairwise correlations among >=3 access-
    sensitive mortality/hospitalization rulers. HONEST CAVEAT: this attributes ALL of a ruler's
    low inter-correlation to noise; a ruler that measures a genuinely DISTINCT construct will also
    score low here. So it is 'reliable variance shared with the common mortality factor', a
    conservative reliability - which is exactly why it must not be read as the index failing."""
    present = [a for a in anchors if a in cty.columns]
    if len(present) < 3:
        return {}
    rho = {}
    for i, a in enumerate(present):
        for b in present[i + 1:]:
            rho[(a, b)] = rho[(b, a)] = _wcorr(cty[a].to_numpy(float), cty[b].to_numpy(float), w)
    out = {}
    for x in present:
        others = [o for o in present if o != x]
        j, k = others[0], others[1]
        rij, rik, rjk = rho.get((x, j)), rho.get((x, k)), rho.get((j, k))
        if None not in (rij, rik, rjk) and rjk and rjk > 0:
            out[x] = max(0.0, min(1.0, rij * rik / rjk))
    return out


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
    exactly why the presets use correlation weighting, not this. See VALIDATION."""
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


def _cv_regression(X: np.ndarray, y: np.ndarray, groups: np.ndarray, floor: float = 5.0) -> dict | None:
    """Point 3 (statistician's critique): the reported R^2 is in-sample - the weights are FIT to
    the outcome, then fit quality is measured on the same outcome (optimism). This does honest
    leave-one-STATE-out CV: fit NNLS on all-but-one state (standardizing on the TRAINING fold only,
    no leakage), predict the held-out state, pool the out-of-sample predictions into one OOS R^2.
    Also returns weight stability (mean +/- SD across folds): if the weights swing wildly when a
    state is removed, the 'data-driven' weighting is really noise. Compare cv_r2 to the in-sample
    r2 - the gap IS the optimism."""
    try:
        from scipy.optimize import nnls
    except Exception:  # noqa: BLE001
        return None
    g = np.asarray(groups, dtype=object)
    m = ~(np.isnan(y) | np.isnan(X).any(axis=1)) & np.array([gi is not None and gi == gi for gi in g])
    X, y, g = X[m], y[m], g[m]
    uniq = [u for u in pd.unique(g)]
    if len(uniq) < 5 or len(y) < 200:
        return None
    preds = np.full(len(y), np.nan)
    fold_w = []
    for u in uniq:
        tr = g != u
        te = ~tr
        if tr.sum() < 100 or te.sum() < 1:
            continue
        mu, sd = X[tr].mean(0), X[tr].std(0)
        sd = np.where(sd > 0, sd, 1.0)
        Xtr, Xte = (X[tr] - mu) / sd, (X[te] - mu) / sd
        ybar = y[tr].mean()
        coef, _ = nnls(Xtr, y[tr] - ybar)
        if coef.sum() == 0:
            continue
        preds[te] = Xte @ coef + ybar           # predict held-out state
        fold_w.append(floor + (100 - floor * len(coef)) * coef / coef.sum())
    ok = ~np.isnan(preds)
    if ok.sum() < 100 or not fold_w:
        return None
    ss_res = float(((y[ok] - preds[ok]) ** 2).sum())
    ss_tot = float(((y[ok] - y[ok].mean()) ** 2).sum())
    W = np.asarray(fold_w)
    return {
        "cv_r2": round(1.0 - ss_res / ss_tot, 3) if ss_tot > 0 else None,
        "n_folds": len(fold_w), "n": int(ok.sum()),
        "weight_mean": {d: round(float(W[:, i].mean()), 1) for i, d in enumerate(DIMENSIONS)},
        "weight_sd": {d: round(float(W[:, i].std()), 1) for i, d in enumerate(DIMENSIONS)},
    }


def build(dev_state: str | None = None, force: bool = False) -> str:
    if not METRICS.exists():
        die("validate", f"missing {METRICS.name}; run join_and_score first")
    df = pd.read_parquet(METRICS)
    df = df[df["scoreable"] == True].copy()  # noqa: E712
    # composite-level _pctile columns are not sub-scores: exclude the additive rank, the
    # multiplicative-lens rank, the life-expectancy outcome rank, and the access-beyond-
    # deprivation diagnostic lens (a residual, not a member of any dimension).
    _not_subscores = ("access_gap_pctile", "access_gap_mult_pctile", "life_expectancy_pctile",
                      "care_access_resid_pctile")
    sub_cols = [c for c in df.columns if c.endswith("_pctile")
                and c not in DIM_COLS and c not in _not_subscores]

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
    comp_col = ["access_gap_score"] if "access_gap_score" in df.columns else []
    cval_cols = DIM_COLS + sub_cols + county_anchor_cols + comp_col
    cdf_src = df.dropna(subset=["county_fips"])
    cty = _wmean(cdf_src, cval_cols, by="county_fips", w="population")
    # county population = the precision weight for the disattenuating WLS (a county estimated from
    # more people is measured with less error and should count more).
    cpop = cdf_src.groupby("county_fips")["population"].sum().rename("_cpop")
    cty = cty.merge(cpop, on="county_fips", how="left")

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
        # PRECISION-WEIGHTED dimension correlations drive the presets for county anchors: pop-weighting
        # down-weights the noisy small counties that attenuate the unweighted association, so the preset
        # weights reflect the better-estimated strength of each dimension (esp. care access, which the
        # small-area noise hits hardest). Falls back to unweighted for the ZCTA-level LE anchor.
        wcol = frame["_cpop"].to_numpy(float) if (scope == "county" and "_cpop" in frame.columns) else None
        dim_corr_pw = ({d: _wcorr(frame[f"{d}_pctile"].to_numpy(float), y, wcol) for d in DIMENSIONS}
                       if wcol is not None else dict(dim_corr))
        if any(r is None for r in dim_corr_pw.values()):
            dim_corr_pw = dict(dim_corr)
        preset_corr = dim_corr_pw  # the association used for the floor-weighted presets
        Xreg = frame[DIM_COLS].to_numpy(float)
        reg = _regression(Xreg, y)  # diagnostic (may be None)
        # leave-one-state-out CV groups: county_fips prefix for county-aggregated frames, the
        # state column for the ZCTA-level LE anchor.
        if scope == "county":
            grp = frame["county_fips"].astype(str).str[:2].to_numpy()
        else:
            grp = frame["state"].astype(str).to_numpy() if "state" in frame.columns else None
        cv = _cv_regression(Xreg, y, grp) if grp is not None else None
        # precision-weighted (population) composite + dimension correlations: the same association
        # with the attenuating small-area noise down-weighted. Reported alongside the unweighted
        # numbers (the delta is the recoverable signal); does NOT change the shipped preset weights.
        prec = None
        if scope == "county" and "_cpop" in frame.columns and comp_col:
            w = frame["_cpop"].to_numpy(float)
            comp = frame["access_gap_score"].to_numpy(float)
            prec = {
                "composite_r": _corr(comp, y),
                "composite_r_popw": _wcorr(comp, y, w),
                "dimension_r_popw": {d: _wcorr(frame[f"{d}_pctile"].to_numpy(float), y, w)
                                     for d in DIMENSIONS},
            }
        anchors_out[a] = {
            "label": label, "scope": scope, "caveat": caveat,
            "precision_weighted": prec,
            # PRESET weights: proportional to the PRECISION-WEIGHTED univariate correlation, 5% floor.
            # Keeps care access visible at its real (attenuation-corrected) association strength instead
            # of letting either the multivariate regression collapse it (collinearity) or small-area
            # noise understate it. `weights_unweighted` retains the prior estimate for transparency.
            "weights": _floor_weights([preset_corr[d] for d in DIMENSIONS]),
            "weights_unweighted": _floor_weights([dim_corr[d] for d in DIMENSIONS]),
            "dimension_corr": {d: round(r, 3) for d, r in dim_corr.items()},
            "dimension_corr_popw": {d: (round(preset_corr[d], 3) if preset_corr[d] is not None else None)
                                    for d in DIMENSIONS},
            "regression_weights": reg["regression_weights"] if reg else None,
            "fit": reg["fit"] if reg else None,
            "cv": cv,  # point 3: honest out-of-sample fit + weight stability (None if scipy/folds short)
        }
        for sc in sub_cols:
            r = _corr(frame[sc].to_numpy(float), y)
            if r is not None:
                sub_diag[a][sc[:-7]] = round(r, 3)

    # DISATTENUATION: how much of the gap from the observed composite-outcome r to 1.0 is
    # recoverable measurement noise vs a real ceiling. disattenuated r = obs / sqrt(rel_x * rel_y).
    # Reframes "care access reads modest": a chunk of the modesty is a NOISY RULER, not a weak index.
    reliab: dict = {}
    mort_anchors = [a for a in ("amenable_mortality", "preventable_hosp", "premature_death")
                    if a in cty.columns]
    rel_index = _index_reliability(cty, sub_cols)
    if rel_index is not None and len(mort_anchors) >= 3:
        w = cty["_cpop"].to_numpy(float)
        rel_out = _parallel_forms_reliability(cty, mort_anchors, w)
        disatt = {}
        for a in mort_anchors:
            ro = rel_out.get(a)
            prec = anchors_out.get(a, {}).get("precision_weighted")
            obs = prec["composite_r_popw"] if prec else None
            if ro and ro > 0 and obs is not None:
                d = obs / np.sqrt(rel_index * ro)
                disatt[a] = {"observed_popw_r": round(obs, 3), "outcome_reliability": round(ro, 3),
                             "disattenuated_r": round(min(1.0, d), 3),
                             "recoverable": round(min(1.0, d) - obs, 3)}
        reliab = {"index_reliability": round(rel_index, 3), "disattenuated": disatt}

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
                        "regression_weights": v["regression_weights"], "fit": v["fit"],
                        "cv": v["cv"]}
                    for a, v in anchors_out.items()},
        "subscore_correlations": sub_diag,
        "supply_density_confound": density_diag,
        "precision_weighting": {a: anchors_out[a]["precision_weighted"] for a in anchors_out
                                if anchors_out[a].get("precision_weighted")},
        "disattenuation": reliab,
        "scope": dev_state or "national",
        "note": "Area outcomes (even ACSC) are disease/need-dominated and care access is "
                "collinear with need, so multivariate regression understates access. The "
                "composite keeps care access at a value-judgment weight by default; the "
                "anchored presets weight by univariate association. See VALIDATION.",
    }})
    log("validate", f"anchors: {list(anchors_out)}")
    for a, v in anchors_out.items():
        r2 = v["fit"]["r2"] if v["fit"] else None
        cv = v["cv"]
        cvstr = f" | CV R2={cv['cv_r2']} (in-sample {r2}; wSD={cv['weight_sd']})" if cv else ""
        log("validate", f"  {a}: preset(corr)={v['weights']} | regression={v['regression_weights']} R2={r2}{cvstr}")

    # before/after summary: precision-weighting recovers attenuated signal; disattenuation shows
    # how much of the residual gap is a noisy ruler vs a true ceiling.
    # preset before/after: how pop-weighting the dimension correlations shifts the anchored presets
    print("\n  === anchored preset weights: unweighted -> precision-weighted dimension corr ===")
    for a, vv in anchors_out.items():
        if vv["weights"] != vv["weights_unweighted"]:
            old = {d: vv["weights_unweighted"][d] for d in DIMENSIONS}
            new = {d: vv["weights"][d] for d in DIMENSIONS}
            print(f"  {a:20s} care_access {old['care_access']:>4.1f} -> {new['care_access']:>4.1f}  "
                  f"(full: {old} -> {new})")

    if reliab:
        print("\n  === precision-weighting + disattenuation (composite vs county outcome) ===")
        print(f"  index reliability (split-half) = {reliab['index_reliability']}")
        print(f"  {'outcome':22s} {'r (unweighted)':>14s} {'r (pop-weighted)':>16s} "
              f"{'rel_out':>8s} {'disattenuated':>14s}")
        for a, d in reliab["disattenuated"].items():
            uw = anchors_out[a]["precision_weighted"]["composite_r"]
            print(f"  {a:22s} {uw:>+14.3f} {d['observed_popw_r']:>+16.3f} "
                  f"{d['outcome_reliability']:>8.3f} {d['disattenuated_r']:>+14.3f}")
        print("  (scores + shipped preset weights unchanged - these are reported diagnostics)")
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
                        "weights": v["weights"], "weights_unweighted": v["weights_unweighted"],
                        "regression_weights": v["regression_weights"],
                        "fit": v["fit"], "cv": v["cv"], "dimension_corr": v["dimension_corr"],
                        "dimension_corr_popw": v["dimension_corr_popw"]}
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

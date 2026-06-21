"""join_and_score: merge all layers and build the hierarchical Access Gap model.

Hierarchy (taxonomy.py): 3 dimensions -> 11 sub-scores -> ~50 measures.
Method follows CDC/ATSDR SVI: percentile-rank each (oriented) measure, average the
available members into a sub-score, re-rank; average sub-scores into a dimension,
re-rank; weight the dimensions into the composite, and report the composite's own
percentile. Re-ranking at each level keeps every node a clean 0-100 "higher = worse."

Outputs: data/processed/metrics.parquet (everything, served per-ZIP by the API) and
frontend/public/metrics.json (slim: geography + dimension/sub-score percentiles +
composite + flags, enough for the map and the client-side weight recompute).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import config
from .common import assert_zcta, die, log, write_provenance
from .taxonomy import (CONTEXT_ACS, CONTEXT_PLACES, DIMENSION_WEIGHTS, DIMENSIONS,
                       subscore_specs)
from .zip_states import state_name, zip3_to_state

OUT_PARQUET = config.PROCESSED / "metrics.parquet"
OUT_JSON = config.FRONTEND_PUBLIC / "metrics.json"

MERGE_STAGES = ("places", "providers", "acs", "geonames", "supply")
OPTIONAL_STAGES = ("fqhc", "lifeexp")  # merged if present (safety-net + outcomes)
WEIGHTS_JSON = config.FRONTEND_PUBLIC / "weights.json"


def _pct(s: pd.Series) -> pd.Series:
    """Deterministic national percentile rank [0,100]; NaN stays NaN."""
    return s.astype("float64").rank(pct=True) * 100.0


def _geometry_universe() -> pd.Series:
    gj = json.loads((config.PROCESSED / "zcta.geojson").read_text())
    z = pd.Series([f["properties"]["zcta5"] for f in gj["features"]], dtype="string")
    return z.drop_duplicates()


def _member_pctile(df: pd.DataFrame, member: dict) -> pd.Series | None:
    col = member["col"]
    if col not in df.columns:
        return None
    v = pd.to_numeric(df[col], errors="coerce")
    if v.notna().sum() < 100:
        return None
    return _pct(v if member["dir"] == 1 else -v)  # orient: higher = worse


def build(dev_state: str | None = None, force: bool = False) -> str:
    universe = _geometry_universe()
    df = pd.DataFrame({"zcta5": universe})
    df["state"] = df["zcta5"].map(zip3_to_state).astype("string")
    df["state_name"] = df["state"].map(state_name, na_action="ignore").astype("string")

    for name in MERGE_STAGES:
        path = config.PROCESSED / f"{name}.parquet"
        if not path.exists():
            die("join", f"missing {path.name}; run build_{name} first")
        part = pd.read_parquet(path)
        part["zcta5"] = part["zcta5"].astype("string")
        df = df.merge(part, on="zcta5", how="left")

    for name in OPTIONAL_STAGES:
        path = config.PROCESSED / f"{name}.parquet"
        if path.exists():
            part = pd.read_parquet(path)
            part["zcta5"] = part["zcta5"].astype("string")
            df = df.merge(part, on="zcta5", how="left")

    # residential ZCTA with no NPPES match = zero registered providers, not missing
    for c in ("providers_total", "providers_primary", "providers_mental"):
        if c in df.columns:
            df[c] = df[c].fillna(0).astype("int64")

    pop = pd.to_numeric(df["population"], errors="coerce")
    pop_k = (pop / 1000.0).where(pop > 0)
    df["primary_per_1k"] = (df["providers_primary"] / pop_k).replace([np.inf, -np.inf], np.nan)
    df["population"] = pop.astype("Int64")
    df["low_confidence"] = (pop < config.POPULATION_FLOOR) | pop.isna()

    # ---- sub-scores (re-ranked mean of available member percentiles) ----
    sub_by_dim: dict[str, list[str]] = {d: [] for d in DIMENSIONS}
    for spec in subscore_specs():
        mps = [mp for m in spec["members"] if (mp := _member_pctile(df, m)) is not None]
        col = f"{spec['key']}_pctile"
        if mps:
            raw = pd.concat(mps, axis=1).mean(axis=1)  # skipna mean of member percentiles
            df[col] = _pct(raw)
            sub_by_dim[spec["dim"]].append(col)
        else:
            df[col] = np.nan

    # ---- dimensions (re-ranked mean of their sub-scores) ----
    dim_cols = []
    for dkey, subs in sub_by_dim.items():
        col = f"{dkey}_pctile"
        dim_cols.append(col)
        df[col] = _pct(df[subs].mean(axis=1)) if subs else np.nan

    # ---- composite (weighted mean of dimension percentiles; renormalized) ----
    num = pd.Series(0.0, index=df.index)
    wsum = pd.Series(0.0, index=df.index)
    for dkey in DIMENSIONS:
        col = f"{dkey}_pctile"
        w = DIMENSION_WEIGHTS[dkey]
        mask = df[col].notna()
        num = num.add(np.where(mask, w * df[col].fillna(0.0), 0.0))
        wsum = wsum.add(np.where(mask, w, 0.0))
    df["access_gap_score"] = (num / wsum).where(wsum > 0)

    n_dims = df[dim_cols].notna().sum(axis=1)
    df["scoreable"] = pop.notna() & (pop > 0) & (n_dims >= 2)
    df.loc[~df["scoreable"], "access_gap_score"] = np.nan
    df["access_gap_pctile"] = _pct(df["access_gap_score"])  # true rank of the composite

    # OUTCOMES layer (separate from the access gap, never in the composite): life
    # expectancy as a national rank where LOW life expectancy = HIGH percentile (worse),
    # consistent with everything else reading higher = worse.
    if "life_expectancy" in df.columns:
        df["life_expectancy_pctile"] = _pct(-df["life_expectancy"])

    _validate(df, dim_cols, dev_state)
    corr = _dimension_correlations(df, dim_cols)
    anchor = _outcome_anchor(df)
    emp = _empirical_weights(df, dim_cols)
    df.to_parquet(OUT_PARQUET, index=False)
    _write_slim_json(df, dim_cols)
    _write_weights(emp)
    write_provenance({"score": {
        "method": "hierarchical percentile (SVI-style), re-ranked per level",
        "dimension_weights": DIMENSION_WEIGHTS,
        "empirical_weights": emp,
        "rows": len(df), "with_score": int(df["access_gap_score"].notna().sum()),
        "low_confidence": int(df["low_confidence"].sum()),
        "dimension_correlations": corr,
        "outcome_anchor": anchor, "scope": dev_state or "national",
    }})
    log("join", f"empirical weights (life-expectancy regression): {emp}")
    log("join", f"outcome anchor (vs fair/poor health): {anchor}")
    log("join", f"wrote {OUT_PARQUET.name} ({len(df)} rows, {df.shape[1]} cols) + {OUT_JSON.name}")
    log("join", f"dimension correlations: {corr}")
    return str(OUT_PARQUET)


SUBSCORE_COLS = [f"{s['key']}_pctile" for s in subscore_specs()]
RAW_DISPLAY = (
    # everything the detail panel shows; served per-ZIP via the API
    [m["col"] for s in subscore_specs() for m in s["members"]]
    + list(CONTEXT_PLACES) + list(CONTEXT_ACS)
    + ["primary_per_1k", "providers_total", "providers_primary", "providers_mental",
       "primary_people_per_provider", "primary_shortage", "population",
       "fqhc_sites_reachable", "nearest_fqhc_km", "life_expectancy"]
)


def _write_slim_json(df: pd.DataFrame, dim_cols: list[str]) -> None:
    # slim payload: geography + composite + dimensions + sub-scores + flags.
    cols = ["zcta5", "state", "state_name", "city", "county_name", "population",
            "access_gap_score", "access_gap_pctile", "low_confidence", "scoreable",
            "life_expectancy", "life_expectancy_pctile",
            *dim_cols, *SUBSCORE_COLS]
    cols = [c for c in dict.fromkeys(cols) if c in df.columns]
    slim = df[cols].copy()
    for c in slim.columns:
        if slim[c].dtype.kind == "f":
            slim[c] = slim[c].round(1)
    records = json.loads(slim.to_json(orient="records"))
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(records, separators=(",", ":")))
    log("join", f"metrics.json: {len(records)} records, {len(cols)} cols "
                f"({OUT_JSON.stat().st_size/1e6:.1f} MB)")


def _outcome_anchor(df: pd.DataFrame) -> dict:
    """Partial credibility check: does the access gap track a health *outcome*?
    Uses PLACES fair/poor general health (ghlth_pct). NOT independent (PLACES is
    SES-conditioned), so it's a sanity anchor, not external validation."""
    if "ghlth_pct" not in df.columns:
        return {}
    sub = df.loc[df["scoreable"], ["access_gap_score", "ghlth_pct", "health_need_pctile",
                                   "social_vulnerability_pctile", "care_access_pctile"]].dropna()
    if len(sub) < 100:
        return {}
    return {
        "metric": "Pearson r of each score vs PLACES fair/poor general health",
        "access_gap": round(float(sub["access_gap_score"].corr(sub["ghlth_pct"])), 3),
        "health_need": round(float(sub["health_need_pctile"].corr(sub["ghlth_pct"])), 3),
        "social_vulnerability": round(float(sub["social_vulnerability_pctile"].corr(sub["ghlth_pct"])), 3),
        "care_access": round(float(sub["care_access_pctile"].corr(sub["ghlth_pct"])), 3),
        "caveat": "not independent — PLACES estimates are SES-conditioned",
    }


def _empirical_weights(df: pd.DataFrame, dim_cols: list[str]) -> dict:
    """Derive dimension weights HPI-style: non-negative least-squares regression of the
    3 dimension percentiles on the LE *deficit* (an independent outcome), with a 5%
    floor, normalized to 100. Replaces the value judgment with a data-driven one."""
    if "life_expectancy" not in df.columns:
        return {}
    try:
        from scipy.optimize import nnls
    except Exception:  # noqa: BLE001
        return {}
    sub = df.loc[df["scoreable"], [*dim_cols, "life_expectancy"]].dropna()
    if len(sub) < 1000:
        return {}
    X = sub[dim_cols].to_numpy(float)
    Xs = (X - X.mean(0)) / X.std(0)
    le = sub["life_expectancy"].to_numpy(float)
    y = (le.max() - le)          # life-expectancy deficit: higher = worse health
    y = y - y.mean()
    coef, _ = nnls(Xs, y)
    if coef.sum() == 0:
        return {}
    floored = np.maximum(coef / coef.sum() * 100, 5.0)   # 5% minimum per dimension (HPI)
    w = floored / floored.sum() * 100
    pred = Xs @ coef
    ss_tot = float((y ** 2).sum())
    r2 = 1.0 - float(((y - pred) ** 2).sum()) / ss_tot if ss_tot > 0 else 0.0
    out = {c[:-7]: round(float(v), 1) for c, v in zip(dim_cols, w)}  # strip "_pctile"
    out["fit"] = {"r2_vs_life_expectancy": round(r2, 3), "n": int(len(sub))}
    return out


def _write_weights(emp: dict) -> None:
    default_pct = {k: round(v * 100) for k, v in DIMENSION_WEIGHTS.items()}
    payload = {
        "default": default_pct,
        "empirical": {k: v for k, v in emp.items() if k != "fit"} if emp else None,
        "fit": emp.get("fit") if emp else None,
        "note": ("default = conceptual value judgment; empirical = NNLS regression of the "
                 "dimensions on CDC USALEEP life expectancy (5% floor, normalized to 100)."),
    }
    WEIGHTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    WEIGHTS_JSON.write_text(json.dumps(payload, indent=2))


def _dimension_correlations(df: pd.DataFrame, dim_cols: list[str]) -> dict:
    sub = df[dim_cols].dropna()
    if len(sub) < 10:
        return {}
    c = sub.corr()
    out = {}
    for i in range(len(dim_cols)):
        for j in range(i + 1, len(dim_cols)):
            a, b = dim_cols[i], dim_cols[j]
            out[f"{a[:-7]}_vs_{b[:-7]}"] = round(float(c.loc[a, b]), 3)
    return out


def _validate(df: pd.DataFrame, dim_cols: list[str], dev_state: str | None) -> None:
    assert_zcta(df, stage="join")
    has_data = df[["diabetes_pct", "providers_total", "median_income"]].notna().any(axis=1)
    overlap = has_data.mean()
    if overlap < 0.90:
        die("join", f"only {overlap:.0%} of geometry ZCTAs have data")
    for col in [*dim_cols, *SUBSCORE_COLS, "access_gap_score", "access_gap_pctile"]:
        v = df[col].dropna()
        if len(v) and (v.min() < -0.001 or v.max() > 100.001):
            die("join", f"{col} outside [0,100]: min={v.min()} max={v.max()}")
    if df["access_gap_score"].isna().all():
        die("join", "access_gap_score entirely null")
    log("join", f"validated: {overlap:.0%} overlap, all percentiles in [0,100], "
                f"{int(df['access_gap_score'].notna().sum())} scored")


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

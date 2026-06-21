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
# merged if present (safety-net + independent outcomes for display/validation). The
# multi-anchor weight derivation lives in pipeline/validate.py (runs after join).
OPTIONAL_STAGES = ("fqhc", "lifeexp", "outcomes")


def _pct(s: pd.Series) -> pd.Series:
    """Deterministic national percentile rank [0,100]; NaN stays NaN."""
    return s.astype("float64").rank(pct=True) * 100.0


def _rank_uncertainty(df: pd.DataFrame, dim_cols: list[str],
                      n: int = 300, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Per-ZCTA 5-95 national-rank interval under plausible re-weighting (each dimension
    15-55%, renormalized) - the Saisana/OECD uncertainty-on-ranks standard. Deterministic
    (fixed seed) so the build + acceptance tests are reproducible. Returns (lo, hi) arrays
    aligned to df, NaN for non-scoreable rows."""
    rng = np.random.default_rng(seed)
    sc = df["scoreable"].to_numpy()
    idx = np.where(sc)[0]
    lo = np.full(len(df), np.nan)
    hi = np.full(len(df), np.nan)
    if len(idx) < 10:
        return lo, hi
    X = df[dim_cols].to_numpy(float)[idx]
    present = ~np.isnan(X)
    Xz = np.where(present, X, 0.0)
    W = rng.uniform(0.15, 0.55, size=(n, len(dim_cols)))
    W /= W.sum(axis=1, keepdims=True)
    ranks = np.empty((len(idx), n))
    for j in range(n):
        w = W[j]
        comp = (Xz @ w) / (present * w).sum(axis=1)   # renormalized over present dims
        ranks[:, j] = pd.Series(comp).rank(pct=True).to_numpy() * 100.0
    lo[idx] = np.percentile(ranks, 5, axis=1)
    hi[idx] = np.percentile(ranks, 95, axis=1)
    return lo, hi


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

    # Safety-net barrier = unmet need: FQHC-desert (distance percentile) x poverty. The raw
    # E2SFCA FQHC-access score is wrong-signed against every outcome (clinics cluster in
    # high-need areas, so "access" is highest where need is highest); this need-relative
    # form is correctly signed and adds signal beyond poverty alone for the access-proximal
    # outcomes (flu/maternity/premature death). See docs/ROADMAP-ACCESS-SIGNAL.md A2.
    if "nearest_fqhc_km" in df.columns and "poverty_rate" in df.columns:
        km = pd.to_numeric(df["nearest_fqhc_km"], errors="coerce")
        df["safetynet_barrier"] = _pct(km) / 100.0 * pd.to_numeric(df["poverty_rate"], errors="coerce")

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

    # Rank uncertainty (Saisana sensitivity): how much would this ZCTA's national rank
    # move under any defensible weighting? The honest answer to "can we compare two ZIPs":
    # only when their bands don't overlap. No production index (ADI/SVI/CHR) ships this.
    lo, hi = _rank_uncertainty(df, dim_cols)
    df["access_gap_rank_lo"] = lo
    df["access_gap_rank_hi"] = hi
    # coarse, communicable tier (decile 1-10) - the resolution the data actually supports
    df["tier"] = np.ceil(df["access_gap_pctile"] / 10.0).clip(1, 10)
    df.loc[~df["scoreable"], "tier"] = np.nan

    # OUTCOMES layer (separate from the access gap, never in the composite): life
    # expectancy as a national rank where LOW life expectancy = HIGH percentile (worse),
    # consistent with everything else reading higher = worse.
    if "life_expectancy" in df.columns:
        df["life_expectancy_pctile"] = _pct(-df["life_expectancy"])

    _validate(df, dim_cols, dev_state)
    corr = _dimension_correlations(df, dim_cols)
    anchor = _outcome_anchor(df)
    df.to_parquet(OUT_PARQUET, index=False)
    _write_slim_json(df, dim_cols)
    write_provenance({"score": {
        "method": "hierarchical percentile (SVI-style), re-ranked per level",
        "dimension_weights": DIMENSION_WEIGHTS,
        "rows": len(df), "with_score": int(df["access_gap_score"].notna().sum()),
        "low_confidence": int(df["low_confidence"].sum()),
        "dimension_correlations": corr,
        "outcome_anchor": anchor, "scope": dev_state or "national",
    }})
    log("join", f"outcome anchor (vs fair/poor health): {anchor}")
    log("join", f"wrote {OUT_PARQUET.name} ({len(df)} rows, {df.shape[1]} cols) + {OUT_JSON.name}")
    log("join", f"dimension correlations: {corr}")
    log("join", "dimension weights derived by pipeline/validate.py (multi-anchor)")
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
            "access_gap_score", "access_gap_pctile", "access_gap_rank_lo",
            "access_gap_rank_hi", "tier", "low_confidence", "scoreable",
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

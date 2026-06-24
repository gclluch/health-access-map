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

import datetime
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
OPTIONAL_STAGES = ("fqhc", "hpsa", "broadband", "medicaldebt", "lifeexp", "outcomes")


def _pct(s: pd.Series) -> pd.Series:
    """Deterministic national percentile rank [0,100]; NaN stays NaN."""
    return s.astype("float64").rank(pct=True) * 100.0


# Layer B measurement-noise calibration. Per-dimension Gaussian σ (percentile points)
# injected into each Monte-Carlo draw, scaled to the ZCTA's RAW ACS input CV in EXCESS of the
# national median CV: σ_z = SCALE * share_dim * clip(cv_z - cv_floor, 0, EXCESS_CAP), cv_floor
# = the FLOOR_Q quantile of CV. A median-or-better-measured ZCTA (cv ≤ cv_floor) gets zero
# added noise, so its band stays the pre-Layer-B weighting-only width; only noisier (low-pop)
# ZCTAs widen. SCALE is calibrated by pipeline.verify_bands gate 3 to an independent member-
# input resample (perturb each ACS rate by its published SE, propagate to the dimension
# percentile): scale=36 puts social_vulnerability within ±20% of that ground truth. Resulting
# bands: high-conf ≈10, low-conf ≈25, ratio ≈2.5× (gate 1 target ≥1.6), median ≈13-15 -
# consistent with docs/VALIDATION.md's ~10-15pt comparability threshold.
_RANK_CV_SIGMA_SCALE = 36.0
_RANK_CV_FLOOR_Q = 0.50
_RANK_CV_EXCESS_CAP = 1.5
# Per-dimension ACS-input share = how much ACS measurement noise propagates into each
# dimension's percentile, MEASURED by the gate-3 resample (care_access SD ≈ 0.47 × social_
# vulnerability SD - care access is ACS only via insurance + the poverty term in safetynet,
# vs social vulnerability's two fully-ACS sub-scores). health_need is PLACES (0; its noise is
# Layer B3). Not a guess: re-measured by verify_bands gate 3 after each care_access membership
# change diluted its ACS share (0.60 -> 0.47 when HPSA was added; -> 0.40 after preventive_use
# left and the noiseless county-level medical_debt joined - only insurance now carries ACS noise).
_ACS_SHARE = {"social_vulnerability_pctile": 1.0, "care_access_pctile": 0.40}

# Layer B3: PLACES measurement-noise term. PLACES is model-based (smoothed), so its input CV is
# small (~0.06) and nearly population-FLAT - it is an irreducible MODELING-uncertainty floor, not
# a low-pop noise effect. So (unlike the ACS term) it is NOT floor-subtracted: σ_places =
# SCALE_p * share * places_cv applies to every ZCTA, and is combined with the ACS term IN
# QUADRATURE (independent noise sources). _PLACES_SHARE = per-dimension propagation ratio
# MEASURED by a member-input resample (perturb each PLACES rate by its CI-derived SE, propagate
# member→sub-score→dimension): health_need is pure PLACES (1.0); care_access carries it via
# access2 only now (0.55 - was 0.78 when the unscored preventive_use also contributed);
# social_vulnerability barely, via social_needs (0.14). SCALE_p
# is calibrated so health_need's injected σ matches that resample (median ≈4.4 pctile pts);
# re-verified by verify_bands gate 3. health_need previously had ZERO band noise term - B3 is the
# completeness fix that closes that gap. See docs/DECISIONS.md B3.
_RANK_PLACES_SIGMA_SCALE = 71.0
_PLACES_SHARE = {"health_need_pctile": 1.0, "care_access_pctile": 0.55,
                 "social_vulnerability_pctile": 0.14}


def _rank_uncertainty(df: pd.DataFrame, dim_cols: list[str],
                      n: int = 300, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Per-ZCTA 5-95 national-rank interval under (1) plausible re-weighting (each dimension
    15-55%, renormalized) and (2) ACS measurement noise scaled to the ZCTA's input CV. The
    band is therefore weighting + ACS measurement noise (PLACES MOE is Layer B3). Saisana/
    OECD uncertainty-on-ranks standard. Deterministic (fixed seed) so the build + acceptance
    tests are reproducible. Returns (lo, hi) arrays aligned to df, NaN for non-scoreable rows."""
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

    # per-ZCTA, per-dimension measurement-noise σ (0 for non-ACS dimensions)
    sigma = _noise_sigma(df, dim_cols, idx)

    ranks = np.empty((len(idx), n))
    for j in range(n):
        w = W[j]
        # perturb each present dimension percentile by its measurement noise, re-aggregate,
        # re-rank. Independent per-dim noise partially cancels in the weighted mean (correct).
        noise = rng.standard_normal((len(idx), len(dim_cols))) * sigma
        Xp = np.clip(Xz + noise, 0.0, 100.0)
        comp = (np.where(present, Xp, 0.0) @ w) / (present * w).sum(axis=1)
        ranks[:, j] = pd.Series(comp).rank(pct=True).to_numpy() * 100.0
    lo[idx] = np.percentile(ranks, 5, axis=1)
    hi[idx] = np.percentile(ranks, 95, axis=1)
    return lo, hi


def _noise_sigma(df: pd.DataFrame, dim_cols: list[str], idx: np.ndarray) -> np.ndarray:
    """(len(idx), len(dim_cols)) array of measurement-noise σ in percentile points, combining
    two independent input-noise sources IN QUADRATURE:
      - ACS (Layer B): scaled to each ZCTA's acs_input_cv in EXCESS of the national median
        (well-measured ZCTAs get 0), weighted per dimension by _ACS_SHARE.
      - PLACES (Layer B3): scaled to places_input_cv with NO floor (irreducible, near-uniform
        modeling uncertainty), weighted per dimension by _PLACES_SHARE.
    Zeros if neither CV column is present (pre-Layer-B builds)."""
    n = len(idx)
    acs_sig = np.zeros((n, len(dim_cols)))
    plc_sig = np.zeros((n, len(dim_cols)))

    if "acs_input_cv" in df.columns:
        cv = df["acs_input_cv"].to_numpy(float)[idx]
        floor = np.nanquantile(cv, _RANK_CV_FLOOR_Q)
        if np.isfinite(floor):
            excess = np.clip(np.where(np.isnan(cv), floor, cv) - floor, 0.0, _RANK_CV_EXCESS_CAP)
            col_sigma = _RANK_CV_SIGMA_SCALE * excess  # 0 for well-measured ZCTAs
            for k, c in enumerate(dim_cols):
                share = _ACS_SHARE.get(c, 0.0)
                if share:
                    acs_sig[:, k] = share * col_sigma

    if "places_input_cv" in df.columns:
        pcv = df["places_input_cv"].to_numpy(float)[idx]
        med = np.nanmedian(pcv)
        pcv = np.where(np.isnan(pcv), med, pcv)  # impute missing CV with the median floor
        col_sigma = _RANK_PLACES_SIGMA_SCALE * pcv  # no floor: applies to every ZCTA
        for k, c in enumerate(dim_cols):
            share = _PLACES_SHARE.get(c, 0.0)
            if share:
                plc_sig[:, k] = share * col_sigma

    return np.sqrt(acs_sig ** 2 + plc_sig ** 2)


def _access_beyond_deprivation(df: pd.DataFrame, dim_cols: list[str]) -> pd.Series:
    """Re-ranked residual of care_access_pctile after regressing it on health_need + social_
    vulnerability percentiles (OLS with intercept, fit on rows where all three are present).
    Higher = barriers to care worse than the area's deprivation gradient predicts. Returns a
    [0,100] national percentile (NaN where any of the three dims is missing)."""
    need, vuln, care = "health_need_pctile", "social_vulnerability_pctile", "care_access_pctile"
    if not all(c in df.columns for c in (need, vuln, care)):
        return pd.Series(np.nan, index=df.index)
    X = df[[need, vuln, care]].to_numpy(float)
    m = ~np.isnan(X).any(axis=1)
    resid = np.full(len(df), np.nan)
    if m.sum() > 100:
        A = np.column_stack([np.ones(m.sum()), X[m, 0], X[m, 1]])
        beta, *_ = np.linalg.lstsq(A, X[m, 2], rcond=None)
        resid[m] = X[m, 2] - A @ beta
    return _pct(pd.Series(resid, index=df.index))


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
    # outcomes (flu/maternity/premature death). See docs/DECISIONS.md A2.
    if "nearest_fqhc_km" in df.columns and "poverty_rate" in df.columns:
        km = pd.to_numeric(df["nearest_fqhc_km"], errors="coerce")
        df["safetynet_barrier"] = _pct(km) / 100.0 * pd.to_numeric(df["poverty_rate"], errors="coerce")

    # ---- sub-scores (re-ranked mean of available member percentiles) ----
    sub_by_dim: dict[str, list[str]] = {d: [] for d in DIMENSIONS}
    for spec in subscore_specs():
        mps = []
        for m in spec["members"]:
            mp = _member_pctile(df, m)
            if mp is not None:
                # per-measure national percentile, oriented so higher = worse access
                # (same convention as the sub-scores). Lets the UI show each raw value
                # alongside where it ranks nationally. See docs.
                df[f"{m['col']}_natpct"] = mp.round(1)
                mps.append(mp)
        col = f"{spec['key']}_pctile"
        if mps:
            raw = pd.concat(mps, axis=1).mean(axis=1)  # skipna mean of member percentiles
            df[col] = _pct(raw)
            # scored=False sub-scores are COMPUTED + DISPLAYED but excluded from the dimension
            # (e.g. safetynet_access - wrong-signed within-county; see taxonomy + VALIDATION.md).
            if spec.get("scored", True):
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

    # ---- diagnostic lens: care access BEYOND deprivation (orthogonalized) ----
    # The three dimensions are ~1.6 effective dimensions (need<->vulnerability 0.74), so a high
    # care_access score is hard to read: genuinely poor access, or just a poor area? This lens
    # residualizes care_access_pctile on health_need + social_vulnerability and re-ranks the
    # residual: higher = barriers to care WORSE than this area's deprivation level predicts (the
    # structural-access part not explained by poverty). Not in the composite - a selectable lens,
    # like the multiplicative one. Directly answers the collinearity critique.
    df["care_access_resid_pctile"] = _access_beyond_deprivation(df, dim_cols)

    n_dims = df[dim_cols].notna().sum(axis=1)
    df["scoreable"] = pop.notna() & (pop > 0) & (n_dims >= 2)
    # How many of the 3 dimensions actually backed this composite. A 2-of-3 score is built from
    # dimensions that are themselves collinear (need<->vulnerability 0.74), so it is a weaker
    # estimate than a 3-of-3 score and must not be presented with equal authority (audit S5).
    df["n_dims_scored"] = n_dims.where(df["scoreable"]).astype("Int64")
    df.loc[~df["scoreable"], "access_gap_score"] = np.nan
    df["access_gap_pctile"] = _pct(df["access_gap_score"])  # true rank of the composite

    # ---- alternative LENS: multiplicative (geometric) gap ----
    # Weighted GEOMETRIC mean of the same dimension percentiles + weights, renormalized over
    # present dims. Unlike the additive default it is NON-compensatory (OECD/JRC geometric
    # aggregation): a surplus in one dimension cannot fully offset a deficit in another, so it
    # concentrates on areas where need AND barriers COINCIDE - the targeting construct
    # (Penchansky-Thomas access-as-fit; VALIDATION rec 6). Shipped as a SELECTABLE
    # LENS, not the default: it tracks outcomes ~identically (clean mean-r 0.500 vs additive
    # 0.502, rank corr 0.994, identical coverage) but down-weights one-dimensional highs
    # (need-only / barrier-only) by ~4-5 pctile pts vs the additive. Frac clipped to [0.01,1]
    # so a 0-rank dimension cannot zero the product. wsum (renormalizer) reused from above.
    lognum = pd.Series(0.0, index=df.index)
    for dkey in DIMENSIONS:
        col = f"{dkey}_pctile"
        mask = df[col].notna()
        frac = np.clip(df[col].fillna(100.0).to_numpy() / 100.0, 0.01, 1.0)
        lognum = lognum.add(np.where(mask, DIMENSION_WEIGHTS[dkey] * np.log(frac), 0.0))
    df["access_gap_mult"] = (100.0 * np.exp(lognum / wsum)).where(wsum > 0)
    df.loc[~df["scoreable"], "access_gap_mult"] = np.nan
    df["access_gap_mult_pctile"] = _pct(df["access_gap_mult"])  # rank of the multiplicative lens

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
    eff_dims = _effective_dimensions(df, dim_cols)
    lens = _lens_diag(df)
    anchor = _outcome_anchor(df)
    df.to_parquet(OUT_PARQUET, index=False)
    _write_slim_json(df, dim_cols)
    _write_public_meta(df, corr, eff_dims)
    write_provenance({"score": {
        "method": "hierarchical percentile (SVI-style), re-ranked per level",
        "dimension_weights": DIMENSION_WEIGHTS,
        "rows": len(df), "with_score": int(df["access_gap_score"].notna().sum()),
        "low_confidence": int(df["low_confidence"].sum()),
        "dimension_correlations": corr,
        "effective_dimensions": eff_dims,
        "access_beyond_deprivation": lens,
        "outcome_anchor": anchor, "scope": dev_state or "national",
        "multiplicative_lens": "access_gap_mult_pctile = weighted GEOMETRIC mean of the 3 "
            "dimension percentiles (OECD non-compensatory aggregation); a selectable lens that "
            "targets need-AND-barrier coincidence. Tracks outcomes ~identically to the additive "
            "default (clean mean-r 0.500 vs 0.502); down-weights one-dimensional highs ~4-5 pts.",
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
            "access_gap_rank_hi", "access_gap_mult_pctile", "care_access_resid_pctile",
            "tier", "low_confidence", "scoreable",
            "n_dims_scored", "life_expectancy", "life_expectancy_pctile",
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


def _write_public_meta(df: pd.DataFrame, corr: dict, eff_dims: dict) -> None:
    """Slim, frontend-fetchable build metadata (provenance.json itself is not in public/). Drives
    the in-app 'data as of' freshness badge + the dynamic methodology vintages. The NPPES vintage
    is read from the providers stage's provenance section if already written."""
    prov = json.loads(config.PROVENANCE.read_text()) if config.PROVENANCE.exists() else {}
    meta = {
        "generated": datetime.date.today().isoformat(),
        "vintages": {
            "places": config.PLACES_DATASET_ID,
            "acs_year": config.ACS_YEAR,
            "tiger_year": config.TIGER_YEAR,
            "nppes": prov.get("providers", {}).get("nppes_zip"),
        },
        "n_scored": int(df["access_gap_score"].notna().sum()),
        "low_confidence": int(df["low_confidence"].sum()),
        "dimension_correlations": corr,
        "effective_dimensions": eff_dims,
    }
    (config.FRONTEND_PUBLIC / "meta.json").write_text(json.dumps(meta))
    log("join", f"wrote frontend/public/meta.json (generated {meta['generated']})")


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


def _effective_dimensions(df: pd.DataFrame, dim_cols: list[str]) -> dict:
    """How many INDEPENDENT axes do the (collinear) dimensions really carry? Eigen-decompose
    their correlation matrix: PC1 share + participation ratio (Σλ)²/Σλ². ~1.6 here, i.e. the
    3-dimension construct is closer to one 'general deprivation' gradient - the statistical
    basis for framing the weight sliders as a sensitivity probe (re-weighting barely moves
    ranks). Surfaced in provenance + the methodology panel."""
    sub = df[dim_cols].dropna()
    if len(sub) < 10:
        return {}
    ev = np.linalg.eigvalsh(sub.corr().to_numpy())[::-1]
    return {
        "pc1_share": round(float(ev[0] / ev.sum()), 3),
        "participation_ratio": round(float(ev.sum() ** 2 / (ev ** 2).sum()), 2),
        "note": "eigen-decomposition of the dimension correlation matrix; participation_ratio "
                "= effective number of independent dimensions (3 nominal). Low value => "
                "re-weighting barely moves ranks; the sliders are a sensitivity probe.",
    }


def _lens_diag(df: pd.DataFrame) -> dict:
    """Diagnostic for the access-beyond-deprivation lens: confirm it is ~orthogonal to the
    deprivation gradient (the point), and whether the residual still tracks an independent
    outcome (low life expectancy) - vs the raw care_access score it is derived from."""
    need, vuln, care, resid = ("health_need_pctile", "social_vulnerability_pctile",
                               "care_access_pctile", "care_access_resid_pctile")
    if not all(c in df.columns for c in (need, vuln, care, resid)):
        return {}
    d = df[df["scoreable"] == True]  # noqa: E712

    def corr(a: str, b: str) -> float | None:
        s = d[[a, b]].dropna()
        return round(float(s[a].corr(s[b])), 3) if len(s) > 100 else None

    out = {
        "method": "OLS residual of care_access_pctile on health_need + social_vulnerability, "
                  "re-ranked. Higher = barriers to care worse than the deprivation gradient predicts.",
        "orthogonality": {"vs_health_need": corr(resid, need),
                          "vs_social_vulnerability": corr(resid, vuln)},
    }
    if "life_expectancy_pctile" in df.columns:
        out["vs_low_life_expectancy"] = {"residualized_care_access": corr(resid, "life_expectancy_pctile"),
                                         "raw_care_access": corr(care, "life_expectancy_pctile")}
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

"""join_and_score: merge all layers and build the hierarchical Access Gap model.

Hierarchy (taxonomy.py): 3 dimensions -> 11 sub-scores -> ~50 measures.
Method follows CDC/ATSDR SVI: percentile-rank each (oriented) measure, average the
available members into a sub-score, re-rank; average sub-scores into a dimension,
re-rank; weight the dimensions into the composite, and report the composite's own
percentile. Re-ranking at each level keeps every node a clean 0-100 "higher = worse."

Outputs: data/processed/metrics.parquet (everything, served per-ZIP by the API) and two columnar
client payloads: frontend/public/map_frame.json (first-paint frame: geography + dimension
percentiles + composite-family lenses + flags, enough for the map and the client-side weight
recompute) and frontend/public/subscores.json (the 14 sub-score lenses + life-expectancy, fetched
lazily by the client the first time one of those map lenses is selected).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import subprocess

import numpy as np
import pandas as pd

from . import config
from .common import assert_zcta, die, log, write_provenance
from .taxonomy import (CONTEXT_ACS, CONTEXT_PLACES, DIMENSION_WEIGHTS, DIMENSIONS,
                       subscore_specs)
from .zip_states import state_name, zip3_to_state

OUT_PARQUET = config.PROCESSED / "metrics.parquet"
# Two-tier client payload (columnar struct-of-arrays). map_frame.json is the first-paint frame
# (labels + the columns the default map/rankings/legend need); subscores.json holds the sub-score
# lenses, fetched lazily the first time one is selected. See _write_map_frame / _write_subscores.
OUT_MAP_FRAME = config.FRONTEND_PUBLIC / "map_frame.json"
OUT_SUBSCORES = config.FRONTEND_PUBLIC / "subscores.json"

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
                      n: int = 300, seed: int = 0,
                      add_noise: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Per-ZCTA 5-95 national-rank interval under (1) plausible re-weighting (each dimension
    15-55%, renormalized) and (2) ACS measurement noise scaled to the ZCTA's input CV. The
    band is therefore weighting + ACS measurement noise (PLACES MOE is Layer B3). Saisana/
    OECD uncertainty-on-ranks standard. Deterministic (fixed seed) so the build + acceptance
    tests are reproducible. Returns (lo, hi) arrays aligned to df, NaN for non-scoreable rows.

    add_noise=False drops the measurement-error term (re-weighting only) - used by the provenance
    decomposition (_rank_band_decomposition) to isolate how much of the shipped band is data noise."""
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

    # per-ZCTA, per-dimension measurement-noise σ (0 for non-ACS dimensions; all-0 if add_noise off)
    sigma = _noise_sigma(df, dim_cols, idx) if add_noise else np.zeros((len(idx), len(dim_cols)))

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


def _rank_band_decomposition(df: pd.DataFrame, dim_cols: list[str]) -> dict:
    """Provenance-only: split the shipped reliable-range width into its re-weighting and ACS/PLACES
    measurement-error parts, so the claim "the per-ZIP band reflects ACS margins of error" (T4) is
    auditable, not asserted. The combined band (access_gap_rank_lo/hi) is already stored; this
    recomputes the weight-only band (measurement noise off) at the same seed/n and reports median
    widths by confidence tier. measurement_contribution = combined - weight_only. The injected σ is
    independently calibrated against an SE-resample in pipeline.verify_bands (gate 3, within ±20%)."""
    sc = df["scoreable"].astype(bool).to_numpy()
    if sc.sum() < 10 or "access_gap_rank_lo" not in df.columns:
        return {}
    combined = (df["access_gap_rank_hi"] - df["access_gap_rank_lo"]).to_numpy(float)
    wlo, whi = _rank_uncertainty(df, dim_cols, add_noise=False)
    weight_only = whi - wlo
    lc = (df["low_confidence"].astype(bool).to_numpy()
          if "low_confidence" in df.columns else np.zeros(len(df), bool))

    def _med(arr: np.ndarray, mask: np.ndarray) -> float | None:
        v = arr[mask & sc]
        v = v[~np.isnan(v)]
        return round(float(np.median(v)), 2) if len(v) else None

    out: dict = {}
    for grp, mask in (("low_confidence", lc), ("high_confidence", ~lc)):
        c, w = _med(combined, mask), _med(weight_only, mask)
        out[grp] = {
            "median_band_combined": c,
            "median_band_weight_only": w,
            "median_band_measurement_contribution":
                round(c - w, 2) if (c is not None and w is not None) else None,
        }
    out["note"] = ("combined = shipped access_gap_rank band (re-weighting + ACS/PLACES measurement "
                   "noise from published SEs); weight_only = same MC with measurement noise off; the "
                   "difference is the measurement-error share of the band. The injected σ is calibrated "
                   "against an independent member-input SE-resample in pipeline.verify_bands gate 3.")
    return out


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
    # Institutional / non-residential ZCTA: registered providers OUTNUMBER residents (a hospital
    # campus, med school, or VA complex - 80045 Anschutz, 77030 Houston TMC, Stanford, Yale...).
    # The provider count reflects a workplace, not the people who live there, so the raw per-capita
    # supply (primary_per_1k can read 454,000) is meaningless and the area must not rank beside real
    # communities. A pop-independent flag: the pop floor (low_confidence) misses 80045 (pop 1,615).
    # Metadata only - does not change any score; kept out of headline rankings + caveated. Audit A2.
    prov_total = pd.to_numeric(df["providers_total"], errors="coerce")
    df["institutional"] = (prov_total > pop) & pop.notna() & (pop > 0)

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
    # The three dimensions are ~1.6 effective dimensions (need<->vulnerability 0.73), so a high
    # care_access score is hard to read: genuinely poor access, or just a poor area? This lens
    # residualizes care_access_pctile on health_need + social_vulnerability and re-ranks the
    # residual: higher = barriers to care WORSE than this area's deprivation level predicts (the
    # structural-access part not explained by poverty). Not in the composite - a selectable lens,
    # like the multiplicative one. Directly answers the collinearity critique.
    df["care_access_resid_pctile"] = _access_beyond_deprivation(df, dim_cols)

    n_dims = df[dim_cols].notna().sum(axis=1)
    df["scoreable"] = pop.notna() & (pop > 0) & (n_dims >= 2)
    # How many of the 3 dimensions actually backed this composite. A 2-of-3 score is built from
    # dimensions that are themselves collinear (need<->vulnerability 0.73), so it is a weaker
    # estimate than a 3-of-3 score and must not be presented with equal authority (audit S5).
    df["n_dims_scored"] = n_dims.where(df["scoreable"]).astype("Int64")
    df.loc[~df["scoreable"], "access_gap_score"] = np.nan
    df["access_gap_pctile"] = _pct(df["access_gap_score"])  # true rank of the composite
    # WITHIN-STATE rank (point 5 / decision-context calibration): a national percentile compares a
    # ZCTA to the whole country, but care is allocated within state programs (Medicaid, state HRSA
    # offices). This re-ranks the composite WITHIN each state so "worst 10% in my state" is
    # answerable - the unit a state administrator actually acts on. NaN for non-scoreable (no score
    # to rank). rank(pct) skips NaN, so each state's rank spans only its scoreable ZCTAs.
    df["access_gap_pctile_within_state"] = (
        df.groupby("state", dropna=False)["access_gap_score"].rank(pct=True) * 100.0)

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
    band_decomp = _rank_band_decomposition(df, dim_cols)
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
    _write_map_frame(df, dim_cols)
    _write_subscores(df)
    _write_public_meta(df, corr, eff_dims)
    write_provenance({"rank_band": band_decomp, "score": {
        "method": "hierarchical percentile (SVI-style), re-ranked per level",
        "dimension_weights": DIMENSION_WEIGHTS,
        "rows": len(df), "with_score": int(df["access_gap_score"].notna().sum()),
        "low_confidence": int(df["low_confidence"].sum()),
        "institutional": int(df["institutional"].sum()),
        # build-over-build drift snapshot: key quantiles of the raw composite. A future build can
        # diff these against the committed provenance to catch a silent distribution shift (A4).
        "score_quantiles": _score_quantiles(df),
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
    log("join", f"wrote {OUT_PARQUET.name} ({len(df)} rows, {df.shape[1]} cols) + "
                f"{OUT_MAP_FRAME.name} + {OUT_SUBSCORES.name}")
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


# First-paint frame columns: labels + composite inputs + composite-family lenses + the reliable-range
# band (T4) + tier/flags. NOT the 14 sub-scores (lazy) and NOT access_gap_score (recomputed client-side),
# state_name / raw life_expectancy (never read client-side).
_FRAME_LABEL_COLS = ["zcta5", "state", "city", "county_name", "population"]
_FRAME_LENS_COLS = ["access_gap_pctile", "access_gap_pctile_within_state", "care_access_resid_pctile",
                    "access_gap_rank_lo", "access_gap_rank_hi"]
_FRAME_FLAG_COLS = ["tier", "n_dims_scored", "low_confidence", "institutional", "scoreable"]


def _cell(v):
    """JSON-safe scalar: NaN/NA -> None; numpy scalars -> native Python; strings pass through."""
    if pd.isna(v):
        return None
    return v.item() if isinstance(v, np.generic) else v


def _columnar(df: pd.DataFrame, cols: list[str]) -> dict:
    """Struct-of-arrays payload: {"n": rows, <col>: [...]}. Float (percentile/rank) columns are
    quantized to nullable int (0-100, NaN -> null); bools -> 0/1; everything else (ids, labels,
    nullable ints) keeps its value with NaN/NA -> null. Killing the repeated object keys (~25 chars
    x 33k rows) is most of the size win over array-of-objects."""
    cols = [c for c in dict.fromkeys(cols) if c in df.columns]
    out: dict = {"n": int(len(df))}
    for c in cols:
        s = df[c]
        if s.dtype.kind == "f":
            s = s.round(0).astype("Int64")
            out[c] = [None if v is pd.NA else int(v) for v in s]
        elif s.dtype.kind == "b":
            out[c] = [int(v) for v in s]
        else:
            out[c] = [_cell(v) for v in s]
    return out


def _write_columnar(path, df: pd.DataFrame, cols: list[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_columnar(df, cols), separators=(",", ":")))
    return path.stat().st_size


def _write_map_frame(df: pd.DataFrame, dim_cols: list[str]) -> None:
    cols = [*_FRAME_LABEL_COLS, *dim_cols, *_FRAME_LENS_COLS, *_FRAME_FLAG_COLS]
    size = _write_columnar(OUT_MAP_FRAME, df, cols)
    log("join", f"map_frame.json: {len(df)} records, {len(cols)} cols ({size/1e6:.1f} MB)")


def _write_subscores(df: pd.DataFrame) -> None:
    cols = ["zcta5", *SUBSCORE_COLS, "life_expectancy_pctile"]
    size = _write_columnar(OUT_SUBSCORES, df, cols)
    log("join", f"subscores.json: {len(df)} records, {len(cols)} cols ({size/1e6:.1f} MB)")


def _sha256(path) -> str | None:
    """sha256 of a file, streamed; None if the file is not present (e.g. pmtiles built separately)."""
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_sha() -> str:
    """Pipeline commit stamped into the build so a live payload is traceable to a source revision.
    Prefers HAM_BUILD_SHA (set in CI where the git dir may be absent), else `git rev-parse HEAD`."""
    env = os.environ.get("HAM_BUILD_SHA")
    if env:
        return env.strip()
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=config.ROOT,
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _write_public_meta(df: pd.DataFrame, corr: dict, eff_dims: dict) -> None:
    """Slim, frontend-fetchable build metadata (provenance.json itself is not in public/). Drives
    the in-app 'data as of' freshness badge + the dynamic methodology vintages. The NPPES vintage
    is read from the providers stage's provenance section if already written.

    T9 governance: also stamps the pipeline git SHA + a sha256 per shipped payload + the
    provenance digest, and emits deploy-manifest.json, so a live deploy is traceable to a data
    vintage and a source revision (the payloads themselves are gitignored / built locally)."""
    prov = json.loads(config.PROVENANCE.read_text()) if config.PROVENANCE.exists() else {}
    payloads = {
        "map_frame.json": OUT_MAP_FRAME,
        "subscores.json": OUT_SUBSCORES,
        "zcta_overview.geojson": config.FRONTEND_PUBLIC / "zcta_overview.geojson",
        "zcta.pmtiles": config.FRONTEND_PUBLIC / "zcta.pmtiles",
    }
    payload_hashes = {name: h for name, p in payloads.items() if (h := _sha256(p)) is not None}
    build = {
        "git_sha": _git_sha(),
        "provenance_sha256": _sha256(config.PROVENANCE),
        "payloads": payload_hashes,
    }
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
        "institutional": int(df["institutional"].sum()),
        "dimension_correlations": corr,
        "effective_dimensions": eff_dims,
        "build": build,
    }
    (config.FRONTEND_PUBLIC / "meta.json").write_text(json.dumps(meta))
    # Ops record that travels with the deploy (served at /deploy-manifest.json): what data vintage +
    # source revision shipped, and the content hash of every payload, so a rollback is traceable.
    manifest = {
        "generated": meta["generated"],
        "git_sha": build["git_sha"],
        "vintages": meta["vintages"],
        "provenance_sha256": build["provenance_sha256"],
        "payloads": payload_hashes,
    }
    (config.FRONTEND_PUBLIC / "deploy-manifest.json").write_text(json.dumps(manifest, indent=2))
    log("join", f"wrote meta.json + deploy-manifest.json (generated {meta['generated']}, "
                f"build {build['git_sha'][:7]}, {len(payload_hashes)} payload hashes)")


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


def _composite_pc1_corr(dim_values: np.ndarray, composite: np.ndarray) -> float | None:
    """|Pearson r| between the additive composite and PC1 of the standardized dimension matrix.
    A value > 0.99 means the weighted sum IS, statistically, the first principal component: the
    three "dimensions" collapse to one latent gradient, so the weights are a sensitivity probe, not
    a choice among independent axes (T3). Pure kernel (no DataFrame) so it is unit-testable.

    `dim_values` is an (n, k) array of the k dimension percentiles; `composite` is the (n,) score.
    Rows with any NaN in either are dropped; returns None if < 10 complete rows or PC1 is degenerate."""
    X = np.asarray(dim_values, float)
    c = np.asarray(composite, float)
    ok = ~np.isnan(c) & ~np.isnan(X).any(axis=1)
    if ok.sum() < 10:
        return None
    X, c = X[ok], c[ok]
    Xs = (X - X.mean(axis=0)) / X.std(axis=0, ddof=0)
    # leading eigenvector of the correlation matrix -> PC1 scores (sign is arbitrary, so |r|)
    w, V = np.linalg.eigh(np.corrcoef(Xs, rowvar=False))
    pc1 = Xs @ V[:, int(np.argmax(w))]
    if pc1.std() == 0 or c.std() == 0:
        return None
    return abs(float(np.corrcoef(pc1, c)[0, 1]))


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
    out = {
        "pc1_share": round(float(ev[0] / ev.sum()), 3),
        "participation_ratio": round(float(ev.sum() ** 2 / (ev ** 2).sum()), 2),
        "note": "eigen-decomposition of the dimension correlation matrix; participation_ratio "
                "= effective number of independent dimensions (3 nominal). Low value => "
                "re-weighting barely moves ranks; the sliders are a sensitivity probe.",
    }
    # the decisive number: does the additive composite ~equal PC1? (T3 - composite ≈ PC1 proof)
    if "access_gap_score" in df.columns:
        cp = _composite_pc1_corr(df[dim_cols].to_numpy(), df["access_gap_score"].to_numpy())
        if cp is not None:
            out["composite_pc1_corr"] = round(cp, 4)
            out["composite_is_pc1"] = bool(cp > 0.99)
    return out


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


def _score_quantiles(df: pd.DataFrame) -> dict:
    """Key quantiles of the raw composite among scoreable ZCTAs - a compact distribution fingerprint
    committed to provenance so a later build can detect drift (A4)."""
    v = df.loc[df["scoreable"], "access_gap_score"].dropna()
    if v.empty:
        return {}
    return {f"p{q}": round(float(np.percentile(v, q)), 2) for q in (5, 25, 50, 75, 95)}


def _validate(df: pd.DataFrame, dim_cols: list[str], dev_state: str | None) -> None:
    assert_zcta(df, stage="join")
    has_data = df[["diabetes_pct", "providers_total", "median_income"]].notna().any(axis=1)
    overlap = has_data.mean()
    if overlap < 0.90:
        die("join", f"only {overlap:.0%} of geometry ZCTAs have data")
    if df["access_gap_score"].isna().all():
        die("join", "access_gap_score entirely null")
    _validate_integrity(df, dim_cols)
    log("join", f"validated: {overlap:.0%} overlap, all percentiles in [0,100], "
                f"{int(df['access_gap_score'].notna().sum())} scored")


# Data-integrity invariants - the audit checks (2026-06-24) that pass TODAY, locked so a future
# build can't silently regress. Mirrored by tests/test_integrity.py (skip-guarded on a real build).
# Each is a hard build-time `die`. See docs/BACKLOG.md A3.
def _validate_integrity(df: pd.DataFrame, dim_cols: list[str]) -> None:
    # 1. every percentile (dimension, sub-score, per-measure _natpct, composite) in [0,100]
    pct_cols = ([*dim_cols, *SUBSCORE_COLS, "access_gap_score", "access_gap_pctile"]
                + [c for c in df.columns if c.endswith(("_pctile", "_natpct"))])
    for col in dict.fromkeys(pct_cols):
        if col not in df.columns:
            continue
        v = df[col].dropna()
        if len(v) and (v.min() < -0.001 or v.max() > 100.001):
            die("join", f"{col} outside [0,100]: min={v.min()} max={v.max()}")
    # 2. every rate (a proportion) in [0,1]
    for col in [c for c in df.columns if c.endswith("_rate")]:
        v = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(v) and (v.min() < -0.001 or v.max() > 1.001):
            die("join", f"{col} not a proportion in [0,1]: min={v.min()} max={v.max()}")
    # 3. no leftover sentinel (e.g. -999999) masquerading as a real value
    num = df.select_dtypes("number")
    sentinel = num.min()[num.min() < -100000]
    if len(sentinel):
        die("join", f"sentinel-like values (< -1e5) survived into output: {sentinel.to_dict()}")
    # 4. a non-positive / missing population can never be scoreable
    pop = pd.to_numeric(df["population"], errors="coerce")
    bad = int((~(pop > 0) & df["scoreable"]).sum())
    if bad:
        die("join", f"{bad} ZCTA(s) scoreable with population <= 0 / missing")
    # 5. every absurd-per-capita ZCTA (>1000 primary providers/1k) must be flagged non-residential
    if "primary_per_1k" in df.columns:
        extreme = pd.to_numeric(df["primary_per_1k"], errors="coerce") > 1000
        unflagged = int((extreme & ~(df["low_confidence"] | df["institutional"])).sum())
        if unflagged:
            die("join", f"{unflagged} ZCTA(s) with >1000 providers/1k not flagged "
                        "low_confidence|institutional")
    # 6. one row per ZCTA (the geometry universe is de-duplicated; a dup would double-serve a ZIP)
    n_dup = int(df["zcta5"].duplicated().sum())
    if n_dup:
        die("join", f"{n_dup} duplicate zcta5 row(s) in output")
    # 7. county_fips, where joined, is a real 5-digit FIPS (valid state/territory prefix). A bad
    #    code silently drops the county joins (medical_debt, amenable, geonames) for that ZCTA.
    if "county_fips" in df.columns:
        cf = df["county_fips"].dropna().astype(str)
        valid_st = {f"{i:02d}" for i in range(1, 57)} | {"60", "66", "69", "72", "74", "78"}
        bad = cf[~cf.str.match(r"^\d{5}$") | ~cf.str[:2].isin(valid_st)]
        if len(bad):
            die("join", f"{len(bad)} invalid county_fips (e.g. {sorted(bad.unique())[:5]})")


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

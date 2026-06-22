"""build_supply: spatial provider supply via E2SFCA (Luo & Qi 2009).

Enhanced Two-Step Floating Catchment Area = 2SFCA + **distance decay**: closer
providers count more than ones at the edge of the catchment (a Gaussian weight on
travel distance), which is more realistic than the binary in/out catchment.

  Step 1: Rj = providers_j / Σ_k [ population_k · w(d_jk) ]   over k within radius
  Step 2: A_i = Σ_j [ Rj · w(d_ij) ]                          over j within radius
  with w(d) = exp(-½ (d/σ)²)   (Gaussian decay)

Also computes a NEED-ADJUSTED variant (demand weighted by chronic-disease burden) and
stores it for transparency — but the *scored* supply stays un-need-adjusted to avoid
double-counting health need, which is already its own dimension (see RATIONALE §11).

Implemented with a BallTree(haversine) radius query returning distances (milliseconds
over 33k points; never all-pairs). Outputs primary/mental access per 1,000 reachable
(higher = better), the need-adjusted primary variant, people-per-provider, and the
HRSA 3,500:1 shortage flag.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from . import config
from .common import assert_zcta, die, log, write_provenance

OUT = config.PROCESSED / "supply.parquet"


def _e2sfca(providers: np.ndarray, demand: np.ndarray,
            neighbors: list[np.ndarray], weights: list[np.ndarray]) -> np.ndarray:
    # Step 1: distance-decay-weighted demand pooled at each supply location
    pooled = np.array([(demand[idx] * w).sum() for idx, w in zip(neighbors, weights)])
    Rj = np.divide(providers, pooled, out=np.zeros_like(providers, dtype=float), where=pooled > 0)
    # Step 2: distance-decay-weighted sum of reachable ratios
    return np.array([(Rj[idx] * w).sum() for idx, w in zip(neighbors, weights)])


def _e2sfca_adaptive(providers: np.ndarray, demand: np.ndarray, ni: np.ndarray,
                     w1: np.ndarray, w2: np.ndarray) -> np.ndarray:
    """Variable-bandwidth E2SFCA (vectorized, bounded kNN). w1[j] uses each demand
    neighbour's own bandwidth (step 1, pooling at supply j); w2[i] uses ZCTA i's own
    bandwidth (step 2, access at i). ni = (n, k) neighbour indices."""
    pooled = (demand[ni] * w1).sum(axis=1)                       # demand pooled at each supply j
    Rj = np.divide(providers, pooled, out=np.zeros(len(providers)), where=pooled > 0)
    return (Rj[ni] * w2).sum(axis=1)                             # access at each ZCTA i


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("supply", f"skip (exists): {OUT.name}")
        return str(OUT)

    gaz = pd.read_parquet(config.PROCESSED / "gazetteer.parquet")
    ptypes = ["providers_primary", "providers_mental", "providers_dental", "providers_obgyn",
              "providers_primary_cap", "providers_mental_cap"]
    pcols = pd.read_parquet(config.PROCESSED / "providers.parquet")
    prov = pcols[["zcta5", *[c for c in ptypes if c in pcols.columns]]]
    acs = pd.read_parquet(config.PROCESSED / "acs.parquet")[["zcta5", "population"]]
    places = pd.read_parquet(config.PROCESSED / "places.parquet")
    df = (gaz.merge(prov, on="zcta5", how="left")
             .merge(acs, on="zcta5", how="left")
             .merge(places[["zcta5", *[c for c in config.NEED_WEIGHT_COLS if c in places.columns]]],
                    on="zcta5", how="left"))
    for c in ptypes:
        df[c] = df[c].fillna(0).astype(float) if c in df.columns else 0.0
    df["population"] = pd.to_numeric(df["population"], errors="coerce").fillna(0).astype(float)

    # demand (need) weight: 1 + normalized chronic-disease burden  -> [1, 2]
    need_cols = [c for c in config.NEED_WEIGHT_COLS if c in df.columns]
    burden = df[need_cols].mean(axis=1) if need_cols else pd.Series(0.0, index=df.index)
    lo, hi = burden.quantile(0.02), burden.quantile(0.98)
    need_mult = 1.0 + ((burden - lo) / (hi - lo)).clip(0, 1).fillna(0.0)

    pop = df["population"].to_numpy()
    coords = np.radians(df[["lat", "lon"]].to_numpy())
    tree = BallTree(coords, metric="haversine")

    if config.ADAPTIVE_CATCHMENT:
        # variable-bandwidth catchment (Layer C3): each ZCTA's σ = distance to the K-th
        # nearest centroid (local density), clipped -> small in cities, large in rural.
        k = min(config.ADAPTIVE_KNN, len(df))
        nd, ni = tree.query(coords, k=k)
        nd_km = nd * config.EARTH_KM
        dK = nd_km[:, min(config.ADAPTIVE_K, k - 1)]
        sig = np.clip(dK, config.ADAPTIVE_SIGMA_MIN_KM, config.ADAPTIVE_SIGMA_MAX_KM)
        log("supply", f"E2SFCA over {len(df)} centroids, ADAPTIVE catchment "
                      f"(σ {np.percentile(sig,10):.0f}-{np.percentile(sig,90):.0f} km, "
                      f"median {np.median(sig):.0f})...")
        w1 = np.exp(-0.5 * (nd_km / sig[ni]) ** 2)      # step 1: neighbour's own bandwidth
        w2 = np.exp(-0.5 * (nd_km / sig[:, None]) ** 2)  # step 2: ZCTA i's own bandwidth
        sfca = lambda prov, dem: _e2sfca_adaptive(np.asarray(prov, float), dem, ni, w1, w2)  # noqa: E731
    else:
        radius = config.CATCHMENT_KM / config.EARTH_KM
        ind, dist = tree.query_radius(coords, r=radius, return_distance=True)
        sigma = config.DECAY_SIGMA_KM / config.EARTH_KM
        weights = [np.exp(-0.5 * (d / sigma) ** 2) for d in dist]
        log("supply", f"E2SFCA over {len(df)} centroids, {config.CATCHMENT_KM} km fixed "
                      f"catchment, Gaussian σ={config.DECAY_SIGMA_KM} km...")
        sfca = lambda prov, dem: _e2sfca(np.asarray(prov, float), dem, ind, weights)  # noqa: E731

    a_primary = sfca(df["providers_primary"], pop)
    a_mental = sfca(df["providers_mental"], pop)
    a_dental = sfca(df["providers_dental"], pop)
    a_obgyn = sfca(df["providers_obgyn"], pop)
    a_primary_need = sfca(df["providers_primary"], pop * need_mult.to_numpy())
    # Layer C2 capacity-weighted variants (kept for diagnostics; not scored).
    a_primary_cap = sfca(df["providers_primary_cap"], pop)
    a_mental_cap = sfca(df["providers_mental_cap"], pop)

    df["primary_2sfca"] = a_primary * 1000.0
    df["mental_2sfca"] = a_mental * 1000.0
    df["dental_2sfca"] = a_dental * 1000.0
    df["ob_2sfca"] = a_obgyn * 1000.0
    df["primary_2sfca_cap"] = a_primary_cap * 1000.0
    df["mental_2sfca_cap"] = a_mental_cap * 1000.0
    df["primary_2sfca_needadj"] = a_primary_need * 1000.0

    # People-per-provider + the HRSA 3,500:1 shortage flag need a FIXED, interpretable
    # service area (the adaptive catchment is for the scored percentile, not an absolute
    # benchmark). So compute these from the fixed 16 km catchment regardless.
    radius = config.CATCHMENT_KM / config.EARTH_KM
    find, fdist = tree.query_radius(coords, r=radius, return_distance=True)
    fsig = config.DECAY_SIGMA_KM / config.EARTH_KM
    fw = [np.exp(-0.5 * (d / fsig) ** 2) for d in fdist]
    a_primary_fixed = _e2sfca(df["providers_primary"].to_numpy(), pop, find, fw)
    df["primary_people_per_provider"] = np.divide(
        1.0, a_primary_fixed, out=np.full_like(a_primary_fixed, np.inf), where=a_primary_fixed > 0)
    df["primary_shortage"] = df["primary_people_per_provider"] > config.HPSA_SHORTAGE_RATIO

    out = df[["zcta5", "primary_2sfca", "mental_2sfca", "dental_2sfca", "ob_2sfca",
              "primary_2sfca_cap", "mental_2sfca_cap",
              "primary_2sfca_needadj", "primary_people_per_provider",
              "primary_shortage"]].copy()
    out["primary_people_per_provider"] = out["primary_people_per_provider"].replace(np.inf, np.nan)
    _validate(out, dev_state)
    out.to_parquet(OUT, index=False)
    write_provenance({"supply": {
        "method": ("E2SFCA (Luo & Qi 2009) with VARIABLE/adaptive catchment "
                   "(McGrail & Humphreys 2009): per-ZCTA Gaussian σ = distance to the "
                   f"{config.ADAPTIVE_K}-th nearest centroid, clipped "
                   f"[{config.ADAPTIVE_SIGMA_MIN_KM:.0f},{config.ADAPTIVE_SIGMA_MAX_KM:.0f}] km"
                   if config.ADAPTIVE_CATCHMENT else
                   "E2SFCA (Luo & Qi 2009), fixed-radius Gaussian distance decay"),
        "shortage_basis": "fixed 16 km catchment vs HRSA 3,500:1 (interpretable benchmark)",
        "catchment_km": config.CATCHMENT_KM, "decay_sigma_km": config.DECAY_SIGMA_KM,
        "hpsa_threshold": config.HPSA_SHORTAGE_RATIO,
        "shortage_zctas": int(out["primary_shortage"].sum()),
        "need_adjusted_variant": "primary_2sfca_needadj (not scored; avoids double-counting need)",
        "centroid_source": "Census ZCTA Gazetteer internal points",
    }})
    log("supply", f"wrote {OUT.name} ({len(out)} zctas, "
                  f"{int(out['primary_shortage'].sum())} below HRSA 3,500:1)")
    return str(OUT)


def _validate(df: pd.DataFrame, dev_state: str | None) -> None:
    assert_zcta(df, stage="supply")
    if df["primary_2sfca"].isna().all() or (df["primary_2sfca"] < 0).any():
        die("supply", "primary_2sfca invalid")
    log("supply", f"validated: median primary access {df['primary_2sfca'].median():.2f}/1k "
                  f"(need-adj {df['primary_2sfca_needadj'].median():.2f}/1k), "
                  f"{int(df['primary_shortage'].sum())} shortage zctas")


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

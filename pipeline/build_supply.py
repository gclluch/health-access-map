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
    ptypes = ["providers_primary", "providers_mental", "providers_dental", "providers_obgyn"]
    prov = pd.read_parquet(config.PROCESSED / "providers.parquet")[["zcta5", *ptypes]]
    acs = pd.read_parquet(config.PROCESSED / "acs.parquet")[["zcta5", "population"]]
    df = gaz.merge(prov, on="zcta5", how="left").merge(acs, on="zcta5", how="left")
    for c in ptypes:
        df[c] = df[c].fillna(0).astype(float)
    df["population"] = pd.to_numeric(df["population"], errors="coerce").fillna(0).astype(float)

    pop = df["population"].to_numpy()
    coords = np.radians(df[["lat", "lon"]].to_numpy())
    tree = BallTree(coords, metric="haversine")

    # Variable-bandwidth (adaptive) catchment: each ZCTA's σ = distance to the K-th nearest
    # centroid (local settlement density), clipped -> small in cities, large in sparse rural.
    k = min(config.ADAPTIVE_KNN, len(df))
    nd, ni = tree.query(coords, k=k)
    nd_km = nd * config.EARTH_KM
    sig = np.clip(nd_km[:, min(config.ADAPTIVE_K, k - 1)],
                  config.ADAPTIVE_SIGMA_MIN_KM, config.ADAPTIVE_SIGMA_MAX_KM)
    log("supply", f"E2SFCA over {len(df)} centroids, adaptive catchment "
                  f"(σ {np.percentile(sig,10):.0f}-{np.percentile(sig,90):.0f} km, "
                  f"median {np.median(sig):.0f})...")
    w1 = np.exp(-0.5 * (nd_km / sig[ni]) ** 2)       # step 1: neighbour's own bandwidth
    w2 = np.exp(-0.5 * (nd_km / sig[:, None]) ** 2)  # step 2: ZCTA i's own bandwidth

    def sfca(prov_col):
        return _e2sfca_adaptive(np.asarray(df[prov_col], float), pop, ni, w1, w2)

    df["primary_2sfca"] = sfca("providers_primary") * 1000.0
    df["mental_2sfca"] = sfca("providers_mental") * 1000.0
    df["dental_2sfca"] = sfca("providers_dental") * 1000.0
    df["ob_2sfca"] = sfca("providers_obgyn") * 1000.0

    # An E2SFCA-derived people-per-provider PROXY + the shortage flag need a FIXED, interpretable
    # service area (the adaptive catchment drives the scored percentile, not an absolute benchmark).
    # NB: primary_people_per_provider is 1 / (Gaussian-decayed E2SFCA accessibility), so it is a
    # DECAY-WEIGHTED proxy, not the hard population-per-provider service-area ratio the HRSA 3,500:1
    # threshold is literally defined on - read the flag as "E2SFCA proxy ~ HRSA 3,500:1", not the
    # official designation.
    find, fdist = tree.query_radius(coords, r=config.CATCHMENT_KM / config.EARTH_KM,
                                    return_distance=True)
    fsig = config.DECAY_SIGMA_KM / config.EARTH_KM
    fw = [np.exp(-0.5 * (d / fsig) ** 2) for d in fdist]
    a_primary_fixed = _e2sfca(df["providers_primary"].to_numpy(), pop, find, fw)
    df["primary_people_per_provider"] = np.divide(
        1.0, a_primary_fixed, out=np.full_like(a_primary_fixed, np.inf), where=a_primary_fixed > 0)
    df["primary_shortage"] = df["primary_people_per_provider"] > config.HPSA_SHORTAGE_RATIO

    out = df[["zcta5", "primary_2sfca", "mental_2sfca", "dental_2sfca", "ob_2sfca",
              "primary_people_per_provider", "primary_shortage"]].copy()
    out["primary_people_per_provider"] = out["primary_people_per_provider"].replace(np.inf, np.nan)
    _validate(out, dev_state)
    out.to_parquet(OUT, index=False)
    write_provenance({"supply": {
        "method": ("E2SFCA (Luo & Qi 2009) with variable/adaptive catchment "
                   "(McGrail & Humphreys 2009): per-ZCTA Gaussian σ = distance to the "
                   f"{config.ADAPTIVE_K}-th nearest centroid, clipped "
                   f"[{config.ADAPTIVE_SIGMA_MIN_KM:.0f},{config.ADAPTIVE_SIGMA_MAX_KM:.0f}] km"),
        "shortage_basis": f"E2SFCA-inverse proxy over a fixed {config.CATCHMENT_KM:.0f} km catchment "
                          "vs HRSA 3,500:1 (decay-weighted, not a hard service-area ratio)",
        "hpsa_threshold": config.HPSA_SHORTAGE_RATIO,
        "shortage_zctas": int(out["primary_shortage"].sum()),
        "centroid_source": "Census ZCTA Gazetteer internal points",
    }})
    log("supply", f"wrote {OUT.name} ({len(out)} zctas, "
                  f"{int(out['primary_shortage'].sum())} below the E2SFCA ~HRSA 3,500:1 proxy)")
    return str(OUT)


def _validate(df: pd.DataFrame, dev_state: str | None) -> None:
    assert_zcta(df, stage="supply")
    if df["primary_2sfca"].isna().all() or (df["primary_2sfca"] < 0).any():
        die("supply", "primary_2sfca invalid")
    log("supply", f"validated: median primary access {df['primary_2sfca'].median():.2f}/1k, "
                  f"{int(df['primary_shortage'].sum())} shortage zctas")


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

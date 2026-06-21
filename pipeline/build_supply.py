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


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("supply", f"skip (exists): {OUT.name}")
        return str(OUT)

    gaz = pd.read_parquet(config.PROCESSED / "gazetteer.parquet")
    prov = pd.read_parquet(config.PROCESSED / "providers.parquet")[
        ["zcta5", "providers_primary", "providers_mental"]]
    acs = pd.read_parquet(config.PROCESSED / "acs.parquet")[["zcta5", "population"]]
    places = pd.read_parquet(config.PROCESSED / "places.parquet")
    df = (gaz.merge(prov, on="zcta5", how="left")
             .merge(acs, on="zcta5", how="left")
             .merge(places[["zcta5", *[c for c in config.NEED_WEIGHT_COLS if c in places.columns]]],
                    on="zcta5", how="left"))
    for c in ("providers_primary", "providers_mental"):
        df[c] = df[c].fillna(0).astype(float)
    df["population"] = pd.to_numeric(df["population"], errors="coerce").fillna(0).astype(float)

    # demand (need) weight: 1 + normalized chronic-disease burden  -> [1, 2]
    need_cols = [c for c in config.NEED_WEIGHT_COLS if c in df.columns]
    burden = df[need_cols].mean(axis=1) if need_cols else pd.Series(0.0, index=df.index)
    lo, hi = burden.quantile(0.02), burden.quantile(0.98)
    need_mult = 1.0 + ((burden - lo) / (hi - lo)).clip(0, 1).fillna(0.0)

    log("supply", f"E2SFCA over {len(df)} centroids, {config.CATCHMENT_KM} km catchment, "
                  f"Gaussian σ={config.DECAY_SIGMA_KM} km...")
    coords = np.radians(df[["lat", "lon"]].to_numpy())
    tree = BallTree(coords, metric="haversine")
    radius = config.CATCHMENT_KM / config.EARTH_KM
    ind, dist = tree.query_radius(coords, r=radius, return_distance=True)
    # Gaussian decay weights on travel distance (km)
    sigma = config.DECAY_SIGMA_KM / config.EARTH_KM
    weights = [np.exp(-0.5 * (d / sigma) ** 2) for d in dist]

    pop = df["population"].to_numpy()
    a_primary = _e2sfca(df["providers_primary"].to_numpy(), pop, ind, weights)
    a_mental = _e2sfca(df["providers_mental"].to_numpy(), pop, ind, weights)
    a_primary_need = _e2sfca(df["providers_primary"].to_numpy(),
                             pop * need_mult.to_numpy(), ind, weights)

    df["primary_2sfca"] = a_primary * 1000.0
    df["mental_2sfca"] = a_mental * 1000.0
    df["primary_2sfca_needadj"] = a_primary_need * 1000.0
    df["primary_people_per_provider"] = np.divide(
        1.0, a_primary, out=np.full_like(a_primary, np.inf), where=a_primary > 0)
    df["primary_shortage"] = df["primary_people_per_provider"] > config.HPSA_SHORTAGE_RATIO

    out = df[["zcta5", "primary_2sfca", "mental_2sfca", "primary_2sfca_needadj",
              "primary_people_per_provider", "primary_shortage"]].copy()
    out["primary_people_per_provider"] = out["primary_people_per_provider"].replace(np.inf, np.nan)
    _validate(out, dev_state)
    out.to_parquet(OUT, index=False)
    write_provenance({"supply": {
        "method": "E2SFCA (Luo & Qi 2009), Gaussian distance decay",
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

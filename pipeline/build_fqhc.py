"""build_fqhc: HRSA Health Center (FQHC) sites -> safety-net spatial access per ZCTA.

The deepest blind spot in a provider-density metric: it counts a concierge physician
the same as a community clinic. FQHCs are mandated to serve everyone on a sliding fee
scale, so they are the access point for the uninsured / Medicaid - exactly the
populations this tool is about. This stage measures spatial access to that safety net.

Method: bipartite E2SFCA (sites = supply, ZCTA centroids = demand) with Gaussian
distance decay - same engine as build_supply, but supply lives at site coordinates.
Each site's effective capacity is weighted by its operating hours/week (a clinic open
70 hrs serves more than one open 10). Outputs per ZCTA: safetynet_2sfca (capacity
reachable per 1,000), fqhc_sites_reachable (count in catchment), nearest_fqhc_km.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from . import config
from .common import assert_zcta, dev_filter, die, download_file, log, write_provenance

OUT = config.PROCESSED / "fqhc.parquet"


def _load_sites() -> pd.DataFrame:
    dest = config.RAW / "hrsa_fqhc_sites.csv"
    download_file(config.FQHC_URL, dest, min_bytes=2_000_000)
    df = pd.read_csv(dest, dtype=str, low_memory=False)
    lon = pd.to_numeric(df[config.FQHC_COL_LON], errors="coerce")
    lat = pd.to_numeric(df[config.FQHC_COL_LAT], errors="coerce")
    status = df[config.FQHC_COL_STATUS].astype("string").str.strip().str.lower()
    hours = pd.to_numeric(df[config.FQHC_COL_HOURS], errors="coerce")
    capacity = hours.clip(config.FQHC_HOURS_FLOOR, config.FQHC_HOURS_CEIL).fillna(
        config.FQHC_HOURS_DEFAULT)
    sites = pd.DataFrame({"lat": lat, "lon": lon, "capacity": capacity, "status": status})
    sites = sites[(sites["status"] == "active") & sites["lat"].between(17, 72)
                  & sites["lon"].between(-180, -64)]
    if len(sites) < 5000:
        die("fqhc", f"only {len(sites)} active geocoded FQHC sites (expected >10k)")
    return sites.reset_index(drop=True)


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("fqhc", f"skip (exists): {OUT.name}")
        return str(OUT)

    sites = _load_sites()
    gaz = pd.read_parquet(config.PROCESSED / "gazetteer.parquet")
    acs = pd.read_parquet(config.PROCESSED / "acs.parquet")[["zcta5", "population"]]
    df = gaz.merge(acs, on="zcta5", how="left")
    df["population"] = pd.to_numeric(df["population"], errors="coerce").fillna(0).astype(float)

    log("fqhc", f"E2SFCA over {len(sites)} active FQHC sites -> {len(df)} ZCTAs...")
    site_xy = np.radians(sites[["lat", "lon"]].to_numpy())
    zcta_xy = np.radians(df[["lat", "lon"]].to_numpy())
    radius = config.CATCHMENT_KM / config.EARTH_KM
    sigma = config.DECAY_SIGMA_KM / config.EARTH_KM
    cap = sites["capacity"].to_numpy()
    pop = df["population"].to_numpy()

    # Step 1: each site's capacity over its decay-weighted demand catchment (ZCTAs)
    tree_zcta = BallTree(zcta_xy, metric="haversine")
    z_ind, z_dist = tree_zcta.query_radius(site_xy, r=radius, return_distance=True)
    Rj = np.zeros(len(sites))
    for j in range(len(sites)):
        if len(z_ind[j]):
            w = np.exp(-0.5 * (z_dist[j] / sigma) ** 2)
            pooled = (pop[z_ind[j]] * w).sum()
            if pooled > 0:
                Rj[j] = cap[j] / pooled

    # Step 2: each ZCTA's decay-weighted sum of reachable site ratios (+ count + nearest)
    tree_site = BallTree(site_xy, metric="haversine")
    s_ind, s_dist = tree_site.query_radius(zcta_xy, r=radius, return_distance=True)
    access = np.array([(Rj[idx] * np.exp(-0.5 * (d / sigma) ** 2)).sum()
                       for idx, d in zip(s_ind, s_dist)])
    count = np.array([len(idx) for idx in s_ind])
    nearest_d, _ = tree_site.query(zcta_xy, k=1)

    df["safetynet_2sfca"] = access * 1000.0
    df["fqhc_sites_reachable"] = count.astype("int64")
    df["nearest_fqhc_km"] = (nearest_d[:, 0] * config.EARTH_KM).round(1)

    out = df[["zcta5", "safetynet_2sfca", "fqhc_sites_reachable", "nearest_fqhc_km"]].copy()
    out = dev_filter(out, dev_state)
    _validate(out, dev_state)
    out.to_parquet(OUT, index=False)
    write_provenance({"fqhc": {
        "method": "bipartite E2SFCA over HRSA FQHC sites (capacity = operating hrs/wk)",
        "active_sites": int(len(sites)), "catchment_km": config.CATCHMENT_KM,
        "zctas_with_no_fqhc_in_catchment": int((out["fqhc_sites_reachable"] == 0).sum()),
        "source": "HRSA Health Center Service Delivery and Look-Alike Sites",
    }})
    log("fqhc", f"wrote {OUT.name} ({len(out)} zctas; "
                f"{int((out['fqhc_sites_reachable'] == 0).sum())} with no FQHC in catchment; "
                f"median nearest {out['nearest_fqhc_km'].median():.1f} km)")
    return str(OUT)


def _validate(df: pd.DataFrame, dev_state: str | None) -> None:
    assert_zcta(df, stage="fqhc")
    if df["safetynet_2sfca"].isna().all() or (df["safetynet_2sfca"] < 0).any():
        die("fqhc", "safetynet_2sfca invalid")
    log("fqhc", f"validated: {int((df['fqhc_sites_reachable'] > 0).mean() * 100)}% of ZCTAs "
                f"reach an FQHC within {config.CATCHMENT_KM:.0f} km")


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

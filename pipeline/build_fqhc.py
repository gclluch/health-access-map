"""build_fqhc: HRSA Health Center (FQHC) sites -> safety-net proximity per ZCTA.

The deepest blind spot in a provider-density metric: it counts a concierge physician
the same as a community clinic. FQHCs are mandated to serve everyone on a sliding fee
scale, so they are the access point for the uninsured / Medicaid - exactly the
populations this tool is about.

Outputs per ZCTA: fqhc_sites_reachable (count within the catchment) and nearest_fqhc_km
(distance to the closest site). The scored "safety-net barrier" is computed in
join_and_score as nearest_fqhc_km-percentile x poverty - the *need-relative* form, because
raw FQHC access is wrong-signed (clinics are sited where need is highest). A raw bipartite
E2SFCA "FQHC access" score was tried and dropped for exactly that reason (see METHODOLOGY).
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
    sites = pd.DataFrame({"lat": lat, "lon": lon, "status": status})
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
    df = pd.read_parquet(config.PROCESSED / "gazetteer.parquet")

    log("fqhc", f"FQHC proximity: {len(sites)} active sites -> {len(df)} ZCTAs...")
    site_xy = np.radians(sites[["lat", "lon"]].to_numpy())
    zcta_xy = np.radians(df[["lat", "lon"]].to_numpy())
    radius = config.CATCHMENT_KM / config.EARTH_KM
    tree_site = BallTree(site_xy, metric="haversine")

    counts = tree_site.query_radius(zcta_xy, r=radius, count_only=True)  # sites within the catchment
    nearest_d, _ = tree_site.query(zcta_xy, k=1)             # distance to the nearest site
    df["fqhc_sites_reachable"] = counts.astype("int64")
    df["nearest_fqhc_km"] = (nearest_d[:, 0] * config.EARTH_KM).round(1)

    out = df[["zcta5", "fqhc_sites_reachable", "nearest_fqhc_km"]].copy()
    out = dev_filter(out, dev_state)
    _validate(out, dev_state)
    out.to_parquet(OUT, index=False)
    write_provenance({"fqhc": {
        "method": "FQHC site count within catchment + nearest-site distance (feeds safetynet_barrier)",
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
    if df["nearest_fqhc_km"].isna().all() or (df["nearest_fqhc_km"] < 0).any():
        die("fqhc", "nearest_fqhc_km invalid")
    log("fqhc", f"validated: {int((df['fqhc_sites_reachable'] > 0).mean() * 100)}% of ZCTAs "
                f"reach an FQHC within {config.CATCHMENT_KM:.0f} km")


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

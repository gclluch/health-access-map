"""build_geonames: ZCTA -> human county label via the Census 2020 relationship file.

Output columns: zcta5(str5); county_name(str); county_fips(str5).
A ZCTA can span multiple counties; we keep the one with the largest land-area
overlap (the dominant county) so the label is the one a person would expect.
"""
from __future__ import annotations

import pandas as pd

from . import config
from .common import assert_zcta, dev_filter, die, download_file, log, norm_zcta

OUT = config.PROCESSED / "geonames.parquet"


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("geonames", f"skip (exists): {OUT.name}")
        return str(OUT)

    dest = config.RAW / "zcta_county_rel2020.txt"
    download_file(config.ZCTA_COUNTY_REL, dest, min_bytes=100_000)

    df = pd.read_csv(dest, sep="|", dtype=str, encoding="utf-8-sig").fillna("")
    z, c = "GEOID_ZCTA5_20", "GEOID_COUNTY_20"
    name, area = "NAMELSAD_COUNTY_20", "AREALAND_PART"
    df = df[df[z].str.strip() != ""].copy()
    df["zcta5"] = norm_zcta(df[z])
    df["county_fips"] = df[c].str.strip().str.zfill(5)
    df["county_name"] = df[name].str.strip()
    df["area"] = pd.to_numeric(df[area], errors="coerce").fillna(0)

    # dominant county per ZCTA = largest land-area overlap
    df = df.sort_values("area", ascending=False).drop_duplicates("zcta5", keep="first")
    out = df[["zcta5", "county_name", "county_fips"]].reset_index(drop=True)
    out = dev_filter(out, dev_state)

    assert_zcta(out, stage="geonames")
    if (dev_state and len(out) < 100) or (not dev_state and len(out) < 25_000):
        die("geonames", f"only {len(out)} ZCTA->county rows")
    out.to_parquet(OUT, index=False)
    log("geonames", f"wrote {OUT.name} ({len(out)} ZCTAs, "
                    f"{out['county_name'].nunique()} counties)")
    return str(OUT)


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

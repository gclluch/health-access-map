"""build_lifeexp: CDC USALEEP census-tract life expectancy -> ZCTA life expectancy.

This is the project's one genuinely INDEPENDENT health outcome (from NCHS death
records, 2010-2015) - not derived from BRFSS/PLACES like the disease layer. It powers:
  (1) an outcomes layer the user can view/compare against the access gap, and
  (2) the empirical weight derivation (regress dimensions on life expectancy, HPI-style).

Tract life expectancy is aggregated to ZCTA with a population-weighted crosswalk
(Census 2010 ZCTA<->tract relationship, POPPT = population in each ZCTA-tract part).

Caveats: 2010-2015 vintage; covers ~89% of tracts (no Maine/Wisconsin); 2010 tracts/ZCTAs
mapped onto 2020 ZCTAs (most codes unchanged). Output: lifeexp.parquet (zcta5, life_expectancy).
"""
from __future__ import annotations

import io

import pandas as pd

from . import config
from .common import assert_zcta, dev_filter, die, download_file, log, norm_zcta

OUT = config.PROCESSED / "lifeexp.parquet"


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("lifeexp", f"skip (exists): {OUT.name}")
        return str(OUT)

    le_path = config.RAW / "usaleep_US_A.csv"
    download_file(config.USALEEP_URL, le_path, min_bytes=500_000)
    le = pd.read_csv(le_path, dtype=str)
    cols = {c.lower(): c for c in le.columns}
    tcol = cols.get("tract id") or cols.get("full_ct_num")
    ecol = cols.get("e(0)") or cols.get("le") or cols.get("life expectancy")
    if not (tcol and ecol):
        die("lifeexp", f"USALEEP columns unexpected: {list(le.columns)}")
    le = le[[tcol, ecol]].rename(columns={tcol: "tract", ecol: "le"})
    le["tract"] = le["tract"].str.strip().str.zfill(11)  # restore stripped leading zero
    le["le"] = pd.to_numeric(le["le"], errors="coerce")
    le = le[le["tract"].str.match(r"^\d{11}$") & le["le"].notna()]

    rel_path = config.RAW / "zcta_tract_rel_10.txt"
    download_file(config.ZCTA_TRACT_REL, rel_path, min_bytes=1_000_000)
    rel = pd.read_csv(rel_path, dtype=str)
    rel["zcta5"] = norm_zcta(rel["ZCTA5"])
    rel["tract"] = rel["GEOID"].str.strip().str.zfill(11)
    rel["pop"] = pd.to_numeric(rel["POPPT"], errors="coerce").fillna(0.0)

    m = rel.merge(le, on="tract", how="inner")
    m = m[m["pop"] > 0].copy()
    # population-weighted mean life expectancy per ZCTA
    m["le_pop"] = m["le"] * m["pop"]
    agg = m.groupby("zcta5", as_index=False).agg(le_pop=("le_pop", "sum"), pop=("pop", "sum"))
    agg["life_expectancy"] = (agg["le_pop"] / agg["pop"]).round(1)
    out = agg[["zcta5", "life_expectancy"]].copy()
    out = dev_filter(out, dev_state)

    assert_zcta(out, stage="lifeexp")
    floor = 50 if dev_state else 20_000
    if len(out) < floor:
        die("lifeexp", f"only {len(out)} ZCTAs with life expectancy (expected >= {floor})")
    if not (out["life_expectancy"].between(60, 100).mean() > 0.95):
        die("lifeexp", "life expectancy values outside a plausible 60-100 range")
    out.to_parquet(OUT, index=False)
    log("lifeexp", f"wrote {OUT.name} ({len(out)} ZCTAs, "
                   f"median LE {out['life_expectancy'].median():.1f} yrs)")
    return str(OUT)


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

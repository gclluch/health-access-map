"""build_hpsa: HRSA primary-care HPSA designations -> a per-ZCTA shortage score.

NPPES counts provider *registrations*; HPSA encodes the thing a raw count cannot - an
official shortage designation that folds in high-need population, travel/distance to the
nearest source of care, and safety-net burden. Empirically it is near-orthogonal to our
E2SFCA provider density (corr ~0.05) yet correlates with INDEPENDENT mortality on its own
(clean signed-r +0.20; premature_death +0.28, life_exp +0.17), so it adds genuine marginal
signal to provider_supply rather than duplicating it (gate-tested - see docs/METHODOLOGY.md).

Mechanics (SUB-COUNTY): keep currently-Designated primary-care HPSAs and resolve each to the finest
geography HRSA gives - ~57% of designations carry a CENSUS TRACT component (11-digit GEOID), so a
tract gets the MAX "HPSA Score" (0-26, higher = worse shortage) of its designations; the remainder
(Single County / County Subdivision) fall back to a county-wide score. A non-designated tract reads
0, NOT its county's worst tract (that county-MAX broadcast over-assigned shortage and was ~0 within
county). Tracts are area-weighted to ZCTA via the shared Census 2020 crosswalk. This is a strict
improvement over the old county-MAX on every validation axis (e.g. national signed-r vs amenable
mortality 0.25 -> 0.49) AND adds real within-county resolution (0% -> ~10% of variance). Output:
hpsa.parquet (zcta5, hpsa_pc_score). See docs/SUBCOUNTY_PLAN.md for the prototype gate.

Mental-health / dental HPSA and the MUA/IMU index were gate-tested too: both are subsumed by
PC-HPSA (they add ~0 beyond it) and MUA is wrong-signed at ZCTA level, so only PC-HPSA ships.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from .common import assert_zcta, dev_filter, die, download_file, load_zcta_tract_xwalk, log

OUT = config.PROCESSED / "hpsa.parquet"


def resolve_zcta_scores(h: pd.DataFrame, xwalk: pd.DataFrame) -> pd.DataFrame:
    """Pure core (no I/O): designated PC-HPSA rows + the ZCTA<->tract crosswalk -> per-ZCTA score.
    Census-Tract components set a tract's score (max over designations); Single-County / County-
    Subdivision components set a county-WIDE fallback; a tract in neither reads 0 (NOT its county's
    worst tract - that broadcast is what made the old county-MAX wrong within county). Tracts are
    area-weighted up to their ZCTA. Returns [zcta5, hpsa_pc_score]."""
    h = h[h[config.HPSA_COL_STATUS].astype(str).str.strip() == "Designated"].copy()
    h["score"] = pd.to_numeric(h[config.HPSA_COL_SCORE], errors="coerce")
    h = h[h["score"].notna()]
    comp = h[config.HPSA_COL_COMPONENT].fillna("")

    ct = h[comp == "Census Tract"].copy()
    ct["tract"] = ct[config.HPSA_COL_GEOID].astype(str).str.strip().str.zfill(11)
    ct = ct[ct["tract"].str.match(r"^\d{11}$")]
    tract_score = ct.groupby("tract")["score"].max()

    cw = h[comp.isin(["Single County", "County Subdivision"])].copy()
    cw["fips"] = cw[config.HPSA_COL_FIPS].astype(str).str.zfill(5)
    cw = cw[cw["fips"].str.match(r"^\d{5}$")]
    countywide = cw.groupby("fips")["score"].max()

    xw = xwalk.rename(columns={
        "GEOID_ZCTA5_20": "zcta5", "GEOID_TRACT_20": "tract", "AREALAND_PART": "w"}).copy()
    xw["tract"] = xw["tract"].astype(str).str.zfill(11)
    xw["w"] = pd.to_numeric(xw["w"], errors="coerce").fillna(0.0)
    xw["score"] = xw["tract"].map(tract_score).fillna(xw["tract"].str[:5].map(countywide)).fillna(0.0)
    xw["sw"] = xw["score"] * xw["w"]
    agg = xw.groupby("zcta5").agg(sw=("sw", "sum"), w=("w", "sum")).reset_index()
    agg["hpsa_pc_score"] = np.where(agg["w"] > 0, agg["sw"] / agg["w"], 0.0)
    agg["zcta5"] = agg["zcta5"].astype(str)
    agg.attrs["n_tract"] = int(tract_score.index.size)
    agg.attrs["n_countywide"] = int(countywide.index.size)
    return agg[["zcta5", "hpsa_pc_score"]]


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("hpsa", f"skip (exists): {OUT.name}")
        return str(OUT)

    geo_path = config.PROCESSED / "geonames.parquet"
    if not geo_path.exists():
        die("hpsa", "missing geonames.parquet; run build_geonames first (need the ZCTA universe)")
    geo = pd.read_parquet(geo_path)[["zcta5"]].drop_duplicates().copy()
    geo["zcta5"] = geo["zcta5"].astype(str)

    raw = config.RAW / "hrsa_hpsa_pc.csv"
    download_file(config.HPSA_PC_URL, raw, min_bytes=5_000_000)
    h = pd.read_csv(raw, dtype=str, low_memory=False)
    for c in (config.HPSA_COL_SCORE, config.HPSA_COL_FIPS, config.HPSA_COL_STATUS,
              config.HPSA_COL_COMPONENT, config.HPSA_COL_GEOID):
        if c not in h.columns:
            die("hpsa", f"HPSA file missing expected column {c!r}: {list(h.columns)[:8]}...")

    agg = resolve_zcta_scores(h, load_zcta_tract_xwalk())
    log("hpsa", f"{agg.attrs['n_tract']} tract + {agg.attrs['n_countywide']} county-wide PC-HPSA "
                f"geographies -> {int((agg['hpsa_pc_score'] > 0).sum())} ZCTAs with a shortage score")

    out = geo.merge(agg, on="zcta5", how="left")
    out["hpsa_pc_score"] = out["hpsa_pc_score"].fillna(0.0)  # not in a designated shortage = 0
    out = dev_filter(out, dev_state)

    assert_zcta(out, stage="hpsa")
    floor = 50 if dev_state else 20_000
    if len(out) < floor:
        die("hpsa", f"only {len(out)} ZCTAs (expected >= {floor})")
    if not out["hpsa_pc_score"].between(0, 30).all():
        die("hpsa", "hpsa_pc_score outside the plausible 0-30 HPSA range")
    out.to_parquet(OUT, index=False)
    shortage = int((out["hpsa_pc_score"] > 0).sum())
    log("hpsa", f"wrote {OUT.name} ({len(out)} ZCTAs, {shortage} in a PC-shortage county, "
                f"median score among those {out.loc[out.hpsa_pc_score>0,'hpsa_pc_score'].median():.0f})")
    return str(OUT)


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

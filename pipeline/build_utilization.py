"""build_utilization: CMS Medicare Geographic Variation PUF -> realized-access per ZCTA.

Layer C1 of the access-signal roadmap. NPPES counts provider *registrations*, not whether
people can actually get care. This stage adds *realized* routine-care access - the share of
Original-Medicare (FFS) beneficiaries who actually saw a clinician (E&M), got lab tests, or
had an outpatient visit - at the county level, mapped to ZCTA via geonames' county FIPS.
Higher use = better access (a barrier when low).

Non-circular with the 6 validation outcomes: deliberately excludes ED / readmission /
inpatient (those relate to the ACSC preventable-hospitalization outcome) and flu / mammography
(themselves outcomes). Caveat: the Medicare 65+/disabled FFS population is an *area proxy* for
realized access (the Dartmouth-Atlas tradition), not an all-ages measure.
"""
from __future__ import annotations

import pandas as pd

from . import config
from .common import assert_zcta, dev_filter, die, download_file, log, write_provenance

OUT = config.PROCESSED / "utilization.parquet"


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("utilization", f"skip (exists): {OUT.name}")
        return str(OUT)

    dest = config.RAW / "cms_gv_puf.csv"
    download_file(config.UTILIZATION_URL, dest, min_bytes=20_000_000, force=force)
    keep = ["YEAR", "BENE_GEO_LVL", "BENE_AGE_LVL", "BENE_GEO_CD", *config.UTILIZATION_MEASURES]
    raw = pd.read_csv(dest, usecols=keep, dtype=str)

    cty = raw[(raw["BENE_GEO_LVL"] == "County") & (raw["BENE_AGE_LVL"] == "All")].copy()
    cty["YEAR"] = pd.to_numeric(cty["YEAR"], errors="coerce")
    latest = int(cty["YEAR"].max())
    cty = cty[cty["YEAR"] == latest]
    cty["county_fips"] = cty["BENE_GEO_CD"].str.strip().str.zfill(5)
    for src, dst in config.UTILIZATION_MEASURES.items():
        cty[dst] = pd.to_numeric(cty[src].replace("*", pd.NA), errors="coerce")
    cty = cty[["county_fips", *config.UTILIZATION_MEASURES.values()]].drop_duplicates("county_fips")
    if len(cty) < 2000:
        die("utilization", f"only {len(cty)} counties with data (expected ~3000)")

    geon = pd.read_parquet(config.PROCESSED / "geonames.parquet")[["zcta5", "county_fips"]]
    geon["county_fips"] = geon["county_fips"].astype("string").str.zfill(5)
    out = geon.merge(cty, on="county_fips", how="left").drop(columns=["county_fips"])
    out = dev_filter(out, dev_state)
    _validate(out)
    out.to_parquet(OUT, index=False)

    cov = float(out["em_visit_rate"].notna().mean())
    write_provenance({"utilization": {
        "source": "CMS Medicare Geographic Variation PUF (Original Medicare FFS)",
        "year": latest,
        "level": "county -> ZCTA via geonames county_fips",
        "measures": list(config.UTILIZATION_MEASURES.values()),
        "counties": int(len(cty)),
        "zcta_coverage": round(cov, 3),
        "caveat": "Medicare 65+/disabled FFS population; area proxy for realized access",
    }})
    log("utilization", f"wrote {OUT.name} ({len(out)} zctas; year {latest}; "
                       f"{cov:.0%} have utilization; "
                       f"median E&M-visit rate {out['em_visit_rate'].median():.1%})")
    return str(OUT)


def _validate(df: pd.DataFrame) -> None:
    assert_zcta(df, stage="utilization")
    for c in config.UTILIZATION_MEASURES.values():
        v = df[c].dropna()
        if len(v) and (v.min() < 0 or v.max() > 1):
            die("utilization", f"{c} must be a fraction [0,1], got [{v.min()}, {v.max()}]")


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

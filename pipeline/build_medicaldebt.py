"""build_medicaldebt: Urban Institute county medical-debt-in-collections -> per-ZCTA.

The AFFORDABILITY barrier the uninsured rate misses: the share of people with medical debt
in collections (deidentified credit-bureau panel). It captures the UNDER-insured / cost-burden
population - a genuine *cause* of care avoidance ("I won't go, I can't pay the bill"), not a
mediator/outcome. Empirically it is the first new scored barrier to survive partial-r in the
whole access-signal program: clean signed-r +0.48 vs independent mortality/ACSC, and +0.27
PARTIAL controlling for need + vulnerability + the rest of care_access (corr ~0.4 with poverty
but NOT subsumed by it). County-level (mapped county->ZCTA via geonames; no sub-county
resolution, like HPSA). Free GitHub CSV. See docs/DECISIONS.md + VALIDATION.md.
"""
from __future__ import annotations

import pandas as pd

from . import config
from .common import assert_zcta, dev_filter, die, download_file, log

OUT = config.PROCESSED / "medicaldebt.parquet"


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("medicaldebt", f"skip (exists): {OUT.name}")
        return str(OUT)

    geo_path = config.PROCESSED / "geonames.parquet"
    if not geo_path.exists():
        die("medicaldebt", "missing geonames.parquet; run build_geonames first (need ZCTA->county)")
    geo = pd.read_parquet(geo_path)[["zcta5", "county_fips"]].copy()
    geo["fips"] = geo["county_fips"].astype(str).str.zfill(5)

    raw = config.RAW / "urban_medical_debt.csv"
    download_file(config.MEDICAL_DEBT_URL, raw, min_bytes=100_000)
    h = pd.read_csv(raw, dtype=str)
    for c in (config.MEDICAL_DEBT_COL_FIPS, config.MEDICAL_DEBT_COL_SHARE):
        if c not in h.columns:
            die("medicaldebt", f"medical-debt file missing column {c!r}: {list(h.columns)[:6]}...")
    h["fips"] = h[config.MEDICAL_DEBT_COL_FIPS].astype(str).str.zfill(5)
    h["medical_debt"] = pd.to_numeric(h[config.MEDICAL_DEBT_COL_SHARE], errors="coerce")
    cty = h.loc[h["fips"].str.match(r"^\d{5}$"), ["fips", "medical_debt"]] \
           .dropna(subset=["medical_debt"]).drop_duplicates("fips")
    log("medicaldebt", f"{len(cty)} counties with a medical-debt share")

    out = geo.merge(cty, on="fips", how="left")[["zcta5", "medical_debt"]].copy()
    out = dev_filter(out, dev_state)

    assert_zcta(out, stage="medicaldebt")
    cov = int(out["medical_debt"].notna().sum())
    floor = 50 if dev_state else 20_000
    if cov < floor:
        die("medicaldebt", f"only {cov} ZCTAs with medical-debt (expected >= {floor})")
    if not out["medical_debt"].dropna().between(0, 1).all():
        die("medicaldebt", "medical_debt outside the [0,1] share range")
    out.to_parquet(OUT, index=False)
    log("medicaldebt", f"wrote {OUT.name} ({len(out)} ZCTAs, {cov} with a value, "
                       f"median {out['medical_debt'].median():.3f})")
    return str(OUT)


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

"""build_outcomes: independent, access-sensitive health OUTCOMES at county level,
crosswalked to ZCTA - for validating the Access Gap composite (never in the composite).

Why this stage exists: the project's only outcome was all-cause life expectancy
(USALEEP), which is dominated by disease/need - so regressing the composite on it
crushes the care-access weight to ~0 (see docs/VALIDATION.md). Area-level
all-cause mortality is a *need* outcome, not an *access* outcome. The access literature
validates against outcomes that good ambulatory care should prevent:

  - Preventable Hospital Stays (ACSC / AHRQ PQI) - the textbook ambulatory-access proxy
  - Premature death (YPLL) - broad mortality burden
  - Infant mortality - the natural validator for maternity (OB-GYN) supply
  - (optional) amenable/treatable mortality - the IHME HAQ gold standard, manual import

Source: County Health Rankings national analytic data (county-level, administrative -
Medicare claims + NCHS vital records, fully independent of CDC PLACES/BRFSS). Values are
county-level; each ZCTA inherits its dominant county's value (display + county-level
validation only - never re-ranked at ZCTA resolution). Optional/non-blocking like fqhc.

Output: outcomes.parquet (zcta5, preventable_hosp, premature_death, infant_mortality[,
amenable_mortality]). All oriented higher = worse, matching the gap scores.
"""
from __future__ import annotations

import pandas as pd

from . import config
from .common import assert_zcta, dev_filter, die, download_file, log

OUT = config.PROCESSED / "outcomes.parquet"

# County Health Rankings 2025 national analytic data (county rows + US/state totals).
# Row 0 = human-readable headers, row 1 = machine codes (skipped), data from row 2.
CHR_URL = ("https://www.countyhealthrankings.org/sites/default/files/media/document/"
           "analytic_data2025_v3.csv")
CHR_RAW = config.RAW / "chr_analytic_2025.csv"

# Resolve columns by case-insensitive label substring (survives minor year-to-year drift,
# matching the project's resolve-at-runtime philosophy). Each maps to an output column.
# Distal mortality/hospitalization outcomes (higher = worse) + proximal process/utilization
# outcomes (higher = better; closer to access in the causal chain, so care access can earn
# more weight against them). Orientation is applied in validate.py, not here.
CHR_MEASURES = {
    "preventable_hosp": "preventable hospital stays raw value",
    "premature_death": "premature death raw value",
    "infant_mortality": "infant mortality raw value",
    "flu_vaccination": "flu vaccinations raw value",          # Medicare; proximal (higher=better)
    "mammography": "mammography screening raw value",          # Medicare; proximal (higher=better)
}
FIPS_LABEL = "5-digit fips code"

# Optional manual gold-standard import: amenable/treatable mortality by county.
# Drop a CSV at this path with columns county_fips (5-digit) + amenable_mortality (rate).
# Not auto-downloaded (CDC WONDER has no clean public county API).
AMENABLE_RAW = config.RAW / "amenable_mortality_county.csv"


def _resolve(cols: list[str], needle: str, *, required: bool) -> str | None:
    matches = [c for c in cols if needle in c.strip().lower()]
    if not matches:
        if required:
            die("outcomes", f"CHR column not found for '{needle}'")
        return None
    return matches[0]


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("outcomes", f"skip (exists): {OUT.name}")
        return str(OUT)

    geo_path = config.PROCESSED / "geonames.parquet"
    if not geo_path.exists():
        die("outcomes", f"missing {geo_path.name}; run build_geonames first")
    geo = pd.read_parquet(geo_path)[["zcta5", "county_fips"]].copy()
    geo["zcta5"] = geo["zcta5"].astype("string")
    geo["county_fips"] = geo["county_fips"].astype("string").str.zfill(5)

    download_file(CHR_URL, CHR_RAW, min_bytes=1_000_000)
    chr_df = pd.read_csv(CHR_RAW, dtype=str, skiprows=[1], encoding="utf-8-sig")
    cols = list(chr_df.columns)
    fips_col = _resolve(cols, FIPS_LABEL, required=True)
    chr_df["county_fips"] = chr_df[fips_col].astype("string").str.strip().str.zfill(5)
    # county rows only: drop US (00000) and state totals (fips ending in 000)
    chr_df = chr_df[chr_df["county_fips"].str.match(r"^\d{5}$") & ~chr_df["county_fips"].str.endswith("000")]

    keep = {"county_fips": chr_df["county_fips"]}
    found = []
    for out_col, needle in CHR_MEASURES.items():
        src = _resolve(cols, needle, required=False)
        if src is None:
            log("outcomes", f"CHR measure absent, skipping: {out_col}")
            continue
        keep[out_col] = pd.to_numeric(chr_df[src], errors="coerce")
        found.append(out_col)
    if not found:
        die("outcomes", "no CHR outcome measures resolved; check the analytic-data schema")
    county = pd.DataFrame(keep).drop_duplicates("county_fips")

    # optional manual amenable-mortality import (non-blocking)
    if AMENABLE_RAW.exists():
        am = pd.read_csv(AMENABLE_RAW, dtype=str)
        am.columns = [c.strip().lower() for c in am.columns]
        fcol = next((c for c in am.columns if "fips" in c), None)
        vcol = next((c for c in am.columns if "amenable" in c or "treatable" in c), None)
        if fcol and vcol:
            am["county_fips"] = am[fcol].astype("string").str.strip().str.zfill(5)
            am["amenable_mortality"] = pd.to_numeric(am[vcol], errors="coerce")
            county = county.merge(am[["county_fips", "amenable_mortality"]], on="county_fips", how="left")
            found.append("amenable_mortality")
            log("outcomes", f"merged manual amenable mortality ({am['amenable_mortality'].notna().sum()} counties)")
        else:
            log("outcomes", f"amenable CSV present but columns unrecognized: {list(am.columns)}")

    out = geo.merge(county, on="county_fips", how="left")[["zcta5", *found]].copy()
    out = dev_filter(out, dev_state)

    assert_zcta(out, stage="outcomes")
    covered = {c: int(out[c].notna().sum()) for c in found}
    if out[found].notna().any(axis=1).sum() < (50 if dev_state else 20_000):
        die("outcomes", f"too few ZCTAs with any outcome: {covered}")
    out.to_parquet(OUT, index=False)
    log("outcomes", f"wrote {OUT.name} ({len(out)} ZCTAs); non-null per outcome: {covered}")
    return str(OUT)


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

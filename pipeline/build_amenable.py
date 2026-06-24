"""build_amenable: treatable (amenable) mortality by county -> the access-validation
gold standard (IHME HAQ concept). Produces `amenable_mortality_county.csv`, which
`build_outcomes.py` already auto-merges as the `amenable_mortality` anchor.

WHY: all-cause life expectancy is a *need* outcome (disease dominates), so it starves
the care-access weight by construction (docs/VALIDATION.md). Amenable/
treatable mortality - deaths timely effective care should prevent (Nolte-McKee ->
OECD/Eurostat 2019 list) - is the outcome the access literature validates against,
and is the frontier outcome for the Phase-4 frontier-gap construct.

DATA-ACCESS REALITY (researched 2026-06-23): there is NO free pre-built county
treatable-mortality file. CDC WONDER's documented XML API returns NATIONAL data only
(it rejects county/state grouping); county data comes only from the interactive web
tool behind a data-use agreement. So this stage CONSUMES a manual WONDER export rather
than auto-downloading it. The OECD treatable ICD-10 list is encoded below so the export
is a 10-minute, fully-specified pull.

EXPECTED-IMPACT NOTE: the sub-county validation (docs/VALIDATION.md) found
care_access stays modest (+0.31) even against a sub-county, risk-adjusted, access-
sensitive outcome (NY PQI), with health_need dominating. So an access-sensitive *county*
outcome is unlikely to flip the care_access hierarchy. Amenable mortality's primary value
is therefore (a) a cleaner-than-LE validation anchor and (b) the frontier-gap outcome -
not a care_access rescue.

------------------------------------------------------------------------------------
WONDER RECIPE (Underlying Cause of Death, 1999-2020 or 2018-2021 single-race):
  https://wonder.cdc.gov/ucd-icd10.html
  1. Group Results By: County (and optionally Census Region for sanity).
  2. Demographics -> Age: select 0-4 ... 70-74 only (the OECD 0-74 amenable window).
  3. ICD-10 Codes: paste the TREATABLE_ICD10 set below (use the code search to add each).
  4. Other options: check "Age-Adjusted Rates"; years = pool 2016-2020 (or 2013-2022) to
     clear the <10-death suppression in small counties.
  5. Export. Save the tab-delimited result to data/raw/wonder_amenable_county.txt, then:
        python -m pipeline.build_amenable
  Suppressed/Unreliable rows (counts 1-9 / <20) are dropped; a rural tail will remain
  missing - that is honest (do NOT zero-fill), and validation is county-level only.
------------------------------------------------------------------------------------
"""
from __future__ import annotations

import re

import pandas as pd

from . import config
from .common import die, log

# WONDER export (tab-delimited) the user drops in. (No auto-download - see module docstring.)
WONDER_RAW = config.RAW / "wonder_amenable_county.txt"
# The CSV build_outcomes.py auto-merges (cols: county_fips, amenable_mortality).
OUT_CSV = config.RAW / "amenable_mortality_county.csv"

# OECD/Eurostat 2019 (rev. 2022) TREATABLE causes, ICD-10, applied to ages 0-74.
# Transcribed from the OECD list / JAMA 2025 (Hill et al.) eTable 2 WONDER mapping.
# Causes split 50/50 with the preventable list are still included whole here (WONDER cannot
# apply a 50% weight at query time); this slightly broadens the set - documented, not silent.
TREATABLE_ICD10 = [
    # Infectious
    "A15-A19", "B90", "J65",
    # Cancers (treatable)
    "C18-C21", "C50", "C53", "C54", "C55", "C62", "C73", "C81", "C91.0", "C91.1", "D10-D36",
    # Endocrine / metabolic
    "E00-E07", "E10-E14", "E24", "E25", "E27",
    # Nervous
    "G40", "G41",
    # Circulatory (treatable)
    "I00-I09", "I10-I13", "I15", "I20-I25", "I26", "I60-I69", "I70", "I71", "I73.9",
    "I80", "I82.9",
    # Respiratory
    "J00-J06", "J12", "J15", "J16-J18", "J20-J22", "J30-J39", "J45-J47", "J80", "J81",
    "J85", "J86", "J90", "J93", "J94",
    # Digestive
    "K25-K28", "K35-K38", "K40-K46", "K80", "K81", "K82", "K83", "K85", "K86",
    # Genitourinary
    "N00-N07", "N13", "N17-N19", "N20", "N21", "N23", "N25", "N26", "N27", "N34.1",
    "N35", "N40", "N70-N73", "N75.0", "N75.1", "N76.4", "N76.6",
    # Maternal / perinatal
    "O00-O99", "P00-P96",
    # Congenital
    "Q20-Q28",
    # Adverse effects of medical & surgical care
    "Y40-Y59", "Y60-Y69", "Y70-Y82", "Y83", "Y84",
]


def _parse_wonder(path) -> pd.DataFrame:
    """Parse a WONDER UCD tab-delimited county export into (county_fips, amenable_mortality).

    WONDER exports: 'County', 'County Code' (5-digit FIPS), 'Deaths', 'Population',
    'Crude Rate', 'Age Adjusted Rate'. Footer 'Notes' rows and Suppressed/Unreliable/
    Missing values are dropped. Prefers the age-adjusted rate (de-confounds age mix)."""
    df = pd.read_csv(path, sep="\t", dtype=str)
    df.columns = [c.strip() for c in df.columns]
    fips_col = next((c for c in df.columns if re.search(r"county code", c, re.I)), None)
    rate_col = next((c for c in df.columns if re.search(r"age.?adjusted rate", c, re.I)), None)
    if rate_col is None:  # fall back to crude rate if age-adjusted wasn't requested
        rate_col = next((c for c in df.columns if re.search(r"crude rate", c, re.I)), None)
    if not fips_col or not rate_col:
        die("amenable", f"WONDER export missing County Code / rate columns: {list(df.columns)}")
    df = df[df[fips_col].astype(str).str.match(r"^\d{5}$", na=False)].copy()
    df["county_fips"] = df[fips_col].str.zfill(5)
    df["amenable_mortality"] = pd.to_numeric(
        df[rate_col].str.replace(r"[^0-9.]", "", regex=True), errors="coerce")
    df = df.dropna(subset=["amenable_mortality"]).drop_duplicates("county_fips")
    return df[["county_fips", "amenable_mortality"]]


def build(dev_state: str | None = None, force: bool = False) -> str:
    if not WONDER_RAW.exists():
        log("amenable", f"no WONDER export at {WONDER_RAW.name}; skipping (see module recipe). "
                        f"The {len(TREATABLE_ICD10)}-code treatable ICD-10 set is encoded here.")
        return ""
    out = _parse_wonder(WONDER_RAW)
    if len(out) < 500:
        die("amenable", f"only {len(out)} counties parsed; check the export / suppression")
    out.to_csv(OUT_CSV, index=False)
    log("amenable", f"wrote {OUT_CSV.name} ({len(out)} counties). Re-run build_outcomes + "
                    f"validate to pick up the amenable_mortality anchor.")
    return str(OUT_CSV)


if __name__ == "__main__":
    build()

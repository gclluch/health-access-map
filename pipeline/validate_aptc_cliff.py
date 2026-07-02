"""validate_aptc_cliff: first stage of the APTC-cliff natural experiment.

The ACA enhanced premium tax credits (APTC) expired at the end of 2025, so the 2026 Open
Enrollment Period is the first priced without them - a large, plausibly exogenous affordability
shock whose intensity varies by ZIP with the 2025 APTC share. CMS publishes ZIP-level OEP public
use files (plan selections, APTC consumers) for HealthCare.gov-platform states. This script builds
the FIRST STAGE of that natural experiment: did enrollment fall more where the subsidy exposure
(2025 APTC share) was higher, and how does the drop line up with the index?

This is a first stage only, NOT an outcome study: the outcome data (ACSC hospitalizations,
amenable mortality) for 2026 will not exist for years. What can be established now is
  (a) the national distribution of the 2025->2026 ZIP enrollment change;
  (b) the dose-response of the drop on 2025 APTC share (the instrument's relevance);
  (c) how the drop correlates with access_gap_score and its components;
  (d) whether (c) survives county fixed effects (within-county residualization).

Data notes, all verified against the 2026 PUF definitions/FAQ documents:
  * HealthCare.gov (FFM + SBE-FP) states ONLY - state-based exchanges (CA, NY, ...) publish no
    ZIP file. Illinois moved to its own SBE for plan year 2026, so its ZIPs exist in the 2025
    file but not the 2026 file; requiring presence in BOTH years drops platform switchers.
  * Suppression: cells with values 1-10 are shown as "*", with complementary suppression where
    needed. Suppressed cells are DROPPED, never imputed. This right-censors the very largest
    relative drops (a ZIP falling from ~20 to <11 consumers suppresses), which attenuates the
    first stage - conservative.
  * 2025 Cnsmr is as of the end of the 2025 OEP (Jan 15, 2025); 2026 Cnsmr as of Jan 15, 2026.
  * ZIP is treated as ZCTA for the metrics join (the project's standard ZIP~ZCTA caveat: a few
    percent of ZIPs are PO-box/point ZIPs with no ZCTA twin and simply fail the join).

Read-only against the index; never feeds the composite. Writes the per-ZIP first-stage frame to
data/processed/aptc_cliff_zip.parquet for use as a map layer / future event-study baseline.

    python -m pipeline.validate_aptc_cliff
"""
from __future__ import annotations

import zipfile

import httpx
import numpy as np
import pandas as pd

from . import config
from .common import log, norm_zcta
from .validation_stats import pearson_corr, weighted_corr, within_residual
from .zip_states import zip3_to_state

PUF_URLS = {
    2025: "https://www.cms.gov/files/zip/2025-oep-zip-code-level-public-use-file.zip",
    2026: "https://www.cms.gov/files/zip/2026-oep-zip-code-level-public-use-file.zip",
}
RAW_PATHS = {y: config.RAW / f"oep_zip_{y}.zip" for y in PUF_URLS}
METRICS = config.PROCESSED / "metrics.parquet"
OUT = config.PROCESSED / "aptc_cliff_zip.parquet"

MIN_CNSMR = 25       # 2025 plan selections below this make % change too noisy to interpret
MIN_COUNTY_ZCTAS = 3  # within-county correlation needs >=3 ZCTAs per county
INDEX_COLS = (
    "access_gap_score",
    "insurance_pctile",
    "medical_debt_pctile",
    "health_need_pctile",
    "social_vulnerability_pctile",
    "care_access_pctile",
)


def _fetch_puf(year: int) -> None:
    """Cache the CMS ZIP-level PUF. CMS 403s the default pipeline UA, so use a browser one."""
    dest = RAW_PATHS[year]
    if dest.exists() and dest.stat().st_size > 100_000:
        log("aptc_cliff", f"cached: {dest.name}")
        return
    log("aptc_cliff", f"GET {PUF_URLS[year]}")
    r = httpx.get(PUF_URLS[year], follow_redirects=True, timeout=120,
                  headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    r.raise_for_status()
    dest.write_bytes(r.content)


def _load_puf(year: int) -> pd.DataFrame:
    """Parse the ZIP-level PUF CSV: zip, Cnsmr, APTC_Cnsmr. '*' = suppressed (1-10) -> NaN."""
    with zipfile.ZipFile(RAW_PATHS[year]) as zf:
        csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(csv_name) as f:
            df = pd.read_csv(f, dtype={"zip": str}, thousands=",", na_values=["*"])
    df["zcta5"] = norm_zcta(df["zip"])
    out = df[["zcta5"]].copy()
    out[f"cnsmr_{year}"] = pd.to_numeric(df["Cnsmr"], errors="coerce")
    out[f"aptc_cnsmr_{year}"] = pd.to_numeric(df["APTC_Cnsmr"], errors="coerce")
    n_sup = out[f"cnsmr_{year}"].isna().sum()
    log("aptc_cliff", f"{year}: {len(out):,} ZIPs, {n_sup:,} with total selections suppressed")
    return out


def build_first_stage() -> pd.DataFrame:
    """Per-ZIP frame: selections both years, % change, 2025 APTC share, joined to the index."""
    p25, p26 = _load_puf(2025), _load_puf(2026)
    df = p25.merge(p26, on="zcta5", how="outer", indicator=True)

    # Presence-in-both-years requirement drops platform switchers (IL -> SBE for 2026) and
    # fully-suppressed/vanished ZIPs. Report the censoring honestly before dropping.
    only25 = df["_merge"] == "left_only"
    log("aptc_cliff", f"ZIPs in 2025 only: {only25.sum():,} "
        f"(states: {sorted(set(df.loc[only25, 'zcta5'].map(zip3_to_state).dropna()))})")
    log("aptc_cliff", f"ZIPs in 2026 only: {(df['_merge'] == 'right_only').sum():,}")

    both = df["_merge"] == "both"
    unsup = df["cnsmr_2025"].notna() & df["cnsmr_2026"].notna()
    log("aptc_cliff", f"suppression-censored (in both files, a year suppressed): "
        f"{(both & ~unsup).sum():,} ZIPs - dropped, not imputed; censors the largest drops")
    df = df[both & unsup & (df["cnsmr_2025"] >= MIN_CNSMR)].drop(columns="_merge").copy()

    df["pct_change"] = 100.0 * (df["cnsmr_2026"] - df["cnsmr_2025"]) / df["cnsmr_2025"]
    # Dose: share of 2025 consumers receiving APTC. NaN where the APTC cell is suppressed.
    df["aptc_share_2025"] = df["aptc_cnsmr_2025"] / df["cnsmr_2025"]
    df["state"] = df["zcta5"].map(zip3_to_state)
    log("aptc_cliff", f"analyzable ZIPs (both years unsuppressed, 2025 Cnsmr>={MIN_CNSMR}): "
        f"{len(df):,} across {df['state'].nunique()} states")

    m = pd.read_parquet(METRICS, columns=["zcta5", "county_fips", "population", "scoreable",
                                          *INDEX_COLS])
    m = m[m["scoreable"] == True].drop(columns="scoreable")  # noqa: E712
    joined = df.merge(m, on="zcta5", how="left")
    log("aptc_cliff", f"metrics join (ZIP~ZCTA): {joined['access_gap_score'].notna().sum():,} of "
        f"{len(joined):,} matched a scoreable ZCTA")
    return joined


def report(df: pd.DataFrame) -> None:
    ch, w = df["pct_change"].to_numpy(), df["cnsmr_2025"].to_numpy()

    log("aptc_cliff", "--- (a) national 2025->2026 enrollment change, % per ZIP ---")
    q = np.percentile(ch, [10, 50, 90])
    log("aptc_cliff", f"mean {ch.mean():+.1f}%  median {q[1]:+.1f}%  p10 {q[0]:+.1f}%  "
        f"p90 {q[2]:+.1f}%  (n={len(ch):,})")
    tot25, tot26 = df["cnsmr_2025"].sum(), df["cnsmr_2026"].sum()
    log("aptc_cliff", f"aggregate selections {tot25:,.0f} -> {tot26:,.0f} "
        f"({100 * (tot26 - tot25) / tot25:+.1f}%)")

    log("aptc_cliff", "--- (b) dose-response first stage: change vs 2025 APTC share ---")
    dose = df["aptc_share_2025"].to_numpy()
    log("aptc_cliff", f"corr(pct_change, aptc_share_2025) = {pearson_corr(ch, dose):+.3f}  "
        f"(weighted {weighted_corr(ch, dose, w):+.3f}); expected NEGATIVE - bigger drops where "
        f"APTC exposure was higher")
    hi, lo = dose >= np.nanmedian(dose), dose < np.nanmedian(dose)
    log("aptc_cliff", f"mean change: high-APTC-share half {ch[hi].mean():+.1f}% vs "
        f"low half {ch[lo].mean():+.1f}%")

    log("aptc_cliff", "--- (c) change vs the index (cross-sectional) ---")
    for col in INDEX_COLS:
        x = df[col].to_numpy(dtype=float)
        log("aptc_cliff", f"corr(pct_change, {col:<28s}) = {pearson_corr(ch, x):+.3f}  "
            f"(weighted {weighted_corr(ch, x, w):+.3f})")

    log("aptc_cliff", f"--- (d) within-county (counties with >={MIN_COUNTY_ZCTAS} ZCTAs) ---")
    d = df[df["county_fips"].notna()].copy()
    d = d[d.groupby("county_fips")["zcta5"].transform("count") >= MIN_COUNTY_ZCTAS]
    rc = within_residual(d, "pct_change")
    rg = within_residual(d, "access_gap_score")
    log("aptc_cliff", f"within-county corr(pct_change, access_gap_score) = "
        f"{pearson_corr(rc, rg):+.3f}  (n={len(d):,} ZCTAs, "
        f"{d['county_fips'].nunique():,} counties)")
    rd = within_residual(d, "aptc_share_2025")
    log("aptc_cliff", f"within-county corr(pct_change, aptc_share_2025)  = "
        f"{pearson_corr(rc, rd):+.3f}")


def main() -> None:
    for year in PUF_URLS:
        _fetch_puf(year)
    df = build_first_stage()
    report(df)
    df.to_parquet(OUT, index=False)
    log("aptc_cliff", f"wrote {OUT} ({len(df):,} rows)")


if __name__ == "__main__":
    main()

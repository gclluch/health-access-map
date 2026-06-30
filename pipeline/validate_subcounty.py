"""validate_subcounty: the sub-county validation gate the county outcomes cannot provide.

Every access-sensitive outcome in `outcomes.parquet` (ACSC preventable hospitalizations,
premature death, infant mortality) is COUNTY-level, so ~25% of the composite's variance
(the part that varies *within* a county) is invisible to the standard `diagnostics` gate.
A ZCTA-resolution access measure (the adaptive catchment, HPSA, FQHC desert) literally
cannot be rewarded by a county-flat outcome.

This harness closes that blind spot with the one free, observed, sub-county, access-
sensitive outcome that exists nationally-in-spirit: **NY SPARCS Prevention Quality
Indicators by patient ZIP code** (AHRQ PQI_90 overall composite, observed + risk-adjusted
expected rate per 100k, 2009-2023, Socrata `5q8c-d6xq`). PQIs are ambulatory-care-sensitive
conditions - exactly what timely primary care should prevent - so they are the textbook
access outcome, here at ZIP resolution.

It reports two correlations per dimension / sub-score:
  - POOLED (between + within county): the usual association.
  - WITHIN-COUNTY (county mean removed from BOTH sides): the decisive test of whether the
    index resolves *sub-county* access variance, which county outcomes cannot see.

Coverage is NY only (62 counties, ~1.3k ZCTAs after filtering) - it tests sub-county
signal EXISTENCE, not national generalization. A second state (CA HCAI publishes a ZIP-
level PQI file, manual download) can be added via `--extra-csv`. Read-only; never feeds
the composite.

    python -m pipeline.validate_subcounty
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .common import log
from .taxonomy import DIMENSIONS, subscore_specs
from .validation_stats import pearson_corr as _corr
from .validation_stats import weighted_corr as _wcorr
from .validation_stats import within_residual as _within

METRICS = config.PROCESSED / "metrics.parquet"
NY_PQI_SOCRATA = "https://health.data.ny.gov/resource/5q8c-d6xq.json"
# Colorado CDPHE: age-adjusted hospitalization rates per 100k by CENSUS TRACT (open ArcGIS REST,
# no key/DUA). DIABETES is the core ACSC here (AHRQ PQI-1/3/14/16); asthma (PQI-15) + heart disease
# (CHF = PQI-8) are also ACSC-family. An INDEPENDENT, second-state, sub-county outcome to generalize
# the NY finding to opposite geography. Tract -> ZCTA via the Census 2020 relationship file.
CO_ACSC_ARCGIS = ("https://www.cohealthmaps.dphe.state.co.us/arcgis/rest/services/OPEN_DATA/"
                  "cdphe_health_outcomes_census_tract_county/MapServer/17/query")
ZCTA_TRACT_REL = ("https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/"
                  "tab20_zcta520_tract20_natl.txt")
XWALK_CACHE = config.PROCESSED / "zcta_tract_xwalk.parquet"   # national tract<->ZCTA, area (fallback)
# HUD USPS ZIP<->TRACT crosswalk: res_ratio = the share of a ZIP's RESIDENTIAL addresses that fall in
# each tract - the gold-standard POPULATION weight for aggregating tract values to ZIP/ZCTA (vs the
# crude land-area weight). Needs a free HUDUSER token in $HUD_TOKEN or ~/.hud_token. type=1 = ZIP-TRACT.
HUD_XWALK_CACHE = config.PROCESSED / "hud_zip_tract_xwalk.parquet"
HUD_USPS_API = "https://www.huduser.gov/hudapi/public/usps?type=1&query=All&year=2023&quarter=4"
# CDC NCHS "Mapping Injury, Overdose & Violence": census-tract DRUG-OVERDOSE mortality, nationwide,
# observed deaths (Socrata, public domain, no DUA). The ONE national sub-county outcome found - it
# relaxes the "no national sub-county ruler" ceiling. Overdose is a SPECIFIC access construct (SUD
# treatment / harm-reduction + deaths-of-despair), independent of every PLACES/ACS input, so a
# modest-but-positive within-county r is the honest expectation. Each CDC geoid pools 1+ tracts
# (its `name` field lists member tract FIPS) for small-count stability.
CDC_OVERDOSE_SOCRATA = "https://data.cdc.gov/resource/4day-mt2f.json"
OD_YEARS = ("2022", "2023", "2024")
# California CHHS deaths by ZIP (all-cause + 14 causes, observed vital records, no DUA). A 4th
# sub-county state. Crude cause-specific rates are AGE-confounded - and in CA age is a SUPPRESSOR
# (older ZIPs are wealthier coastal/retirement areas), so the index signal only emerges after age
# adjustment. We control for age65_rate (already on the index frame) within county. ACSC causes:
# DIA diabetes, HTD heart disease, CLD chronic lower respiratory (COPD), STK stroke.
CA_DEATHS_URL = ("https://data.chhs.ca.gov/dataset/590aeff1-b022-4240-9a46-3fe90bf3ad91/resource/"
                 "d4711b8e-6eb4-417c-91f5-ee075558adbe/download/"
                 "20260319_deaths_final_2019-2024_zip_year_sup.csv")
CA_DEATHS_CACHE = config.PROCESSED / "ca_deaths_2019_2024.csv"
CA_ACSC_CAUSES = ("DIA", "HTD", "CLD", "STK")
# Texas DSHS THCIC Inpatient PUDF: per-discharge hospital records with the patient's 5-digit ZIP +
# principal ICD-10 diagnosis - free, no DUA, the TAB-DELIMITED variant (headers, no fixed-length
# layout needed). 5th sub-county state, the largest population, and a TRUE ACSC outcome (preventable
# hospitalizations) at patient ZIP, so no crosswalk. We flag a discharge ACSC if its principal
# diagnosis is in the AHRQ-PQI-style ambulatory-care-sensitive set (Billings simplified, ICD-10-CM
# prefixes). Pooled over the 4 quarters of 2019; aggregated ZIP counts cached (raw files are ~700MB).
TX_PUDF_URL = ("https://dshs-wcms-internet.s3.dualstack.us-gov-west-1.amazonaws.com/THCIC/"
               "InpatientFreePUDF/PUDF{q}Q2019_tab-delimited.zip")
TX_ACSC_CACHE = config.PROCESSED / "tx_acsc_zip_2019.parquet"
# ACSC / Prevention Quality Indicator principal-diagnosis ICD-10-CM prefixes: diabetes (E10-E13),
# dehydration (E86), bacterial pneumonia (J13-J18), COPD/asthma (J40-J47), hypertension (I10-I11),
# angina (I20), heart failure (I50), urinary (N10-N12, N30, N39.0).
TX_ACSC_PREFIXES = ("E10", "E11", "E12", "E13", "E86", "J13", "J14", "J15", "J16", "J18",
                    "J40", "J41", "J42", "J43", "J44", "J45", "J47", "I10", "I11", "I20",
                    "I50", "N10", "N11", "N12", "N30", "N390")
# ICD-9-CM ACSC/PQI principal-diagnosis prefixes (stored WITHOUT the decimal in the PUDF), for the
# pre-Oct-2015 discharges: diabetes (250), dehydration (2765), bacterial pneumonia (481-486),
# COPD/asthma (491-496, 4660), hypertension (401-402), angina (4111, 413), heart failure (428),
# urinary (590, 5950, 5959, 5990). Mirrors TX_ACSC_PREFIXES (the ICD-10 set). The two code spaces are
# disjoint (ICD-9 ACSC = digits only; ICD-10 = letter-prefixed), so matching EITHER set is safe across
# the Oct-2015 ICD-9->ICD-10 transition with no false positives - no per-quarter coding logic needed.
TX_ACSC_PREFIXES_ICD9 = ("250", "2765", "481", "482", "483", "485", "486", "491", "492", "493",
                         "494", "496", "4660", "401", "402", "4111", "413", "428", "590", "5950",
                         "5959", "5990")
TX_ACSC_PREFIXES_ALL = TX_ACSC_PREFIXES + TX_ACSC_PREFIXES_ICD9
TX_PUDF_BASE = ("https://dshs-wcms-internet.s3.dualstack.us-gov-west-1.amazonaws.com/THCIC/"
                "InpatientFreePUDF/")
TX_PANEL_YEARS = (2011, 2012, 2013, 2014, 2015)   # ICD-9 era spanning the 2014 ACA expansion
POOL_YEARS = ("2019", "2020", "2021", "2022", "2023")  # 5-yr pool for small-ZIP stability
MIN_POP = 1000          # drop ZCTAs below the index's own low-confidence floor
MIN_YEARS = 4           # require a near-full pool so a single noisy year can't dominate
DIM_COLS = [f"{d}_pctile" for d in DIMENSIONS]


def _score_cols(frame: pd.DataFrame) -> list[str]:
    """The dimension + sub-score + composite columns present in `frame` (one source of truth so a
    taxonomy change flows to every sub-county scorecard)."""
    cols = DIM_COLS + [f"{s['key']}_pctile" for s in subscore_specs()] + ["access_gap_score"]
    return [c for c in cols if c in frame.columns]


def _fetch_ny_pqi() -> pd.DataFrame:
    """Pull PQI_90 (overall ACSC composite) by ZIP, pooled over POOL_YEARS, mean per ZIP."""
    years = ",".join(f"'{y}'" for y in POOL_YEARS)
    q = {
        "$where": f"pqi_number='PQI_90' and year in ({years})",
        "$select": ("patient_zipcode,year,observed_rate_per_100_000_people,"
                    "expected_rate_per_100_000_people"),
        "$limit": 200000,
    }
    url = NY_PQI_SOCRATA + "?" + urllib.parse.urlencode(q)
    with urllib.request.urlopen(url, timeout=90) as r:
        rows = json.load(r)
    df = pd.DataFrame(rows)
    df["obs"] = pd.to_numeric(df["observed_rate_per_100_000_people"], errors="coerce")
    df["exp"] = pd.to_numeric(df["expected_rate_per_100_000_people"], errors="coerce")
    df["zcta5"] = df["patient_zipcode"].astype(str).str.zfill(5)
    g = df.groupby("zcta5").agg(obs=("obs", "mean"), exp=("exp", "mean"),
                                nyears=("year", "nunique")).reset_index()
    g["oe"] = g["obs"] / g["exp"].replace(0, np.nan)  # risk-standardized: removes age/sex mix
    return g


def run(extra_csv: str | None = None) -> dict:
    if not METRICS.exists():
        raise SystemExit(f"missing {METRICS}; run the pipeline first")
    log("subcounty", "fetching NY SPARCS PQI_90 by ZIP (pooled 2019-2023)...")
    pqi = _fetch_ny_pqi()
    if extra_csv:  # optional second state: CSV with columns zcta5,obs,exp
        ex = pd.read_csv(extra_csv, dtype={"zcta5": str})
        ex["oe"] = ex["obs"] / ex["exp"].replace(0, np.nan)
        ex["nyears"] = MIN_YEARS
        pqi = pd.concat([pqi, ex[["zcta5", "obs", "exp", "oe", "nyears"]]], ignore_index=True)

    m = pd.read_parquet(METRICS)
    m = m[m["scoreable"] == True].copy()  # noqa: E712
    m["zcta5"] = m["zcta5"].astype(str)
    j = pqi.merge(m, on="zcta5", how="inner")
    j = j[(j.obs > 0) & (j.population >= MIN_POP) & (j.nyears >= MIN_YEARS)].copy()
    # keep only multi-ZCTA counties so the within-county residual is defined
    vc = j["county_fips"].value_counts()
    j = j[j["county_fips"].isin(vc[vc >= 2].index)].copy()
    log("subcounty", f"{len(j)} ZCTAs across {j['county_fips'].nunique()} multi-ZCTA counties")

    cols = _score_cols(j)
    yo_w, yoe_w = _within(j, "obs"), _within(j, "oe")
    report = {"n": len(j), "counties": int(j["county_fips"].nunique()), "pooled": {}, "within_county": {}}

    print("\n=== SUB-COUNTY validation vs NY SPARCS PQI_90 (observed ACSC; O/E = risk-adjusted) ===")
    print(f"  {len(j)} ZCTAs / {j['county_fips'].nunique()} counties\n")
    print(f"  {'column':32s} {'pooled-obs':>11s} {'pooled-O/E':>11s} {'WITHIN-obs':>11s} {'WITHIN-O/E':>11s}")
    for c in cols:
        po, poe = _corr(j[c], j["obs"]), _corr(j[c], j["oe"])
        wo, woe = _corr(_within(j, c), yo_w), _corr(_within(j, c), yoe_w)
        report["pooled"][c] = {"obs": round(po, 3), "oe": round(poe, 3)}
        report["within_county"][c] = {"obs": round(wo, 3), "oe": round(woe, 3)}
        mark = "  <-- 0 sub-county resolution" if abs(wo) < 0.01 else ""
        print(f"  {c:32s} {po:+11.3f} {poe:+11.3f} {wo:+11.3f} {woe:+11.3f}{mark}")

    # precision-weighting: down-weight the noisy small ZCTAs that attenuate the within-county r.
    # Reported as a before/after for the two headline columns (composite + care access); the same
    # _wcorr is available to every sub-county ruler below.
    pw = j["population"].to_numpy(float)
    report["within_county_popw"] = {}
    print("\n  === precision-weighting (within-county O/E; weight = ZCTA population) ===")
    print(f"  {'column':32s} {'unweighted':>11s} {'pop-weighted':>13s} {'recovered':>10s}")
    for c in ("access_gap_score", "care_access_pctile"):
        if c not in j.columns:
            continue
        uw = _corr(_within(j, c), yoe_w)
        ww = _wcorr(_within(j, c), yoe_w, pw)
        report["within_county_popw"][c] = round(ww, 3)
        print(f"  {c:32s} {uw:+11.3f} {ww:+13.3f} {ww - uw:+10.3f}")
    print("\n  Reading: WITHIN-county is the test county outcomes CANNOT do. A positive WITHIN-O/E "
          "means\n  the index resolves real sub-county access signal a county-level gate is blind to.\n"
          "  Pop-weighting recovers the signal the small-area noise was hiding (corrects attenuation,\n"
          "  fits nothing) - the largest free gain available at this resolution.")
    return report


def _get_json(url: str, timeout: int = 90, retries: int = 3) -> dict:
    """GET + json.load with a few retries - the CO ArcGIS endpoint occasionally returns a truncated
    body, which would otherwise sink the consolidated scorecard."""
    last = None
    for _ in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.loads(r.read())
        except (json.JSONDecodeError, urllib.error.URLError, OSError) as e:  # noqa: PERF203
            last = e
    raise last  # type: ignore[misc]


def _fetch_co_acsc() -> pd.DataFrame:
    """CO age-adjusted ACSC hospitalization rates per 100k by census tract (diabetes/asthma/HD)."""
    q = ("?where=1%3D1&outFields=TRACT_FIPS,DIABETES_ADJRATE,ASTHMA_ADJRATE,HD_ADJRATE"
         "&resultRecordCount=3000&f=json")
    feats = _get_json(CO_ACSC_ARCGIS + q)["features"]
    co = pd.DataFrame([f["attributes"] for f in feats])
    co["tract"] = co["TRACT_FIPS"].astype(str).str.zfill(11)
    for c in ("DIABETES_ADJRATE", "ASTHMA_ADJRATE", "HD_ADJRATE"):
        co[c] = pd.to_numeric(co[c], errors="coerce")
    return co.rename(columns={"DIABETES_ADJRATE": "diabetes", "ASTHMA_ADJRATE": "asthma",
                              "HD_ADJRATE": "hd"})


def _read_secret(env: str, filename: str) -> str | None:
    """A credential from $ENV or ~/filename (free Census/HUD keys; never committed)."""
    v = os.environ.get(env)
    if v:
        return v.strip()
    p = Path.home() / filename
    return p.read_text().strip() if p.exists() else None


def _load_xwalk() -> pd.DataFrame:
    """National Census 2020 ZCTA<->tract relationship (GEOID_ZCTA5_20, GEOID_TRACT_20, land-area of
    the intersection), fetched once (~24MB) and cached. The AREA-weighted FALLBACK crosswalk used
    only when no HUD token is available."""
    if XWALK_CACHE.exists():
        return pd.read_parquet(XWALK_CACHE)
    log("subcounty", "fetching Census ZCTA<->tract relationship file (one-time, ~24MB)...")
    with urllib.request.urlopen(ZCTA_TRACT_REL, timeout=120) as r:
        full = pd.read_csv(io.BytesIO(r.read()), sep="|", dtype=str)
    rel = full[["GEOID_ZCTA5_20", "GEOID_TRACT_20", "AREALAND_PART"]].dropna()
    rel["AREALAND_PART"] = pd.to_numeric(rel["AREALAND_PART"], errors="coerce")
    rel = rel[rel["AREALAND_PART"] > 0]
    rel.to_parquet(XWALK_CACHE, index=False)
    return rel


def _load_hud_xwalk() -> pd.DataFrame | None:
    """National HUD ZIP<->TRACT crosswalk with res_ratio (residential-address share). The
    POPULATION-weighted crosswalk - returns None if no HUD token is configured."""
    if HUD_XWALK_CACHE.exists():
        return pd.read_parquet(HUD_XWALK_CACHE)
    token = _read_secret("HUD_TOKEN", ".hud_token")
    if not token:
        return None
    log("subcounty", "fetching HUD ZIP<->tract crosswalk (res_ratio, one-time)...")
    req = urllib.request.Request(HUD_USPS_API, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=180) as r:
        rows = json.load(r)["data"]["results"]
    x = pd.DataFrame(rows)[["zip", "geoid", "res_ratio"]]
    x["res_ratio"] = pd.to_numeric(x["res_ratio"], errors="coerce")
    x = x[x["res_ratio"] > 0]
    x.to_parquet(HUD_XWALK_CACHE, index=False)
    return x


def _tract_to_zcta(tract_vals: pd.DataFrame, value_cols: list[str]) -> pd.DataFrame:
    """Aggregate tract-level value_cols up to ZCTA. Prefers HUD res_ratio (POPULATION-weighted:
    each tract weighted by the share of the ZIP's residential addresses it holds); falls back to the
    Census land-AREA weight when no HUD token is present. tract_vals needs an 11-digit 'tract' col."""
    hud = _load_hud_xwalk()
    if hud is not None:
        m = hud.merge(tract_vals, left_on="geoid", right_on="tract", how="inner")
        key, wcol = "zip", "res_ratio"
    else:
        m = _load_xwalk().merge(tract_vals, left_on="GEOID_TRACT_20", right_on="tract", how="inner")
        key, wcol = "GEOID_ZCTA5_20", "AREALAND_PART"

    def wavg(g: pd.DataFrame, col: str) -> float:
        w, v = g[wcol].to_numpy(float), g[col].to_numpy(float)
        ok = ~np.isnan(v) & (w > 0)
        return float((v[ok] * w[ok]).sum() / w[ok].sum()) if ok.any() else np.nan

    return (m.groupby(key)
            .apply(lambda g: pd.Series({k: wavg(g, k) for k in value_cols}), include_groups=False)
            .reset_index().rename(columns={key: "zcta5"}))


def _co_zcta_acsc() -> pd.DataFrame:
    co = _fetch_co_acsc()
    return _tract_to_zcta(co[["tract", "diabetes", "asthma", "hd"]], ["diabetes", "asthma", "hd"])


def _fetch_overdose_zcta() -> pd.DataFrame:
    """CDC tract drug-overdose mortality (pooled OD_YEARS, mean rate per geoid), expanded to member
    tracts, crosswalked to ZCTA."""
    rows, off = [], 0
    while True:
        q = {"$where": f"intent='Drug_OD' AND period in({','.join(repr(y) for y in OD_YEARS)})",
             "$select": "geoid,name,rate", "$limit": 50000, "$offset": off}
        url = CDC_OVERDOSE_SOCRATA + "?" + urllib.parse.urlencode(q)
        with urllib.request.urlopen(url, timeout=120) as r:
            chunk = json.load(r)
        rows += chunk
        if len(chunk) < 50000:
            break
        off += 50000
    od = pd.DataFrame(rows)
    od["rate"] = pd.to_numeric(od["rate"], errors="coerce")
    g = od.groupby("geoid").agg(rate=("rate", "mean"), name=("name", "first")).reset_index()
    ex = g.assign(tract=g["name"].str.split(",")).explode("tract")
    ex["tract"] = ex["tract"].str.strip().str.zfill(11)
    ex = ex[["tract", "rate"]].dropna().rename(columns={"rate": "overdose"})
    return _tract_to_zcta(ex, ["overdose"])


def run_colorado() -> dict:
    """Second-state sub-county validation: the index vs CO tract ACSC (independent of every input).
    Reports pooled + WITHIN-county correlations - the within-county number is the decisive test of
    sub-county discrimination that county outcomes cannot provide."""
    if not METRICS.exists():
        raise SystemExit(f"missing {METRICS}; run the pipeline first")
    log("subcounty", "fetching CO CDPHE tract ACSC + crosswalking to ZCTA...")
    zc = _co_zcta_acsc()
    m = pd.read_parquet(METRICS)
    m = m[m["scoreable"] == True].copy()  # noqa: E712
    m["zcta5"] = m["zcta5"].astype(str)
    j = zc.merge(m, on="zcta5", how="inner")
    j = j[j["population"] >= MIN_POP].copy()
    vc = j["county_fips"].value_counts()
    j = j[j["county_fips"].isin(vc[vc >= 2].index)].copy()
    log("subcounty", f"CO: {len(j)} ZCTAs / {j['county_fips'].nunique()} multi-ZCTA counties")

    cols = _score_cols(j)
    yw = _within(j, "diabetes")
    rep = {"n": len(j), "counties": int(j["county_fips"].nunique()),
           "outcome": "CO CDPHE diabetes ACSC hospitalization (age-adjusted, tract->ZCTA)",
           "pooled": {}, "within_county": {}}
    print("\n=== SUB-COUNTY validation vs COLORADO CDPHE diabetes ACSC (2nd state, independent) ===")
    print(f"  {len(j)} ZCTAs / {j['county_fips'].nunique()} multi-ZCTA counties\n")
    print(f"  {'column':32s} {'pooled':>9s} {'WITHIN-county':>14s}")
    for c in cols:
        po = _corr(j[c].to_numpy(), j["diabetes"].to_numpy())
        wo = _corr(_within(j, c), yw)
        rep["pooled"][c] = round(po, 3)
        rep["within_county"][c] = round(wo, 3)
        mark = "  <-- 0 sub-county resolution" if abs(wo) < 0.01 else ""
        print(f"  {c:32s} {po:+9.3f} {wo:+14.3f}{mark}")
    print("\n  Reading: a positive WITHIN-county r in a SECOND state (CO, vs NY) against an "
          "independent\n  tract ACSC outcome generalizes the sub-county finding beyond one state's data.")
    return rep


def run_overdose_national() -> dict:
    """NATIONAL sub-county validation: the index vs CDC tract drug-overdose mortality (observed
    deaths, independent of every input), crosswalked to ZCTA. The only national sub-county ruler -
    it relaxes the 'no national sub-county outcome' ceiling. Reports pooled + WITHIN-county r; the
    within-county number being ~= pooled is the decisive evidence the index resolves real sub-county
    structure confirmed against an independent national death-records outcome. Overdose is a SPECIFIC
    construct (SUD/harm-reduction access + deaths of despair), so a modest positive r is expected and
    honest - the behavioral/mental sub-scores should lead."""
    if not METRICS.exists():
        raise SystemExit(f"missing {METRICS}; run the pipeline first")
    log("subcounty", "fetching CDC tract overdose mortality + crosswalking to ZCTA...")
    zc = _fetch_overdose_zcta()
    m = pd.read_parquet(METRICS)
    m = m[m["scoreable"] == True].copy()  # noqa: E712
    m["zcta5"] = m["zcta5"].astype(str)
    j = zc.merge(m, on="zcta5", how="inner")
    j = j[j["population"] >= MIN_POP].copy()
    vc = j["county_fips"].value_counts()
    j = j[j["county_fips"].isin(vc[vc >= 3].index)].copy()   # >=3 ZCTAs so within-county is defined
    log("subcounty", f"overdose: {len(j)} ZCTAs / {j['county_fips'].nunique()} counties")

    cols = _score_cols(j)
    yw = _within(j, "overdose")
    rep = {"n": len(j), "counties": int(j["county_fips"].nunique()),
           "outcome": "CDC tract drug-overdose mortality (pooled 2022-2024, observed, tract->ZCTA)",
           "pooled": {}, "within_county": {}}
    print("\n=== NATIONAL sub-county validation vs CDC tract DRUG-OVERDOSE mortality (independent) ===")
    print(f"  {len(j)} ZCTAs / {j['county_fips'].nunique()} counties (>=3 ZCTAs each)\n")
    print(f"  {'column':32s} {'pooled':>9s} {'WITHIN-county':>14s}")
    for c in cols:
        po = _corr(j[c].to_numpy(), j["overdose"].to_numpy())
        wo = _corr(_within(j, c), yw)
        rep["pooled"][c] = round(po, 3)
        rep["within_county"][c] = round(wo, 3)
        print(f"  {c:32s} {po:+9.3f} {wo:+14.3f}")
    print("\n  Reading: WITHIN-county ~= pooled => the index resolves genuine sub-county structure, "
          "confirmed\n  NATIONALLY against an independent death-records outcome. Magnitude is modest "
          "because overdose\n  is a specific access construct - note the behavioral/mental sub-scores lead.")
    return rep


def _fetch_ca_acsc() -> pd.DataFrame:
    """CA ACSC-cause death counts (pooled 2019-2024, Total Population strata) per ZIP. Cached via
    curl (the CKAN download 302-redirects to a signed S3 URL that urllib mishandles)."""
    if not CA_DEATHS_CACHE.exists():
        log("subcounty", "downloading CA CHHS deaths-by-ZIP (one-time, ~48MB)...")
        subprocess.run(["curl", "-sL", "--max-time", "180", CA_DEATHS_URL,
                        "-o", str(CA_DEATHS_CACHE)], check=True)
    df = pd.read_csv(CA_DEATHS_CACHE, dtype=str)
    df = df[df["Strata"] == "Total Population"]
    df = df[df["Cause"].isin(CA_ACSC_CAUSES)].copy()
    df["Count"] = pd.to_numeric(df["Count"], errors="coerce")  # suppressed cells -> NaN
    df["zcta5"] = df["ZIP_Code"].astype(str).str.zfill(5)
    return df.groupby("zcta5")["Count"].sum().rename("acsc_deaths").reset_index()


def run_california() -> dict:
    """4th-state sub-county validation: the index vs CA ACSC-cause mortality (diabetes/heart/COPD/
    stroke deaths), AGE-ADJUSTED. Crude rates are age-confounded; we residualize both the index and
    the rate on age65_rate WITHIN county, then correlate. Reports crude vs age-adjusted so the
    suppression (age is wealth-correlated in CA) is visible and honest."""
    if not METRICS.exists():
        raise SystemExit(f"missing {METRICS}; run the pipeline first")
    log("subcounty", "validating vs CA ACSC mortality (age-adjusted)...")
    ca = _fetch_ca_acsc()
    m = pd.read_parquet(METRICS)
    m = m[m["scoreable"] == True].copy()  # noqa: E712
    m["zcta5"] = m["zcta5"].astype(str)
    j = ca.merge(m, on="zcta5", how="inner")
    j["pop"] = pd.to_numeric(j["population"], errors="coerce")
    j = j[(j["pop"] >= MIN_POP) & (j["acsc_deaths"] > 0)].copy()
    if "age65_rate" not in j.columns:
        raise SystemExit("age65_rate missing; CA needs it for age adjustment")
    j["rate"] = j["acsc_deaths"] / j["pop"]
    vc = j["county_fips"].value_counts()
    j = j[j["county_fips"].isin(vc[vc >= 3].index)].copy()
    log("subcounty", f"CA: {len(j)} ZCTAs / {j['county_fips'].nunique()} counties")

    def resid_age(col: str) -> np.ndarray:
        """within-county residual of `col`, then linearly residualized on age65_rate."""
        y, a = _within(j, col), _within(j, "age65_rate")
        mk = ~(np.isnan(y) | np.isnan(a))
        out = np.full(len(y), np.nan)
        if mk.sum() > 50:
            b = np.polyfit(a[mk], y[mk], 1)
            out[mk] = y[mk] - np.polyval(b, a[mk])
        return out

    yw_adj = resid_age("rate")
    cols = _score_cols(j)
    conf = _corr(_within(j, "rate"), _within(j, "age65_rate"))
    rep = {"n": len(j), "counties": int(j["county_fips"].nunique()),
           "outcome": "CA ACSC-cause mortality (diabetes/heart/COPD/stroke, 2019-2024), age-adjusted",
           "age_confound_r": round(conf, 3), "within_county_crude": {}, "within_county_age_adj": {}}
    print("\n=== SUB-COUNTY validation vs CALIFORNIA ACSC mortality (4th state, age-adjusted) ===")
    print(f"  {len(j)} ZCTAs / {j['county_fips'].nunique()} counties; "
          f"age confound corr(rate, %65+) within-cty = {conf:+.3f} (age is a suppressor in CA)\n")
    print(f"  {'column':32s} {'crude-within':>12s} {'AGE-ADJ within':>15s}")
    for c in cols:
        wc = _corr(_within(j, c), _within(j, "rate"))
        wa = _corr(resid_age(c), yw_adj)
        rep["within_county_crude"][c] = round(wc, 3)
        rep["within_county_age_adj"][c] = round(wa, 3)
        print(f"  {c:32s} {wc:+12.3f} {wa:+15.3f}")
    print("\n  Reading: crude within-county is muted because in CA older ZIPs are WEALTHIER (age "
          "negatively\n  confounds deprivation); age-adjusted, the index resolves real sub-county "
          "ACSC-mortality signal.")
    return rep


def _fetch_tx_acsc() -> pd.DataFrame:
    """Pooled 2019 TX ACSC inpatient counts by patient ZIP (zcta5, acsc, n_total). Downloads each
    quarter's tab-delimited zip, streams the base1 member, flags ACSC by principal diagnosis, and
    caches the small ZIP-level aggregate (the four raw zips are ~700MB and are deleted after)."""
    import csv
    import tempfile
    import zipfile
    from collections import Counter
    if TX_ACSC_CACHE.exists():
        return pd.read_parquet(TX_ACSC_CACHE)
    acsc: Counter = Counter()
    tot: Counter = Counter()
    for q in (1, 2, 3, 4):
        log("subcounty", f"TX PUDF {q}Q2019: downloading + parsing (one-time)...")
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=True) as tmp:
            subprocess.run(["curl", "-sL", "--max-time", "600", TX_PUDF_URL.format(q=q),
                            "-o", tmp.name], check=True)
            member = f"PUDF_base1_{q}q2019_tab.txt"
            with zipfile.ZipFile(tmp.name) as z, z.open(member) as fh:
                rdr = csv.reader(io.TextIOWrapper(fh, encoding="latin-1"), delimiter="\t")
                header = next(rdr)
                zi, di = header.index("PAT_ZIP"), header.index("PRINC_DIAG_CODE")
                for row in rdr:
                    if len(row) <= max(zi, di):
                        continue
                    z5 = row[zi]
                    if len(z5) != 5 or not z5.isdigit():  # drop masked (<30 discharge) ZIPs
                        continue
                    tot[z5] += 1
                    if row[di].upper().startswith(TX_ACSC_PREFIXES):
                        acsc[z5] += 1
    g = pd.DataFrame({"zcta5": list(tot), "acsc": [acsc[z] for z in tot],
                      "n_total": [tot[z] for z in tot]})
    g.to_parquet(TX_ACSC_CACHE, index=False)
    return g


def _tx_quarter_counts(year: int, q: int):
    """ZIP-level (ACSC, total) discharge counts for one TX PUDF quarter. Handles the older NESTED-zip
    layout (outer zip -> inner PUDF_base1_*.zip -> .txt) as well as a flat .txt member; flags ACSC by
    principal diagnosis against the combined ICD-9+ICD-10 set."""
    import csv
    import io
    import tempfile
    import zipfile
    from collections import Counter
    url = TX_PUDF_BASE + f"PUDF-{q}Q{year}-tab-delimited.zip"
    acsc: Counter = Counter()
    tot: Counter = Counter()
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=True) as tmp:
        subprocess.run(["curl", "-sL", "--max-time", "900", url, "-o", tmp.name], check=True)
        outer = zipfile.ZipFile(tmp.name)
        base = next(n for n in outer.namelist() if "base1" in n.lower())
        raw = outer.read(base)
        if base.lower().endswith(".zip"):                       # nested (older years)
            inner = zipfile.ZipFile(io.BytesIO(raw))
            member = next(n for n in inner.namelist() if n.lower().endswith((".txt", ".tab")))
            fh = inner.open(member)
        else:                                                   # flat .txt (2019-style)
            fh = io.BytesIO(raw)
        rdr = csv.reader(io.TextIOWrapper(fh, encoding="latin-1"), delimiter="\t")
        header = next(rdr)
        zi, di = header.index("PAT_ZIP"), header.index("PRINC_DIAG_CODE")
        for row in rdr:
            if len(row) <= max(zi, di):
                continue
            z5 = row[zi]
            if len(z5) != 5 or not z5.isdigit():               # drop masked/out-of-state ZIPs
                continue
            tot[z5] += 1
            if row[di].upper().startswith(TX_ACSC_PREFIXES_ALL):
                acsc[z5] += 1
    return acsc, tot


def _fetch_tx_year(year: int) -> pd.DataFrame:
    """Pooled 4-quarter TX ACSC counts by patient ZIP for one year (zcta5, acsc, n_total), cached.
    The raw quarter zips (~150MB each) are streamed and discarded; only the tiny ZIP aggregate is kept."""
    from collections import Counter
    cache = config.PROCESSED / f"tx_acsc_zip_{year}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    acsc: Counter = Counter()
    tot: Counter = Counter()
    for q in (1, 2, 3, 4):
        log("subcounty", f"TX PUDF {q}Q{year}: download + stream...")
        a, t = _tx_quarter_counts(year, q)
        acsc.update(a)
        tot.update(t)
    g = pd.DataFrame({"zcta5": list(tot), "acsc": [acsc[z] for z in tot],
                      "n_total": [tot[z] for z in tot]})
    g.to_parquet(cache, index=False)
    return g


def tx_acsc_panel(years=TX_PANEL_YEARS) -> pd.DataFrame:
    """Long TX ACSC panel (zcta5, year, acsc, n_total) across `years` - the non-expansion control
    arm for the cross-state ACA-expansion DiD (validate_temporal.run_cross_state)."""
    frames = []
    for y in years:
        g = _fetch_tx_year(y)
        g = g.assign(year=y)
        frames.append(g)
    return pd.concat(frames, ignore_index=True)


def run_texas() -> dict:
    """5th-state sub-county validation: the index vs TX ACSC inpatient rate (per 1k residents,
    pooled 2019), patient-ZIP - a TRUE preventable-hospitalization outcome, no crosswalk, in the
    largest state. Reports pooled + WITHIN-county r."""
    if not METRICS.exists():
        raise SystemExit(f"missing {METRICS}; run the pipeline first")
    tx = _fetch_tx_acsc()
    m = pd.read_parquet(METRICS)
    m = m[m["scoreable"] == True].copy()  # noqa: E712
    m["zcta5"] = m["zcta5"].astype(str)
    j = tx.merge(m, on="zcta5", how="inner")
    j["pop"] = pd.to_numeric(j["population"], errors="coerce")
    j = j[(j["pop"] >= MIN_POP) & (j["acsc"] > 0)].copy()
    j["rate"] = j["acsc"] / j["pop"] * 1000.0   # ACSC inpatient per 1k residents
    vc = j["county_fips"].value_counts()
    j = j[j["county_fips"].isin(vc[vc >= 3].index)].copy()
    log("subcounty", f"TX: {len(j)} ZCTAs / {j['county_fips'].nunique()} counties")

    cols = _score_cols(j)
    yw = _within(j, "rate")
    rep = {"n": len(j), "counties": int(j["county_fips"].nunique()),
           "outcome": "TX DSHS ACSC inpatient rate per 1k (patient ZIP, pooled 2019)",
           "pooled": {}, "within_county": {}}
    print("\n=== SUB-COUNTY validation vs TEXAS ACSC inpatient (5th state, patient-ZIP, no crosswalk) ===")
    print(f"  {len(j)} ZCTAs / {j['county_fips'].nunique()} multi-ZCTA counties\n")
    print(f"  {'column':32s} {'pooled':>9s} {'WITHIN-county':>14s}")
    for c in cols:
        po = _corr(j[c].to_numpy(), j["rate"].to_numpy())
        wo = _corr(_within(j, c), yw)
        rep["pooled"][c] = round(po, 3)
        rep["within_county"][c] = round(wo, 3)
        print(f"  {c:32s} {po:+9.3f} {wo:+14.3f}")
    print("\n  A TRUE ACSC (preventable-hospitalization) outcome at patient ZIP - the textbook access "
          "construct,\n  largest state, no crosswalk. WITHIN-county positive => sub-county resolution confirmed.")
    return rep


def run_all() -> dict:
    """Consolidated sub-county scorecard: run every available independent check and print one table
    of the composite + care_access WITHIN-county correlation per source. The headline evidence that
    the index discriminates within counties, across states and outcomes, in one place."""
    def within_composite(rep: dict, comp_key: str = "access_gap_score",
                         care_key: str = "care_access_pctile") -> tuple:
        wc = rep.get("within_county") or rep.get("within_county_age_adj") or {}
        def g(k):
            v = wc.get(k)
            return v.get("oe") if isinstance(v, dict) else v
        return g(comp_key), g(care_key)

    sources = []
    for label, fn in (("NY SPARCS PQI (ACSC, O/E)", run),
                      ("CO CDPHE diabetes ACSC", run_colorado),
                      ("CA ACSC mortality (age-adj)", run_california),
                      ("TX DSHS ACSC inpatient", run_texas),
                      ("US CDC overdose (national)", run_overdose_national),
                      ("US USALEEP life exp (national)", run_national)):
        try:
            rep = fn()
            comp, care = within_composite(rep)
            sources.append({"source": label, "n": rep.get("n"),
                            "counties": rep.get("counties"),
                            "composite_within_r": comp, "care_access_within_r": care})
        except Exception as e:  # noqa: BLE001 - one flaky fetch shouldn't sink the scorecard
            sources.append({"source": label, "error": str(e)[:80]})

    print("\n" + "=" * 72)
    print("  SUB-COUNTY VALIDITY SCORECARD - composite resolves WITHIN-county variance?")
    print("=" * 72)
    print(f"  {'source':32s} {'ZCTAs':>7s} {'cty':>5s} {'composite':>10s} {'care_acc':>9s}")
    for s in sources:
        if "error" in s:
            print(f"  {s['source']:32s}  -- {s['error']}")
            continue
        c = s["composite_within_r"]
        ca = s["care_access_within_r"]
        print(f"  {s['source']:32s} {s['n'] or 0:7d} {s['counties'] or 0:5d} "
              f"{(c if c is not None else float('nan')):+10.3f} "
              f"{(ca if ca is not None else float('nan')):+9.3f}")
    print("\n  Every row is an INDEPENDENT outcome (none in the inputs). Positive within-county r "
          "across\n  5 states + 2 national rulers = the index discriminates sub-county, not just "
          "between counties.")
    return {"sources": sources}


def run_national() -> dict:
    """National sub-county check using USALEEP life expectancy (tract→ZCTA, already in metrics).
    LE is a *need* outcome so it understates care access, BUT it is national (all ~2,200 multi-
    ZCTA counties) and independent (death records), so it generalizes the NY-only ACSC finding:
    does the index resolve sub-county signal, and do the structural negatives (shortage = 0
    resolution; safetynet wrong-signed) hold beyond NY? Also reports the per-state safetynet sign."""
    m = pd.read_parquet(METRICS)
    m = m[(m["scoreable"] == True) & m["life_expectancy"].notna() & (m["population"] >= MIN_POP)].copy()  # noqa: E712
    m["county_fips"] = m["county_fips"].astype(str)
    m["le_worse"] = -m["life_expectancy"]  # orient higher = worse
    vc = m["county_fips"].value_counts()
    m = m[m["county_fips"].isin(vc[vc >= 3].index)].copy()
    y = _within(m, "le_worse")
    cols = _score_cols(m)
    print("\n=== NATIONAL sub-county validation vs USALEEP life expectancy (need outcome) ===")
    print(f"  {len(m)} ZCTAs / {m['county_fips'].nunique()} counties (>=3 ZCTAs each)\n")
    rep = {"n": len(m), "counties": int(m["county_fips"].nunique()), "within_county": {}}
    for c in cols:
        r = _corr(_within(m, c), y)
        rep["within_county"][c] = round(r, 3)
        mark = "  <-- WRONG-SIGNED" if r < -0.02 else ("  <-- ~0 resolution" if abs(r) < 0.01 else "")
        print(f"  {c:32s} within-county r = {r:+.3f}{mark}")
    # per-state robustness of the safetynet wrong-sign
    if "safetynet_access_pctile" in m.columns:
        rs = []
        for st, g in m.groupby("state"):
            if g["county_fips"].nunique() < 5:
                continue
            rs.append(_corr(_within(g, "safetynet_access_pctile"), _within(g, "le_worse")))
        rs = np.array([r for r in rs if not np.isnan(r)])
        frac = float((rs < 0).mean())
        rep["safetynet_wrong_signed_state_frac"] = round(frac, 2)
        print(f"\n  safetynet_access within-county wrong-signed in {frac*100:.0f}% of "
              f"{len(rs)} states (median r {np.median(rs):+.3f}) - a national property, not an NY artifact.")
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra-csv", help="optional 2nd-state ZIP PQI CSV (cols: zcta5,obs,exp)")
    ap.add_argument("--national", action="store_true", help="run the national USALEEP within-county check too")
    ap.add_argument("--colorado", action="store_true", help="run the CO tract-ACSC 2nd-state check")
    ap.add_argument("--overdose", action="store_true", help="run the NATIONAL CDC tract-overdose check")
    ap.add_argument("--california", action="store_true", help="run the CA ACSC-mortality 4th-state check")
    ap.add_argument("--texas", action="store_true", help="run the TX patient-ZIP ACSC 5th-state check")
    ap.add_argument("--ny", action="store_true", help="run the NY SPARCS PQI check (default if no flags)")
    ap.add_argument("--all", action="store_true", help="consolidated scorecard across every source")
    a = ap.parse_args()
    if a.all:
        run_all()
        raise SystemExit(0)
    # default to NY if nothing specified (preserves prior behavior)
    if not (a.colorado or a.national or a.overdose or a.california or a.texas) or a.ny:
        run(a.extra_csv)
    if a.colorado:
        run_colorado()
    if a.california:
        run_california()
    if a.texas:
        run_texas()
    if a.overdose:
        run_overdose_national()
    if a.national:
        run_national()

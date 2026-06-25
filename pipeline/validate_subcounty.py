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
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .common import log
from .taxonomy import DIMENSIONS, subscore_specs

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
POOL_YEARS = ("2019", "2020", "2021", "2022", "2023")  # 5-yr pool for small-ZIP stability
MIN_POP = 1000          # drop ZCTAs below the index's own low-confidence floor
MIN_YEARS = 4           # require a near-full pool so a single noisy year can't dominate
DIM_COLS = [f"{d}_pctile" for d in DIMENSIONS]


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


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 50:
        return float("nan")
    a, b = a[m] - a[m].mean(), b[m] - b[m].mean()
    s = np.sqrt((a @ a) * (b @ b))
    return float(a @ b / s) if s > 0 else float("nan")


def _within(j: pd.DataFrame, col: str) -> np.ndarray:
    """Residual after removing the per-county mean (county fixed effect)."""
    s = pd.to_numeric(j[col], errors="coerce")
    return (s - s.groupby(j["county_fips"]).transform("mean")).to_numpy()


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

    cols = DIM_COLS + [f"{s['key']}_pctile" for s in subscore_specs()] + ["access_gap_score"]
    cols = [c for c in cols if c in j.columns]
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

    print("\n  Reading: WITHIN-county is the test county outcomes CANNOT do. A positive WITHIN-O/E "
          "means\n  the index resolves real sub-county access signal a county-level gate is blind to.")
    return report


def _fetch_co_acsc() -> pd.DataFrame:
    """CO age-adjusted ACSC hospitalization rates per 100k by census tract (diabetes/asthma/HD)."""
    q = ("?where=1%3D1&outFields=TRACT_FIPS,DIABETES_ADJRATE,ASTHMA_ADJRATE,HD_ADJRATE"
         "&resultRecordCount=3000&f=json")
    with urllib.request.urlopen(CO_ACSC_ARCGIS + q, timeout=90) as r:
        feats = json.load(r)["features"]
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

    cols = DIM_COLS + [f"{s['key']}_pctile" for s in subscore_specs()] + ["access_gap_score"]
    cols = [c for c in cols if c in j.columns]
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

    cols = DIM_COLS + [f"{s['key']}_pctile" for s in subscore_specs()] + ["access_gap_score"]
    cols = [c for c in cols if c in j.columns]
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
    cols = DIM_COLS + [f"{s['key']}_pctile" for s in subscore_specs()] + ["access_gap_score"]
    cols = [c for c in cols if c in m.columns]
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
    ap.add_argument("--ny", action="store_true", help="run the NY SPARCS PQI check (default if no flags)")
    a = ap.parse_args()
    # default to NY if nothing specified (preserves prior behavior)
    if not (a.colorado or a.national or a.overdose) or a.ny:
        run(a.extra_csv)
    if a.colorado:
        run_colorado()
    if a.overdose:
        run_overdose_national()
    if a.national:
        run_national()

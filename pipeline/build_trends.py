"""build_trends: a small, honest time-dimension PROOF + the vintage-keyed scaffold (BACKLOG B5 /
time-dimension). DISPLAY-ONLY - it never touches metrics.parquet or the scored build.

The app is a single snapshot. A faithful multi-vintage trend for every dimension means re-running
ACS + PLACES + NPPES per year and storing them - a real pipeline effort, and PLACES year-over-year
is contaminated by model changes while NPPES history is ~1 GB/month. What IS cheap and honest is a
**poverty-rank trend** from two adjacent ACS 5-year vintages: poverty (B17001) is the backbone of
the social-vulnerability dimension, ACS is a direct (non-modelled) measurement, and the API serves
any year by URL.

Correctness guard - the ZCTA vintage basis: ACS 5-year adopted 2020 ZCTAs with the 2023 release, so
the trend is restricted to vintages on that basis (default 2023 -> 2024) and computed only for ZCTAs
present in BOTH years (an inner join drops anything renumbered). Comparing across the 2010/2020 break
would silently compare different geographies, which we refuse to do.

Output: frontend/public/trends.json = {prior, curr, measure, deltas:{zcta5: <pctile change>}}.
A positive delta = relatively MORE poverty than the prior vintage (rank rose). Run: `make trends`.
"""
from __future__ import annotations

import json

import pandas as pd

from . import config
from .common import die, http_client, load_env, log, norm_zcta, scrub_sentinels

# Both on the 2020-ZCTA basis (ACS switched with the 2023 release). Keep adjacent so the 5-year
# windows overlap minimally and the delta reads as "recent change". Extend this list to add vintages.
ACS_VINTAGES = [2023, 2024]
GEO = "zip code tabulation area"
OUT = config.FRONTEND_PUBLIC / "trends.json"


def _poverty_rate(year: int) -> pd.DataFrame:
    """One national ZCTA call for poverty universe + below-poverty -> rate in [0,1]."""
    url = f"https://api.census.gov/data/{year}/acs/acs5"
    params = {"get": "B17001_001E,B17001_002E", "for": f"{GEO}:*"}
    if config.CENSUS_API_KEY:
        params["key"] = config.CENSUS_API_KEY
    with http_client() as c:
        r = c.get(url, params=params)
    if r.status_code != 200:
        die("trends", f"ACS {year} poverty fetch -> HTTP {r.status_code}: {r.text[:160]}")
    rows = r.json()
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df["zcta5"] = norm_zcta(df[GEO])
    total = scrub_sentinels(pd.to_numeric(df["B17001_001E"], errors="coerce"))
    below = scrub_sentinels(pd.to_numeric(df["B17001_002E"], errors="coerce"))
    rate = (below / total).where(total > 0).clip(0, 1)
    return pd.DataFrame({"zcta5": df["zcta5"], f"pov_{year}": rate}).dropna()


def build(dev_state: str | None = None, force: bool = False) -> str:
    load_env()
    prior, curr = ACS_VINTAGES[0], ACS_VINTAGES[-1]
    log("trends", f"poverty-rank trend {prior} -> {curr} (2020-ZCTA basis)")
    a = _poverty_rate(prior)
    b = _poverty_rate(curr)
    # Inner join: only ZCTAs measured in BOTH vintages (drops anything renumbered between them).
    m = a.merge(b, on="zcta5", how="inner")
    log("trends", f"{len(a)} + {len(b)} ZCTAs -> {len(m)} shared")
    # National percentile rank of poverty in each vintage; higher = relatively more poverty.
    rank_prior = m[f"pov_{prior}"].rank(pct=True) * 100
    rank_curr = m[f"pov_{curr}"].rank(pct=True) * 100
    delta = (rank_curr - rank_prior).round(1)
    deltas = {z: float(d) for z, d in zip(m["zcta5"], delta) if pd.notna(d)}

    OUT.write_text(json.dumps({
        "prior": prior, "curr": curr, "measure": "poverty rank",
        "deltas": deltas,
    }, separators=(",", ":")))
    moved = sum(1 for d in deltas.values() if abs(d) >= 5)
    log("trends", f"wrote {OUT.name}: {len(deltas)} ZCTAs, {moved} moved >=5 pctile "
                  f"(median |delta| {delta.abs().median():.1f})")
    return str(OUT)


if __name__ == "__main__":
    build()

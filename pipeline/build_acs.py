"""build_acs: Census ACS 5-year -> economic / insurance parquet.

Output columns (brief 12.6): zcta5(str5); median_income(num);
poverty_rate, uninsured_rate (float, FRACTION [0,1]); population(int).

Design choices honoring the brief:
- ZCTAs are a nation-based geography since 2019 -> one national call (no in=state).
- Variable codes resolved/asserted by LABEL from variables.json, never hardcoded
  blind across vintages (brief 11.2).
- Uninsured via get=group(B27001) in ONE call (Census 50-var cap), summing the
  "No health insurance coverage" members client-side (brief 16.1).
- Census sentinel negatives scrubbed to null before arithmetic.
- Key just activated? Auto-retry to ride out API-side propagation lag.
"""
from __future__ import annotations

import re
import time

import pandas as pd

from . import config
from .common import (assert_zcta, dev_filter, die, http_client, log,
                     norm_zcta, scrub_sentinels, write_provenance)

OUT = config.PROCESSED / "acs.parquet"
GEO = "zip code tabulation area"


class CensusError(RuntimeError):
    pass


def _census_get(base: str, params: dict, retries: int = 6) -> list[list[str]]:
    """GET a Census API call, returning parsed rows. Retries on invalid-key
    (handles freshly-activated key propagation) and transient errors."""
    params = {**params, "key": config.CENSUS_API_KEY}
    delay = 5
    for attempt in range(1, retries + 1):
        try:
            with http_client(120) as c:
                r = c.get(base, params=params)
            ct = r.headers.get("content-type", "")
            if "json" in ct or r.text.lstrip().startswith("["):
                return r.json()
            # Non-JSON -> error page (Invalid Key / Missing Key / etc.)
            title = re.search(r"<title>([^<]+)</title>", r.text)
            reason = title.group(1) if title else f"HTTP {r.status_code}"
            if "invalid key" in reason.lower() and attempt < retries:
                log("acs", f"key not live yet ({reason}); retry {attempt}/{retries} in {delay}s")
                time.sleep(delay); delay = min(delay * 2, 60)
                continue
            raise CensusError(f"{reason} :: {base}")
        except CensusError:
            raise
        except Exception as e:  # noqa: BLE001
            if attempt < retries:
                log("acs", f"transient {type(e).__name__}; retry {attempt}/{retries} in {delay}s")
                time.sleep(delay); delay = min(delay * 2, 60)
                continue
            raise
    raise CensusError("exhausted retries")


def _rows_to_df(rows: list[list[str]]) -> pd.DataFrame:
    return pd.DataFrame(rows[1:], columns=rows[0])


def _resolve_and_assert_vars() -> dict[str, list[str]]:
    """Confirm detailed var labels and discover B27001 no-coverage members."""
    with http_client(60) as c:
        dvars = c.get(config.ACS_VARS_DETAILED).json()["variables"]
    expect = {
        config.ACS_VAR_MEDIAN_INCOME: "median household income",
        config.ACS_VAR_POVERTY_BELOW: "income in the past 12 months below poverty",
        config.ACS_VAR_POPULATION: "total",
    }
    for var, frag in expect.items():
        label = dvars.get(var, {}).get("label", "").lower()
        if frag not in label:
            log("acs", f"WARN {var} label '{label}' lacks '{frag}' (vintage drift?)")
    no_cov = sorted(
        v for v, meta in dvars.items()
        if re.match(r"^B27001_\d+E$", v)
        and config.ACS_UNINSURED_LABEL_MATCH in meta.get("label", "").lower()
    )
    if not no_cov:
        die("acs", "no B27001 'No health insurance coverage' members found in variables.json")
    log("acs", f"uninsured: summing {len(no_cov)} B27001 no-coverage members")
    return {"no_cov": no_cov}


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("acs", f"skip (exists): {OUT.name}")
        return str(OUT)
    if not config.CENSUS_API_KEY:
        die("acs", "CENSUS_API_KEY missing; set it in .env then re-run this stage")

    resolved = _resolve_and_assert_vars()

    # Call 1: detailed table vars (5 vars, well under the 50 cap)
    det_vars = [config.ACS_VAR_MEDIAN_INCOME, config.ACS_VAR_POVERTY_TOTAL,
                config.ACS_VAR_POVERTY_BELOW, config.ACS_VAR_POPULATION,
                config.ACS_VAR_MEDIAN_AGE]
    log("acs", "fetching detailed table (income/poverty/population), national ZCTA...")
    det = _rows_to_df(_census_get(config.ACS_BASE_DETAILED,
                                  {"get": ",".join(det_vars), "for": f"{GEO}:*"}))

    # Call 2: B27001 whole group for uninsured
    log("acs", "fetching B27001 group (uninsured), national ZCTA...")
    grp = _rows_to_df(_census_get(config.ACS_BASE_DETAILED,
                                  {"get": "group(B27001)", "for": f"{GEO}:*"}))

    det["zcta5"] = norm_zcta(det[GEO])
    grp["zcta5"] = norm_zcta(grp[GEO])

    df = det[["zcta5"] + det_vars].copy()
    df["median_income"] = scrub_sentinels(df[config.ACS_VAR_MEDIAN_INCOME])
    pov_total = scrub_sentinels(df[config.ACS_VAR_POVERTY_TOTAL])
    pov_below = scrub_sentinels(df[config.ACS_VAR_POVERTY_BELOW])
    df["poverty_rate"] = (pov_below / pov_total).where(pov_total > 0)
    df["population"] = scrub_sentinels(df[config.ACS_VAR_POPULATION])
    df["median_age"] = scrub_sentinels(df[config.ACS_VAR_MEDIAN_AGE])

    # uninsured = sum(no-coverage members) / B27001_001E   -> fraction
    denom = scrub_sentinels(grp["B27001_001E"])
    nocov = grp[resolved["no_cov"]].apply(scrub_sentinels).sum(axis=1, min_count=1)
    unins = pd.DataFrame({"zcta5": grp["zcta5"],
                          "uninsured_rate": (nocov / denom).where(denom > 0)})
    df = df.merge(unins, on="zcta5", how="left")

    keep = ["zcta5", "median_income", "poverty_rate", "uninsured_rate",
            "population", "median_age"]
    df = df[keep]

    # SVI-style rates from detailed B-tables (each its own group() call).
    svi = _fetch_svi_rates()
    if svi is not None:
        df = df.merge(svi, on="zcta5", how="left")

    df["population"] = df["population"].round().astype("Int64")
    df = df.drop_duplicates("zcta5")
    df = dev_filter(df, dev_state)

    _validate(df, dev_state)
    df.to_parquet(OUT, index=False)
    write_provenance({"acs": {"year": config.ACS_YEAR, "rows": len(df),
                              "uninsured_members": len(resolved["no_cov"]),
                              "svi_rates": [c for c in df.columns if c in config.ACS_SVI],
                              "rate_unit": "fraction"}})
    log("acs", f"wrote {OUT.name} ({len(df)} rows, {len(df.columns)-1} cols)")
    return str(OUT)


def _fetch_svi_rates() -> pd.DataFrame | None:
    """One group() call per ACS table -> a fraction rate. Failures are skipped
    (the hierarchical score averages over whichever members are present)."""
    frames: list[pd.DataFrame] = []
    for name, (table, nums, denom) in config.ACS_SVI.items():
        try:
            grp = _rows_to_df(_census_get(config.ACS_BASE_DETAILED,
                                          {"get": f"group({table})", "for": f"{GEO}:*"}))
            grp["zcta5"] = norm_zcta(grp[GEO])
            den = scrub_sentinels(grp[f"{table}_{denom}E"])
            if name == "pct_minority":
                white = scrub_sentinels(grp[f"{table}_003E"])
                rate = ((den - white) / den).where(den > 0)
            else:
                num = grp[[f"{table}_{s}E" for s in nums]].apply(scrub_sentinels).sum(axis=1, min_count=1)
                rate = (num / den).where(den > 0)
            rate = rate.clip(0, 1)
            frames.append(pd.DataFrame({"zcta5": grp["zcta5"], name: rate}))
            log("acs", f"  svi {name}: median {rate.median():.3f}")
        except Exception as e:  # noqa: BLE001
            log("acs", f"  svi {name}: FAILED ({type(e).__name__}); skipping")
    if not frames:
        return None
    out = frames[0]
    for f in frames[1:]:
        out = out.merge(f, on="zcta5", how="outer")
    return out


def _validate(df: pd.DataFrame, dev_state: str | None) -> None:
    assert_zcta(df, stage="acs")
    floor = 200 if dev_state else 30_000
    if len(df) < floor:
        die("acs", f"only {len(df)} rows (expected >= {floor})")
    med = df["median_income"].median()
    if not (30_000 <= med <= 120_000):
        die("acs", f"median of median_income = {med} outside sane $30k-$120k")
    for col in ("poverty_rate", "uninsured_rate"):
        vals = df[col].dropna()
        if len(vals) and (vals.min() < 0 or vals.max() > 1):
            die("acs", f"{col} outside [0,1] (unit contract broken): "
                       f"min={vals.min()} max={vals.max()}")
    log("acs", f"validated {len(df)} rows, median income ${med:,.0f}, rates in [0,1]")


if __name__ == "__main__":
    import sys
    from .common import load_env
    load_env()
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

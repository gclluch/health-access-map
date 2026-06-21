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

import numpy as np

from . import config
from .common import (assert_zcta, dev_filter, die, http_client, log,
                     norm_zcta, scrub_sentinels, write_provenance)
from .zip_states import zip3_to_state

OUT = config.PROCESSED / "acs.parquet"
GEO = "zip code tabulation area"
ACS_MOE_Z = 1.645  # ACS publishes 90% margins of error: SE = MOE / 1.645


def _moe(series: pd.Series) -> pd.Series:
    """Parse an ACS margin-of-error column. Census uses negative sentinels for
    'not applicable'/suppressed margins; scrub to null and take the magnitude."""
    return scrub_sentinels(series).abs()


def _proportion_se(moe_num: pd.Series, moe_den: pd.Series, p: pd.Series, den: pd.Series) -> pd.Series:
    """Standard error of a proportion p = num/den from component MOEs (ACS ratio
    formula, always real): SE = (1/(1.645*den)) * sqrt(MOE_num^2 + p^2 * MOE_den^2)."""
    moe_p = np.sqrt(moe_num ** 2 + (p ** 2) * (moe_den ** 2)) / den.where(den > 0)
    return moe_p / ACS_MOE_Z


def _eb_shrink(rate: pd.Series, se: pd.Series, state: pd.Series) -> pd.Series:
    """Fay-Herriot empirical-Bayes shrinkage of a small-area rate toward its STATE
    mean, weighted by reliability: shrunk = gamma*rate + (1-gamma)*mean_s, with
    gamma = tau_s^2 / (tau_s^2 + SE^2) and tau_s^2 = max(0, Var(rate) - mean(SE^2))
    estimated per state (method of moments). Noisy (small-pop) ZCTAs shrink hard;
    well-measured ones keep their own value. Rows without an SE are left untouched."""
    out = rate.copy()
    df = pd.DataFrame({"r": rate, "se": se, "st": state})
    for st, g in df.groupby("st"):
        v = g["r"].notna() & g["se"].notna()
        if v.sum() < 5:
            continue
        r, s = g.loc[v, "r"], g.loc[v, "se"]
        m = r.mean()
        tau2 = max(0.0, r.var() - (s ** 2).mean())
        gamma = tau2 / (tau2 + s ** 2)
        out.loc[r.index] = gamma * r + (1 - gamma) * m
    return out.clip(0, 1)


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

    # Call 1: detailed table vars (+ poverty margins for shrinkage; well under the 50 cap)
    pov_total_m = config.ACS_VAR_POVERTY_TOTAL[:-1] + "M"
    pov_below_m = config.ACS_VAR_POVERTY_BELOW[:-1] + "M"
    det_vars = [config.ACS_VAR_MEDIAN_INCOME, config.ACS_VAR_POVERTY_TOTAL,
                config.ACS_VAR_POVERTY_BELOW, config.ACS_VAR_POPULATION,
                config.ACS_VAR_MEDIAN_AGE]
    log("acs", "fetching detailed table (income/poverty/population), national ZCTA...")
    det = _rows_to_df(_census_get(config.ACS_BASE_DETAILED,
                                  {"get": ",".join(det_vars + [pov_total_m, pov_below_m]),
                                   "for": f"{GEO}:*"}))

    # Call 2: B27001 whole group for uninsured
    log("acs", "fetching B27001 group (uninsured), national ZCTA...")
    grp = _rows_to_df(_census_get(config.ACS_BASE_DETAILED,
                                  {"get": "group(B27001)", "for": f"{GEO}:*"}))

    det["zcta5"] = norm_zcta(det[GEO])
    grp["zcta5"] = norm_zcta(grp[GEO])

    df = det[["zcta5"] + det_vars + [pov_total_m, pov_below_m]].copy()
    df["median_income"] = scrub_sentinels(df[config.ACS_VAR_MEDIAN_INCOME])
    pov_total = scrub_sentinels(df[config.ACS_VAR_POVERTY_TOTAL])
    pov_below = scrub_sentinels(df[config.ACS_VAR_POVERTY_BELOW])
    df["poverty_rate"] = (pov_below / pov_total).where(pov_total > 0)
    df["poverty_rate_se"] = _proportion_se(_moe(df[pov_below_m]), _moe(df[pov_total_m]),
                                           df["poverty_rate"], pov_total)
    df["population"] = scrub_sentinels(df[config.ACS_VAR_POPULATION])
    df["median_age"] = scrub_sentinels(df[config.ACS_VAR_MEDIAN_AGE])

    # uninsured = sum(no-coverage members) / B27001_001E   -> fraction (+ SE from margins)
    denom = scrub_sentinels(grp["B27001_001E"])
    nocov = grp[resolved["no_cov"]].apply(scrub_sentinels).sum(axis=1, min_count=1)
    moe_nocov = np.sqrt((grp[[m[:-1] + "M" for m in resolved["no_cov"]]]
                         .apply(_moe) ** 2).sum(axis=1, min_count=1))
    unins = pd.DataFrame({"zcta5": grp["zcta5"],
                          "uninsured_rate": (nocov / denom).where(denom > 0)})
    unins["uninsured_rate_se"] = _proportion_se(moe_nocov, _moe(grp["B27001_001M"]),
                                                unins["uninsured_rate"], denom)
    df = df.merge(unins, on="zcta5", how="left")

    keep = ["zcta5", "median_income", "poverty_rate", "poverty_rate_se",
            "uninsured_rate", "uninsured_rate_se", "population", "median_age"]
    df = df[keep]

    # SVI-style rates from detailed B-tables (each its own group() call) + their SEs.
    svi = _fetch_svi_rates()
    if svi is not None:
        df = df.merge(svi, on="zcta5", how="left")

    # ---- empirical-Bayes shrinkage of the noisy [0,1] rates toward the state mean ----
    df = _apply_shrinkage(df)

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
    """One group() call per ACS table -> a fraction rate + its SE (from the table's
    margins). Failures are skipped (the hierarchical score averages over whichever
    members are present)."""
    frames: list[pd.DataFrame] = []
    for name, (table, nums, denom) in config.ACS_SVI.items():
        try:
            grp = _rows_to_df(_census_get(config.ACS_BASE_DETAILED,
                                          {"get": f"group({table})", "for": f"{GEO}:*"}))
            grp["zcta5"] = norm_zcta(grp[GEO])
            den = scrub_sentinels(grp[f"{table}_{denom}E"])
            moe_den = _moe(grp[f"{table}_{denom}M"])
            if name == "pct_minority":
                white = scrub_sentinels(grp[f"{table}_003E"])
                rate = ((den - white) / den).where(den > 0)
                moe_num = np.sqrt(moe_den ** 2 + _moe(grp[f"{table}_003M"]) ** 2)  # complement
            else:
                num = grp[[f"{table}_{s}E" for s in nums]].apply(scrub_sentinels).sum(axis=1, min_count=1)
                moe_num = np.sqrt((grp[[f"{table}_{s}M" for s in nums]].apply(_moe) ** 2)
                                  .sum(axis=1, min_count=1))
                rate = (num / den).where(den > 0)
            rate = rate.clip(0, 1)
            se = _proportion_se(moe_num, moe_den, rate, den)
            frames.append(pd.DataFrame({"zcta5": grp["zcta5"], name: rate, f"{name}_se": se}))
            log("acs", f"  svi {name}: median {rate.median():.3f}")
        except Exception as e:  # noqa: BLE001
            log("acs", f"  svi {name}: FAILED ({type(e).__name__}); skipping")
    if not frames:
        return None
    out = frames[0]
    for f in frames[1:]:
        out = out.merge(f, on="zcta5", how="outer")
    return out


def _local_group(zcta5: pd.Series, min_per_county: int = 8) -> pd.Series:
    """Shrinkage group key per ZCTA: its county (from the geonames crosswalk) when that
    county has >= min_per_county ZCTAs to estimate a stable mean, else the state. Falls
    back to state entirely if geonames isn't built yet."""
    state = zcta5.map(zip3_to_state)
    geo_path = config.PROCESSED / "geonames.parquet"
    if not geo_path.exists():
        return "ST:" + state.fillna("?")
    geo = pd.read_parquet(geo_path)[["zcta5", "county_fips"]]
    cf = zcta5.to_frame("zcta5").merge(geo, on="zcta5", how="left")["county_fips"]
    big = cf.value_counts()
    big = set(big[big >= min_per_county].index)
    return pd.Series(
        ["CO:" + c if (c in big) else "ST:" + (s if isinstance(s, str) else "?")
         for c, s in zip(cf, state)],
        index=zcta5.index,
    )


def _apply_shrinkage(df: pd.DataFrame) -> pd.DataFrame:
    """Shrink every rate that has a sibling `<rate>_se` column (Fay-Herriot, state-grouped),
    then drop the SE helper columns so the output schema is unchanged. Records how far the
    low-population ZCTAs moved - that is the point: their noise is pulled toward the state."""
    df = df.reset_index(drop=True)
    # Shrink toward the finest stable local mean: county where it has enough ZCTAs to
    # estimate one, else state. County preserves real sub-state variation that shrinking
    # to the whole state would wash out.
    group = _local_group(df["zcta5"])
    rate_cols = [c[:-3] for c in df.columns if c.endswith("_se") and c[:-3] in df.columns]
    moved = {}
    for col in rate_cols:
        before = df[col].copy()
        df[col] = _eb_shrink(df[col], df[f"{col}_se"], group)
        moved[col] = round(float((df[col] - before).abs().mean()), 4)
    df = df.drop(columns=[f"{c}_se" for c in rate_cols])
    log("acs", f"EB-shrinkage applied to {len(rate_cols)} rates; mean |Δ| per rate: {moved}")
    write_provenance({"acs_shrinkage": {"method": "Fay-Herriot EB toward state mean (MOE-weighted)",
                                        "rates": rate_cols, "mean_abs_shift": moved}})
    return df


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

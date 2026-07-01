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

import os
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


def _fh_solve(r: np.ndarray, s2: np.ndarray) -> tuple[float, float]:
    """Full Fay-Herriot moment fit for one group: jointly solve the between-area variance tau^2
    and the GLS mean m. Model r_i = mu + b_i + e_i, b_i ~ N(0,tau^2), e_i ~ N(0,SE_i^2). The
    estimator finds tau^2 satisfying the moment condition Sum (r_i-m)^2/(tau^2+SE_i^2) = n-1
    with m the precision-weighted mean using weights 1/(tau^2+SE_i^2) - so the mean and tau^2
    are mutually consistent (unlike a precision-weighted mean paired with an unweighted MoM
    tau^2). g(tau^2) is monotone decreasing, so solve by bracketed bisection. tau^2=0 when the
    between-area spread is fully explained by sampling error (full shrinkage to the GLS mean)."""
    n = len(r)

    def g(tau2: float) -> float:
        prec = 1.0 / (tau2 + s2)
        m = (prec * r).sum() / prec.sum()
        return float((prec * (r - m) ** 2).sum() - (n - 1))

    if g(0.0) <= 0.0:
        tau2 = 0.0
    else:
        lo, hi = 0.0, max(1e-8, float(r.var()) * 10 + float(s2.max()))
        tries = 0
        while g(hi) > 0 and tries < 60:
            hi *= 2.0
            tries += 1
        for _ in range(80):
            mid = (lo + hi) / 2.0
            if g(mid) > 0:
                lo = mid
            else:
                hi = mid
        tau2 = (lo + hi) / 2.0
    prec = 1.0 / (tau2 + s2)
    m = float((prec * r).sum() / prec.sum())
    return tau2, m


def _eb_shrink(rate: pd.Series, se: pd.Series, group: pd.Series) -> pd.Series:
    """Fay-Herriot empirical-Bayes shrinkage of a small-area rate toward its LOCAL group mean
    (county where stable, else state - the key is supplied by _local_group), weighted by
    reliability: shrunk = gamma*rate + (1-gamma)*m, gamma = tau^2/(tau^2+SE^2). Noisy (small-pop)
    ZCTAs shrink hard toward the group mean; well-measured ones keep their own value. Rows
    without an SE are left untouched; groups with < 5 valid units are skipped.

    tau^2 and the target mean m are fit jointly per group by the full FH moment estimator
    (_fh_solve), so the precision weighting is internally consistent end to end."""
    out = rate.copy()
    df = pd.DataFrame({"r": rate, "se": se, "grp": group})
    for _key, g in df.groupby("grp"):
        v = g["r"].notna() & g["se"].notna() & (g["se"] > 0)
        if v.sum() < 5:
            continue
        r = g.loc[v, "r"].to_numpy(float)
        s2 = g.loc[v, "se"].to_numpy(float) ** 2
        tau2, m = _fh_solve(r, s2)
        gamma = tau2 / (tau2 + s2)
        out.loc[g.loc[v].index] = gamma * r + (1 - gamma) * m
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

    # ---- empirical-Bayes shrinkage of the noisy [0,1] rates toward their local mean ----
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


# B03002 (Hispanic origin by race) member suffixes -> the five context buckets the detail
# panel shows. Non-Hispanic single-race for white/black/asian; 012 = Hispanic/Latino (any
# race); "other" = AIAN(005) + NHPI(007) + some-other-race(008) + two-or-more(009), all NH.
_RACE_BUCKETS = {
    "pct_white": ["003"],
    "pct_black": ["004"],
    "pct_asian": ["006"],
    "pct_hispanic": ["012"],
    "pct_other_race": ["005", "007", "008", "009"],
}


def _fetch_svi_rates() -> pd.DataFrame | None:
    """One group() call per ACS table -> a fraction rate + its SE (from the table's margins).
    A CONTEXT-only table's failure is skipped, but a SCORED input's failure is fatal: silently
    dropping it would ship a different, degraded, non-deterministic composite between runs."""
    from .taxonomy import subscore_specs
    scored_inputs = {m["col"] for s in subscore_specs() if s.get("scored", True) for m in s["members"]}
    frames: list[pd.DataFrame] = []
    for name, (table, nums, denom) in config.ACS_SVI.items():
        try:
            grp = _rows_to_df(_census_get(config.ACS_BASE_DETAILED,
                                          {"get": f"group({table})", "for": f"{GEO}:*"}))
            grp["zcta5"] = norm_zcta(grp[GEO])
            den = scrub_sentinels(grp[f"{table}_{denom}E"])
            moe_den = _moe(grp[f"{table}_{denom}M"])
            extra: dict[str, pd.Series] = {}
            if name == "pct_minority":
                white = scrub_sentinels(grp[f"{table}_003E"])
                rate = ((den - white) / den).where(den > 0)
                moe_num = np.sqrt(moe_den ** 2 + _moe(grp[f"{table}_003M"]) ** 2)  # complement
                # Race/ethnicity composition (context only, never scored) from the same B03002
                # group already fetched here. Non-Hispanic single-race buckets + Hispanic (any
                # race); "other" rolls up AIAN/NHPI/some-other/two-or-more so the five sum to ~1.
                for col, mems in _RACE_BUCKETS.items():
                    rnum = (grp[[f"{table}_{s}E" for s in mems]].apply(scrub_sentinels)
                            .sum(axis=1, min_count=1))
                    extra[col] = (rnum / den).where(den > 0).clip(0, 1)
            else:
                num = grp[[f"{table}_{s}E" for s in nums]].apply(scrub_sentinels).sum(axis=1, min_count=1)
                moe_num = np.sqrt((grp[[f"{table}_{s}M" for s in nums]].apply(_moe) ** 2)
                                  .sum(axis=1, min_count=1))
                rate = (num / den).where(den > 0)
            rate = rate.clip(0, 1)
            se = _proportion_se(moe_num, moe_den, rate, den)
            frames.append(pd.DataFrame({"zcta5": grp["zcta5"], name: rate, f"{name}_se": se, **extra}))
            log("acs", f"  svi {name}: median {rate.median():.3f}")
        except Exception as e:  # noqa: BLE001
            if name in scored_inputs:
                die("acs", f"scored SVI input {name} failed ({type(e).__name__}: {e}) - dropping it "
                           "would silently ship a degraded, non-deterministic composite")
            log("acs", f"  svi {name}: FAILED ({type(e).__name__}); skipping (context-only)")
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
    """Shrink every rate that has a sibling `<rate>_se` column (Fay-Herriot, grouped by the
    local key from `_local_group` - county where stable, else state), emit a per-ZCTA
    `acs_input_cv` from the *raw published* SE, then drop the SE helper columns. Records how far
    the low-population ZCTAs moved - that is the point: their noise is pulled toward the local mean.

    The CV uses the RAW SE (not the post-shrinkage posterior SD): it is the honest 'how
    precisely do we measure this ZCTA's inputs' that feeds the Layer-B rank bands, so noisy
    (low-pop) ZCTAs get wider bands. Shrinkage's own value is a point-estimate improvement
    (validated separately in Layer 0 against outcomes), not a band-narrowing - using the
    posterior SD here would invert the confidence ordering (heavy shrinkage collapses the
    band of the noisiest ZCTAs below the well-measured ones). See docs/DECISIONS.md B."""
    df = df.reset_index(drop=True)
    # Shrink toward the finest stable local mean: county where it has enough ZCTAs to
    # estimate one, else state. County preserves real sub-state variation that shrinking
    # to the whole state would wash out.
    group = _local_group(df["zcta5"])
    rate_cols = [c[:-3] for c in df.columns if c.endswith("_se") and c[:-3] in df.columns]

    # Per-ZCTA input-noise summary fed to the Layer-B rank bands: mean coefficient of
    # variation (raw SE / pre-shrinkage estimate) across the scored rates. Computed BEFORE
    # shrinkage smooths the estimate. Per-rate CV clipped to [0,2] so a near-zero denominator
    # can't blow up the mean. See docs/DECISIONS.md B1.
    cvs = []
    for col in rate_cols:
        est = df[col].where(df[col] > 0)
        cvs.append((df[f"{col}_se"] / est).clip(0, 2))
    df["acs_input_cv"] = pd.concat(cvs, axis=1).mean(axis=1, skipna=True) if cvs else np.nan

    # Debug-only (HAM_SE_DEBUG=1): dump per-rate raw estimate + raw SE so the Layer-B gate-3
    # calibration can resample real inputs without a re-fetch. Gitignored, never shipped.
    if os.environ.get("HAM_SE_DEBUG"):
        dbg = {"zcta5": df["zcta5"]}
        for col in rate_cols:
            dbg[col] = df[col]
            dbg[f"{col}_se"] = df[f"{col}_se"]
        pd.DataFrame(dbg).to_parquet(config.PROCESSED / "acs_se_debug.parquet", index=False)
        log("acs", f"HAM_SE_DEBUG: wrote acs_se_debug.parquet ({len(rate_cols)} rates)")

    moved = {}
    for col in rate_cols:
        before = df[col].copy()
        df[col] = _eb_shrink(df[col], df[f"{col}_se"], group)
        moved[col] = round(float((df[col] - before).abs().mean()), 4)
    df = df.drop(columns=[f"{c}_se" for c in rate_cols])
    log("acs", f"EB-shrinkage applied to {len(rate_cols)} rates; mean |Δ| per rate: {moved}")
    write_provenance({"acs_shrinkage": {"method": "Fay-Herriot EB (joint iterative tau^2 + GLS mean) toward county/state local mean",
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

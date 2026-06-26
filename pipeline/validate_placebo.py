"""validate_placebo: the negative-control (placebo-outcome) test that separates ACCESS from
DEPRIVATION.

Every prior validation shows the index correlates with bad health outcomes. The hostile-but-
fair critique that survives all of it is: *of course it does - it's a poverty/deprivation
gradient, and poverty predicts everything bad.* Within-county and amenable-mortality work shows
the access component is statistically distinct, but distinct is not the same as access-specific.

A negative-control design answers it directly. Split mortality into two buckets that are BOTH
strongly deprivation-loaded but differ on one axis - whether timely ambulatory care can prevent
the death:

  * ACCESS-SENSITIVE (the real target): ambulatory-care-sensitive deaths - diabetes (DIA),
    heart disease (HTD), chronic lower-respiratory/COPD (CLD), stroke (STK). Timely primary
    care, medication, and disease management prevent these.
  * PLACEBO / ACCESS-INSENSITIVE (the control): external-cause deaths - unintentional injury
    (INJ), homicide (HOM), suicide (SUI). These track poverty just as hard, but a primary-care
    clinic does not prevent a car crash or an assault.

If the index is "just deprivation," it predicts both buckets equally (differential r ~= 0). If
it carries genuine ACCESS signal, it predicts the access-sensitive bucket MORE than the placebo
(differential r > 0) - and that excess must concentrate in the CARE-ACCESS dimension, not in the
health-need/deprivation dimension. We report the per-dimension differential with a county-cluster
bootstrap CI on care_access; a CI excluding 0 is the evidence that the care-access signal is
access-specific, not a restatement of poverty.

Honest limits, stated in the output: injury includes drug-poisoning, which has a real SUD-access
component, and suicide has a mental-health-care component - so the placebo is conservative
(slightly access-contaminated), which biases the differential test TOWARD the null, not away
from it. Homicide is the cleanest placebo but too sparse alone. California only (the cached
ZIP-level vital-records file with cause detail); age-adjusted because injury skews young and ACSC
skews old. Read-only; never feeds the composite.

    python -m pipeline.validate_placebo
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common import download_file, log
from .taxonomy import DIMENSIONS, subscore_specs
from .validation_stats import pearson_corr as _corr
from .validation_stats import within_residual as _within
from .validate_subcounty import (
    CA_DEATHS_CACHE, CA_DEATHS_URL, MIN_POP, METRICS,
)

ACSC_CAUSES = ("DIA", "HTD", "CLD", "STK")          # access-sensitive (ambulatory-care preventable)
PLACEBO_CAUSES = ("INJ", "HOM", "SUI")              # access-insensitive external causes (control)
DIM_COLS = [f"{d}_pctile" for d in DIMENSIONS]
N_BOOT = 1000
MIN_COUNTY_ZCTAS = 3                                # so the within-county residual is well-defined


def _fetch_ca_cause_counts(causes: tuple[str, ...]) -> pd.DataFrame:
    """Pooled 2019-2024 CA death counts (Total Population strata) summed over `causes`, per ZIP.
    Suppressed small cells are NaN in the source and drop out of the sum."""
    if not CA_DEATHS_CACHE.exists():
        log("placebo", "downloading CA CHHS deaths-by-ZIP (one-time, ~48MB)...")
        download_file(CA_DEATHS_URL, CA_DEATHS_CACHE, min_bytes=1_000_000)
    df = pd.read_csv(CA_DEATHS_CACHE, dtype=str)
    df = df[(df["Strata"] == "Total Population") & df["Cause"].isin(causes)].copy()
    df["Count"] = pd.to_numeric(df["Count"], errors="coerce")
    df["zcta5"] = df["ZIP_Code"].astype(str).str.zfill(5)
    return df.groupby("zcta5")["Count"].sum().rename("deaths").reset_index()


def _resid_age(j: pd.DataFrame, col: str) -> np.ndarray:
    """Within-county residual of `col`, then linearly residualized on age65_rate (also within-
    county). The same age-adjustment used by the CA sub-county validator - injury mortality skews
    young and ACSC mortality skews old, so age must come out of BOTH outcome and index column."""
    y, a = _within(j, col), _within(j, "age65_rate")
    mk = ~(np.isnan(y) | np.isnan(a))
    out = np.full(len(y), np.nan)
    if mk.sum() > 50:
        b = np.polyfit(a[mk], y[mk], 1)
        out[mk] = y[mk] - np.polyval(b, a[mk])
    return out


def _build_frame() -> pd.DataFrame:
    """Index frame joined to per-ZIP ACSC and placebo mortality rates (per 1k residents), kept to
    multi-ZCTA counties where BOTH buckets are observed so the differential is on a common set."""
    if not METRICS.exists():
        raise SystemExit(f"missing {METRICS}; run the pipeline first")
    acsc = _fetch_ca_cause_counts(ACSC_CAUSES).rename(columns={"deaths": "acsc_deaths"})
    plac = _fetch_ca_cause_counts(PLACEBO_CAUSES).rename(columns={"deaths": "placebo_deaths"})
    m = pd.read_parquet(METRICS)
    m = m[m["scoreable"] == True].copy()  # noqa: E712
    m["zcta5"] = m["zcta5"].astype(str)
    j = m.merge(acsc, on="zcta5", how="inner").merge(plac, on="zcta5", how="inner")
    j["pop"] = pd.to_numeric(j["population"], errors="coerce")
    # require BOTH outcomes observed (>0) so r(acsc) and r(placebo) compare like with like
    j = j[(j["pop"] >= MIN_POP) & (j["acsc_deaths"] > 0) & (j["placebo_deaths"] > 0)].copy()
    if "age65_rate" not in j.columns:
        raise SystemExit("age65_rate missing; placebo test needs it for age adjustment")
    j["acsc_rate"] = j["acsc_deaths"] / j["pop"] * 1000.0
    j["placebo_rate"] = j["placebo_deaths"] / j["pop"] * 1000.0
    vc = j["county_fips"].value_counts()
    j = j[j["county_fips"].isin(vc[vc >= MIN_COUNTY_ZCTAS].index)].copy()
    return j.reset_index(drop=True)


def _differential(j: pd.DataFrame, col: str) -> tuple[float, float, float]:
    """(r vs access-sensitive, r vs placebo, differential) for one index column, age-adjusted
    within county. The differential r_acsc - r_placebo is the access-specific signal."""
    ya, yp = _resid_age(j, "acsc_rate"), _resid_age(j, "placebo_rate")
    x = _resid_age(j, col)
    ra, rp = _corr(x, ya), _corr(x, yp)
    return ra, rp, ra - rp


def _bootstrap_diff(j: pd.DataFrame, col: str, n: int = N_BOOT) -> tuple[float, float]:
    """County-cluster bootstrap 95% CI on the differential r_acsc - r_placebo. Resamples whole
    counties with replacement (spatial clustering), re-does the age-adjustment on each resample."""
    counties = j["county_fips"].unique()
    groups = {c: g for c, g in j.groupby("county_fips")}
    rng = np.random.default_rng(20260625)
    diffs = []
    for _ in range(n):
        pick = rng.choice(counties, size=len(counties), replace=True)
        # re-label resampled counties uniquely so a county drawn twice yields two fixed effects
        boot = pd.concat([groups[c].assign(county_fips=f"{c}__{i}") for i, c in enumerate(pick)],
                         ignore_index=True)
        _, _, d = _differential(boot, col)
        if not np.isnan(d):
            diffs.append(d)
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return float(lo), float(hi)


def run() -> dict:
    j = _build_frame()
    n_cty = j["county_fips"].nunique()
    log("placebo", f"CA: {len(j)} ZCTAs / {n_cty} multi-ZCTA counties (both buckets observed)")

    # care_access_resid = the access-beyond-deprivation lens (care_access residualized on
    # need+vulnerability). It is the a-priori-correct column for an "is it access, not poverty"
    # test, since the placebo and the raw dimensions all share the deprivation gradient we want OUT.
    cols = (DIM_COLS + ["care_access_resid_pctile"]
            + [f"{s['key']}_pctile" for s in subscore_specs()] + ["access_gap_score"])
    cols = [c for c in cols if c in j.columns]
    rep = {
        "n": len(j), "counties": int(n_cty),
        "access_sensitive": "CA ACSC mortality (DIA/HTD/CLD/STK, 2019-2024), age-adjusted",
        "placebo": "CA external-cause mortality (INJ/HOM/SUI), age-adjusted",
        "rows": {},
    }
    print("\n=== NEGATIVE-CONTROL (placebo) validation - is it ACCESS or just DEPRIVATION? ===")
    print(f"  CA, {len(j)} ZCTAs / {n_cty} counties, age-adjusted within county")
    print("  access-sensitive = ACSC deaths (DIA/HTD/CLD/STK); placebo = external (INJ/HOM/SUI)\n")
    print(f"  {'column':30s} {'r:ACSC':>8s} {'r:placebo':>10s} {'DIFFERENTIAL':>13s}")
    for c in cols:
        ra, rp, d = _differential(j, c)
        rep["rows"][c] = {"r_acsc": round(ra, 3), "r_placebo": round(rp, 3), "diff": round(d, 3)}
        print(f"  {c:30s} {ra:+8.3f} {rp:+10.3f} {d:+13.3f}")

    # the decisive inferential test: care_access (and the composite) must beat its own placebo
    print("\n  --- county-cluster bootstrap 95% CI on the differential (access-specific signal) ---")
    rep["bootstrap"] = {}
    for c in ("access_gap_score", "care_access_pctile", "care_access_resid_pctile",
              "health_need_pctile", "social_vulnerability_pctile"):
        if c not in j.columns:
            continue
        _, _, d = _differential(j, c)
        lo, hi = _bootstrap_diff(j, c)
        excl = lo > 0
        rep["bootstrap"][c] = {"diff": round(d, 3), "ci": [round(lo, 3), round(hi, 3)],
                               "excludes_zero": bool(excl)}
        flag = "  <-- access-specific (CI > 0)" if excl else ("  <-- predicts both equally"
                                                              if hi > 0 > lo else "")
        print(f"  {c:30s} diff {d:+.3f}  CI [{lo:+.3f}, {hi:+.3f}]{flag}")
    print("\n  Reading: a deprivation gradient predicts ACSC and placebo deaths EQUALLY (diff ~ 0).\n"
          "  A positive differential concentrated in care_access (CI excluding 0) is signal that\n"
          "  the access dimension predicts the PREVENTABLE deaths specifically - access, not poverty.\n"
          "  The placebo is conservative (injury/suicide carry some SUD/MH-access content), so this\n"
          "  test is biased toward the null.")
    return rep


if __name__ == "__main__":
    run()

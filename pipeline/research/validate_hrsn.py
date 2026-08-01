"""validate_hrsn: gate-test the CDC PLACES 2025 HRSN measures as candidate barrier inputs.

PLACES 2025 (Socrata qnzd-25i4) publishes seven Health-Related Social Needs measures at
ZCTA resolution - transportation barriers, food insecurity, housing insecurity, utility
shut-off threat, loneliness/social isolation, food stamps, lack of emotional support.
"Lack of reliable transportation" is the headline candidate: a direct transportation-
barrier-to-care construct the index currently only proxies (no_vehicle_rate).

Each measure faces the same kill test that felled ACS Medicaid coverage (+0.28 raw ->
-0.06 partial): PARTIAL r vs amenable mortality controlling for all three dimension
percentiles. A raw correlation is cheap - everything deprivation-shaped correlates with
mortality; the question is whether the measure adds signal BEYOND what the index already
encodes. Also reported: within-county r vs life expectancy (the sub-county signal test
county-level outcomes cannot see) and the collinearity profile vs the three dimensions.
The transportation measure gets a county-cluster bootstrap 95% CI on its partial r.

Two circularity caveats bound any SURVIVES verdict:
  1. Model-on-model: PLACES HRSN estimates come from the same SAE machinery (BRFSS +
     ACS covariates) as the PLACES inputs inside health_need, so shared modeled variance
     can masquerade as signal.
  2. Already-an-input: these seven measures ARE the social_needs sub-score inside
     social_vulnerability (metrics carries foodinsecu_pct, lacktrpt_pct, ...), so the
     partial is partly conditioning the candidate on itself - which biases the partial
     TOWARD zero. A collapse here is therefore expected, not merely damning; a survival
     would be strong.

Read-only against the composite; never feeds it.

    python -m pipeline.validate_hrsn [n_boot]   # default 500
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from .. import config
from ..bootstrap_gate import _cluster_groups, _partial_corr
from ..common import log
from ..validation_stats import pearson_corr as _corr
from ..validation_stats import within_residual as _within

METRICS = config.PROCESSED / "metrics.parquet"
HRSN_CACHE = config.RAW / "places_hrsn_zcta_2025.parquet"
PLACES_ZCTA_2025 = "https://data.cdc.gov/resource/qnzd-25i4.json"
# The seven PLACES HRSN (categoryid=SOCLNEED) measures, all CrdPrv, ~24k ZCTAs each.
HRSN_MEASURES = {
    "LACKTRPT": "transportation",
    "FOODINSECU": "food_insecurity",
    "HOUSINSECU": "housing_insecurity",
    "SHUTUTILITY": "utility_shutoff",
    "LONELINESS": "social_isolation",
    "FOODSTAMP": "food_stamps",
    "EMOTIONSPT": "no_emotional_support",
}
DIM_COLS = ["health_need_pctile", "social_vulnerability_pctile", "care_access_pctile"]
MIN_POP = 1000   # same low-confidence floor as validate_subcounty
PAGE = 50000


def _fetch_hrsn() -> pd.DataFrame:
    """Pull the SOCLNEED category (crude prevalence) from the PLACES ZCTA 2025 release,
    pivot to one row per ZCTA, and cache the wide frame."""
    if HRSN_CACHE.exists():
        return pd.read_parquet(HRSN_CACHE)
    log("hrsn", "fetching PLACES 2025 HRSN measures by ZCTA (one-time)...")
    rows, off = [], 0
    while True:
        q = {"$where": "categoryid='SOCLNEED' AND datavaluetypeid='CrdPrv'",
             "$select": "locationname,measureid,data_value",
             "$limit": PAGE, "$offset": off}
        url = PLACES_ZCTA_2025 + "?" + urllib.parse.urlencode(q)
        with urllib.request.urlopen(url, timeout=120) as r:
            chunk = json.load(r)
        rows += chunk
        if len(chunk) < PAGE:
            break
        off += PAGE
    df = pd.DataFrame(rows)
    df["zcta5"] = df["locationname"].astype(str).str.zfill(5)
    df["data_value"] = pd.to_numeric(df["data_value"], errors="coerce")
    wide = (df.pivot_table(index="zcta5", columns="measureid", values="data_value")
              .rename(columns=HRSN_MEASURES).reset_index())
    HRSN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    wide.to_parquet(HRSN_CACHE, index=False)
    log("hrsn", f"cached {len(wide)} ZCTAs x {len(wide.columns) - 1} measures -> {HRSN_CACHE.name}")
    return wide


def _boot_partial_ci(d: pd.DataFrame, c: np.ndarray, y: np.ndarray, Z: np.ndarray,
                     n_boot: int, seed: int = 0) -> list[float]:
    """County-cluster bootstrap 95% CI on partial r(y, c | Z) - same blocking as
    bootstrap_gate (state|county_name), so within-county pseudo-replication is respected."""
    groups = _cluster_groups(d)
    rng = np.random.default_rng(seed)
    boot = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        ridx = np.concatenate([groups[i] for i in pick])
        boot.append(_partial_corr(y[ridx], c[ridx], Z[ridx]))
    a = np.asarray(boot, float)
    a = a[~np.isnan(a)]
    return [round(float(np.percentile(a, 2.5)), 3), round(float(np.percentile(a, 97.5)), 3)]


def run(n_boot: int = 500) -> dict:
    if not METRICS.exists():
        raise SystemExit(f"missing {METRICS}; run the pipeline first")
    hrsn = _fetch_hrsn()
    m = pd.read_parquet(METRICS)
    m = m[m["scoreable"] == True].copy()  # noqa: E712
    m["zcta5"] = m["zcta5"].astype(str)
    d = m.merge(hrsn, on="zcta5", how="inner", suffixes=("", "_hrsn2025")).reset_index(drop=True)
    measures = [v for v in HRSN_MEASURES.values() if v in d.columns]
    log("hrsn", f"{len(d)} scoreable ZCTAs joined ({len(measures)} HRSN measures)")

    y = d["amenable_mortality"].to_numpy(float)          # higher = worse (county broadcast)
    Z = d[DIM_COLS].to_numpy(float)

    # within-county frame: LE negated so higher = worse, multi-ZCTA counties only
    w = d[d["life_expectancy"].notna() & (d["population"] >= MIN_POP)].copy()
    w["le_worse"] = -w["life_expectancy"]
    vc = w["county_fips"].value_counts()
    w = w[w["county_fips"].isin(vc[vc >= 3].index)].copy()
    yw = _within(w, "le_worse")

    report = {"source": "PLACES ZCTA 2025 (qnzd-25i4), SOCLNEED crude prevalence",
              "controls": DIM_COLS, "n_zctas": int(len(d)),
              "within_county": {"n": int(len(w)), "counties": int(w["county_fips"].nunique())},
              "measures": {}}
    for name in measures:
        c = d[name].to_numpy(float)
        row = {
            "raw_r": round(_corr(c, y), 3),
            "partial_r": round(_partial_corr(y, c, Z), 3),
            "within_county_r": round(_corr(_within(w, name), yw), 3),
            "dim_corr": {dc: round(_corr(c, Z[:, j]), 3) for j, dc in enumerate(DIM_COLS)},
        }
        if name == "transportation":
            row["partial_ci95"] = _boot_partial_ci(d, c, y, Z, n_boot)
        report["measures"][name] = row

    _print(report)
    return report


def _print(r: dict) -> None:
    print("\n=== HRSN GATE: PLACES 2025 social-needs measures vs amenable mortality ===")
    print(f"  {r['n_zctas']} scoreable ZCTAs; partial controls = need, vulnerability, care access")
    w = r["within_county"]
    print(f"  within-county ruler: -life_expectancy, {w['n']} ZCTAs / {w['counties']} counties (>=3 ZCTAs)\n")
    print(f"  {'measure':22s} {'raw_r':>7s} {'partial_r':>10s} {'95% CI':>17s} {'within_r':>9s} "
          f"{'max_dim_corr':>13s}  verdict")
    for name, s in r["measures"].items():
        ci = s.get("partial_ci95")
        ci_txt = f"[{ci[0]:+.3f},{ci[1]:+.3f}]" if ci else ""
        maxd = max(s["dim_corr"].items(), key=lambda kv: abs(kv[1]))
        ci_ok = ci is None or ci[0] > 0
        verdict = "SURVIVES" if (s["partial_r"] > 0.05 and ci_ok) else "COLLAPSES"
        print(f"  {name:22s} {s['raw_r']:+7.3f} {s['partial_r']:+10.3f} {ci_txt:>17s} "
              f"{s['within_county_r']:+9.3f} {maxd[1]:+.3f} ({maxd[0].split('_pctile')[0][:9]})"
              f"  {verdict}")
    print("\n  Kill test: partial r > +0.05 (CI excluding 0 where bootstrapped) AND correctly "
          "signed.\n  Caveats: (1) PLACES HRSN shares SAE machinery with the health_need inputs "
          "(model-on-model);\n  (2) these measures already feed social_needs inside "
          "social_vulnerability, so the partial\n  partly conditions the candidate on itself - "
          "collapse is the expected outcome here.")


if __name__ == "__main__":
    run(n_boot=int(sys.argv[1]) if len(sys.argv) > 1 else 500)

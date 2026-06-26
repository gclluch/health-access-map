"""validate_acceptability: a time-boxed research spike on the ACCEPTABILITY axis (BACKLOG C1) -
does "will a local provider actually see a Medicaid patient?" add signal beyond the deprivation
gradient + raw provider supply? VALIDATION-ONLY; nothing here touches the score.

The scrape-to-calibrate idea: NY publishes its full Medicaid-enrolled provider directory (Socrata
keti-qx5t, ~1.1M rows). The per-ZIP **acceptance rate** = Medicaid-enrolled primary-care NPIs /
all local primary-care providers (NPPES) proxies willingness-to-accept, which a raw provider count
cannot see. We test it against an INDEPENDENT, access-sensitive outcome (NY SPARCS PQI_90 ACSC O/E,
the same ruler validate_subcounty uses) with a partial correlation that controls for need, social
vulnerability, AND care_access (supply). If acceptance only echoes supply/deprivation it collapses;
if it carries its own protective signal the partial r is negative with a CI excluding 0.

Direction: more acceptance -> better real access -> LOWER ACSC, so a real signal is partial r < 0.

Run: `python -m pipeline.validate_acceptability` (needs network; NY only). Memory says prior
acceptability probes collapsed in partial-r - this measures it cleanly and writes the number down.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from .bootstrap_gate import _cluster_groups, _corr, _partial_corr
from .common import http_client, log, norm_zcta
from .validate_subcounty import _fetch_ny_pqi

MEDICAID_URL = "https://health.data.ny.gov/resource/keti-qx5t.json"
PC_PROFESSIONS = ("PHYSICIAN", "NURSE PRACTITIONER", "PHYSICIAN ASSISTANT", "NURSE MIDWIFE")
CONTROLS = ["health_need_pctile", "social_vulnerability_pctile", "care_access_pctile"]


def _fetch_medicaid_pc_by_zip() -> pd.DataFrame:
    """Server-side: distinct Medicaid-enrolled primary-care NPIs per ZIP+4, summed to ZIP5."""
    where = " OR ".join(f"profession_or_service='{p}'" for p in PC_PROFESSIONS)
    params = {"$select": "zip_code, count(distinct npi) as n", "$where": where,
              "$group": "zip_code", "$limit": "50000"}
    with http_client() as c:
        r = c.get(MEDICAID_URL, params=params)
    if r.status_code != 200:
        raise RuntimeError(f"Medicaid fetch HTTP {r.status_code}: {r.text[:160]}")
    df = pd.DataFrame(r.json())
    df["zcta5"] = norm_zcta(df["zip_code"]).astype(str)
    df["n"] = pd.to_numeric(df["n"], errors="coerce")
    return df.groupby("zcta5", as_index=False)["n"].sum().rename(columns={"n": "medicaid_pc_npi"})


def _bootstrap_ci(d: pd.DataFrame, ycol: str, ccol: str, zcols: list[str],
                  n_boot: int = 1000, seed: int = 0) -> tuple[float, float, float]:
    y = d[ycol].to_numpy(float)
    c = d[ccol].to_numpy(float)
    Z = d[zcols].to_numpy(float)
    point = _partial_corr(y, c, Z)
    groups = _cluster_groups(d, "county")  # resample whole counties (spatial dependence)
    rng = np.random.default_rng(seed)
    boot = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        idx = np.concatenate([groups[i] for i in pick])
        boot.append(_partial_corr(y[idx], c[idx], Z[idx]))
    lo, hi = np.nanpercentile(boot, [2.5, 97.5])
    return point, float(lo), float(hi)


def build(dev_state: str | None = None, force: bool = False) -> None:
    log("acceptability", "fetching NY Medicaid-enrolled primary-care providers by ZIP...")
    med = _fetch_medicaid_pc_by_zip()
    log("acceptability", f"  {len(med)} NY ZIPs with Medicaid PC providers")

    df = pd.read_parquet(config.PROCESSED / "metrics.parquet")
    ny = df[df["state"] == "NY"][["zcta5", "providers_primary", "population",
                                  "county_name", "state", *CONTROLS]].copy()
    ny["zcta5"] = norm_zcta(ny["zcta5"]).astype(str)
    ny = ny.merge(med, on="zcta5", how="left")
    ny["medicaid_pc_npi"] = ny["medicaid_pc_npi"].fillna(0)
    # Acceptance RATE: Medicaid-enrolled PC NPIs / all local PC providers. Clip the upper tail
    # (cross-source NPI/location mismatch can push a few ZIPs slightly over 1).
    ny["acceptance"] = (ny["medicaid_pc_npi"] / ny["providers_primary"]).where(
        ny["providers_primary"] > 0).clip(0, 1.5)

    outcome = _fetch_ny_pqi().reset_index()  # zcta5 -> oe (risk-std ACSC; lower = better access)
    outcome["zcta5"] = outcome["zcta5"].astype(str)
    m = ny.merge(outcome[["zcta5", "oe"]], on="zcta5", how="inner").dropna(
        subset=["acceptance", "oe", *CONTROLS])
    log("acceptability", f"  {len(m)} NY ZIPs with acceptance + PQI outcome + controls")

    raw = _corr(m["acceptance"].to_numpy(float), m["oe"].to_numpy(float))
    point, lo, hi = _bootstrap_ci(m, "oe", "acceptance", CONTROLS)

    print("\n=== ACCEPTABILITY spike: NY Medicaid PC-acceptance rate vs ACSC (PQI_90 O/E) ===")
    print(f"  n ZIPs                : {len(m)}")
    print(f"  raw corr(accept, ACSC): {raw:+.3f}  (negative = more acceptance, less ACSC)")
    print(f"  partial r | need+vuln+care_access: {point:+.3f}  95% CI [{lo:+.3f}, {hi:+.3f}]")
    protective = hi < 0  # CI entirely below 0 => acceptance lowers ACSC net of supply+deprivation
    verdict = ("SURVIVES - acceptance carries protective signal beyond supply/deprivation; "
               "candidate for a future gated column (do NOT auto-add)."
               if protective else
               "COLLAPSES - no signal net of supply+deprivation (CI includes 0 / wrong sign). "
               "Matches the prior C1 finding; keep BLOCKED, document the number.")
    print(f"  VERDICT: {verdict}\n")
    return None


if __name__ == "__main__":
    build()

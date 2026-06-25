"""build_provider_capacity: CMS Medicare Physician & Other Practitioners (by-Provider) -> ZIP-level
ACTIVE clinical capacity, the answer to the index's oldest limitation ("a registered NPI is not an
FTE and says nothing about active volume or who it serves").

NPPES (build_providers) counts REGISTRATIONS. This stage counts what providers actually DID: the
file is claims-based, so an NPI only appears if it billed Medicare Part B FFS, and the numbers are
real served volume. Two new signals per ZIP:
  - capacity  = sum of Tot_Benes (distinct beneficiaries actually served) - a panel-size weight that
    replaces "1 NPI = 1 unit" with "how many patients this place actually carries".
  - dual_share = sum(Bene_Dual_Cnt)/sum(Tot_Benes) - the share of served beneficiaries who are
    Medicare-Medicaid DUAL eligibles. A provider serving many duals demonstrably accepts low-income
    patients, so this is the first free, national, provider-level ACCEPTABILITY proxy (the true
    Medicaid-participation registry, T-MSIS, is DUA-gated; this is the headless stand-in).

Free, no key, no DUA: resolved live from the CMS metastore (data.cms.gov/data.json) and streamed
with DuckDB (projecting 5 of 81 columns), exactly like the NPPES stage. Practice ZIP = NPPES ZIP, so
this WEIGHTS the existing supply points; it is not a patient-demand geography. Honest caveats encoded
downstream: FFS-only (excludes Medicare Advantage ~half of seniors + all commercial/uninsured, so it
is a RELATIVE capacity signal), and rows with <=10 beneficiaries are suppressed (drops the very
smallest/rural NPIs).

    python -m pipeline.build_provider_capacity
"""
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

import duckdb
import pandas as pd

from . import config
from .common import die, log

CMS_METASTORE = "https://data.cms.gov/data.json"
DATASET_TITLE = "Medicare Physician & Other Practitioners - by Provider"
RAW_CSV = config.RAW / "cms_phys_by_provider.csv"
OUT = config.PROCESSED / "provider_capacity.parquet"

# primary-care specialties (claims-derived Rndrng_Prvdr_Type) - the access-proximal subset, matching
# the spirit of build_providers' primary-care classification.
PRIMARY_CARE = (
    "Family Practice", "Internal Medicine", "General Practice", "Geriatric Medicine",
    "Pediatric Medicine", "Nurse Practitioner", "Physician Assistant", "Obstetrics & Gynecology",
)


def _resolve_csv_url() -> str:
    """Latest by-Provider CSV download URL from the CMS metastore (robust to per-release UUIDs)."""
    cat = json.load(urllib.request.urlopen(CMS_METASTORE, timeout=90))
    ds = [d for d in cat["dataset"] if d.get("title") == DATASET_TITLE]
    if not ds:
        die("capacity", f"CMS metastore has no dataset titled {DATASET_TITLE!r}")
    csvs = [di["downloadURL"] for di in ds[0]["distribution"]
            if di.get("format") == "CSV" and di.get("downloadURL")]
    if not csvs:
        die("capacity", "no CSV distribution on the by-Provider dataset")
    return csvs[0]  # newest release is first


def _download(url: str) -> Path:
    if RAW_CSV.exists() and RAW_CSV.stat().st_size > 10_000_000:
        log("capacity", f"using cached {RAW_CSV.name}")
        return RAW_CSV
    RAW_CSV.parent.mkdir(parents=True, exist_ok=True)
    log("capacity", f"downloading by-Provider CSV (~1.3M rows, one-time)...")
    subprocess.run(["curl", "-sL", "--max-time", "900", url, "-o", str(RAW_CSV)], check=True)
    return RAW_CSV


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("capacity", f"{OUT.name} exists; use force=True to rebuild")
        return str(OUT)
    csv_path = _download(_resolve_csv_url())
    pc = ",".join(f"'{s}'" for s in PRIMARY_CARE)
    log("capacity", "DuckDB streaming aggregate to ZIP...")
    con = duckdb.connect()
    df = con.execute(f"""
        SELECT
            substr(Rndrng_Prvdr_Zip5, 1, 5)                              AS zcta5,
            COUNT(*)                                                      AS cap_n_providers,
            SUM(TRY_CAST(Tot_Benes AS BIGINT))                           AS cap_benes,
            SUM(TRY_CAST(Tot_Srvcs AS DOUBLE))                           AS cap_srvcs,
            SUM(TRY_CAST(Bene_Dual_Cnt AS BIGINT))                       AS cap_dual_benes,
            SUM(CASE WHEN Rndrng_Prvdr_Type IN ({pc})
                     THEN TRY_CAST(Tot_Benes AS BIGINT) ELSE 0 END)      AS cap_benes_primary,
            SUM(CASE WHEN Rndrng_Prvdr_Type IN ({pc}) THEN 1 ELSE 0 END) AS cap_n_primary
        FROM read_csv('{csv_path}', all_varchar=true, ignore_errors=true,
                      header=true, sample_size=-1)
        WHERE Rndrng_Prvdr_Zip5 IS NOT NULL AND length(Rndrng_Prvdr_Zip5) >= 5
        GROUP BY 1
    """).df()
    con.close()
    df = df[df["zcta5"].str.fullmatch(r"\d{5}")].copy()
    df["cap_dual_share"] = (df["cap_dual_benes"] / df["cap_benes"]).where(df["cap_benes"] > 0)
    _validate(df)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    log("capacity", f"wrote {OUT.name}: {len(df)} ZIPs, "
                    f"{int(df['cap_benes'].sum()):,} served beneficiaries, "
                    f"mean dual share {df['cap_dual_share'].mean():.3f}")
    if RAW_CSV.exists():       # the ~hundreds-MB raw is not needed once aggregated
        RAW_CSV.unlink()
    return str(OUT)


def _validate(df: pd.DataFrame) -> None:
    if len(df) < 10_000:
        die("capacity", f"only {len(df)} ZIPs aggregated; expected ~30k - check the source columns")
    if not (df["cap_dual_share"].dropna().between(0, 1).all()):
        die("capacity", "dual_share outside [0,1] - column mismatch")
    if df["cap_benes"].sum() < 1_000_000:
        die("capacity", "implausibly low total beneficiaries - check Tot_Benes parse")


if __name__ == "__main__":
    build(force=True)

"""build_sud_mh_supply: SAMHSA FindTreatment.gov -> ZIP-level behavioral-health / substance-use
treatment SUPPLY. The index has NO behavioral-health access layer, yet the CDC tract-overdose
validation (validate_subcounty --overdose) proved a SUD/mental-health-access construct EXISTS and
is partly orthogonal to the deprivation gradient. This is the missing supply input for it.

Source: the free, headless JSON endpoint that powers FindTreatment.gov (the national SAMHSA-surveyed
treatment-facility locator). Each record is a geocoded point (lat/lon + ZIP) with a facility type
(OTP opioid-treatment program / SA substance-use / MH mental-health) and a services list we mine for
MAT capability and Medicaid / sliding-scale acceptance flags. No key, no DUA: the same endpoint serves
the public site; we sweep all pages at the 2000 cap.

    python -m pipeline.build_sud_mh_supply
"""
from __future__ import annotations

import json
import time
import urllib.request

import pandas as pd

from . import config
from .common import die, log

EXPORT = "https://findtreatment.gov/locator/exportsAsJson/v2?pageSize=2000&page={page}"
OUT = config.PROCESSED / "sud_mh_facilities.parquet"

# substring probes over the stringified services blob -> boolean capability/acceptance flags
FLAGS = {
    "mat": ("buprenorphine", "methadone", "naltrexone", "vivitrol", "medication assisted",
            "medications for"),
    "accepts_medicaid": ("medicaid",),
    "sliding_scale": ("sliding fee", "sliding scale", "payment assistance"),
    "accepts_uninsured": ("no payment", "free", "self-payment", "cash or self"),
}


def _fetch_all() -> list[dict]:
    first = json.load(urllib.request.urlopen(EXPORT.format(page=1), timeout=60))
    pages = int(first.get("totalPages") or 1)
    rows = list(first.get("rows") or [])
    for p in range(2, pages + 1):
        for attempt in range(3):
            try:
                r = json.load(urllib.request.urlopen(EXPORT.format(page=p), timeout=60))
                rows += r.get("rows") or []
                break
            except Exception:  # noqa: BLE001 - transient; retry
                time.sleep(1.5)
        else:
            log("sudmh", f"page {p} failed after retries; continuing")
    return rows


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("sudmh", f"{OUT.name} exists; force=True to rebuild")
        return str(OUT)
    log("sudmh", "sweeping FindTreatment.gov facility universe...")
    rows = _fetch_all()
    recs = []
    for r in rows:
        blob = json.dumps(r.get("services") or "").lower()
        z = str(r.get("zip") or "").zfill(5)[:5]
        rec = {
            "zcta5": z,
            "lat": pd.to_numeric(r.get("latitude"), errors="coerce"),
            "lon": pd.to_numeric(r.get("longitude"), errors="coerce"),
            "state": r.get("state"),
            "type_facility": r.get("typeFacility"),
            "is_otp": (r.get("typeFacility") == "OTP"),
        }
        for flag, kws in FLAGS.items():
            rec[flag] = any(k in blob for k in kws)
        recs.append(rec)
    df = pd.DataFrame(recs)
    df = df[df["zcta5"].str.fullmatch(r"\d{5}")].copy()
    _validate(df)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    log("sudmh", f"wrote {OUT.name}: {len(df)} facilities, "
                 f"{df['zcta5'].nunique()} ZIPs, MAT={int(df['mat'].sum())}, "
                 f"Medicaid={int(df['accepts_medicaid'].sum())}, OTP={int(df['is_otp'].sum())}")
    return str(OUT)


def _validate(df: pd.DataFrame) -> None:
    if len(df) < 10_000:
        die("sudmh", f"only {len(df)} facilities; expected ~45k - check the endpoint/paging")
    if df["lat"].notna().mean() < 0.8:
        die("sudmh", "too many missing coordinates - geocoding field changed")


if __name__ == "__main__":
    build(force=True)

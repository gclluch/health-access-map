"""build_places: CDC PLACES ZCTA (GIS Friendly) -> disease burden parquet.

Output columns (brief 12.6): zcta5(str5); diabetes_pct, copd_pct, chd_pct,
casthma_pct, depression_pct (float, crude prevalence %).

These are model-based small-area estimates (BRFSS), not raw counts -- surfaced
in the UI as estimated prevalence (brief 4.1 / 15.3).
"""
from __future__ import annotations

import re

import pandas as pd

from . import config
from .common import (assert_zcta, dev_filter, die, download_file, http_client,
                     log, norm_zcta, write_provenance)
from .taxonomy import all_places_keys

OUT = config.PROCESSED / "places.parquet"
# We keep EVERY measure the hierarchy uses. Our column key `<base>_pct` maps to the
# PLACES GIS column `<base>_crudeprev` (case-insensitive).
PLACES_KEYS = all_places_keys()                       # e.g. 'diabetes_pct'
WANTED = {k: k[:-4] + "_crudeprev" for k in PLACES_KEYS}  # 'diabetes_pct' -> 'diabetes_crudeprev'


def _resolve_dataset_id() -> str:
    """Pick the newest ZCTA GIS-Friendly release from the Socrata catalog."""
    try:
        with http_client(30) as c:
            results = c.get(config.PLACES_CATALOG_URL).json().get("results", [])
        best, best_year = None, -1
        for r in results:
            name = r["resource"]["name"]
            if "zcta" in name.lower() and "gis friendly" in name.lower():
                years = [int(y) for y in re.findall(r"\b(20\d{2})\b", name)]
                year = max(years) if years else 0
                if year > best_year:
                    best, best_year = r["resource"]["id"], year
        if best:
            log("places", f"resolved dataset {best} ({best_year} release)")
            return best
    except Exception as e:  # noqa: BLE001
        log("places", f"catalog resolution failed ({type(e).__name__}); using seed")
    return config.PLACES_DATASET_ID


def _download(dataset_id: str):
    candidates = [dataset_id, config.PLACES_DATASET_ID, *config.PLACES_DATASET_ID_FALLBACKS]
    seen = set()
    for did in candidates:
        if did in seen:
            continue
        seen.add(did)
        url = config.PLACES_EXPORT_TMPL.format(id=did)
        dest = config.RAW / f"places_{did}.csv"
        try:
            download_file(url, dest, min_bytes=1_000_000)
            return dest, did
        except Exception as e:  # noqa: BLE001
            log("places", f"download {did} failed ({type(e).__name__}); trying next")
    die("places", "no PLACES dataset id resolved")


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("places", f"skip (exists): {OUT.name}")
        return str(OUT)

    dest, did = _download(_resolve_dataset_id())
    # Read header to map columns case-insensitively.
    header = pd.read_csv(dest, nrows=0)
    lower = {c.lower(): c for c in header.columns}
    if "zcta5" not in lower:
        die("places", f"no zcta5 column in {dest.name}; cols={list(header.columns)[:8]}")

    # resolve each wanted measure to its actual CSV column; warn on any absent
    present = {key: lower[csv] for key, csv in WANTED.items() if csv in lower}
    absent = [key for key in WANTED if key not in present]
    if absent:
        log("places", f"WARN {len(absent)} measures not in this release: {absent}")
    keep = list(present.values())

    df = pd.read_csv(dest, usecols=[lower["zcta5"], *keep], dtype={lower["zcta5"]: str})
    rename = {orig: key for key, orig in present.items()}
    df = df.rename(columns={lower["zcta5"]: "zcta5", **rename})
    df["zcta5"] = norm_zcta(df["zcta5"])
    for c in present:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["zcta5"]).drop_duplicates("zcta5")
    df = dev_filter(df, dev_state)

    _validate(df, dev_state, list(present))
    df = df[["zcta5", *present]]
    df.to_parquet(OUT, index=False)
    write_provenance({"places": {"dataset_id": did, "rows": len(df), "measures": len(present)}})
    log("places", f"wrote {OUT.name} ({len(df)} rows, {len(present)} measures)")
    return str(OUT)


def _validate(df: pd.DataFrame, dev_state: str | None, cols: list[str]) -> None:
    assert_zcta(df, stage="places")
    floor = 200 if dev_state else 10_000
    if len(df) < floor:
        die("places", f"only {len(df)} rows (expected >= {floor}); dataset id likely wrong")
    if len(cols) < 30:
        die("places", f"only {len(cols)} measures resolved (expected ~40)")
    # the 5 core chronic measures should be well populated
    core = [c for c in ("diabetes_pct", "copd_pct", "chd_pct", "casthma_pct", "depression_pct") if c in df]
    nonnull = df[core].notna().all(axis=1).mean()
    if nonnull < 0.85:
        die("places", f"only {nonnull:.0%} rows have the core measures (expected > 85%)")
    log("places", f"validated {len(df)} rows, {len(cols)} measures, core {nonnull:.0%} populated")


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

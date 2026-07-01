"""Shared pipeline utilities: env, zcta normalization, downloads, provenance, logging."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Iterable

import httpx
import pandas as pd
from dotenv import load_dotenv

from . import config

ZCTA_RE = re.compile(r"^\d{5}$")

# ZIP/ZCTA leading-3-digit ranges per state, for --dev-state filtering.
# Inclusive ranges on the first 3 digits of the 5-digit code.
DEV_STATE_PREFIXES: dict[str, list[tuple[int, int]]] = {
    "CA": [(900, 961)],
    "NY": [(100, 149)],
    "TX": [(750, 799), (885, 885)],
    "FL": [(320, 349)],
    "WA": [(980, 994)],
}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def log(stage: str, msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {stage:<14} {msg}", flush=True)


def die(stage: str, msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"[{time.strftime('%H:%M:%S')}] {stage:<14} FATAL: {msg}", file=sys.stderr, flush=True)
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# Env
# ---------------------------------------------------------------------------
def load_env() -> None:
    load_dotenv(config.ROOT / ".env")
    config.CENSUS_API_KEY = __import__("os").environ.get("CENSUS_API_KEY", config.CENSUS_API_KEY)


# ---------------------------------------------------------------------------
# ZCTA normalization + assertions
# ---------------------------------------------------------------------------
def norm_zcta(series: pd.Series) -> pd.Series:
    """Force string, strip, take first 5 chars (handles ZIP+4), zero-pad to 5."""
    s = series.astype("string").str.strip()
    s = s.str.replace(r"\.0$", "", regex=True)  # undo accidental float reads
    s = s.str[:5].str.zfill(5)
    return s


def assert_zcta(df: pd.DataFrame, col: str = "zcta5", stage: str = "") -> None:
    if col not in df.columns:
        die(stage, f"missing required column '{col}'")
    bad = df[~df[col].astype("string").str.match(ZCTA_RE, na=False)]
    if len(bad):
        die(stage, f"{len(bad)} zcta5 values fail ^\\d{{5}}$ (e.g. {bad[col].head(3).tolist()})")


def dev_filter(df: pd.DataFrame, state: str | None, col: str = "zcta5") -> pd.DataFrame:
    """Filter a dataframe to a dev state's ZCTA prefix ranges."""
    if not state:
        return df
    ranges = DEV_STATE_PREFIXES.get(state.upper())
    if not ranges:
        log("dev-filter", f"no prefix ranges for state '{state}', passing through unfiltered")
        return df
    p3 = df[col].astype("string").str[:3].astype("int64")
    mask = pd.Series(False, index=df.index)
    for lo, hi in ranges:
        mask |= (p3 >= lo) & (p3 <= hi)
    return df[mask].copy()


def dev_prefix_sql(state: str, col: str) -> str:
    """SQL WHERE fragment matching a dev state's ZCTA prefix ranges (DuckDB)."""
    ranges = DEV_STATE_PREFIXES.get(state.upper(), [])
    if not ranges:
        return "TRUE"
    parts = [f"(CAST(SUBSTR({col},1,3) AS INTEGER) BETWEEN {lo} AND {hi})" for lo, hi in ranges]
    return "(" + " OR ".join(parts) + ")"


def dev_prefix_js(state: str, col: str = "zcta5") -> str | None:
    """A mapshaper -filter JS expression for a dev state's ZCTA prefix ranges."""
    ranges = DEV_STATE_PREFIXES.get(state.upper(), [])
    if not ranges:
        return None
    conds = [f"(p>={lo}&&p<={hi})" for lo, hi in ranges]
    return f"(function(){{var p=+{col}.substr(0,3);return {'||'.join(conds)};}})()"


# ---------------------------------------------------------------------------
# HTTP / downloads
# ---------------------------------------------------------------------------
def http_client(timeout: float = 60.0) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "health-access-map/1.0 (+pipeline)"},
    )


def download_file(url: str, dest: Path, min_bytes: int = 0, force: bool = False) -> Path:
    """Idempotent, resumable download. Skips if dest exists and is large enough."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force and dest.stat().st_size >= max(min_bytes, 1):
        log("download", f"skip (cached {dest.stat().st_size:,}B): {dest.name}")
        return dest

    headers = {}
    mode = "wb"
    resume_from = 0
    part = dest.with_suffix(dest.suffix + ".part")
    if part.exists() and not force:
        resume_from = part.stat().st_size
        headers["Range"] = f"bytes={resume_from}-"
        mode = "ab"

    log("download", f"GET {url}")
    with http_client(timeout=None) as client:
        with client.stream("GET", url, headers=headers) as r:
            if r.status_code not in (200, 206):
                raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
            written = resume_from
            with open(part, mode) as f:
                for chunk in r.iter_bytes(chunk_size=1 << 20):
                    f.write(chunk)
                    written += len(chunk)
    if min_bytes and written < min_bytes:
        raise RuntimeError(f"download too small: {written}B < expected {min_bytes}B ({url})")
    part.replace(dest)
    log("download", f"saved {written:,}B -> {dest.name}")
    return dest


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------
def write_provenance(updates: dict) -> None:
    prov = {}
    if config.PROVENANCE.exists():
        prov = json.loads(config.PROVENANCE.read_text())
    prov.update(updates)
    config.PROVENANCE.write_text(json.dumps(prov, indent=2, default=str))


def scrub_sentinels(series: pd.Series, sentinels: Iterable[int] = config.CENSUS_SENTINELS) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    return s.mask(s.isin(list(sentinels)))


def load_zcta_tract_xwalk() -> pd.DataFrame:
    """National Census 2020 ZCTA<->tract relationship (GEOID_ZCTA5_20, GEOID_TRACT_20, AREALAND_PART
    = land area of the intersection). Fetched once (~24MB) and cached as zcta_tract_xwalk.parquet.
    Shared by build_hpsa (tract-level shortage) and validate_subcounty (sub-county validation)."""
    cache = config.PROCESSED / "zcta_tract_xwalk.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    raw = config.RAW / "tab20_zcta520_tract20_natl.txt"
    download_file(config.ZCTA_TRACT_REL_2020, raw, min_bytes=1_000_000)
    full = pd.read_csv(raw, sep="|", dtype=str)
    rel = full[["GEOID_ZCTA5_20", "GEOID_TRACT_20", "AREALAND_PART"]].dropna()
    rel["AREALAND_PART"] = pd.to_numeric(rel["AREALAND_PART"], errors="coerce")
    rel = rel[rel["AREALAND_PART"] > 0].reset_index(drop=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    rel.to_parquet(cache, index=False)
    return rel

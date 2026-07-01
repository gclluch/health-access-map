"""build_shards: per-ZIP full-record JSON shards for the static (no-backend) deploy.

The detail panel's deepest drill-down (every raw measure + its national percentile) and the
Who-lives-here block need the full per-ZIP row the FastAPI backend serves at /api/zcta/{z}. On
the static Netlify host there is no backend, so we pre-shard that data: one JSON file per ZIP3
prefix (zcta5[:3]) holding { zcta5: {full record} }. The client (lib/api.ts) fetches one
~110 KB shard on demand per ZIP click, so it mirrors the backend without a server.

~900 shards into frontend/public/zcta/ (gitignored, like map_frame.json). Mirrors backend
data._clean (NaN/inf/NA -> dropped) and rounds floats to bound size.
"""
from __future__ import annotations

import json
import math
import shutil
from collections import defaultdict

import pandas as pd

from . import config
from .common import die, log

PARQUET = config.PROCESSED / "metrics.parquet"
OUT_DIR = config.FRONTEND_PUBLIC / "zcta"


def _clean(v):
    """NaN/inf/NA -> None (dropped by caller); numpy scalar -> python; floats rounded to 4dp."""
    if v is None:
        return None
    if hasattr(v, "item"):  # numpy scalar
        v = v.item()
    if isinstance(v, float):
        return None if (math.isnan(v) or math.isinf(v)) else round(v, 4)
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def build(dev_state: str | None = None, force: bool = False):
    if not PARQUET.exists():
        die("shards", f"missing {PARQUET} - run the data build first")
    df = pd.read_parquet(PARQUET)
    if "zcta5" not in df.columns:
        df = df.reset_index()  # zcta5 was the index
    df["zcta5"] = df["zcta5"].astype(str).str.zfill(5)

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    shards: dict[str, dict] = defaultdict(dict)
    for row in df.to_dict("records"):
        z = row["zcta5"]
        rec = {k: c for k, v in row.items() if (c := _clean(v)) is not None}
        rec["zcta5"] = z
        shards[z[:3]][z] = rec

    for prefix, recs in shards.items():
        (OUT_DIR / f"{prefix}.json").write_text(json.dumps(recs, separators=(",", ":")))

    total_mb = sum((OUT_DIR / f"{p}.json").stat().st_size for p in shards) / 1e6
    log("shards", f"wrote {len(shards)} ZIP3 shards ({len(df)} ZCTAs, {total_mb:.1f} MB) -> {OUT_DIR}")
    return OUT_DIR


if __name__ == "__main__":
    import sys

    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None, force=True)

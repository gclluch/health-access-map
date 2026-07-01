"""Freeze a small, representative slice of the national metrics as a CI fixture, so the acceptance
and integrity suites run in CI (where the full multi-GB build is unavailable) instead of skipping.

The slice keeps NATIONAL percentiles (it is a subsample, not a re-ranked mini-index), so the row-level
invariants (no NaN/inf, ranges, rates, zcta format) and the PER-ROW server/client parity hold exactly.
The one test that re-ranks WITHIN the frame (test_dimensions_reproducible) is national-scope-only and
skips here. Includes the 90210/90011 face-validity anchors. Re-freeze with:  python tests/fixtures/build_slice.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "processed" / "metrics.parquet"
OUT = Path(__file__).resolve().parent / "metrics_slice.parquet"
PROV = Path(__file__).resolve().parent / "provenance.json"

ANCHORS = ["90210", "90011"]  # Beverly Hills < South LA face validity
N = 800

if __name__ == "__main__":
    df = pd.read_parquet(SRC)
    df["zcta5"] = df["zcta5"].astype(str)
    rng = np.random.RandomState(20260701)
    pool = df[~df["zcta5"].isin(ANCHORS)]
    sample = pool.iloc[rng.permutation(len(pool))[:N]]
    keep = pd.concat([df[df["zcta5"].isin(ANCHORS)], sample], ignore_index=True).drop_duplicates("zcta5")
    keep.to_parquet(OUT, index=False)
    PROV.write_text(json.dumps({"score": {"scope": "fixture-slice", "n": int(len(keep))}}, indent=2))
    print(f"wrote {OUT.name} ({len(keep)} rows, {OUT.stat().st_size/1e6:.2f} MB) + provenance.json")

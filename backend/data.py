"""Loads metrics.parquet into memory once at startup. No DB engine -- 33k rows
of attribute lookups by zcta5 / state / top-N fit trivially in a DataFrame."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import pandas as pd

from pipeline.taxonomy import DIMENSIONS, subscore_specs

ROOT = Path(__file__).resolve().parent.parent
METRICS_PATH = ROOT / "data" / "processed" / "metrics.parquet"

def _rankable_metrics() -> set[str]:
    """Composite, dimensions, and sub-scores that can be ranked / colorized."""
    return (
        {"access_gap_score", "access_gap_pctile"}
        | {f"{d}_pctile" for d in DIMENSIONS}
        | {f"{s['key']}_pctile" for s in subscore_specs()}
    )


RANKABLE_METRICS = _rankable_metrics()

# The composite and its rank inherit the 2-of-3 renormalization, so a partial (2-dim) score is a
# weaker estimate on these (T2). A bare dimension/sub-score percentile that is itself present stays
# comparable, so the n_dims_scored gate applies only to the composite family.
_COMPOSITE_FAMILY = {"access_gap_score", "access_gap_pctile"}

_DF: pd.DataFrame | None = None


def load() -> pd.DataFrame:
    global _DF
    if _DF is None:
        if not METRICS_PATH.exists():
            raise RuntimeError(
                f"{METRICS_PATH} not found. Run the pipeline first: "
                f"`python -m pipeline.run --dev-state CA` (or national)."
            )
        df = pd.read_parquet(METRICS_PATH)
        df["zcta5"] = df["zcta5"].astype("string")
        _DF = df.set_index("zcta5", drop=False)
    return _DF


def count() -> int:
    return len(load())


def _clean(value):
    """NaN/NA/inf -> None so the payload is valid JSON."""
    if value is None:
        return None
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    # numpy scalar -> python scalar
    if hasattr(value, "item"):
        return value.item()
    return value


# The metrics table is loaded once at startup and never mutated, so per-ZIP records and the
# (full-sort) rankings responses are pure functions of their args - cache them. This turns the
# hot rankings path from an O(n log n) sort on every request into a dict lookup. If a reload
# path is ever added, call record.cache_clear() / rankings.cache_clear() after load().
# The metrics table is immutable and bounded (~33k rows), so an unbounded cache fully covers it.
@lru_cache(maxsize=None)
def record(zcta5: str) -> dict | None:
    df = load()
    if zcta5 not in df.index:
        return None
    row = df.loc[zcta5]
    if isinstance(row, pd.DataFrame):  # dup guard
        row = row.iloc[0]
    return {k: _clean(v) for k, v in row.to_dict().items()}


@lru_cache(maxsize=2048)
def rankings(metric: str, state: str | None, limit: int, order: str,
             include_low_confidence: bool, min_dims: int = 3) -> list[dict]:
    df = load()
    sub = df[df["scoreable"]] if "scoreable" in df.columns else df
    sub = sub[sub[metric].notna()]
    if state:
        # state is canonicalized (stripped + uppercased) by the caller before the cache boundary.
        sub = sub[sub["state"] == state]
    if not include_low_confidence and "low_confidence" in sub.columns:
        sub = sub[~sub["low_confidence"]]
    # institutional (providers > residents - a hospital campus, not a community) is always held out
    # of headline rankings; its raw supply reflects a workplace, not the people who live there.
    if "institutional" in sub.columns:
        sub = sub[~sub["institutional"].fillna(False)]
    # 2-of-3 composites are built from collinear dimensions over a non-random (MNAR: rural, tiny,
    # low-confidence) subset, so they are not comparable to the 3-of-3 majority (T2 / audit S5). The
    # headline defaults to min_dims=3; only the composite family is gated (a present sub-score is fine).
    if metric in _COMPOSITE_FAMILY and "n_dims_scored" in sub.columns:
        sub = sub[sub["n_dims_scored"].fillna(0) >= min_dims]
    sub = sub.sort_values(metric, ascending=(order == "asc")).head(limit)
    keep = ["zcta5", "state", "city", "county_name", metric, "access_gap_score",
            "health_need_pctile", "social_vulnerability_pctile", "care_access_pctile",
            "median_income", "poverty_rate", "population", "low_confidence", "n_dims_scored"]
    keep = [c for c in dict.fromkeys(keep) if c in sub.columns]
    return [{k: _clean(r[k]) for k in keep} for _, r in sub.iterrows()]


def compare(zips: list[str]) -> list[dict]:
    return [r for r in (record(z) for z in zips) if r is not None]


@lru_cache(maxsize=1)
def states() -> list[str]:
    df = load()
    return sorted(s for s in df["state"].dropna().unique())

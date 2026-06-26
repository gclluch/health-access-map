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
@lru_cache(maxsize=4096)
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
             include_low_confidence: bool) -> list[dict]:
    df = load()
    sub = df[df["scoreable"]] if "scoreable" in df.columns else df
    sub = sub[sub[metric].notna()]
    if state:
        sub = sub[sub["state"] == state.upper()]
    if not include_low_confidence and "low_confidence" in sub.columns:
        sub = sub[~sub["low_confidence"]]
    # institutional (providers > residents - a hospital campus, not a community) is always held out
    # of headline rankings; its raw supply reflects a workplace, not the people who live there.
    if "institutional" in sub.columns:
        sub = sub[~sub["institutional"].fillna(False)]
    sub = sub.sort_values(metric, ascending=(order == "asc")).head(limit)
    keep = ["zcta5", "state", "city", "county_name", metric, "access_gap_score",
            "health_need_pctile", "social_vulnerability_pctile", "care_access_pctile",
            "median_income", "poverty_rate", "population", "low_confidence"]
    keep = [c for c in dict.fromkeys(keep) if c in sub.columns]
    return [{k: _clean(r[k]) for k in keep} for _, r in sub.iterrows()]


def compare(zips: list[str]) -> list[dict]:
    return [r for r in (record(z) for z in zips) if r is not None]


@lru_cache(maxsize=1)
def states() -> list[str]:
    df = load()
    return sorted(s for s in df["state"].dropna().unique())

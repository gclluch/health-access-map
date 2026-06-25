"""Data-integrity invariants (audit 2026-06-24, docs/BACKLOG.md A3).

These lock the audit findings that pass on the current build so a future build can't silently
regress: percentiles in [0,100], rates in [0,1], no surviving sentinels, non-positive population
never scoreable, and every absurd-per-capita (provider-campus) ZCTA flagged non-residential.

Mirrors pipeline.join_and_score._validate_integrity (the build-time `die`). Skip-guarded on the
real parquet so CI stays green without a data build; the last test proves the guard actually bites
by corrupting a value in-memory and asserting the build-time check rejects it."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
METRICS = ROOT / "data" / "processed" / "metrics.parquet"

pytestmark = pytest.mark.skipif(not METRICS.exists(), reason="run the pipeline first")


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    return pd.read_parquet(METRICS)


def test_percentiles_in_range(df: pd.DataFrame) -> None:
    cols = [c for c in df.columns if c.endswith(("_pctile", "_natpct"))]
    assert cols, "no percentile columns found"
    for c in cols:
        v = df[c].dropna()
        if len(v):
            assert v.min() >= -0.001 and v.max() <= 100.001, f"{c} outside [0,100]"


def test_rates_are_proportions(df: pd.DataFrame) -> None:
    for c in [c for c in df.columns if c.endswith("_rate")]:
        v = pd.to_numeric(df[c], errors="coerce").dropna()
        if len(v):
            assert v.min() >= -0.001 and v.max() <= 1.001, f"{c} not a proportion in [0,1]"


def test_no_surviving_sentinels(df: pd.DataFrame) -> None:
    num = df.select_dtypes("number")
    offenders = num.min()[num.min() < -100000]
    assert offenders.empty, f"sentinel-like values survived: {offenders.to_dict()}"


def test_nonpositive_population_not_scoreable(df: pd.DataFrame) -> None:
    pop = pd.to_numeric(df["population"], errors="coerce")
    assert int((~(pop > 0) & df["scoreable"]).sum()) == 0


def test_extreme_per_capita_is_flagged(df: pd.DataFrame) -> None:
    """A ZCTA with >1000 primary providers/1k residents is a hospital campus, not a community;
    it must be low_confidence or institutional so it never ranks beside real places (audit A1/A2)."""
    extreme = pd.to_numeric(df["primary_per_1k"], errors="coerce") > 1000
    if extreme.any():
        flagged = df["low_confidence"] | df["institutional"]
        assert int((extreme & ~flagged).sum()) == 0


def test_institutional_flag_present_and_excludes_anschutz(df: pd.DataFrame) -> None:
    assert "institutional" in df.columns
    # 80045 = Anschutz Medical Campus: providers >> residents, above the pop floor (so NOT caught by
    # low_confidence). The flag must catch it. Skip if the ZCTA isn't in a dev-state-scoped build.
    row = df[df["zcta5"] == "80045"]
    if len(row):
        assert bool(row["institutional"].iloc[0]) is True


def test_no_duplicate_zctas(df: pd.DataFrame) -> None:
    assert int(df["zcta5"].duplicated().sum()) == 0


def test_county_fips_valid(df: pd.DataFrame) -> None:
    if "county_fips" not in df.columns:
        pytest.skip("no county_fips column")
    cf = df["county_fips"].dropna().astype(str)
    valid_st = {f"{i:02d}" for i in range(1, 57)} | {"60", "66", "69", "72", "74", "78"}
    bad = cf[~cf.str.match(r"^\d{5}$") | ~cf.str[:2].isin(valid_st)]
    assert len(bad) == 0, f"invalid county_fips: {sorted(bad.unique())[:5]}"


def test_validate_integrity_rejects_corruption(df: pd.DataFrame) -> None:
    """The guard bites: corrupt one percentile and the build-time check (die -> SystemExit)
    must reject it."""
    from pipeline.join_and_score import _validate_integrity

    dim_cols = [c for c in df.columns if c.endswith("_pctile")]
    bad = df.copy()
    bad.loc[bad.index[0], "access_gap_pctile"] = 250.0  # out of [0,100]
    with pytest.raises(SystemExit):
        _validate_integrity(bad, dim_cols)

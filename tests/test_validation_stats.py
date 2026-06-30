"""Oracle tests for the shared statistical kernel (pipeline/validation_stats.py).

These helpers are reused by every validation gate (diagnostics, bootstrap_gate, the validators), so a
silent error here corrupts every headline number. The tests pin the math against independent oracles
(numpy, and weight-by-replication identities) and lock the NaN / min-pairs / zero-variance contracts.
No data or network needed - they run in CI. (T7, docs/REMEDIATION_PLAN.md)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.validation_stats import pearson_corr, weighted_corr, within_residual


def _rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


# --- pearson_corr ----------------------------------------------------------------------------

def test_pearson_matches_numpy():
    r = _rng(1)
    a = r.normal(size=500)
    b = 0.7 * a + r.normal(size=500)  # genuine partial signal
    assert pearson_corr(a, b) == pytest.approx(np.corrcoef(a, b)[0, 1], abs=1e-12)


def test_pearson_sign_and_unit_bounds():
    a = np.arange(200, dtype=float)
    assert pearson_corr(a, 2 * a + 5) == pytest.approx(1.0, abs=1e-12)   # perfect positive
    assert pearson_corr(a, -3 * a) == pytest.approx(-1.0, abs=1e-12)     # perfect negative


def test_pearson_drops_nan_pairs_only():
    r = _rng(2)
    a = r.normal(size=300)
    b = 0.5 * a + r.normal(size=300)
    a_nan, b_nan = a.copy(), b.copy()
    a_nan[::10] = np.nan          # NaNs in a
    b_nan[5::10] = np.nan         # disjoint NaNs in b
    mask = ~(np.isnan(a_nan) | np.isnan(b_nan))
    assert pearson_corr(a_nan, b_nan) == pytest.approx(
        np.corrcoef(a[mask], b[mask])[0, 1], abs=1e-12)


def test_pearson_min_pairs_floor_returns_nan():
    a = np.arange(60, dtype=float)
    b = a + 1
    assert not np.isnan(pearson_corr(a, b, min_pairs=50))   # 60 >= 50 -> computed
    assert np.isnan(pearson_corr(a, b, min_pairs=100))      # 60 < 100 -> nan
    # default floor is 50
    assert np.isnan(pearson_corr(a[:40], b[:40]))


def test_pearson_zero_variance_returns_nan():
    a = np.ones(200)             # constant -> zero denominator
    b = _rng(3).normal(size=200)
    assert np.isnan(pearson_corr(a, b))


# --- weighted_corr ---------------------------------------------------------------------------

def test_weighted_equals_unweighted_under_uniform_weights():
    r = _rng(4)
    a = r.normal(size=300)
    b = 0.6 * a + r.normal(size=300)
    w = np.full(300, 3.7)        # any constant weight
    assert weighted_corr(a, b, w) == pytest.approx(pearson_corr(a, b), abs=1e-12)


def test_weighted_corr_equals_replication_oracle():
    """Independent oracle: integer-weighting must equal Pearson on the row-replicated arrays."""
    r = _rng(5)
    a = r.normal(size=120)
    b = 0.4 * a + r.normal(size=120)
    w = r.integers(1, 5, size=120).astype(float)
    expanded_a = np.repeat(a, w.astype(int))
    expanded_b = np.repeat(b, w.astype(int))
    assert weighted_corr(a, b, w) == pytest.approx(
        pearson_corr(expanded_a, expanded_b), abs=1e-12)


def test_weighted_corr_excludes_nonpositive_and_nan_weights():
    a = np.arange(200, dtype=float)
    b = a.copy()
    w = np.ones(200)
    w[:50] = 0          # zero weight -> excluded
    w[50:60] = np.nan   # nan weight -> excluded
    # the surviving rows are perfectly correlated -> 1.0, and the excluded rows can't change that
    assert weighted_corr(a, b, w) == pytest.approx(1.0, abs=1e-12)


def test_weighted_corr_min_pairs_floor():
    a = np.arange(200, dtype=float)
    b = a + 1
    w = np.zeros(200)
    w[:40] = 1.0        # only 40 positive-weight rows < default 50 -> nan
    assert np.isnan(weighted_corr(a, b, w))


# --- within_residual -------------------------------------------------------------------------

def test_within_residual_is_zero_mean_per_group():
    df = pd.DataFrame({
        "county_fips": ["A", "A", "A", "B", "B"],
        "x": [1.0, 3.0, 5.0, 10.0, 20.0],
    })
    w = within_residual(df, "x")
    # group A mean = 3 -> [-2,0,2]; group B mean = 15 -> [-5,5]
    assert w[:3] == pytest.approx([-2.0, 0.0, 2.0])
    assert w[3:] == pytest.approx([-5.0, 5.0])
    assert abs(np.nanmean(w[:3])) < 1e-12 and abs(np.nanmean(w[3:])) < 1e-12


def test_within_residual_coerces_non_numeric_to_nan():
    df = pd.DataFrame({"county_fips": ["A", "A", "A"], "x": ["1.0", "bad", "3.0"]})
    w = within_residual(df, "x")
    assert np.isnan(w[1])                      # "bad" -> NaN
    # mean over the valid {1,3} = 2 -> residuals -1 and +1
    assert w[0] == pytest.approx(-1.0) and w[2] == pytest.approx(1.0)

"""CI-runnable unit tests for bootstrap_gate's pure kernels.

test_bootstrap_gate.py is gated on a real metrics.parquet, so in CI the bootstrap CI machinery,
partial correlation, ordinal rank, spatial blocking, and FDR are NOT exercised. These synthetic-data
tests close that gap: they pin the kernels against planted-signal oracles with fixed seeds and need
no data or network. (T7, docs/REMEDIATION_PLAN.md)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.bootstrap_gate import (
    _bh_fdr,
    _block_ci,
    _cluster_groups,
    _mean_abs_r,
    _mean_r,
    _partial_corr,
    _rank,
)
from pipeline.validation_stats import pearson_corr


# --- _rank (ordinal, NaN-preserving) ---------------------------------------------------------

def test_rank_is_ordinal_ascending():
    np.testing.assert_array_equal(_rank(np.array([3.0, 1.0, 2.0])), [2.0, 0.0, 1.0])


def test_rank_preserves_nan_positions():
    out = _rank(np.array([3.0, np.nan, 1.0]))
    assert np.isnan(out[1])
    np.testing.assert_array_equal(out[[0, 2]], [1.0, 0.0])   # 1 -> rank0, 3 -> rank1


def test_rank_breaks_ties_stably_by_position():
    # stable ordinal: equal values keep original order and get consecutive ranks
    np.testing.assert_array_equal(_rank(np.array([5.0, 5.0, 1.0])), [1.0, 2.0, 0.0])


def test_rank_outputs_dense_permutation():
    # the gate uses rank(x) as a monotone transform, so the all-finite output must be a dense
    # permutation of 0..n-1 (no gaps, no duplicates).
    v = np.array([10.0, -4.0, 7.0, 0.0, 3.0])
    r = _rank(v)
    assert sorted(r.tolist()) == [0.0, 1.0, 2.0, 3.0, 4.0]


# --- _partial_corr ---------------------------------------------------------------------------

def test_partial_corr_recovers_signal_beyond_controls():
    rng = np.random.default_rng(0)
    n = 600
    z = rng.normal(size=n)
    c = rng.normal(size=n)                 # c independent of z
    y = 1.5 * c + 2.0 * z + rng.normal(size=n) * 0.3
    pc = _partial_corr(y, c, z.reshape(-1, 1))
    assert pc > 0.9                        # c's direct effect survives controlling for z


def test_partial_corr_kills_spurious_via_common_cause():
    rng = np.random.default_rng(1)
    n = 600
    z = rng.normal(size=n)
    c = z + rng.normal(size=n) * 0.3       # c driven by z
    y = z + rng.normal(size=n) * 0.3       # y driven by z, NO direct c->y link
    assert pearson_corr(c, y) > 0.7        # strong *marginal* correlation...
    assert abs(_partial_corr(y, c, z.reshape(-1, 1))) < 0.15   # ...vanishes net of z


def test_partial_corr_min_pairs_floor():
    rng = np.random.default_rng(2)
    n = 80                                 # < 100 -> nan
    z = rng.normal(size=n)
    assert np.isnan(_partial_corr(z, z, z.reshape(-1, 1)))


# --- _mean_r / _mean_abs_r -------------------------------------------------------------------

def test_mean_r_and_mean_abs_r_delegate_correctly():
    rng = np.random.default_rng(3)
    n = 300
    s = rng.normal(size=n)
    Y = np.column_stack([0.6 * s + rng.normal(size=n) * 0.5,    # positive r
                         -0.6 * s + rng.normal(size=n) * 0.5])  # negative r
    r0 = pearson_corr(s, Y[:, 0], min_pairs=100)
    r1 = pearson_corr(s, Y[:, 1], min_pairs=100)
    assert _mean_r(s, Y) == pytest.approx((r0 + r1) / 2, abs=1e-12)
    assert _mean_abs_r(s, Y) == pytest.approx((abs(r0) + abs(r1)) / 2, abs=1e-12)
    # the signed mean ~cancels; the abs mean does not
    assert _mean_abs_r(s, Y) > abs(_mean_r(s, Y))


# --- _cluster_groups (spatial blocking) ------------------------------------------------------

def _block_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "state": ["NY", "NY", "NY", "TX", "TX", "CA"],
        "county_name": ["Kings", "Kings", "Queens", "Harris", "Harris", ""],  # CA county missing
    })


def test_cluster_groups_partition_by_county():
    groups = _cluster_groups(_block_frame(), "county")
    # 3 real county blocks (NY|Kings, NY|Queens, TX|Harris) + 1 singleton for the blank CA county
    assert len(groups) == 4
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 1, 2, 2]
    # every row appears exactly once across blocks
    assert sorted(np.concatenate(groups).tolist()) == [0, 1, 2, 3, 4, 5]


def test_cluster_groups_state_level_is_coarser():
    groups = _cluster_groups(_block_frame(), "state")
    assert len(groups) == 3                  # NY, TX, CA
    assert sorted(len(g) for g in groups) == [1, 2, 3]


# --- _block_ci (cluster bootstrap CI) --------------------------------------------------------

def _clustered_corr_frame(true_beta: float, seed: int, n_counties: int = 60, per: int = 6):
    """Frame with county clusters and y = beta*x + county effect + noise; returns (df, x, y)."""
    rng = np.random.default_rng(seed)
    rows, xs, ys = [], [], []
    for ci in range(n_counties):
        ceff = rng.normal() * 2.0            # county-level latent (induces within-county dependence)
        for _ in range(per):
            x = rng.normal()
            y = true_beta * x + ceff + rng.normal() * 0.5
            rows.append({"state": "S", "county_name": f"c{ci}"})
            xs.append(x); ys.append(y)
    df = pd.DataFrame(rows)
    return df, np.asarray(xs), np.asarray(ys)


def test_block_ci_brackets_planted_signal_and_excludes_zero():
    df, x, y = _clustered_corr_frame(true_beta=0.8, seed=0)
    stat = lambda idx: float(np.corrcoef(x[idx], y[idx])[0, 1])  # noqa: E731
    res = _block_ci(df, stat, level="county", n_boot=400, seed=0)
    assert res["n_clusters"] == 60
    assert res["ci95"][0] <= res["point"] <= res["ci95"][1]
    assert res["point"] > 0.2 and res["excludes_0"] is True


def test_block_ci_null_includes_zero():
    df, x, y = _clustered_corr_frame(true_beta=0.0, seed=7)  # no x->y signal
    stat = lambda idx: float(np.corrcoef(x[idx], y[idx])[0, 1])  # noqa: E731
    res = _block_ci(df, stat, level="county", n_boot=400, seed=0)
    assert res["ci95"][0] < 0 < res["ci95"][1]
    assert res["excludes_0"] is False


# --- _bh_fdr (Benjamini-Hochberg) ------------------------------------------------------------

def test_bh_fdr_matches_known_oracle():
    pvals = {"a": 0.001, "b": 0.008, "c": 0.039, "d": 0.041, "e": 0.9}
    out = _bh_fdr(pvals, q=0.05)
    # step-up adjusted: a=0.005, b=0.02, c=d=0.05125, e=0.9
    assert out["a"]["q_value"] == pytest.approx(0.005, abs=1e-4)
    assert out["b"]["q_value"] == pytest.approx(0.02, abs=1e-4)
    assert out["c"]["q_value"] == pytest.approx(0.0513, abs=1e-4)
    # survivors at q=0.05 are exactly the two smallest
    assert {k for k, v in out.items() if v["survives_fdr"]} == {"a", "b"}


def test_bh_fdr_drops_nan_and_none():
    out = _bh_fdr({"a": 0.01, "b": None, "c": float("nan")}, q=0.05)
    assert set(out) == {"a"}

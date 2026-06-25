"""Precision-weighting + disattenuation estimators: offline, planted-answer checks. These lock the
math (weighted correlation recovers attenuated signal; reliability triangulation is correct) - not
the live data."""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline import validate as v
from pipeline import validate_subcounty as vs


def test_wcorr_matches_unweighted_under_uniform_weights():
    rng = np.random.default_rng(0)
    a = rng.normal(size=500)
    b = 0.5 * a + rng.normal(size=500)
    w = np.ones(500)
    for mod in (v, vs):
        assert abs(mod._wcorr(a, b, w) - v._corr(a, b)) < 1e-9


def test_wcorr_recovers_attenuated_signal():
    """Large units measured precisely (true r high); small units swamped by noise. The unweighted
    correlation is attenuated by the noisy small units; weighting by precision (size) must recover
    a HIGHER correlation - the whole point of the approach."""
    rng = np.random.default_rng(1)
    n = 2000
    size = rng.integers(50, 50_000, n).astype(float)        # population / precision of each unit
    true = rng.normal(size=n)                               # the latent signal both sides share
    # measurement noise on the outcome scales like 1/sqrt(size) (sampling error of a rate)
    noise = rng.normal(size=n) / np.sqrt(size / size.mean())
    x = true + 0.1 * rng.normal(size=n)
    y = true + noise
    unweighted = v._corr(x, y)
    weighted = v._wcorr(x, y, size)
    assert weighted > unweighted + 0.05                     # precision-weighting recovers signal


def test_index_reliability_high_when_subscores_agree():
    """Reliability ~1 when the sub-scores are near-identical (low noise), and clearly lower when
    each carries independent noise."""
    rng = np.random.default_rng(2)
    n = 400
    latent = rng.normal(size=n)
    clean = pd.DataFrame({f"s{i}_pctile": latent + 0.01 * rng.normal(size=n) for i in range(8)})
    noisy = pd.DataFrame({f"s{i}_pctile": latent + 1.5 * rng.normal(size=n) for i in range(8)})
    cols = list(clean.columns)
    rel_clean = v._index_reliability(clean, cols, n_splits=50)
    rel_noisy = v._index_reliability(noisy, cols, n_splits=50)
    assert rel_clean > 0.95
    assert rel_noisy < rel_clean - 0.1


def test_parallel_forms_reliability_recovers_planted_values():
    """Three rulers loading on one common factor with planted reliabilities r_i: the single-factor
    triangulation rel_i = r(i,j)*r(i,k)/r(j,k) must recover them (one noisy ruler reads low)."""
    rng = np.random.default_rng(3)
    n = 4000
    f = rng.normal(size=n)                                  # the common mortality factor
    rel = {"a": 0.9, "b": 0.8, "c": 0.3}                    # planted reliabilities (c is the noisy one)
    cty = pd.DataFrame({k: np.sqrt(r) * f + np.sqrt(1 - r) * rng.normal(size=n)
                        for k, r in rel.items()})
    w = np.ones(n)
    out = v._parallel_forms_reliability(cty, ["a", "b", "c"], w)
    for k in rel:
        assert abs(out[k] - rel[k]) < 0.12                  # recovered within tolerance
    assert out["c"] < out["a"] and out["c"] < out["b"]      # the noisy ruler reads lowest


def test_subcounty_wcorr_handles_nan_and_short():
    a = np.array([1.0, 2, 3, np.nan])
    b = np.array([1.0, 2, np.nan, 4])
    assert np.isnan(vs._wcorr(a, b, np.ones(4)))            # too few valid pairs -> nan, no crash

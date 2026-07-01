"""Leave-one-state-out CV regression: on data with a known linear signal, the pooled
out-of-sample R^2 must be high and the per-fold weights stable; on pure noise it must NOT report a
high CV R^2 (the whole point of CV is that it refuses to certify an overfit)."""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("scipy")
from pipeline.validate import _cv_regression  # noqa: E402


def _make(groups: int = 12, per: int = 120, seed: int = 0, noise: float = 0.3):
    rng = np.random.default_rng(seed)
    n = groups * per
    X = rng.normal(0, 1, (n, 3))
    g = np.repeat(np.arange(groups), per).astype(object)
    return X, g, rng


def test_cv_recovers_signal_and_is_stable():
    X, g, rng = _make()
    # y depends mostly on dim 0, some on dim 2, none on dim 1 (all non-negative => NNLS-friendly)
    y = 2.0 * X[:, 0] + 1.0 * X[:, 2] + rng.normal(0, 0.3, len(X))
    out = _cv_regression(X, y, g)
    assert out is not None
    assert out["cv_r2"] > 0.6                      # real signal recovered out-of-sample
    assert out["n_folds"] >= 5
    # weights stable across folds (SD small relative to the 0-100 scale)
    assert max(out["weight_sd"].values()) < 8.0


def test_cv_refuses_noise():
    X, g, rng = _make(seed=1)
    y = rng.normal(0, 1, len(X))                   # no relationship to X
    out = _cv_regression(X, y, g)
    assert out is not None
    assert out["cv_r2"] < 0.1                       # CV does not certify an overfit

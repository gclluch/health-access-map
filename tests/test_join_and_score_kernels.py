"""CI-runnable unit tests for join_and_score's dimensionality kernels.

join_and_score's scoring path needs a real metrics.parquet, so the composite≈PC1 proof and the
taxonomy resolution derivation are otherwise only checkable against live data. These synthetic
tests pin both against planted-structure oracles with fixed seeds, no data or network. (T3, T7;
docs/REMEDIATION_PLAN.md)
"""
from __future__ import annotations

import numpy as np

from pipeline.join_and_score import _composite_pc1_corr
from pipeline.taxonomy import subscore_resolution, subscore_specs


# --- _composite_pc1_corr (composite ≈ PC1 ?) -------------------------------------------------

def _equal_mean(X: np.ndarray) -> np.ndarray:
    return X.mean(axis=1)


def test_pc1_corr_is_one_when_dimensions_are_one_gradient():
    # three near-collinear "dimensions" (shared latent + small noise) -> the equal-weight mean IS
    # the first principal component, so |r| ~ 1 (the real index sits here, 0.999).
    rng = np.random.default_rng(0)
    n = 2000
    latent = rng.normal(size=n)
    X = np.column_stack([latent + rng.normal(size=n) * 0.25 for _ in range(3)])
    r = _composite_pc1_corr(X, _equal_mean(X))
    assert r is not None and r > 0.99


def test_pc1_corr_drops_when_a_dimension_is_independent():
    # two collinear dims + one independent dim: PC1 loads on the correlated pair, but the equal-weight
    # composite still carries the independent dim, so it is NO LONGER ~PC1.
    rng = np.random.default_rng(1)
    n = 2000
    latent = rng.normal(size=n)
    X = np.column_stack([latent + rng.normal(size=n) * 0.2,
                         latent + rng.normal(size=n) * 0.2,
                         rng.normal(size=n)])               # independent third axis
    r = _composite_pc1_corr(X, _equal_mean(X))
    assert r is not None and r < 0.95                       # clearly separated from the 1-gradient case


def test_pc1_corr_drops_nan_rows():
    rng = np.random.default_rng(2)
    n = 500
    latent = rng.normal(size=n)
    X = np.column_stack([latent + rng.normal(size=n) * 0.25 for _ in range(3)])
    comp = _equal_mean(X)
    X[5, 1] = np.nan          # a NaN in a dimension...
    comp[9] = np.nan          # ...and in the composite
    r = _composite_pc1_corr(X, comp)
    assert r is not None and r > 0.99   # still recovered from the complete rows


def test_pc1_corr_none_below_min_rows():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(8, 3))
    assert _composite_pc1_corr(X, X.mean(axis=1)) is None


def test_pc1_corr_none_on_constant_composite():
    rng = np.random.default_rng(4)
    X = rng.normal(size=(200, 3))
    assert _composite_pc1_corr(X, np.zeros(200)) is None


# --- subscore_resolution (taxonomy per-measure resolution) -----------------------------------

def test_subscore_resolution_classifies_member_mix():
    assert subscore_resolution([{"res": "zcta"}, {"res": "zcta"}]) == "zcta"
    assert subscore_resolution([{"res": "county"}]) == "county"
    assert subscore_resolution([{"res": "zcta"}, {"res": "county"}]) == "mixed"
    assert subscore_resolution([{}]) == "zcta"            # missing res defaults to zcta


def test_county_subscores_tagged_in_taxonomy():
    res = {s["key"]: s["resolution"] for s in subscore_specs()}
    # the two county-broadcast scored barriers (within-county r ~0) are tagged county...
    assert res["shortage_designation"] == "county"
    assert res["medical_debt"] == "county"
    # ...and the genuinely sub-county-varying ones are not.
    assert res["provider_supply"] == "zcta"
    assert res["insurance"] == "zcta"
    assert res["socioeconomic"] == "zcta"

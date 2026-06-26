"""Small statistical helpers shared by validation gates.

The validation scripts intentionally stay script-like, but the low-level math should not be
copy/pasted across them. These helpers are deliberately minimal: no modeling policy lives here,
only reusable transforms/correlations with consistent NaN handling.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_VALID_PAIRS = 50


def pearson_corr(a: np.ndarray, b: np.ndarray, min_pairs: int = MIN_VALID_PAIRS) -> float:
    """NaN-safe Pearson correlation on two 1-D arrays."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < min_pairs:
        return float("nan")
    a, b = a[m] - a[m].mean(), b[m] - b[m].mean()
    denom = np.sqrt((a @ a) * (b @ b))
    return float(a @ b / denom) if denom > 0 else float("nan")


def within_residual(frame: pd.DataFrame, col: str, group_col: str = "county_fips") -> np.ndarray:
    """Residual after removing a group mean, used for county fixed-effect validation."""
    s = pd.to_numeric(frame[col], errors="coerce")
    return (s - s.groupby(frame[group_col]).transform("mean")).to_numpy()


def weighted_corr(
    a: np.ndarray,
    b: np.ndarray,
    weights: np.ndarray,
    min_pairs: int = MIN_VALID_PAIRS,
) -> float:
    """NaN-safe precision-weighted Pearson correlation."""
    a, b, weights = np.asarray(a, float), np.asarray(b, float), np.asarray(weights, float)
    m = ~(np.isnan(a) | np.isnan(b) | np.isnan(weights)) & (weights > 0)
    if m.sum() < min_pairs:
        return float("nan")
    a, b, weights = a[m], b[m], weights[m]
    total = weights.sum()
    am, bm = (a * weights).sum() / total, (b * weights).sum() / total
    cov = (weights * (a - am) * (b - bm)).sum()
    va = (weights * (a - am) ** 2).sum()
    vb = (weights * (b - bm) ** 2).sum()
    return float(cov / np.sqrt(va * vb)) if va > 0 and vb > 0 else float("nan")

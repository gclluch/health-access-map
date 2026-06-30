"""CI-runnable unit tests for the per-ZCTA rank band's measurement-error decomposition (T4).

The shipped reliable range (access_gap_rank_lo/hi) combines plausible re-weighting with ACS/PLACES
measurement noise propagated from published standard errors. These synthetic, fixed-seed tests pin
the two T4 invariants without live data: (1) measurement noise can only WIDEN the band, and (2) the
measurement share is MONOTONE in input noise - a noisier (low-confidence) ZCTA gets a wider band.
The σ magnitude itself is separately calibrated against an SE-resample by pipeline.verify_bands.
(docs/REMEDIATION_PLAN.md T4)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.join_and_score import _rank_band_decomposition, _rank_uncertainty
from pipeline.taxonomy import DIMENSIONS


def _synthetic_band_frame(n: int = 2000, seed: int = 0) -> tuple[pd.DataFrame, list[str]]:
    """Scoreable ZCTAs on one latent gradient. Half are noisy (high ACS input CV, low_confidence),
    half well-measured - so the median band width is comparable across the two confidence tiers
    and the only systematic difference is the planted measurement noise."""
    rng = np.random.default_rng(seed)
    dim_cols = [f"{d}_pctile" for d in DIMENSIONS]
    latent = rng.uniform(0, 100, size=n)
    df = pd.DataFrame({c: np.clip(latent + rng.normal(0, 15, n), 0, 100) for c in dim_cols})
    df["scoreable"] = True
    low_conf = np.zeros(n, dtype=bool)
    low_conf[: n // 2] = True
    df["low_confidence"] = low_conf
    df["acs_input_cv"] = np.where(low_conf, 1.2, 0.1)  # noisy vs clean ACS inputs
    df["places_input_cv"] = 0.02  # small + uniform: isolates the ACS contribution difference
    return df, dim_cols


def test_measurement_noise_only_widens_the_band():
    df, dim_cols = _synthetic_band_frame()
    clo, chi = _rank_uncertainty(df, dim_cols, add_noise=True)
    wlo, whi = _rank_uncertainty(df, dim_cols, add_noise=False)
    # the combined (noise-on) band is never narrower than the weight-only band, in the median
    assert np.nanmedian(whi - wlo) <= np.nanmedian(chi - clo)


def test_decomposition_share_is_nonneg_and_monotone_in_noise():
    df, dim_cols = _synthetic_band_frame()
    lo, hi = _rank_uncertainty(df, dim_cols, add_noise=True)
    df["access_gap_rank_lo"], df["access_gap_rank_hi"] = lo, hi
    out = _rank_band_decomposition(df, dim_cols)
    lc = out["low_confidence"]
    hc = out["high_confidence"]
    # measurement contribution = combined - weight_only is non-negative for both tiers
    assert lc["median_band_measurement_contribution"] >= 0
    assert hc["median_band_measurement_contribution"] >= 0
    # and it is larger for the noisier (low-confidence) tier - the band tracks the ACS MOE
    assert lc["median_band_measurement_contribution"] > hc["median_band_measurement_contribution"]


def test_decomposition_empty_without_band_columns():
    df, dim_cols = _synthetic_band_frame()
    # no access_gap_rank_lo/hi present -> nothing to decompose
    assert _rank_band_decomposition(df, dim_cols) == {}

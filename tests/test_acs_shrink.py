"""Synthetic tests for the Fay-Herriot empirical-Bayes shrinkage (_eb_shrink),
which shrinks every small-area social/economic rate. The key property under test:
the shrinkage TARGET is the precision-weighted state mean, so a single very noisy
outlier cannot drag the destination that the noisy units are then shrunk toward.
"""
import numpy as np
import pandas as pd

from pipeline.build_acs import _eb_shrink


def test_fh_shrinks_noisy_outlier_toward_precise_center():
    # Five precisely-measured ZCTAs cluster tightly at ~0.10; one wildly noisy ZCTA reads 0.90.
    # The full FH (jointly-fit tau^2 + precision-weighted GLS mean) must (a) pull the noisy unit
    # hard toward the ~0.10 cluster, and (b) leave the precise units essentially untouched - the
    # noisy unit moves far more than any precise one, because gamma is small only where SE is large.
    rate = pd.Series([0.10, 0.11, 0.09, 0.10, 0.10, 0.90])
    se = pd.Series([0.005, 0.005, 0.005, 0.005, 0.005, 0.40])  # last unit hugely uncertain
    group = pd.Series(["AA"] * 6)

    out = _eb_shrink(rate, se, group)

    assert out.iloc[5] < 0.60                       # noisy unit pulled well down from 0.90
    precise_moves = [abs(out.iloc[i] - rate.iloc[i]) for i in range(5)]
    assert max(precise_moves) < 0.03                # well-measured units barely move
    assert (0.90 - out.iloc[5]) > 5 * max(precise_moves)  # outlier moves far more than any precise unit


def test_fh_zero_tau2_when_spread_is_pure_noise():
    # If between-area spread is fully explained by sampling error (huge SEs, tight latent mean),
    # tau^2 -> 0 and every unit shrinks essentially to the common GLS mean.
    rng = np.random.default_rng(1)
    truth = 0.30
    se = pd.Series([0.25] * 12)                      # very noisy
    rate = pd.Series(truth + rng.standard_normal(12) * 0.25).clip(0, 1)
    out = _eb_shrink(rate, se, pd.Series(["AA"] * 12))
    # all shrunk values collapse near the single GLS mean (spread shrinks dramatically)
    assert out.std() < rate.std() / 3


def test_no_se_rows_left_untouched():
    # Rows lacking an SE are not shrunk (the guard requires both rate and se present).
    rate = pd.Series([0.10, 0.20, 0.30, 0.40, 0.50, 0.60])
    se = pd.Series([0.01, 0.01, 0.01, 0.01, 0.01, np.nan])
    state = pd.Series(["AA"] * 6)
    out = _eb_shrink(rate, se, state)
    assert out.iloc[5] == 0.60  # untouched (no SE)


def test_small_groups_skipped():
    # Fewer than 5 valid units in a state -> no shrinkage (too few to estimate tau^2).
    rate = pd.Series([0.10, 0.90])
    se = pd.Series([0.01, 0.01])
    state = pd.Series(["AA", "AA"])
    out = _eb_shrink(rate, se, state)
    pd.testing.assert_series_equal(out, rate.clip(0, 1))


def test_output_bounded_and_aligned():
    rng = np.random.default_rng(0)
    n = 200
    rate = pd.Series(rng.uniform(0, 1, n))
    se = pd.Series(rng.uniform(0.001, 0.2, n))
    state = pd.Series(rng.choice(["AA", "BB", "CC"], n))
    out = _eb_shrink(rate, se, state)
    assert out.index.equals(rate.index)
    assert (out >= 0).all() and (out <= 1).all()

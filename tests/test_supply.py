"""Isolated correctness tests for the E2SFCA spatial-supply kernels.

These verify the two-step floating-catchment math on a hand-computable toy grid -
the acceptance suite only checks the downstream outcome correlation, which is an
integration proxy that a compensating bug could pass. Here the expected values are
derived by hand from Luo & Qi (2009):
  Step 1: Rj = providers_j / Sum_k demand_k * w(d_jk)
  Step 2: A_i = Sum_j Rj * w(d_ij)
"""
import numpy as np

from pipeline.build_supply import _e2sfca, _e2sfca_adaptive


def test_e2sfca_decay_asymmetry_hand_computed():
    # Two co-catchment points. All providers sit at loc0. Decay weight is 1.0 to self,
    # 0.5 across the gap, so loc0 (on top of the provider) should end up with exactly
    # twice the access of loc1 (one decay-step away).
    providers = np.array([10.0, 0.0])
    demand = np.array([50.0, 50.0])
    neighbors = [np.array([0, 1]), np.array([0, 1])]
    weights = [np.array([1.0, 0.5]), np.array([0.5, 1.0])]

    # Step 1: pooled[0]=50*1.0+50*0.5=75; pooled[1]=50*0.5+50*1.0=75; Rj=[10/75, 0]
    # Step 2: A[0]=0.13333*1.0=0.13333; A[1]=0.13333*0.5=0.066667
    a = _e2sfca(providers, demand, neighbors, weights)
    assert a[0] == np.float64(10.0 / 75.0)
    assert a[1] == np.float64(10.0 / 75.0 * 0.5)
    assert abs(a[0] - 2.0 * a[1]) < 1e-12  # near point is exactly 2x the far point


def test_e2sfca_zero_demand_pooled_is_guarded():
    # A supply location whose catchment pools zero demand must not divide by zero -
    # Rj is defined as 0 there (the np.divide where= guard), so access is 0, not inf/nan.
    providers = np.array([5.0])
    demand = np.array([0.0])
    neighbors = [np.array([0])]
    weights = [np.array([1.0])]
    a = _e2sfca(providers, demand, neighbors, weights)
    assert a[0] == 0.0
    assert np.isfinite(a[0])


def test_e2sfca_adaptive_matches_fixed_on_same_inputs():
    # The vectorized adaptive kernel must reproduce the list-comprehension _e2sfca on
    # identical neighbour/weight structure (k=2 here). Same hand-computed expectation.
    providers = np.array([10.0, 0.0])
    demand = np.array([50.0, 50.0])
    ni = np.array([[0, 1], [0, 1]])
    w1 = np.array([[1.0, 0.5], [0.5, 1.0]])
    w2 = np.array([[1.0, 0.5], [0.5, 1.0]])
    a = _e2sfca_adaptive(providers, demand, ni, w1, w2)
    np.testing.assert_allclose(a, [10.0 / 75.0, 10.0 / 75.0 * 0.5])


def test_e2sfca_adaptive_parity_with_list_kernel_random():
    # Property test: on a random small graph with a shared symmetric neighbour set, the
    # adaptive (vectorized) and fixed (list) kernels must agree to floating tolerance.
    rng = np.random.default_rng(0)
    n, k = 6, 4
    providers = rng.integers(0, 8, n).astype(float)
    demand = rng.integers(1, 200, n).astype(float)
    ni = np.array([rng.permutation(n)[:k] for _ in range(n)])
    w1 = rng.uniform(0.1, 1.0, (n, k))
    w2 = rng.uniform(0.1, 1.0, (n, k))
    neighbors = [ni[i] for i in range(n)]
    weights1 = [w1[i] for i in range(n)]

    # _e2sfca uses one weight set for both steps, so build the fixed expectation
    # step-by-step with the same w1 (step 1) and w2 (step 2) the adaptive kernel uses.
    pooled = np.array([(demand[neighbors[j]] * weights1[j]).sum() for j in range(n)])
    Rj = np.divide(providers, pooled, out=np.zeros(n), where=pooled > 0)
    expected = np.array([(Rj[ni[i]] * w2[i]).sum() for i in range(n)])

    got = _e2sfca_adaptive(providers, demand, ni, w1, w2)
    np.testing.assert_allclose(got, expected, rtol=1e-12)

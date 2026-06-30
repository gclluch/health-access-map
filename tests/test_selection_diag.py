"""Selection/missingness audit must run on a real build and report the three nested selections
plus member completeness, each as a well-shaped block (so the honest caveats are reproducible)."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
METRICS = ROOT / "data" / "processed" / "metrics.parquet"

needs_data = pytest.mark.skipif(not METRICS.exists(), reason="run the pipeline first")


@needs_data
def test_selection_diag_shape():
    from pipeline import selection_diag

    r = selection_diag.run()
    # scoreability: a population share in [0,1]
    assert 0.0 <= r["scoreability"]["non_scoreable_pop_share"] <= 1.0
    # dimension completeness reports an effect size vs the independent outcome
    dc = r["dimension_completeness"]
    assert "amenable_mortality_d" in dc or "life_expectancy_d" in dc
    # the 2-of-3 missingness mechanism is characterized (T2): which dim is absent + a pop signal
    assert "mechanism" in dc and "missing_dimension_counts" in dc["mechanism"]
    # validation-subset selection covers each present outcome with a coverage fraction
    for o, v in r["validation_subset"].items():
        assert 0.0 <= v.get("coverage_among_scoreable", 1.0) <= 1.0
    # member completeness: every reported sub-score has a present-fraction in [0,1]
    for k, v in r["subscore_member_completeness"].items():
        assert 0.0 <= v["mean_frac_present"] <= 1.0


def test_cohend_sign_and_zero():
    import numpy as np
    from pipeline.selection_diag import _cohend

    rng = np.random.default_rng(0)
    a = rng.normal(1.0, 1.0, 500)
    b = rng.normal(0.0, 1.0, 500)
    assert _cohend(a, b) > 0.5            # a clearly higher than b
    assert abs(_cohend(b, b)) < 0.05      # identical-distribution => ~0


def test_two_dim_mechanism_detects_planted_mnar():
    """Plant the real-world MNAR shape (2-dim ZCTAs are tiny, low-confidence, all missing health_need)
    and assert the mechanism diagnostic surfaces it - the evidence T2's headline exclusion rests on."""
    import numpy as np
    import pandas as pd
    from pipeline.selection_diag import _two_dim_mechanism

    n_full, n_part = 100, 20
    df = pd.DataFrame({
        "health_need_pctile": [50.0] * n_full + [np.nan] * n_part,     # 2-dim group lacks health_need
        "social_vulnerability_pctile": [50.0] * (n_full + n_part),
        "care_access_pctile": [50.0] * (n_full + n_part),
        "population": [3000.0] * n_full + [40.0] * n_part,             # 2-dim are tiny
        "low_confidence": [False] * n_full + [True] * n_part,          # ...and low-confidence
    })
    full = np.array([True] * n_full + [False] * n_part)
    partial = ~full
    m = _two_dim_mechanism(df, full, partial, df["population"])
    assert m["missing_dimension_counts"] == {"health_need": n_part}
    assert m["median_pop_2of3"] < m["median_pop_3of3"]                 # MNAR: smaller areas
    assert m["low_confidence_share_2of3"] > m["low_confidence_share_3of3"]

"""Selection/missingness audit must run on a real build and report the three nested selections
plus member completeness, each as a well-shaped block (so the honest caveats are reproducible)."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
METRICS = ROOT / "data" / "processed" / "metrics.parquet"

pytestmark = pytest.mark.skipif(not METRICS.exists(), reason="run the pipeline first")


def test_selection_diag_shape():
    from pipeline import selection_diag

    r = selection_diag.run()
    # scoreability: a population share in [0,1]
    assert 0.0 <= r["scoreability"]["non_scoreable_pop_share"] <= 1.0
    # dimension completeness reports an effect size vs the independent outcome
    dc = r["dimension_completeness"]
    assert "amenable_mortality_d" in dc or "life_expectancy_d" in dc
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

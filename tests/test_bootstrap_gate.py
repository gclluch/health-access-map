"""The bootstrap gate must run, be deterministic (fixed seed), and produce a
well-shaped CI report - so ship/kill decisions can cite an interval, not a point."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
METRICS = ROOT / "data" / "processed" / "metrics.parquet"

pytestmark = pytest.mark.skipif(not METRICS.exists(), reason="run the pipeline first")


def test_bootstrap_gate_shape_and_determinism():
    from pipeline import bootstrap_gate

    a = bootstrap_gate.run(n_boot=80, seed=0)
    b = bootstrap_gate.run(n_boot=80, seed=0)

    # deterministic for a fixed seed (the build + gate are reproducible)
    assert a["margins"]["care_access"] == b["margins"]["care_access"]
    assert a["care_access_adds_signal_boot_p"] == b["care_access_adds_signal_boot_p"]

    # clustering really happened (counties << zctas)
    assert a["n_clusters"] < a["n_zctas"]

    for m in a["margins"].values():
        assert "point" in m and len(m["ci95"]) == 2
        assert m["ci95"][0] <= m["point"] <= m["ci95"][1] + 1e-9
    # care access marginal value is robustly positive at national scope
    assert a["margins"]["care_access"]["ci95"][0] > 0

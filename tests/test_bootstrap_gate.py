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


def test_bh_fdr_monotone_and_correct():
    """BH-adjusted q-values are monotone in raw p and reproduce a hand-checked example."""
    from pipeline.bootstrap_gate import _bh_fdr

    # 4 hypotheses; BH q_(i) = min over j>=i of p_(j)*m/j, enforced monotone
    out = _bh_fdr({"a": 0.001, "b": 0.01, "c": 0.03, "d": 0.5}, q=0.05)
    qs = [out[k]["q_value"] for k in ("a", "b", "c", "d")]
    assert qs == sorted(qs)                       # monotone in rank
    assert out["a"]["survives_fdr"] and not out["d"]["survives_fdr"]
    assert abs(out["d"]["q_value"] - 0.5) < 1e-9  # largest p: q = p


def test_spatial_blocking_widens_ci():
    """Point 2: state blocking (fewer, spatially-honest clusters) must produce a CI at least as
    wide as county blocking on the same statistic - resampling whole states cannot make the
    interval narrower. Skips if no amenable outcome is built."""
    import pandas as pd
    from pipeline import bootstrap_gate, config

    d = pd.read_parquet(config.PROCESSED / "metrics.parquet")
    d = d[d["scoreable"] == True].reset_index(drop=True)  # noqa: E712
    res = bootstrap_gate.spatial_sensitivity(d, n_boot=120, seed=0)
    if res is None:
        pytest.skip("no amenable_mortality column")
    p = res["care_access_partial_r"]
    assert p["state"]["n_clusters"] < p["county"]["n_clusters"]  # states << counties
    cw = p["county"]["ci95"][1] - p["county"]["ci95"][0]
    sw = p["state"]["ci95"][1] - p["state"]["ci95"][0]
    assert sw >= cw - 0.005   # state CI no narrower than county (allow tiny MC noise)


def test_amenable_subscores_shape():
    """B2: if the WONDER amenable export is built, every scored care sub-score gets a partial-r,
    a 2-element CI, and an FDR verdict; otherwise the function no-ops (None)."""
    import pandas as pd
    from pipeline import bootstrap_gate, config

    d = pd.read_parquet(config.PROCESSED / "metrics.parquet")
    d = d[d["scoreable"] == True].reset_index(drop=True)  # noqa: E712
    res = bootstrap_gate.amenable_subscores(d, n_boot=80, seed=0)
    if res is None:
        pytest.skip("no amenable_mortality column (WONDER export not built)")
    assert res["n_candidates"] == len(res["subscores"])
    for s in res["subscores"].values():
        assert len(s["ci95"]) == 2 and "partial_r" in s and "survives_fdr" in s

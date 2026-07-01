"""CI-runnable unit tests for the T8 two-tier columnar client payload.

join_and_score's full write path needs a real metrics.parquet, so the payload writers are otherwise
only checkable against a live build. These synthetic tests pin the columnar shape (struct-of-arrays,
int-quantized percentiles, NaN -> null) and the frame/sub-score partition, no data or network.
(T8; docs/REMEDIATION_PLAN.md)
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from pipeline.join_and_score import (SUBSCORE_COLS, _columnar, _write_map_frame,
                                     _write_subscores)


def _frame() -> pd.DataFrame:
    return pd.DataFrame({
        "zcta5": ["01001", "01002", "01003"],
        "state": ["MA", "MA", None],
        "state_name": ["Massachusetts", "Massachusetts", None],
        "city": ["Agawam", None, "Amherst"],
        "county_name": ["Hampden", "Hampden", "Hampshire"],
        "population": [4895, 0, 8123],
        "access_gap_score": [45.3, np.nan, 88.7],
        "access_gap_pctile": [45.3, np.nan, 88.7],
        "access_gap_pctile_within_state": [40.1, np.nan, 90.2],
        "care_access_resid_pctile": [50.9, np.nan, 12.4],
        "access_gap_rank_lo": [39.4, np.nan, 82.5],
        "access_gap_rank_hi": [51.6, np.nan, 94.9],
        "tier": [5, None, 9],
        "n_dims_scored": [3, 2, 3],
        "low_confidence": [False, True, False],
        "institutional": [False, False, False],
        "scoreable": [True, False, True],
        "life_expectancy": [80.1, np.nan, 78.4],
        "life_expectancy_pctile": [50.5, np.nan, 61.9],
        "health_need_pctile": [61.2, np.nan, 92.8],
        "social_vulnerability_pctile": [58.0, np.nan, 87.1],
        "care_access_pctile": [40.0, np.nan, 85.5],
        **{c: [10.4, np.nan, 70.6] for c in SUBSCORE_COLS},
    })


def test_columnar_is_struct_of_arrays_with_int_quantized_floats():
    df = _frame()
    # nullable-int + NA columns must survive json.dumps (the real build tripped on numpy/NAType
    # scalars leaking through) -> round-trip through JSON, not just compare the dict.
    df["tier"] = df["tier"].astype("Int64")
    out = _columnar(df, ["zcta5", "access_gap_pctile", "population", "scoreable", "tier"])
    out = json.loads(json.dumps(out, separators=(",", ":")))
    assert out["n"] == 3
    # struct-of-arrays: one array per column, length n
    assert out["zcta5"] == ["01001", "01002", "01003"]
    # floats quantized to int, NaN -> null
    assert out["access_gap_pctile"] == [45, None, 89]
    # booleans -> 0/1
    assert out["scoreable"] == [1, 0, 1]
    assert out["population"] == [4895, 0, 8123]
    # nullable Int64 with a NA -> null, values stay ints
    assert out["tier"] == [5, None, 9]


def test_map_frame_excludes_subscores_and_dropped_columns(tmp_path, monkeypatch):
    import pipeline.join_and_score as mod
    monkeypatch.setattr(mod, "OUT_MAP_FRAME", tmp_path / "map_frame.json")
    dim_cols = ["health_need_pctile", "social_vulnerability_pctile", "care_access_pctile"]
    _write_map_frame(_frame(), dim_cols)
    frame = json.loads((tmp_path / "map_frame.json").read_text())

    assert frame["n"] == 3
    # first-paint columns present
    for c in ["zcta5", "access_gap_rank_lo", "tier", "scoreable", *dim_cols]:
        assert c in frame
    # sub-scores + client-unused columns are NOT in the frame
    for c in [*SUBSCORE_COLS, "access_gap_score", "state_name", "life_expectancy"]:
        assert c not in frame


def test_subscores_payload_has_all_lenses_keyed_by_zcta(tmp_path, monkeypatch):
    import pipeline.join_and_score as mod
    monkeypatch.setattr(mod, "OUT_SUBSCORES", tmp_path / "subscores.json")
    _write_subscores(_frame())
    subs = json.loads((tmp_path / "subscores.json").read_text())

    assert subs["n"] == 3
    assert subs["zcta5"] == ["01001", "01002", "01003"]
    for c in [*SUBSCORE_COLS, "life_expectancy_pctile"]:
        assert c in subs
        assert len(subs[c]) == 3
    # NaN row -> null; quantized to int elsewhere
    assert subs["insurance_pctile"] == [10, None, 71]

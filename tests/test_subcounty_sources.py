"""Sub-county validation sources: light, offline-safe checks. The fetchers hit the network (or a
~700MB TX download), so these run only against the small cached aggregates a prior real run wrote;
they skip cleanly in CI. They lock the parsing/aggregation contract, not the live endpoints."""
from __future__ import annotations

import numpy as np
import pytest

from pipeline import validate_subcounty as vs


def test_acsc_prefix_flags_known_codes():
    """The ACSC principal-diagnosis prefix set flags ambulatory-care-sensitive ICD-10 codes and
    not obvious non-ACSC ones - the core of the TX (and construct) definition."""
    pref = vs.TX_ACSC_PREFIXES
    for acsc in ("E119", "J441", "J189", "I50", "N390", "I20"):       # diabetes, COPD, pneumonia...
        assert acsc.upper().startswith(pref)
    for non in ("C61", "S72001A", "O80", "Z3800"):                    # cancer, fracture, birth...
        assert not non.upper().startswith(pref)


def test_tx_cache_shape_if_present():
    if not vs.TX_ACSC_CACHE.exists():
        pytest.skip("TX aggregate not built (run validate_subcounty --texas)")
    g = vs._fetch_tx_acsc()
    assert {"zcta5", "acsc", "n_total"} <= set(g.columns)
    assert (g["acsc"] <= g["n_total"]).all()                          # ACSC is a subset of discharges
    assert g["zcta5"].str.fullmatch(r"\d{5}").all()                   # only full 5-digit ZIPs kept


def test_within_residual_removes_county_mean():
    """_within must produce a zero-mean residual per county (the within-county transform every
    source relies on)."""
    import pandas as pd
    df = pd.DataFrame({"county_fips": ["A", "A", "B", "B", "B"], "x": [1.0, 3.0, 10.0, 20.0, 30.0]})
    w = vs._within(df, "x")
    assert abs(w[:2].mean()) < 1e-9 and abs(w[2:].mean()) < 1e-9

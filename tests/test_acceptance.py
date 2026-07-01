"""Acceptance suite = definition of done (brief 12.7). Adapts thresholds to the
build scope (national vs --dev-state) read from provenance.json."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
# Prefer the full national build; fall back to the committed slice so CI runs the guards instead of
# skipping (the multi-GB build is unavailable in CI). The slice keeps national percentiles.
_REAL = PROCESSED / "metrics.parquet"
METRICS = _REAL if _REAL.exists() else FIXTURES / "metrics_slice.parquet"
PROVENANCE = (PROCESSED / "provenance.json") if _REAL.exists() else (FIXTURES / "provenance.json")
GEOJSON = ROOT / "frontend" / "public" / "zcta_overview.geojson"

pytestmark = pytest.mark.skipif(not METRICS.exists(), reason="no metrics build and no fixture")
# Tests needing the FULL build (backend API over the whole table, outcomes.parquet, a live
# validate.build, or national-scope ranking) rather than the row-level slice.
_REAL_ONLY = pytest.mark.skipif(not _REAL.exists(), reason="needs the full national build, not the slice")
_HAS_GEOJSON = pytest.mark.skipif(not GEOJSON.exists(), reason="overview geojson not built")


def _scope() -> str:
    if PROVENANCE.exists():
        return json.loads(PROVENANCE.read_text()).get("score", {}).get("scope", "national")
    return "national"


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    return pd.read_parquet(METRICS)


@pytest.fixture(scope="module")
def client() -> TestClient:
    from backend.main import app
    return TestClient(app)


# ---- Data ----
def test_row_count(df):
    if _scope() == "national":
        assert 30_000 <= len(df) <= 34_000, f"national rows={len(df)}"
    else:
        assert len(df) >= 200


def test_zcta5_format(df):
    assert df["zcta5"].astype(str).str.match(r"^\d{5}$").all()


@_REAL_ONLY
@_HAS_GEOJSON
def test_geometry_overlap(df):
    gj = json.loads(GEOJSON.read_text())
    geo = {f["properties"]["zcta5"] for f in gj["features"]}
    met = set(df["zcta5"].astype(str))
    overlap = len(geo & met) / max(1, len(geo))
    assert overlap > 0.95, f"overlap={overlap:.3f}"


def test_no_nan_inf_in_score(df):
    s = df.loc[df["scoreable"], "access_gap_score"]
    assert s.notna().all(), "scoreable rows must have a score"
    assert not np.isinf(s.to_numpy(dtype="float64")).any()


DIM_COLS = ["health_need_pctile", "social_vulnerability_pctile", "care_access_pctile"]
DIM_COLS_BARE = [c[:-7] for c in DIM_COLS]  # strip "_pctile"
SUB_COLS = [f"{s['key']}_pctile" for s in __import__("pipeline.taxonomy",
            fromlist=["subscore_specs"]).subscore_specs()]


def test_percentiles_in_range(df):
    for col in [*DIM_COLS, *SUB_COLS, "access_gap_score", "access_gap_pctile"]:
        v = df[col].dropna()
        assert len(v) and v.min() >= -0.001 and v.max() <= 100.001, col


def test_rates_unit_fraction(df):
    for col in ("poverty_rate", "uninsured_rate", "unemployment_rate", "no_vehicle_rate"):
        if col in df:
            v = df[col].dropna()
            if len(v):
                assert v.min() >= 0 and v.max() <= 1, f"{col} must be a fraction [0,1]"


def _client_access_gap(row, w=(35, 30, 35)):
    """Re-implement the TS accessGap (lib/scoring.ts): weighted mean of the 3
    dimension percentiles, renormalized over present dimensions."""
    parts = []
    for weight, col in zip(w, DIM_COLS):
        if pd.notna(row[col]):
            parts.append((weight, row[col]))
    if len(parts) < 2:
        return None
    wsum = sum(p[0] for p in parts)
    return sum(p[0] * p[1] for p in parts) / wsum if wsum > 0 else None


@pytest.mark.skipif(_scope() != "national", reason="re-ranks within the frame; national scope only")
def test_dimensions_reproducible_from_subscores(df):
    """Each dimension percentile must reproduce by re-ranking the mean of its SCORED
    sub-scores - guards the hierarchical aggregation + nullable-rank determinism.
    scored=False sub-scores (e.g. safetynet_access) are computed + displayed but excluded
    from their dimension, so the recomputation uses only scored members."""
    from pipeline.join_and_score import _pct
    from pipeline.taxonomy import DIMENSIONS, subscore_specs

    by_dim = {d: [] for d in DIMENSIONS}
    for s in subscore_specs():
        if s.get("scored", True):
            by_dim[s["dim"]].append(f"{s['key']}_pctile")
    for dkey, subs in by_dim.items():
        recomputed = _pct(df[subs].mean(axis=1))
        assert (recomputed - df[f"{dkey}_pctile"]).abs().max() < 1e-6, dkey


def test_server_client_score_parity(df):
    sub = df[df["scoreable"]].head(2000)
    for _, row in sub.iterrows():
        client = _client_access_gap(row)
        server = row["access_gap_score"]
        assert client is not None and abs(client - server) < 1e-6, (
            f"{row['zcta5']}: client {client} != server {server}"
        )


def _client_access_gap_mult(row, w=(35, 30, 35)):
    """Re-implement the TS accessGapMult (lib/scoring.ts): weighted GEOMETRIC mean of the
    3 dimension percentiles, frac clipped to [0.01,1], renormalized over present dims."""
    import math
    parts = [(weight, row[col]) for weight, col in zip(w, DIM_COLS) if pd.notna(row[col])]
    if len(parts) < 2:
        return None
    wsum = sum(p[0] for p in parts)
    lognum = sum(pw * math.log(min(1.0, max(0.01, v / 100.0))) for pw, v in parts)
    return math.exp(lognum / wsum) * 100 if wsum > 0 else None


def test_server_client_mult_lens_parity(df):
    """The multiplicative-lens client recompute (geometric mean) must match the server's
    raw access_gap_mult at default weights - guards the coincidence-lens scoring path."""
    sub = df[df["scoreable"]].head(2000)
    for _, row in sub.iterrows():
        client = _client_access_gap_mult(row)
        server = row["access_gap_mult"]
        assert client is not None and abs(client - server) < 1e-6, (
            f"{row['zcta5']}: mult client {client} != server {server}"
        )


# ---- Sanity / face validity ----
def test_affluent_vs_underserved_direction(df):
    d = df.set_index("zcta5")
    if "90210" in d.index and "90011" in d.index:
        bev = d.loc["90210", "access_gap_score"]
        sla = d.loc["90011", "access_gap_score"]  # South LA, high poverty
        assert bev < sla, f"Beverly Hills {bev} should be < South LA {sla}"


# ---- API ----
@_REAL_ONLY
def test_api_health(client, df):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["zcta_count"] == len(df)


@_REAL_ONLY
def test_api_zcta_record(client):
    r = client.get("/api/zcta/90210")
    if r.status_code == 200:
        assert r.json()["zcta5"] == "90210"


@_REAL_ONLY
def test_api_bad_zip_404(client):
    assert client.get("/api/zcta/00000").status_code == 404


@_REAL_ONLY
def test_api_rankings_sorted(client):
    r = client.get("/api/rankings?metric=access_gap_score&limit=10&order=desc")
    assert r.status_code == 200
    scores = [row["access_gap_score"] for row in r.json()["results"]]
    assert scores == sorted(scores, reverse=True)


# ---- Outcomes + multi-anchor validation (Phase 1) ----
OUTCOMES = PROCESSED / "outcomes.parquet"
WEIGHTS = ROOT / "frontend" / "public" / "weights.json"


@_REAL_ONLY
def test_outcomes_format():
    if not OUTCOMES.exists():
        pytest.skip("outcomes stage not run")
    o = pd.read_parquet(OUTCOMES)
    assert o["zcta5"].astype(str).str.match(r"^\d{5}$").all()
    assert "preventable_hosp" in o.columns
    v = o["preventable_hosp"].dropna()
    assert len(v) and (v > 0).all(), "ACSC rates must be positive"


def test_weights_json_multi_anchor_shape():
    if not WEIGHTS.exists():
        pytest.skip("validate stage not run")
    w = json.loads(WEIGHTS.read_text())
    assert set(w) >= {"default", "anchors", "subscore_correlations", "note"}
    assert set(w["default"]) == set(DIM_COLS_BARE)
    for name, a in w["anchors"].items():
        assert set(a["weights"]) == set(DIM_COLS_BARE), name
        assert abs(sum(a["weights"].values()) - 100) < 0.5, name
        assert min(a["weights"].values()) >= 4.9, f"{name}: 5% floor"
        assert "r2" in a["fit"] and "n" in a["fit"], name
        assert a["scope"] in ("county", "zcta")


@_REAL_ONLY
def test_validate_idempotent(tmp_path, monkeypatch):
    """Re-running validate against the same metrics must be deterministic - the cheap
    re-tune contract (run --only validate after supply changes) depends on this. Writes to a tmp
    weights.json so the test never clobbers the committed frontend/public/weights.json artifact."""
    from pipeline import validate
    wp = tmp_path / "weights.json"
    monkeypatch.setattr(validate, "WEIGHTS_JSON", wp)
    validate.build()
    first = wp.read_text()
    validate.build()
    assert wp.read_text() == first


def test_composite_quality_flag(df):
    """Every scoreable ZCTA records how many of the 3 dimensions backed its composite (2 or 3).
    A 2-of-3 score is a weaker estimate (audit S5) and must be distinguishable, not silent."""
    s = df[df["scoreable"]]
    n = s["n_dims_scored"].dropna()
    assert len(n) == len(s), "every scoreable row needs n_dims_scored"
    assert set(n.unique()) <= {2, 3}, f"unexpected dim counts: {sorted(n.unique())}"
    assert (n == 2).any(), "expect some partial (2-of-3) composites to flag"
    # non-scoreable rows must not carry a spurious count
    assert df.loc[~df["scoreable"], "n_dims_scored"].isna().all()


def test_access_beyond_deprivation_lens(df):
    """The orthogonalized lens (care_access residualized on need + vulnerability, re-ranked) must
    be a valid percentile AND near-orthogonal to the deprivation gradient it removes - that
    orthogonality is the whole point (it isolates structural access from 'just a poor area')."""
    col = "care_access_resid_pctile"
    assert col in df.columns
    s = df[df["scoreable"]]
    v = s[col].dropna()
    assert len(v) and v.min() >= -0.001 and v.max() <= 100.001
    # near-orthogonal to the predictors it was residualized on (observed ~0.05)
    for pred in ("health_need_pctile", "social_vulnerability_pctile"):
        pair = s[[col, pred]].dropna()
        assert abs(pair[col].corr(pair[pred])) < 0.15, f"{col} not orthogonal to {pred}"


def test_rank_uncertainty_band(df):
    """Each scoreable ZCTA carries a 5-95 rank band (Saisana sensitivity) that contains
    its point percentile, plus a coarse tier - the comparability machinery."""
    s = df[df["scoreable"]]
    for c in ("access_gap_rank_lo", "access_gap_rank_hi", "tier"):
        assert c in df.columns, c
    lo, hi, p = s["access_gap_rank_lo"], s["access_gap_rank_hi"], s["access_gap_pctile"]
    assert (lo.notna() & hi.notna()).all(), "scoreable rows need a band"
    assert (hi >= lo).all(), "band hi must be >= lo"
    # point percentile lies within the band (small tolerance for rank discretization)
    assert ((p >= lo - 3) & (p <= hi + 3)).mean() > 0.99
    assert s["tier"].between(1, 10).all()


@_REAL_ONLY
def test_access_signal_against_access_sensitive_outcome():
    """Post-Layer-C3 (variable/adaptive catchment): spatial provider supply now carries
    real, correctly-signed signal against BOTH infant mortality AND all-cause life
    expectancy. The adaptive catchment fixed the urbanicity confound that had left supply
    ~uncorrelated with life expectancy under the fixed 16 km catchment. Guards that gain."""
    if not WEIGHTS.exists():
        pytest.skip("validate stage not run")
    sc = json.loads(WEIGHTS.read_text())["subscore_correlations"]
    if "infant_mortality" not in sc or "provider_supply" not in sc.get("infant_mortality", {}):
        pytest.skip("infant mortality anchor unavailable (e.g. dev-state slice)")
    assert sc["infant_mortality"]["provider_supply"] > 0.1, "supply should track infant mortality"
    if "life_expectancy" in sc and "provider_supply" in sc["life_expectancy"]:
        # C3 win: supply now positively tracks life expectancy (was ~0 under fixed catchment)
        assert sc["life_expectancy"]["provider_supply"] > 0.08, "supply should now track LE (C3)"

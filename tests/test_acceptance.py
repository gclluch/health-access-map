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
METRICS = PROCESSED / "metrics.parquet"
PROVENANCE = PROCESSED / "provenance.json"
GEOJSON = ROOT / "frontend" / "public" / "zcta.geojson"

pytestmark = pytest.mark.skipif(not METRICS.exists(), reason="run the pipeline first")


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


def test_dimensions_reproducible_from_subscores(df):
    """Each dimension percentile must reproduce by re-ranking the mean of its
    sub-scores - guards the hierarchical aggregation + nullable-rank determinism."""
    from pipeline.join_and_score import _pct
    from pipeline.taxonomy import DIMENSIONS, subscore_specs

    by_dim = {d: [] for d in DIMENSIONS}
    for s in subscore_specs():
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


# ---- Sanity / face validity ----
def test_affluent_vs_underserved_direction(df):
    d = df.set_index("zcta5")
    if "90210" in d.index and "90011" in d.index:
        bev = d.loc["90210", "access_gap_score"]
        sla = d.loc["90011", "access_gap_score"]  # South LA, high poverty
        assert bev < sla, f"Beverly Hills {bev} should be < South LA {sla}"


# ---- API ----
def test_api_health(client, df):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["zcta_count"] == len(df)


def test_api_zcta_record(client):
    r = client.get("/api/zcta/90210")
    if r.status_code == 200:
        assert r.json()["zcta5"] == "90210"


def test_api_bad_zip_404(client):
    assert client.get("/api/zcta/00000").status_code == 404


def test_api_rankings_sorted(client):
    r = client.get("/api/rankings?metric=access_gap_score&limit=10&order=desc")
    assert r.status_code == 200
    scores = [row["access_gap_score"] for row in r.json()["results"]]
    assert scores == sorted(scores, reverse=True)


# ---- Outcomes + multi-anchor validation (Phase 1) ----
OUTCOMES = PROCESSED / "outcomes.parquet"
WEIGHTS = ROOT / "frontend" / "public" / "weights.json"


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


def test_validate_idempotent():
    """Re-running validate against the same metrics must be deterministic - the cheap
    re-tune contract (run --only validate after supply changes) depends on this."""
    from pipeline import validate
    validate.build()
    first = WEIGHTS.read_text()
    validate.build()
    assert WEIGHTS.read_text() == first


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


def test_access_signal_against_access_sensitive_outcome():
    """The core Phase-1 finding: spatial provider supply carries ~no signal against
    all-cause life expectancy but real, correctly-signed signal against an
    access-sensitive outcome (infant mortality). Guards the rationale for the rework."""
    if not WEIGHTS.exists():
        pytest.skip("validate stage not run")
    sc = json.loads(WEIGHTS.read_text())["subscore_correlations"]
    if "infant_mortality" not in sc or "provider_supply" not in sc.get("infant_mortality", {}):
        pytest.skip("infant mortality anchor unavailable (e.g. dev-state slice)")
    assert sc["infant_mortality"]["provider_supply"] > 0.1, "supply should track infant mortality"
    if "life_expectancy" in sc and "provider_supply" in sc["life_expectancy"]:
        assert abs(sc["life_expectancy"]["provider_supply"]) < 0.1, "supply ~uncorrelated with LE"

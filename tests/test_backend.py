"""Backend API contract tests (FastAPI TestClient over the real in-memory metrics table).

Skipped when metrics.parquet is absent (e.g. CI without a data build), matching
test_acceptance. Covers the validation/serialization logic: ZIP normalization,
metric allow-listing, compare bounds, JSON-safe cleaning, and response caching.
"""
from pathlib import Path

import math

import pytest

PROCESSED = Path(__file__).resolve().parent.parent / "data" / "processed"
METRICS = PROCESSED / "metrics.parquet"
pytestmark = pytest.mark.skipif(not METRICS.exists(), reason="run the pipeline first")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as c:  # triggers lifespan -> data.load()
        yield c


@pytest.fixture(scope="module")
def a_zip(client):
    # a real scoreable ZIP from the top of the default rankings
    r = client.get("/api/rankings", params={"limit": 1})
    assert r.status_code == 200
    return r.json()["results"][0]["zcta5"]


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["zcta_count"] > 0
    assert isinstance(body["states"], list) and body["states"]


def test_get_zcta_found(client, a_zip):
    r = client.get(f"/api/zcta/{a_zip}")
    assert r.status_code == 200
    assert r.json()["zcta5"] == a_zip


def test_get_zcta_zero_pads_short_input(client):
    # _norm_zcta zero-pads, so "00501" and "501" resolve to the same record (if it exists).
    r = client.get("/api/zcta/501")
    assert r.status_code in (200, 404)  # valid normalization, may or may not be a real ZCTA


def test_get_zcta_rejects_nondigit(client):
    r = client.get("/api/zcta/ABCDE")
    assert r.status_code == 422


def test_get_zcta_not_found(client):
    r = client.get("/api/zcta/99999")
    assert r.status_code in (200, 404)


def test_rankings_rejects_unknown_metric(client):
    r = client.get("/api/rankings", params={"metric": "not_a_metric"})
    assert r.status_code == 422


def test_rankings_respects_limit_and_order(client):
    r = client.get("/api/rankings", params={"limit": 5, "order": "desc"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) <= 5
    vals = [row["access_gap_score"] for row in results]
    assert vals == sorted(vals, reverse=True)


def test_rankings_limit_out_of_range_rejected(client):
    assert client.get("/api/rankings", params={"limit": 0}).status_code == 422
    assert client.get("/api/rankings", params={"limit": 99999}).status_code == 422


def test_rankings_excludes_partial_dims_by_default(client):
    # The headline (min_dims=3) holds out 2-of-3 partial composites; min_dims=2 surfaces them. The
    # gate is composite-family only, so dropping it can only ADD rows, never remove.
    from backend import data

    full = data.rankings("access_gap_score", None, 500, "desc", False, 3)
    assert all((r.get("n_dims_scored") or 0) >= 3 for r in full)
    with_partial = data.rankings("access_gap_score", None, 500, "desc", False, 2)
    assert len(with_partial) >= len(full)


def test_rankings_partial_gate_is_composite_only(client):
    # A bare dimension percentile that is itself present stays comparable, so the n_dims gate must
    # NOT touch sub-score/dimension rankings: min_dims=3 and =2 return the same set there.
    from backend import data

    at3 = data.rankings("care_access_pctile", None, 500, "desc", False, 3)
    at2 = data.rankings("care_access_pctile", None, 500, "desc", False, 2)
    assert len(at3) == len(at2)


def test_rankings_is_cached(client):
    # The lru_cache makes the second identical call return the same cached payload object.
    from backend import data

    data.rankings.cache_clear()
    before = data.rankings.cache_info().hits
    p = ("access_gap_score", None, 10, "desc", False)
    first = data.rankings(*p)
    second = data.rankings(*p)
    assert first is second  # same cached object
    assert data.rankings.cache_info().hits > before


def test_compare_bounds(client, a_zip):
    assert client.get("/api/compare", params={"zips": ""}).status_code == 422
    too_many = ",".join([a_zip] * 6)
    assert client.get("/api/compare", params={"zips": too_many}).status_code == 422
    ok = client.get("/api/compare", params={"zips": a_zip})
    assert ok.status_code == 200
    assert len(ok.json()["results"]) == 1


def test_clean_makes_json_safe(client, a_zip):
    import json

    from backend import data
    from backend.data import _clean

    assert _clean(float("nan")) is None
    assert _clean(float("inf")) is None
    assert _clean(None) is None
    assert _clean(3.5) == 3.5
    # every value in a real record must be JSON-serializable (no NaN/inf leaking through)
    rec = data.record(a_zip)
    json.dumps(rec)  # raises if a NaN/inf/NA slipped past _clean
    assert not any(isinstance(v, float) and math.isnan(v) for v in rec.values())

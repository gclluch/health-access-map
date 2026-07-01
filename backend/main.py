"""FastAPI app: dynamic attribute queries over the in-memory metrics table.

The heavy static files (zcta.geojson, map_frame.json, subscores.json) are served by Vite/CDN from
frontend/public -- NOT routed through here. This API handles only the dynamic
lookups: one ZIP, rankings, compare. CORS is opened to the Vite dev origin.
"""
from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import data

ZCTA_RE = re.compile(r"^\d{5}$")

# CORS origins are environment-driven so production deploys work without a code change.
# ALLOWED_ORIGINS = comma-separated list (e.g. "https://healthaccessmap.org"). Default is the
# Vite dev origin. "*" allows any origin (use only if the API is genuinely public + read-only).
_DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
_origins_env = os.environ.get("ALLOWED_ORIGINS")


def _parse_origins(raw: str | None) -> list[str]:
    return [origin.strip() for origin in (raw or _DEFAULT_ORIGINS).split(",") if origin.strip()]


ALLOWED_ORIGINS = _parse_origins(_origins_env)
if not _origins_env:
    # Loud warning: an unset ALLOWED_ORIGINS in a real deploy means the browser app on its prod
    # origin gets opaque CORS failures against the localhost-only default. Better a log line at
    # startup than a silently-broken SPA.
    import warnings
    warnings.warn(
        "ALLOWED_ORIGINS is not set; defaulting to localhost dev origins. Set it to your "
        "frontend origin(s) for any non-local deploy.",
        RuntimeWarning, stacklevel=2,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    data.load()  # fail fast at startup if metrics are missing
    yield


app = FastAPI(title="Care Access Map API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=os.environ.get("ALLOWED_ORIGIN_REGEX") or None,  # e.g. preview deploys
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _norm_zcta(z: str) -> str:
    z = z.strip()
    if not z.isdigit():
        raise HTTPException(422, detail=f"invalid ZIP '{z}': must be digits")
    z = z.zfill(5)
    if not ZCTA_RE.match(z):
        raise HTTPException(422, detail=f"invalid ZIP '{z}': must be 5 digits")
    return z


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "zcta_count": data.count(), "states": data.states()}


@app.get("/api/zcta/{zcta5}")
def get_zcta(zcta5: str) -> dict:
    rec = data.record(_norm_zcta(zcta5))
    if rec is None:
        raise HTTPException(404, detail=f"ZIP {zcta5} not found")
    return rec


@app.get("/api/rankings")
def get_rankings(
    metric: str = "access_gap_score",
    state: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    include_low_confidence: bool = False,
    # 3 = headline (full 3-of-3 scores only); 2 surfaces the weaker partial (2-of-3) composites,
    # which are flagged in the UI. Only gates the composite family (see data.rankings).
    min_dims: int = Query(3, ge=2, le=3),
) -> dict:
    if metric not in data.RANKABLE_METRICS:
        raise HTTPException(422, detail=f"metric must be one of {sorted(data.RANKABLE_METRICS)}")
    rows = data.rankings(metric, state, limit, order, include_low_confidence, min_dims)
    return {"metric": metric, "state": state, "order": order, "count": len(rows), "results": rows}


@app.get("/api/compare")
def get_compare(zips: str = Query(..., description="comma-separated ZIPs")) -> dict:
    parsed = [_norm_zcta(z) for z in zips.split(",") if z.strip()]
    if not (1 <= len(parsed) <= 5):
        raise HTTPException(422, detail="provide 1-5 ZIPs")
    return {"results": data.compare(parsed)}

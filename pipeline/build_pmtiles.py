"""build_pmtiles: simplified ZCTA GeoJSON -> client geometry artifacts (hybrid renderer).

Vector tiles generalize geometry per zoom, so at the national overview the sub-pixel urban
ZCTAs thin into slivers and the dense choropleth falls apart. Full-resolution tiles at low
zoom would negate the cold-load win. So the client renders a HYBRID: a tiny, heavily-
simplified all-ZCTA overview for the national/low zooms (complete coverage, dense, small), and
range-requested vector tiles for z6+ where only the viewport's ZCTAs stream at full detail.

Two artifacts, written straight to frontend/public/ (like metrics.json):
  - zcta.pmtiles          range-requested vector tiles for z>=6. The map streams only the
                          tiles in view, so zoomed-in geometry transfer + resident memory are
                          bounded instead of holding the whole ~16 MB GeoJSON.
  - zcta_overview.geojson every ZCTA, topology-simplified hard + coarse precision (~small).
                          Drives the dense low-zoom choropleth AND the client's centroids
                          (fly-to / bounds / nearest-ZIP), so no separate centroids payload.

Tile recipe (-Z5 -z10): every ZCTA keeps its zcta5 (the client joins fill colour on it), so we
never coalesce/merge features. z5 gives a one-level overlap with the overview hand-off; the
8%-simplified source already bounds boundary detail, so z10 captures all of it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import config
from .common import die, log, write_provenance

GEOJSON = config.PROCESSED / "zcta.geojson"
PMTILES = config.PROCESSED / "zcta.pmtiles"
PUBLIC_PMTILES = config.FRONTEND_PUBLIC / "zcta.pmtiles"
PUBLIC_OVERVIEW = config.FRONTEND_PUBLIC / "zcta_overview.geojson"
MAPSHAPER = config.ROOT / "node_modules" / ".bin" / "mapshaper"

# tile zoom envelope - keep in sync with TILE_MIN_ZOOM/TILE_MAX_ZOOM + the z<6 overview
# hand-off in frontend/src/components/MapView.tsx.
TILE_MINZOOM = 5
TILE_MAXZOOM = 10


def _tippecanoe(out: Path) -> None:
    exe = shutil.which("tippecanoe")
    if not exe:
        die("pmtiles", "tippecanoe not found - install it (brew install tippecanoe). "
                       "See pipeline/preflight.py.")
    cmd = [
        exe, "-q", "--force",
        f"-Z{TILE_MINZOOM}", f"-z{TILE_MAXZOOM}",
        "--no-tile-size-limit", "--no-feature-limit",  # keep every ZCTA (join needs each zcta5)
        "-l", "zcta",                                   # layer name the client reads
        "-o", str(out), str(GEOJSON),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        die("pmtiles", f"tippecanoe failed: {res.stderr[-500:]}")


def _overview(out: Path) -> None:
    """Re-simplify the (already 8%-simplified) geojson hard + coarse precision for the low-zoom
    overview. mapshaper's simplification is topology-aware, so shared borders stay coincident
    (no gaps between neighbours) even when aggressive - the choropleth stays dense."""
    cmd = [
        str(MAPSHAPER), str(GEOJSON),
        "-simplify", "5%", "keep-shapes",
        "-o", "format=geojson", "precision=0.005", str(out),  # ~500 m, invisible at z<6
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        die("pmtiles", f"mapshaper overview failed: {res.stderr[-500:]}")


def build(dev_state: str | None = None, force: bool = False) -> Path:
    if not GEOJSON.exists():
        die("pmtiles", f"missing {GEOJSON} - run the geometry stage first")
    if PUBLIC_PMTILES.exists() and PUBLIC_OVERVIEW.exists() and not force:
        log("pmtiles", "skip (exists): zcta.pmtiles + zcta_overview.geojson")
        return PUBLIC_PMTILES

    config.FRONTEND_PUBLIC.mkdir(parents=True, exist_ok=True)
    log("pmtiles", "tiling zcta.geojson -> zcta.pmtiles (tippecanoe)...")
    _tippecanoe(PMTILES)
    shutil.copyfile(PMTILES, PUBLIC_PMTILES)

    log("pmtiles", "building low-zoom overview (mapshaper re-simplify)...")
    _overview(PUBLIC_OVERVIEW)

    pm_mb = PUBLIC_PMTILES.stat().st_size / 1e6
    ov_mb = PUBLIC_OVERVIEW.stat().st_size / 1e6
    write_provenance({"pmtiles": {"pmtiles_mb": round(pm_mb, 1), "overview_mb": round(ov_mb, 1),
                                  "tippecanoe": f"-Z{TILE_MINZOOM} -z{TILE_MAXZOOM}"}})
    log("pmtiles", f"wrote zcta.pmtiles ({pm_mb:.1f} MB) + zcta_overview.geojson ({ov_mb:.1f} MB)")
    return PUBLIC_PMTILES


if __name__ == "__main__":
    import sys

    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None, force=True)

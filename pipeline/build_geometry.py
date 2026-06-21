"""build_geometry: TIGER ZCTA cartographic boundary -> simplified WGS84 GeoJSON.

Output: data/processed/zcta.geojson with feature property `zcta5` (str5) only.
"""
from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import httpx

from . import config
from .common import die, dev_prefix_js, download_file, log, write_provenance

OUT = config.PROCESSED / "zcta.geojson"
MAPSHAPER = config.ROOT / "node_modules" / ".bin" / "mapshaper"


def _resolve_tiger() -> tuple[Path, int]:
    """Try TIGER_YEAR then fallbacks until a cb_<Y>_us_zcta520_500k.zip resolves."""
    years = [config.TIGER_YEAR] + [y for y in config.TIGER_YEAR_FALLBACKS if y != config.TIGER_YEAR]
    for year in years:
        url = config.TIGER_TMPL.format(year=year)
        dest = config.RAW / f"cb_{year}_us_zcta520_500k.zip"
        try:
            if not dest.exists():
                with httpx.Client(timeout=20, follow_redirects=True) as c:
                    r = c.head(url)
                if r.status_code >= 400:
                    log("geometry", f"TIGER {year} -> HTTP {r.status_code}, trying older")
                    continue
            download_file(url, dest, min_bytes=1_000_000)
            return dest, year
        except Exception as e:  # noqa: BLE001
            log("geometry", f"TIGER {year} failed ({type(e).__name__}); trying older")
    die("geometry", "no TIGER vintage resolved")


def _unzip_shp(zip_path: Path, year: int) -> Path:
    out_dir = config.RAW / f"tiger_{year}"
    out_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out_dir)
    shp = next(out_dir.glob("*.shp"), None)
    if not shp:
        die("geometry", f"no .shp inside {zip_path.name}")
    return shp


def _detect_field(shp: Path) -> str:
    res = subprocess.run(
        [str(MAPSHAPER), str(shp), "-info"], capture_output=True, text=True
    )
    info = res.stdout + res.stderr  # mapshaper writes -info to stderr
    for field in config.TIGER_ZCTA_FIELDS:
        if field in info:
            return field
    die("geometry", f"no known ZCTA field in {shp.name}; looked for {config.TIGER_ZCTA_FIELDS}")


def build(dev_state: str | None = None, force: bool = False) -> Path:
    if OUT.exists() and not force:
        log("geometry", f"skip (exists): {OUT.name}")
        return OUT

    zip_path, year = _resolve_tiger()
    shp = _unzip_shp(zip_path, year)
    field = _detect_field(shp)
    log("geometry", f"vintage {year}, field {field}")

    cmd = [
        str(MAPSHAPER), str(shp),
        "-simplify", "8%", "keep-shapes",
        "-proj", "wgs84",
        "-rename-fields", f"zcta5={field}",
    ]
    if dev_state:
        expr = dev_prefix_js(dev_state)
        if expr:
            cmd += ["-filter", expr]
    cmd += [
        "-filter-fields", "zcta5",
        "-o", "format=geojson", "precision=0.0001", str(OUT),
    ]
    log("geometry", "running mapshaper simplify/reproject...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        die("geometry", f"mapshaper failed: {res.stderr[-500:]}")

    _validate(dev_state)
    size_mb = OUT.stat().st_size / 1e6
    write_provenance({"geometry": {"tiger_year": year, "zcta_field": field,
                                   "geojson_mb": round(size_mb, 1)}})
    log("geometry", f"wrote {OUT.name} ({size_mb:.1f} MB)")
    return OUT


def _validate(dev_state: str | None) -> None:
    gj = json.loads(OUT.read_text())
    feats = gj.get("features", [])
    n = len(feats)
    floor = 200 if dev_state else 25_000
    if n < floor:
        die("geometry", f"only {n} features (expected >= {floor})")
    import re
    sample = feats[: min(500, n)]
    for f in sample:
        z = f["properties"].get("zcta5")
        if not (isinstance(z, str) and re.match(r"^\d{5}$", z)):
            die("geometry", f"bad zcta5 property: {z!r}")
    # spot-check first coordinate in range
    coords = feats[0]["geometry"]["coordinates"]
    flat = coords
    while isinstance(flat[0], list):
        flat = flat[0]
    lon, lat = flat[0], flat[1]
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        die("geometry", f"coords out of range: {lon},{lat}")
    log("geometry", f"validated {n} features, zcta5 str5, coords in range")


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

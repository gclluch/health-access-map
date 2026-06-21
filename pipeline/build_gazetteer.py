"""build_gazetteer: Census ZCTA Gazetteer -> internal-point lat/lon centroids.

Output: gazetteer.parquet (zcta5(str5), lat, lon). Used by the 2SFCA supply stage.
The Gazetteer "internal point" is a guaranteed-inside-the-polygon representative
point - a better catchment anchor than a raw geometric centroid for odd shapes.
"""
from __future__ import annotations

import io
import zipfile

import httpx
import pandas as pd

from . import config
from .common import assert_zcta, dev_filter, die, download_file, log, norm_zcta

OUT = config.PROCESSED / "gazetteer.parquet"


def _resolve():
    for year in config.GAZETTEER_YEARS:
        url = config.GAZETTEER_TMPL.format(year=year)
        dest = config.RAW / f"gaz_zcta_{year}.zip"
        try:
            if not dest.exists():
                with httpx.Client(timeout=20, follow_redirects=True) as c:
                    if c.head(url).status_code >= 400:
                        continue
            download_file(url, dest, min_bytes=100_000)
            return dest, year
        except Exception:  # noqa: BLE001
            continue
    die("gazetteer", "no Gazetteer vintage resolved")


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("gazetteer", f"skip (exists): {OUT.name}")
        return str(OUT)
    dest, year = _resolve()
    with zipfile.ZipFile(dest) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".txt"))
        raw = z.read(name)
    # tab-separated, latin-1 safe; columns: GEOID, ..., INTPTLAT, INTPTLONG
    df = pd.read_csv(io.BytesIO(raw), sep="\t", dtype=str, encoding="latin-1")
    df.columns = [c.strip() for c in df.columns]
    geo = next(c for c in df.columns if c.upper() in ("GEOID", "GEOID20"))
    lat = next(c for c in df.columns if "INTPTLAT" in c.upper())
    lon = next(c for c in df.columns if "INTPTLONG" in c.upper())
    out = pd.DataFrame({
        "zcta5": norm_zcta(df[geo]),
        "lat": pd.to_numeric(df[lat], errors="coerce"),
        "lon": pd.to_numeric(df[lon], errors="coerce"),
    }).dropna().drop_duplicates("zcta5")
    out = dev_filter(out, dev_state)
    assert_zcta(out, stage="gazetteer")
    if (dev_state and len(out) < 100) or (not dev_state and len(out) < 25_000):
        die("gazetteer", f"only {len(out)} centroids")
    out.to_parquet(OUT, index=False)
    log("gazetteer", f"wrote {OUT.name} ({len(out)} centroids, {year} vintage)")
    return str(OUT)


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

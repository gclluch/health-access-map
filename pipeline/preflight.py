"""Preflight: fail fast with actionable messages before any download (brief 12.2)."""
from __future__ import annotations

import shutil
import subprocess
import sys

import httpx

from . import config
from .common import load_env, log

MIN_FREE_GB = 25


def _ok(label: str, detail: str = "") -> None:
    log("preflight", f"OK   {label} {detail}".rstrip())


def _fail(label: str, detail: str) -> None:
    log("preflight", f"FAIL {label}: {detail}")


def check() -> bool:
    load_env()
    ok = True

    # Python
    if sys.version_info >= (3, 10):
        _ok("python", f"{sys.version_info.major}.{sys.version_info.minor}")
    else:
        _fail("python", "need >= 3.10"); ok = False

    # Node
    node = shutil.which("node")
    if node:
        v = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
        _ok("node", v)
    else:
        _fail("node", "not on PATH (need >= 18)"); ok = False

    # mapshaper (local node_modules preferred, else PATH)
    ms = config.ROOT / "node_modules" / ".bin" / "mapshaper"
    if ms.exists() or shutil.which("mapshaper"):
        _ok("mapshaper", str(ms) if ms.exists() else "(PATH)")
    else:
        _fail("mapshaper", "missing; run `npm install` in repo root"); ok = False

    # unzip
    if shutil.which("unzip"):
        _ok("unzip")
    else:
        _fail("unzip", "not on PATH"); ok = False

    # Disk
    free_gb = shutil.disk_usage(config.ROOT).free / 1e9
    if free_gb >= MIN_FREE_GB:
        _ok("disk", f"{free_gb:.0f} GB free")
    else:
        _fail("disk", f"{free_gb:.0f} GB free, need >= {MIN_FREE_GB} (NPPES unzips ~10 GB)")
        ok = False

    # Census key
    if config.CENSUS_API_KEY:
        _ok("census-key", "present")
    else:
        _fail("census-key", "CENSUS_API_KEY missing in .env (ACS layer will be skipped)")
        # not fatal -- ACS can be skipped

    # Host reachability (HEAD; report, don't hard-fail individually)
    for host in config.DATA_HOSTS:
        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as c:
                r = c.head(f"https://{host}", headers={"User-Agent": "health-access-map/1.0"})
            _ok("reach", f"{host} ({r.status_code})")
        except Exception as e:  # noqa: BLE001
            _fail("reach", f"{host} unreachable ({type(e).__name__})")

    return ok


if __name__ == "__main__":
    raise SystemExit(0 if check() else 1)

"""build_hpsa: HRSA primary-care HPSA designations -> a per-ZCTA shortage score.

NPPES counts provider *registrations*; HPSA encodes the thing a raw count cannot - an
official shortage designation that folds in high-need population, travel/distance to the
nearest source of care, and safety-net burden. Empirically it is near-orthogonal to our
E2SFCA provider density (corr ~0.05) yet correlates with INDEPENDENT mortality on its own
(clean signed-r +0.20; premature_death +0.28, life_exp +0.17), so it adds genuine marginal
signal to provider_supply rather than duplicating it (gate-tested - see docs/METHODOLOGY.md).

Mechanics: keep currently-Designated primary-care HPSAs, take the MAX "HPSA Score" (0-26,
higher = worse shortage) per county, map county -> ZCTA via geonames.county_fips, and fill
non-designated counties with 0 (no shortage). Output: hpsa.parquet (zcta5, hpsa_pc_score).

Mental-health / dental HPSA and the MUA/IMU index were gate-tested too: both are subsumed by
PC-HPSA (they add ~0 beyond it) and MUA is wrong-signed at ZCTA level, so only PC-HPSA ships.
"""
from __future__ import annotations

import pandas as pd

from . import config
from .common import assert_zcta, dev_filter, die, download_file, log

OUT = config.PROCESSED / "hpsa.parquet"


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("hpsa", f"skip (exists): {OUT.name}")
        return str(OUT)

    geo_path = config.PROCESSED / "geonames.parquet"
    if not geo_path.exists():
        die("hpsa", "missing geonames.parquet; run build_geonames first (need the ZCTA->county map)")
    geo = pd.read_parquet(geo_path)[["zcta5", "county_fips"]].copy()
    geo["fips"] = geo["county_fips"].astype(str).str.zfill(5)

    raw = config.RAW / "hrsa_hpsa_pc.csv"
    download_file(config.HPSA_PC_URL, raw, min_bytes=5_000_000)
    h = pd.read_csv(raw, dtype=str, low_memory=False)
    for c in (config.HPSA_COL_SCORE, config.HPSA_COL_FIPS, config.HPSA_COL_STATUS):
        if c not in h.columns:
            die("hpsa", f"HPSA file missing expected column {c!r}: {list(h.columns)[:8]}...")

    h = h[h[config.HPSA_COL_STATUS].astype(str).str.strip() == "Designated"].copy()
    h["score"] = pd.to_numeric(h[config.HPSA_COL_SCORE], errors="coerce")
    h["fips"] = h[config.HPSA_COL_FIPS].astype(str).str.zfill(5)
    h = h[h["score"].notna() & h["fips"].str.match(r"^\d{5}$")]
    # one county can carry several designations (geographic / population-group / facility);
    # the MAX score is the county's worst-case shortage intensity.
    cty = h.groupby("fips", as_index=False)["score"].max().rename(columns={"score": "hpsa_pc_score"})
    log("hpsa", f"{len(h)} designated PC-HPSA rows -> {len(cty)} counties with a shortage score")

    out = geo.merge(cty, on="fips", how="left")
    out["hpsa_pc_score"] = out["hpsa_pc_score"].fillna(0.0)  # no designation = no shortage
    out = out[["zcta5", "hpsa_pc_score"]].copy()
    out = dev_filter(out, dev_state)

    assert_zcta(out, stage="hpsa")
    floor = 50 if dev_state else 20_000
    if len(out) < floor:
        die("hpsa", f"only {len(out)} ZCTAs (expected >= {floor})")
    if not out["hpsa_pc_score"].between(0, 30).all():
        die("hpsa", "hpsa_pc_score outside the plausible 0-30 HPSA range")
    out.to_parquet(OUT, index=False)
    shortage = int((out["hpsa_pc_score"] > 0).sum())
    log("hpsa", f"wrote {OUT.name} ({len(out)} ZCTAs, {shortage} in a PC-shortage county, "
                f"median score among those {out.loc[out.hpsa_pc_score>0,'hpsa_pc_score'].median():.0f})")
    return str(OUT)


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

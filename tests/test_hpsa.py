"""CI-runnable unit test for the tract-level HPSA resolution (no I/O, no network).

Locks the sub-county build (docs/SUBCOUNTY_PLAN.md): Census-Tract components set a tract's score,
Single-County/County-Subdivision set a county-wide fallback, and a tract in NEITHER reads 0 - never
its county's worst tract. That last rule is the guard against the wrong-signed hybrid the prototype
rejected (backfilling non-designated tracts with county-MAX flips the within-county sign).
"""
from __future__ import annotations

import pandas as pd

from pipeline import config
from pipeline.build_hpsa import resolve_zcta_scores


def _hpsa_row(status, score, fips, comp, geoid):
    return {config.HPSA_COL_STATUS: status, config.HPSA_COL_SCORE: score,
            config.HPSA_COL_FIPS: fips, config.HPSA_COL_COMPONENT: comp, config.HPSA_COL_GEOID: geoid}


def test_resolve_zcta_scores_rules():
    h = pd.DataFrame([
        # county 06001: two Census-Tract designations on the SAME tract -> max wins (20)
        _hpsa_row("Designated", "15", "06001", "Census Tract", "06001000100"),
        _hpsa_row("Designated", "20", "06001", "Census Tract", "06001000100"),
        # county 06003: a whole-county (Single County) designation -> county-wide fallback = 10
        _hpsa_row("Designated", "10", "06003", "Single County", ""),
        # a withdrawn row must be ignored entirely
        _hpsa_row("Withdrawn", "25", "06001", "Census Tract", "06001000900"),
    ])
    xwalk = pd.DataFrame([
        # ZCTA A: half designated tract (20), half a non-designated tract (0) -> area-weighted 10
        {"GEOID_ZCTA5_20": "A", "GEOID_TRACT_20": "06001000100", "AREALAND_PART": "100"},
        {"GEOID_ZCTA5_20": "A", "GEOID_TRACT_20": "06001000200", "AREALAND_PART": "100"},
        # ZCTA B: a non-tract-designated tract in county 06003 -> county-wide fallback 10
        {"GEOID_ZCTA5_20": "B", "GEOID_TRACT_20": "06003000500", "AREALAND_PART": "100"},
        # ZCTA C: a non-designated tract in county 06001 (which has ONLY tract designations)
        {"GEOID_ZCTA5_20": "C", "GEOID_TRACT_20": "06001000200", "AREALAND_PART": "100"},
    ])
    s = resolve_zcta_scores(h, xwalk).set_index("zcta5")["hpsa_pc_score"]

    assert s["A"] == 10.0                      # area-weighted max-tract(20) + non-designated(0)
    assert s["B"] == 10.0                      # county-wide fallback for a whole-county designation
    # THE GUARD: a non-designated tract whose county has no whole-county designation reads 0,
    # NOT the county's worst tract (20). Backfilling it with county-MAX was the wrong-signed bug.
    assert s["C"] == 0.0

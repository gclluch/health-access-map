"""Unit tests for build_medicaldebt._county_shares - the Urban Institute "Debt in America"
county medical-debt parser (the affordability barrier). Guards FIPS zero-padding, share
coercion, dropping of non-county / unparseable rows, and dedup."""
from __future__ import annotations

import pandas as pd

from pipeline import build_medicaldebt as bmd


def _raw(rows):
    # mirror the Urban CSV columns we read (id = FIPS, medcoll = debt share)
    return pd.DataFrame(rows, columns=["county", "id", "medcoll"])


def test_county_shares_basic():
    out = bmd._county_shares(_raw([
        ["Autauga County", "01001", "0.1275766"],   # leading-zero FIPS preserved
        ["Cook County", "17031", "0.0892"],
        ["Bad row", "n/a*", "0.5"],                  # non-numeric FIPS -> dropped
        ["No value", "06037", "n/a*"],               # unparseable share -> dropped
    ]))
    assert list(out.columns) == ["fips", "medical_debt"]
    assert set(out["fips"]) == {"01001", "17031"}    # footer/suppressed rows gone
    v = out.set_index("fips")["medical_debt"]
    assert abs(v.loc["01001"] - 0.1275766) < 1e-9
    assert (v >= 0).all() and (v <= 1).all()


def test_county_shares_zfills_4digit_fips():
    # if a FIPS lost its leading zero upstream, zfill restores it
    out = bmd._county_shares(_raw([["Autauga", "1001", "0.12"]]))
    assert out["fips"].tolist() == ["01001"]


def test_county_shares_dedups():
    out = bmd._county_shares(_raw([
        ["Dup A", "01001", "0.10"],
        ["Dup B", "01001", "0.20"],
    ]))
    assert len(out) == 1 and out["fips"].iloc[0] == "01001"

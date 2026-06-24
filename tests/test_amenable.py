"""Unit test for build_amenable._parse_wonder - the CDC WONDER export parser that
runs when a manual treatable-mortality county export is dropped in. Guards FIPS
zero-padding, age-adjusted-rate preference, and dropping of footer/suppressed rows."""
from __future__ import annotations

import pandas as pd

from pipeline import build_amenable


def _write(tmp_path, text):
    p = tmp_path / "wonder_amenable_county.txt"
    p.write_text(text)
    return p


def test_parse_wonder_basic(tmp_path):
    # tab-delimited WONDER UCD export: header, data rows, a Suppressed row, and footer Notes.
    # real WONDER county exports keep 5-digit County Code (leading zeros preserved)
    txt = "\n".join([
        "Notes\tCounty\tCounty Code\tDeaths\tPopulation\tCrude Rate\tAge Adjusted Rate",
        "\tAutauga County, AL\t01001\t120\t58000\t206.9\t198.4",
        "\tBaldwin County, AL\t01003\t300\t230000\t130.4\t142.7",
        "\tSuppressedville, XX\t99999\tSuppressed\tNot Applicable\tSuppressed\tSuppressed",
        "\"Dataset: Underlying Cause of Death\"\t\t\t\t\t\t",
        "\"Query parameters omitted\"\t\t\t\t\t\t",
    ])
    out = build_amenable._parse_wonder(_write(tmp_path, txt))
    assert list(out.columns) == ["county_fips", "amenable_mortality"]
    # footer rows (no 5-digit code) + suppressed row (rate -> NaN) dropped
    assert set(out["county_fips"]) == {"01001", "01003"}
    # age-adjusted rate preferred over crude
    row = out.set_index("county_fips").loc["01001", "amenable_mortality"]
    assert abs(row - 198.4) < 1e-9


def test_parse_wonder_falls_back_to_crude(tmp_path):
    # no Age Adjusted Rate column -> use Crude Rate
    txt = "\n".join([
        "County\tCounty Code\tDeaths\tCrude Rate",
        "Autauga County, AL\t01001\t120\t206.9",
    ])
    out = build_amenable._parse_wonder(_write(tmp_path, txt))
    assert abs(out.set_index("county_fips").loc["01001", "amenable_mortality"] - 206.9) < 1e-9


def test_treatable_codes_nonempty_and_shaped():
    codes = build_amenable.TREATABLE_ICD10
    assert len(codes) > 50
    assert all(isinstance(c, str) and c[0].isalpha() for c in codes)  # ICD-10 letter prefix

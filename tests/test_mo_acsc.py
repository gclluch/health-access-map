"""Parsing/aggregation contract for the Missouri MICA panel (B5f).

Browser-free: every test here exercises the pure functions, so the suite stays green
without playwright or network. The scrape path is covered by the raw-CSV cache instead.

The fixtures reproduce the real export shape verified against the live MOPHIMS site on
2026-08-01 (Boone County, 2022: 65010=42, 65039=13, 65201=292, 65215=0).
"""
import pandas as pd
import pytest

from pipeline.research.build_mo_acsc import (
    Cell, combine, parse_cell, parse_table_csv, YEAR_GROUPS,
)

# The real export: title/preamble lines, a Year row, a Statistics row, then the table.
BOONE_CSV = """Title:,Missouri Resident Preventable Hospitalizations
Data selected in addition to rows and columns below:,None
Year:,2021,2022
Statistics:,Count,Count
Zip / ZCTA,,
65010,39,42
65039,11,13
65201,281,292
65215,0,0
65216,0,0
65251,205,213
TOTAL,536,573
"""

CENSORED_CSV = """Title:,Missouri Resident Preventable Hospitalizations
Year:,2022
Statistics:,Count
Zip / ZCTA,
63001,*
63002,
63003,S
63004,17
63005,0
"""


# --- parse_cell -----------------------------------------------------------------------

@pytest.mark.parametrize("raw,value", [("42", 42.0), ("0", 0.0), ("1,234", 1234.0), (" 7 ", 7.0)])
def test_parse_cell_reads_numbers(raw, value):
    assert parse_cell(raw) == Cell(value, False)


@pytest.mark.parametrize("raw", ["*", "", "  ", "S", "NR", "-", "n/a", None, "suppressed"])
def test_parse_cell_treats_suppression_as_missing(raw):
    c = parse_cell(raw)
    assert c.censored is True and c.value is None


def test_zero_is_a_real_zero_not_censored():
    """The prereg forbids conflating suppression with zero - in BOTH directions."""
    c = parse_cell("0")
    assert c.value == 0.0
    assert c.censored is False


# --- parse_table_csv ------------------------------------------------------------------

def test_parses_zip_by_year_matrix():
    df = parse_table_csv(BOONE_CSV, "post2016", "Boone")
    assert len(df) == 12                       # 6 ZIPs x 2 years
    assert set(df["year"]) == {2021, 2022}
    assert df["zcta5"].nunique() == 6
    v = df[(df.zcta5 == "65201") & (df.year == 2022)]["count"].iloc[0]
    assert v == 292


def test_total_row_is_dropped():
    df = parse_table_csv(BOONE_CSV, "post2016", "Boone")
    assert "TOTAL" not in set(df["zcta5"])
    assert all(z.isdigit() and len(z) == 5 for z in df["zcta5"])


def test_year_group_and_county_are_stamped():
    df = parse_table_csv(BOONE_CSV, "post2016", "Boone")
    assert set(df["year_group"]) == {"post2016"}
    assert set(df["county"]) == {"Boone"}


def test_censored_cells_are_na_never_zero():
    df = parse_table_csv(CENSORED_CSV, "post2016", "St. Louis")
    cens = df[df["censored"]]
    assert set(cens["zcta5"]) == {"63001", "63002", "63003"}
    assert cens["count"].isna().all()           # the whole point
    real_zero = df[df.zcta5 == "63005"].iloc[0]
    assert real_zero["count"] == 0 and not real_zero["censored"]


def test_malformed_input_yields_empty_not_crash():
    for bad in ["", "nonsense", "a,b,c\n1,2,3"]:
        out = parse_table_csv(bad, "post2016", "X")
        assert out.empty
        assert list(out.columns) == ["zcta5", "year", "count", "censored", "year_group", "county"]


# --- combine --------------------------------------------------------------------------

def test_combine_dedupes_zips_straddling_counties():
    a = parse_table_csv(BOONE_CSV, "post2016", "Boone")
    b = parse_table_csv(BOONE_CSV, "post2016", "Callaway")   # same ZIP listed twice
    out = combine([a, b])
    assert len(out) == len(a)
    assert not out.duplicated(["zcta5", "year", "year_group"]).any()


def test_combine_prefers_uncensored_row():
    good = parse_table_csv("Year:,2022\nStatistics:,Count\nZip / ZCTA,\n63004,17\n", "post2016", "A")
    bad = parse_table_csv("Year:,2022\nStatistics:,Count\nZip / ZCTA,\n63004,*\n", "post2016", "B")
    out = combine([bad, good])
    row = out[out.zcta5 == "63004"].iloc[0]
    assert row["count"] == 17 and not row["censored"]


def test_combine_keeps_the_two_modules_separate():
    """The 2015/16 break means these are different measures - never collapsed."""
    pre = parse_table_csv("Year:,2015\nStatistics:,Count\nZip / ZCTA,\n65201,100\n", "pre2016", "Boone")
    post = parse_table_csv("Year:,2016\nStatistics:,Count\nZip / ZCTA,\n65201,90\n", "post2016", "Boone")
    out = combine([pre, post])
    assert len(out) == 2
    assert set(out["year_group"]) == {"pre2016", "post2016"}


def test_combine_of_nothing_is_empty_not_error():
    assert combine([]).empty
    assert combine([pd.DataFrame()]).empty


# --- config sanity --------------------------------------------------------------------

def test_year_groups_cover_the_opening_window_with_pre_period():
    """FQHC openings run 2012-2019; the panel must reach well before that."""
    pre_years = YEAR_GROUPS["pre2016"][1]
    post_years = YEAR_GROUPS["post2016"][1]
    assert min(pre_years) <= 2005, "need a real pre-period before the 2012 cohorts"
    assert max(post_years) >= 2022
    assert set(pre_years).isdisjoint(post_years)
    assert max(pre_years) + 1 == min(post_years), "no gap between the modules"

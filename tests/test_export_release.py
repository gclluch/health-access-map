"""The release bundle's one real invariant: nothing ships undocumented.

The data dictionary is derived from taxonomy.py, so a column added to the model shows up in the
bundle whether or not anyone wrote a description for it. These tests fail on that case rather
than letting an unlabelled column reach a citable release, and pin the taxonomy-derived shape
(measure, its `_natpct`, its sub-score, its dimension) that the derivation depends on."""
from __future__ import annotations

import pandas as pd
import pytest

from pipeline import export_release, taxonomy


def _frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame({c: [1.0, 2.0] for c in columns})


def test_taxonomy_columns_are_described_without_a_hand_written_entry():
    spec = taxonomy.subscore_specs()[0]
    member = spec["members"][0]["col"]
    cols = [member, f"{member}_natpct", f"{spec['key']}_pctile", f"{spec['dim']}_pctile"]

    dd = export_release._dictionary(_frame(cols)).set_index("column")

    assert list(dd.index) == cols  # dictionary rows follow the table's column order
    assert dd.loc[member, "description"] == spec["members"][0]["label"]
    assert "percentile" in dd.loc[f"{member}_natpct", "units"]
    assert dd.loc[f"{spec['key']}_pctile", "group"].startswith("sub-score")
    assert dd.loc[f"{spec['dim']}_pctile", "group"] == "dimension"
    assert (dd["group"] != "undocumented").all()


def test_an_unknown_column_is_flagged_rather_than_shipped_silently():
    dd = export_release._dictionary(_frame(["zcta5", "some_new_measure"])).set_index("column")

    assert dd.loc["some_new_measure", "group"] == "undocumented"
    assert dd.loc["zcta5", "group"] == "identifier"


def test_every_documented_column_carries_units():
    """A number without a unit is not usable by a stranger, which is the point of the bundle."""
    described = set(export_release.NON_TAXONOMY)
    described |= {m["col"] for s in taxonomy.subscore_specs() for m in s["members"]}
    described |= set(taxonomy.CONTEXT_PLACES) | set(taxonomy.CONTEXT_ACS)

    dd = export_release._dictionary(_frame(sorted(described)))
    missing = dd[dd["units"].fillna("") == ""]["column"].tolist()

    assert not missing, f"no units for: {missing}"


@pytest.mark.parametrize("col", ["access_gap_pctile", "amenable_mortality", "low_confidence"])
def test_the_columns_a_reader_reaches_for_first_are_documented(col):
    dd = export_release._dictionary(_frame([col])).set_index("column")

    assert dd.loc[col, "group"] in {"score", "outcome", "quality"}
    assert dd.loc[col, "description"]

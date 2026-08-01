"""export_release: bundle a citable snapshot of the scored table.

Running the pipeline costs ~1.5-3 h and an 11 GB manual NPPES download, which is the wrong
price for someone who just wants the ZIP-level numbers. This writes the four files that make
the build usable and citable without reproducing it:

  metrics.parquet      the scored table, verbatim
  metrics.csv.gz       the same table for people who don't have a parquet reader
  data_dictionary.csv  one row per column: label, source, direction, resolution, units
  provenance.json      what each stage actually ingested, from the build itself

The dictionary is DERIVED from taxonomy.py rather than hand-written, so it cannot drift out of
sync with the model: every scored measure, sub-score and dimension is generated from the same
structure the scoring uses. The columns that sit outside the taxonomy - identifiers, validation
outcomes, quality flags, score outputs - are described in NON_TAXONOMY below.
"""
from __future__ import annotations

import argparse
import shutil

import pandas as pd

from . import config, taxonomy
from .common import die, log

OUT_DIR = config.DATA / "release"

# Columns that carry no taxonomy entry, because they are not scored measures.
# column -> (group, description, units)
NON_TAXONOMY: dict[str, tuple[str, str, str]] = {
    # --- identifiers / geography ---
    "zcta5": ("identifier", "5-digit ZIP Code Tabulation Area (Census 2020 vintage)", "code"),
    "state": ("identifier", "USPS state abbreviation", "code"),
    "state_name": ("identifier", "State name", "text"),
    "city": ("identifier", "Primary place name for the ZCTA", "text"),
    "county_name": ("identifier", "County containing the largest share of the ZCTA", "text"),
    "county_fips": ("identifier", "5-digit county FIPS code", "code"),
    # --- context (never scored) ---
    "population": ("context", "Total population (ACS 5-year)", "people"),
    "age65_rate": ("context", "Share of population 65 and older", "fraction 0-1"),
    "age17_rate": ("context", "Share of population under 18", "fraction 0-1"),
    "limited_english_rate": ("context", "Share of households with limited English", "fraction 0-1"),
    "pct_white": ("context", "Share white non-Hispanic", "fraction 0-1"),
    "pct_black": ("context", "Share Black", "fraction 0-1"),
    "pct_asian": ("context", "Share Asian", "fraction 0-1"),
    "pct_hispanic": ("context", "Share Hispanic", "fraction 0-1"),
    "pct_other_race": ("context", "Share other / multiple races", "fraction 0-1"),
    # --- provider supply inputs (NPPES + HRSA) ---
    "providers_total": ("supply", "Individual providers with a practice address in the ZCTA", "count"),
    "providers_primary": ("supply", "Primary-care providers (NUCC taxonomy)", "count"),
    "providers_mental": ("supply", "Mental-health providers (NUCC taxonomy)", "count"),
    "providers_dental": ("supply", "Dentists (NUCC taxonomy)", "count"),
    "providers_obgyn": ("supply", "OB/GYN providers (NUCC taxonomy)", "count"),
    "primary_per_1k": ("supply", "Primary-care providers per 1,000 residents in the ZCTA itself", "rate"),
    "primary_people_per_provider": ("supply", "Population per primary-care provider within the E2SFCA catchment", "ratio"),
    "primary_shortage": ("supply", f"Catchment ratio worse than the HRSA {config.HPSA_SHORTAGE_RATIO}:1 shortage threshold", "boolean"),
    "fqhc_sites_reachable": ("supply", "FQHC / look-alike sites inside the catchment", "count"),
    "nearest_fqhc_km": ("supply", "Straight-line distance to the nearest FQHC site", "km"),
    # --- validation outcomes: NEVER inputs. The independent rulers the score is tested against. ---
    "life_expectancy": ("outcome", "Life expectancy at birth (CDC USALEEP, tract-to-ZCTA)", "years"),
    "preventable_hosp": ("outcome", "Preventable hospital stays (County Health Rankings)", "rate per 100k"),
    "premature_death": ("outcome", "Years of potential life lost before 75 (County Health Rankings)", "rate per 100k"),
    "infant_mortality": ("outcome", "Infant mortality (County Health Rankings)", "rate per 1k births"),
    "flu_vaccination": ("outcome", "Flu vaccination rate (County Health Rankings)", "fraction 0-1"),
    "mammography": ("outcome", "Mammography screening rate (County Health Rankings)", "fraction 0-1"),
    "amenable_mortality": ("outcome", "Amenable (treatable) mortality, ages 0-74, age-adjusted, 2016-2020 (CDC WONDER)", "rate per 100k"),
    "life_expectancy_pctile": ("outcome", "National percentile of life_expectancy, oriented higher = worse", "percentile 0-100"),
    # --- data-quality flags ---
    "low_confidence": ("quality", f"Population below {config.POPULATION_FLOOR}; ranks are unstable", "boolean"),
    "institutional": ("quality", "Population dominated by an institution (prison, campus); not a residential ZIP", "boolean"),
    "scoreable": ("quality", "Enough dimensions present to carry a composite score", "boolean"),
    "n_dims_scored": ("quality", "How many of the 3 dimensions were present (3 = full score)", "count"),
    "places_input_cv": ("quality", "Mean coefficient of variation of the scored PLACES inputs", "fraction"),
    "acs_input_cv": ("quality", "Mean coefficient of variation of the scored ACS inputs", "fraction"),
    # --- score outputs ---
    "access_gap_score": ("score", "Composite access disadvantage, the weighted sum of the 3 dimension percentiles", "0-100"),
    "access_gap_pctile": ("score", "National percentile rank of access_gap_score; the headline number", "percentile 0-100"),
    "access_gap_pctile_within_state": ("score", "Percentile rank of access_gap_score within its state", "percentile 0-100"),
    "access_gap_rank_lo": ("score", "Low end of the reliable range for access_gap_pctile (re-weighting + measurement error)", "percentile 0-100"),
    "access_gap_rank_hi": ("score", "High end of the reliable range for access_gap_pctile", "percentile 0-100"),
    "access_gap_mult": ("score", "Coincidence lens: need x barriers, for places where both are high", "index"),
    "access_gap_mult_pctile": ("score", "National percentile of access_gap_mult", "percentile 0-100"),
    "care_access_resid_pctile": ("score", "Access-beyond-deprivation lens: care_access residualized on need + vulnerability", "percentile 0-100"),
    "tier": ("score", "Decile of access_gap_pctile, 1 (least disadvantaged) to 10", "1-10"),
}

DIRECTION_NOTE = {1: "higher = worse access", -1: "higher = better (reversed before ranking)"}

# Units for the taxonomy's measure columns. The `_pct` / `_rate` suffixes are the pipeline's own
# naming convention (see taxonomy.py), so the suffix is the honest key; the rest are one-offs.
MEASURE_UNITS = {
    "median_income": "USD (ACS median household income)",
    "hpsa_pc_score": "0-26 HRSA shortage score (higher = worse shortage)",
    "medical_debt": "fraction 0-1 of people with medical debt in collections",
    "safetynet_barrier": "index (FQHC desert x poverty)",
    "median_age": "years",
    "pct_minority": "fraction 0-1",
    "pct_under5": "fraction 0-1",
}


def _measure_units(col: str) -> str:
    if col in MEASURE_UNITS:
        return MEASURE_UNITS[col]
    if col.endswith("_2sfca"):
        return "E2SFCA index (distance-weighted providers per 1,000 people in the catchment)"
    if col.endswith("_pct"):
        return "percent 0-100 (PLACES model-based crude prevalence)"
    if col.endswith("_rate"):
        return "fraction 0-1"
    return ""


def _dictionary(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []

    def add(col, group, desc, source="", direction="", resolution="", units=""):
        if col not in df.columns:
            return
        s = df[col]
        rows.append({
            "column": col, "group": group, "description": desc, "source": source,
            "direction": direction, "resolution": resolution, "units": units,
            "dtype": str(s.dtype), "non_null": int(s.notna().sum()),
        })

    for spec in taxonomy.subscore_specs():
        dim = taxonomy.DIMENSIONS[spec["dim"]]["label"]
        scored = "scored" if spec["scored"] else "computed but NOT scored"
        for m in spec["members"]:
            add(m["col"], f"measure / {spec['label']}", m["label"], spec["source"],
                DIRECTION_NOTE[m["dir"]], m.get("res", "zcta"), _measure_units(m["col"]))
            add(f"{m['col']}_natpct", f"measure percentile / {spec['label']}",
                f"National percentile of {m['label']}, oriented higher = worse",
                spec["source"], "higher = worse access", m.get("res", "zcta"), "percentile 0-100")
        add(f"{spec['key']}_pctile", f"sub-score / {dim}",
            f"{spec['label']} sub-score ({scored}): mean of its member percentiles, re-ranked",
            spec["source"], "higher = worse access", spec["resolution"], "percentile 0-100")

    for dkey, dim in taxonomy.DIMENSIONS.items():
        add(f"{dkey}_pctile", "dimension", f"{dim['label']}: {dim['blurb']}",
            "", "higher = worse access", "", "percentile 0-100")

    for col, label in {**taxonomy.CONTEXT_PLACES, **taxonomy.CONTEXT_ACS}.items():
        add(col, "context", f"{label} (displayed, never scored)", "", "", "", _measure_units(col))

    for col, (group, desc, units) in NON_TAXONOMY.items():
        add(col, group, desc, "", "", "", units)

    described = {r["column"] for r in rows}
    for col in df.columns:  # nothing ships undocumented, even if the model gains a column
        if col not in described:
            add(col, "undocumented", "No dictionary entry - add one in pipeline/export_release.py")
    return pd.DataFrame(rows).set_index("column").loc[list(df.columns)].reset_index()


def build(out_dir=OUT_DIR) -> str:
    src = config.PROCESSED / "metrics.parquet"
    if not src.exists():
        die("release", f"{src} not found -- run `make data` first")
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(src)
    shutil.copy2(src, out_dir / "metrics.parquet")

    csv = out_dir / "metrics.csv.gz"
    df.to_csv(csv, index=False, compression="gzip")

    dd = _dictionary(df)
    dd.to_csv(out_dir / "data_dictionary.csv", index=False)
    undocumented = (dd["group"] == "undocumented").sum()
    if undocumented:
        log("release", f"WARNING: {undocumented} columns have no dictionary entry")

    if config.PROVENANCE.exists():
        shutil.copy2(config.PROVENANCE, out_dir / "provenance.json")
    else:
        log("release", "WARNING: no provenance.json -- the bundle cannot date itself")

    mb = sum(p.stat().st_size for p in out_dir.iterdir()) / 1e6
    log("release", f"{len(df):,} rows x {len(df.columns)} cols -> {out_dir} ({mb:.1f} MB)")
    return f"release: {len(df):,} rows, {len(dd)} documented columns"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Bundle a citable release of the scored table.")
    ap.add_argument("--out", type=str, default=str(OUT_DIR))
    from pathlib import Path
    print(build(Path(ap.parse_args().out)))

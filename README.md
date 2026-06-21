# Health Access Map

A national, ZIP-level (ZCTA) explorer of U.S. health-care access.

> **New here? Read [`docs/PRIMER.md`](docs/PRIMER.md)** - the comprehensive guide to the
> app, the problem space, every dataset and field, the math, and the jargon. Scoring
> rationale + precedent: [`docs/RATIONALE.md`](docs/RATIONALE.md).

The model is **hierarchical**: one tunable **Access Gap** composite → 3 dimensions →
11 sub-scores → ~50 measures, all drill-downable in the detail panel.

1. **Health need** - chronic disease, behavioral risk, mental/social health, disability (CDC PLACES)
2. **Social vulnerability** - socioeconomic, household, housing/transport, unmet social needs (Census ACS + PLACES SDOH)
3. **Care access** - provider supply (**2SFCA spatial catchment**, not ZIP containment), insurance, preventive-care use (CMS NPPES + ACS + PLACES)
4. **Access Gap Score** - the relative national-rank composite of the three

The map is the product: pan/zoom a cividis choropleth, click a ZIP for a decomposed
detail panel, switch the coloring metric, search a ZIP, read a ranked list of
worst-access areas, and **re-weight the score live with sliders** (recomputed
client-side - no backend round-trip).

![screenshot](docs/screenshot.png)

---

## Quickstart

```bash
make setup            # venv + python deps + mapshaper + frontend deps
cp .env.example .env  # then paste your free Census API key (api.census.gov/data/key_signup.html)

make data-ca          # fast California vertical slice (minutes) -- recommended first
# or
make data             # full national build (~33k ZIPs; NPPES is a ~1 GB download / ~11 GB unzip)

make api              # FastAPI backend on :8000   (terminal 1)
make web              # Vite dev server on :5173    (terminal 2)
make acceptance       # run the acceptance suite
```

Requires Python ≥ 3.10, Node ≥ 18, ~25 GB free disk for the national NPPES stage.

---

## Architecture

```
data/raw/*  ──(pipeline: Python + DuckDB + mapshaper)──►  data/processed/metrics.parquet
                                                          data/processed/zcta.geojson (geometry only)
                                                                 │
                          ┌──────────────────────────────────────┼───────────────────────────┐
                          ▼                                       ▼                            ▼
                   FastAPI (in-memory parquet)            zcta.geojson + metrics.json   static files
                   /api/zcta /api/rankings /api/compare    copied to frontend/public     (Vite / CDN)
                          │                                       │
                          └──────────────► React + deck.gl + MapLibre map ◄───────────────────┘
```

- **DuckDB** streams the ~11 GB NPPES CSV (projecting 3 columns) - never loaded into pandas.
- **SQLite/Postgres rejected**: 33k rows of attribute lookups fit trivially in memory.
- **Simplified GeoJSON** (mapshaper, 8% simplify, reprojected to WGS84) - no tippecanoe/PMTiles in v1.
- **Base metrics precomputed server-side; the Access Gap is recomputed client-side** from the
  stored component percentiles, which is what makes the weight sliders instant.

See `pipeline/` for the stages and `data/processed/provenance.json` for the exact
dataset ids and vintages each run resolved.

---

## Data sources & vintages

| Layer | Source | Notes |
|---|---|---|
| Disease burden | CDC PLACES, ZCTA GIS-Friendly (2025 release, `kee5-23sr`) | Crude prevalence of diabetes, COPD, CHD, asthma, depression. Dataset id resolved + asserted at runtime. |
| Provider supply | CMS NPPES monthly full file | Individuals only (Entity Type 1); taxonomy classified via the NUCC crosswalk. |
| Economic / insurance | Census ACS 5-year (2023) | Variable codes resolved by label from `variables.json`; uninsured summed from the `B27001` group in one call. |
| Geometry | Census TIGER `cb_2020_us_zcta520_500k` | The only vintage that publishes ZCTA cartographic boundaries; field `ZCTA5CE20`. |
| Human geography | Census ZCTA→county relationship (2020) + NPPES | County name from the relationship file (dominant by land area); city is the modal provider city from NPPES; full state name + median age for context. |

**Vintage alignment:** PLACES, ACS, and TIGER are all kept on the **2020 ZCTA** basis so
the join doesn't silently drop ZCTAs that were renumbered between the 2010 and 2020 vintages.

---

## Scoring methodology

1. Outer-join the three layers on `zcta5`, left-anchored on the geometry ZCTA universe.
2. Derive supply per capita (`primary_per_1k`), guarding divide-by-zero to null (never `inf`).
   A geometry ZCTA with no NPPES match is treated as **zero** registered providers, not missing.
3. Percentile-rank each component nationally (robust to skew):
   - `disease_burden_pctile` - mean of z-scored prevalences, percentiled
   - `provider_supply_pctile` - `primary_per_1k` percentiled (higher = better access)
   - `econ_vuln_pctile` - mean of poverty, uninsured, and inverted-income percentiles
4. **Access Gap = 0.40·disease + 0.35·(100 − supply) + 0.25·econ** (default weights;
   the client sliders re-weight this live). Stored as the three percentiles so the
   frontend recomputes without re-fetching.
5. A ZCTA is **scoreable** only with population present and ≥ 2 of 3 components; otherwise
   it renders gray ("no reliable data"). Small-population ZCTAs are flagged `low_confidence`
   and excluded from the headline rankings.

The three components are **collinear** (e.g. disease↔econ correlation is reported in
`provenance.json` and the methodology panel), so the weighted sum double-counts shared
variance - which is exactly why the weights are user-tunable rather than presented as truth.

---

## Limitations (read this - integrity hidden is integrity absent)

This tool can mislead about real communities. Each flaw below is stated plainly in the
in-app **"How to read this"** panel as well:

- **Relative, not absolute.** A score of 95 means "worse access than 95% of U.S. ZIPs,"
  not "objectively bad." Absolute values are shown beside every percentile.
- **Modeled disease estimates.** PLACES is a model partly conditioned on socioeconomic
  structure, so the disease↔poverty correlation partly recovers the model's own
  assumptions - not two independent measurements confirming each other.
- **Registered providers ≠ capacity.** An NPI is not an FTE and says nothing about
  Medicaid/uninsured acceptance. Supply is by **ZIP containment** in v1, so a residential
  ZIP next to a clinic-heavy ZIP reads artificially low. (Catchment smoothing is the
  v1.1 upgrade.)
- **Small-area noise.** Low-population ZCTAs have wide ACS margins of error; they are
  flagged and de-emphasized.
- **Different vintages & universes.** NPPES (this month), ACS (centered ~2-3 yrs back),
  PLACES (a BRFSS year) describe different times and populations (adults 18+, civilian
  noninstitutionalized, total). Recorded in `provenance.json`.
- **Ecological fallacy / age.** Area patterns are not individual-level facts; crude
  prevalence reflects age mix.

HRSA HPSA validation is intentionally **out of v1** (optional, non-blocking) - and even
when added, it shares inputs with the score, so it is a consistency check against the
federal definition, not independent ground truth.

---

## Project layout

```
pipeline/      ETL stages (config, preflight, build_*, join_and_score, run)
backend/       FastAPI over the in-memory metrics table
frontend/      Vite + React + TS + MapLibre + deck.gl
data/          raw/ (gitignored downloads) + processed/ (gitignored outputs)
tests/         acceptance suite (definition of done)
```

Volatile identifiers (PLACES dataset id, ACS variable codes, NPPES/NUCC/TIGER links)
are **resolved and asserted at runtime** so drift fails loudly at a validation gate
rather than silently producing a wrong column.

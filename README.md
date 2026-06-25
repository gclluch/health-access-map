# Health Access Map

A national, ZIP-level (ZCTA) explorer of U.S. health-care access.

> **New here?** Start with [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) - the "follow the
> logic" guide: every design choice, its rationale, and how to extend the model safely. Then
> [`docs/PRIMER.md`](docs/PRIMER.md) (dataset/field dictionary),
> [`docs/RATIONALE.md`](docs/RATIONALE.md) (per-formula math + precedent),
> [`docs/DECISIONS.md`](docs/DECISIONS.md) (the ledger of what we tried, kept, and rejected -
> don't re-run these), [`docs/VALIDATION.md`](docs/VALIDATION.md) (outcomes, the sub-county
> gate, comparability, and uncertainty), and [`docs/BACKLOG.md`](docs/BACKLOG.md) (open edges &
> known limitations as pick-up-ready tickets - start here if you're extending the project).

The model is **hierarchical**: one tunable **Access Gap** composite → 3 dimensions →
11 sub-scores → ~50 measures, all drill-downable in the detail panel.

1. **Health need** - chronic disease, behavioral risk, mental/social health, disability (CDC PLACES)
2. **Social vulnerability** - socioeconomic, household, housing/transport, unmet social needs (Census ACS + PLACES SDOH)
3. **Care access** - provider supply (**2SFCA spatial catchment**, not ZIP containment), insurance, preventive-care use (CMS NPPES + ACS + PLACES)
4. **Access Gap Score** - the relative national-rank composite of the three

The map is the product: pan/zoom a cividis choropleth, click a ZIP for a decomposed
detail panel, switch the coloring metric, search a ZIP, read a ranked list of
worst-access areas, and **re-weight the score live with sliders** (recomputed
client-side - no backend round-trip). The sliders are an honest **sensitivity probe, not a
control that rewrites the map**: because the three dimensions are strongly collinear,
re-weighting moves ranks by only Spearman ~0.999 / ~±6 pts (see Scoring methodology below) -
that near-inertness is the finding, deliberately surfaced rather than hidden behind a knob that
looks more powerful than it is.

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
| Disease & health need | CDC PLACES, ZCTA GIS-Friendly (2025 release, `kee5-23sr`) | Crude prevalence across ~30 measures - chronic disease (diabetes, CHD, COPD, …), behavioral risk, mental/social distress, disability, plus SDOH + preventive-care use. Dataset id resolved + asserted at runtime. |
| Provider supply | CMS NPPES monthly full file | Individuals only (Entity Type 1); taxonomy classified via the NUCC crosswalk. |
| Economic / insurance | Census ACS 5-year (2023) | Variable codes resolved by label from `variables.json`; uninsured summed from the `B27001` group in one call. |
| Geometry | Census TIGER `cb_2020_us_zcta520_500k` | The only vintage that publishes ZCTA cartographic boundaries; field `ZCTA5CE20`. |
| Human geography | Census ZCTA→county relationship (2020) + NPPES | County name from the relationship file (dominant by land area); city is the modal provider city from NPPES; full state name + median age for context. |

**Vintage alignment:** PLACES, ACS, and TIGER are all kept on the **2020 ZCTA** basis so
the join doesn't silently drop ZCTAs that were renumbered between the 2010 and 2020 vintages.

---

## Scoring methodology

A hierarchy (SVI method - percentile-rank, average, **re-rank at each level** so every node is
a uniform 0-100 "higher = worse"). See [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) for the full logic.

1. Each **measure** (~50) is oriented (higher = worse access) and percentile-ranked nationally
   (ordinal → immune to the heavy right-skew of provider density / income).
2. **Sub-scores** (11; **10 scored**) = re-ranked mean of their available member percentiles.
   `safetynet_access` is computed + displayed but **unscored** - it is wrong-signed *within*
   counties (see [`docs/VALIDATION.md`](docs/VALIDATION.md)).
3. **Dimensions** (3) = re-ranked mean of their sub-scores: health need, social vulnerability,
   care access.
4. **Access Gap = 0.35·need + 0.30·vulnerability + 0.35·care-access** (default; a conceptual
   value judgment, as in County Health Rankings). The client sliders re-weight live from the
   stored dimension percentiles. A **multiplicative "coincidence" lens** (weighted geometric
   mean - lights up only where need *and* barriers coincide) is selectable alongside the additive default.
5. A ZCTA is **scoreable** only with population present and ≥ 2 of 3 dimensions; otherwise it
   renders gray. Low-population ZCTAs are flagged `low_confidence` and kept out of headline rankings.

The three dimensions are **strongly collinear** (need↔vulnerability **0.73**, need↔access
0.59, vulnerability↔access 0.61; reported in `provenance.json` and the methodology panel).
At the dimension level PC1 explains **76%** of the joint variance and the participation ratio
is **~1.6 effective dimensions** - the index is closer to one "general deprivation" gradient
than to three independent axes. Two consequences, both stated in-product: (a) the weighted sum
double-counts shared variance, which is why the weights are user-tunable rather than presented
as truth; and (b) because the dimensions move together, *re-weighting barely moves ranks*
(Spearman ~0.999, ~±6 pts) - so the sliders are an honest **sensitivity probe**, not a knob that
rewrites the map. (An earlier draft cited "~0.5" here; the live build is higher - see the
bootstrap-gate note in `docs/VALIDATION.md`.)

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
  Medicaid/uninsured acceptance. Supply uses an **E2SFCA variable/adaptive spatial catchment**
  (not ZIP containment), which fixed the urbanicity artifact; but it remains straight-line, not
  drive-time, and counts registrations, not active accepting capacity.
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

---

## Production & ops

- **CI** (`.github/workflows/ci.yml`): pytest (pipeline + backend), frontend typecheck + Vitest
  unit + production build, and a Playwright smoke/compare e2e on a tiny fixture. Data-level
  acceptance (`make acceptance`) runs against a real build, gated pre-deploy.
- **Deploy** (`docs/DEPLOY.md`): two Dockerfiles + `docker compose up` (nginx-served SPA with
  `gzip_static` + cache headers, same-origin `/api` proxy to FastAPI). CORS and the SPA's API
  base are env-driven (`ALLOWED_ORIGINS`, `VITE_API_BASE`) so prod works without code changes.
- **Gate with error bars** (`make gate`): `pipeline.bootstrap_gate` puts 95% CIs (cluster bootstrap
  over county, paired) on every diagnostics margin - ship only if the relevant CI excludes 0. It also
  runs the **amenable-mortality focus** (care-access partial r vs the access-sensitive outcome).
  **This anchor has now been pulled and run** (CDC WONDER treatable mortality, age-adjusted, 0-74,
  2016-2020; committed at `data/manual/wonder_amenable_county.txt`): care_access partial r vs
  treatable mortality is **+0.395 [0.368, 0.43]** - strong and net of the deprivation gradient,
  vs only +0.125 against all-cause LE. This is the gold-standard validation the field uses and it
  confirms the care-access dimension was sound (see `docs/VALIDATION.md` §4). Re-run any time with
  `make amenable`; refresh the export via the recipe in `pipeline/build_amenable.py`.
- **Observability**: `lib/observability.ts` - env-gated, dependency-free error + usage hooks
  (`VITE_SENTRY_DSN`, `VITE_ANALYTICS_URL`); no-ops when unset.
- **Freshness**: the pipeline emits `frontend/public/meta.json`; the UI shows a "data as of" badge.

### Roadmap / honestly not done yet

- **Time dimension.** The app is a single snapshot. A true trend view needs multi-vintage
  ingestion (historical ACS/PLACES/NPPES re-run and stored per year) - a real pipeline effort,
  not a UI toggle. Not started; would be the highest-value next feature for decision use.
- **Vector tiles / PMTiles for geometry.** The ~16.7 MB `zcta.geojson` (~4.5 MB gzip) is the
  real cold-load weight. Mitigated for now (gzip_static, off-main-thread Web Worker parse, immutable
  hashed assets) but the structural fix is tippecanoe -> PMTiles, which is not yet wired.
- **Drive-time E2SFCA** (vs straight-line adaptive catchment) and the **acceptability**
  (Medicaid/new-patient acceptance) axis remain open - see `docs/METHODOLOGY.md §10`.

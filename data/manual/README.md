# data/manual/ - manually-pulled inputs that are NOT auto-downloadable

Unlike `data/raw/` (gitignored, reproducible via `make data`), these files are **committed**
because they cannot be fetched headlessly and would otherwise be lost.

## wonder_amenable_county.txt

County-level **treatable (amenable) mortality**, age-adjusted, ages 0-74, pooled 2016-2020,
from the CDC WONDER Underlying Cause of Death interactive tool (the county API is national-only,
so this is a manual web export behind a data-use agreement - see `pipeline/build_amenable.py`
for the exact query recipe and the OECD treatable ICD-10 set).

`pipeline/build_amenable.py` reads this file (preferring this committed copy over any drop-in in
`data/raw/`), parses it to `data/raw/amenable_mortality_county.csv`, and `build_outcomes.py`
merges it as the `amenable_mortality` validation anchor. To re-pull a fresher vintage, follow the
recipe in `build_amenable.py` and overwrite this file.

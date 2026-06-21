"""Central configuration: ALL volatile URLs/IDs/constants live here.

Several identifiers rotate per release. Where possible the pipeline RESOLVES the
live value at runtime and ASSERTS its shape, so drift fails loudly at a gate
rather than silently producing a wrong column. The constants below are seeds /
fallbacks (see brief sections 11.0, 12.5, 16.6).
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
FRONTEND_PUBLIC = ROOT / "frontend" / "public"
PROVENANCE = PROCESSED / "provenance.json"

for _d in (RAW, PROCESSED):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Vintages -- choose ONE ZCTA vintage across PLACES + ACS + TIGER (brief 16.7).
# All three below are 2020-ZCTA based, which keeps the join consistent.
# ---------------------------------------------------------------------------
ACS_YEAR = 2023      # ACS 5-year, published at ZCTA, 2020-ZCTA based
# ZCTA cartographic boundaries are only published in the 2020 (decennial) vintage;
# GENZ2021/2022/2023 do NOT ship cb_*_zcta520 files. 2020 + ZCTA5CE20 is correct
# and matches the 2020-ZCTA basis of PLACES + ACS (brief 16.7).
TIGER_YEAR = 2020    # cb_2020_us_zcta520_500k.zip, field ZCTA5CE20

# ---------------------------------------------------------------------------
# CDC PLACES (disease burden) -- Socrata, data.cdc.gov
# ---------------------------------------------------------------------------
# Known-good GIS-Friendly ZCTA dataset ids (brief 16.6). Resolved at runtime via
# the catalog; this is the seed/fallback if catalog resolution fails.
PLACES_DATASET_ID = "kee5-23sr"          # 2025 release (current default)
PLACES_DATASET_ID_FALLBACKS = ["c7b2-4ecy", "c76y-7pzg"]  # 2023, 2022
PLACES_CATALOG_URL = "https://data.cdc.gov/api/catalog/v1?q=PLACES%20ZCTA%20GIS&only=dataset"
PLACES_EXPORT_TMPL = "https://data.cdc.gov/api/views/{id}/rows.csv?accessType=DOWNLOAD"

# PLACES measure -> our scoring column. GIS-friendly format is already wide with
# <MEASURE>_CrudePrev columns. Crude (not age-adjusted) prevalence for pop impact.
PLACES_MEASURES = {
    "DIABETES_CrudePrev": "diabetes_pct",
    "COPD_CrudePrev": "copd_pct",
    "CHD_CrudePrev": "chd_pct",
    "CASTHMA_CrudePrev": "casthma_pct",
    "DEPRESSION_CrudePrev": "depression_pct",
}
DISEASE_COLS = list(PLACES_MEASURES.values())

# ---------------------------------------------------------------------------
# CMS NPPES (provider supply) -- full monthly NPI file
# ---------------------------------------------------------------------------
NPPES_PAGE = "https://download.cms.gov/nppes/NPI_Files.html"
NPPES_NBER_MIRROR_TMPL = "https://data.nber.org/npi/{year}/"  # fallback
# Confirmed header strings inside npidata_pfile_*.csv (brief 11.4):
NPPES_COL_POSTAL = "Provider Business Practice Location Address Postal Code"
NPPES_COL_TAXONOMY = "Healthcare Provider Taxonomy Code_1"
NPPES_COL_ENTITY = "Entity Type Code"
NPPES_COL_STATE = "Provider Business Practice Location Address State Name"
NPPES_COL_CITY = "Provider Business Practice Location Address City Name"

# NUCC Provider Taxonomy crosswalk (free CSV). The download URL rotates by
# version; resolve from the index page, fall back to the seed below.
NUCC_INDEX_URL = "https://www.nucc.org/index.php/code-sets-mainmenu-41/provider-taxonomy-mainmenu-40/csv-mainmenu-57"
NUCC_CSV_SEED = "https://www.nucc.org/images/stories/CSV/nucc_taxonomy_250.csv"

# Taxonomy classification rules (brief 11.4 / 16.3). Only primary_care and
# mental_health must be right; everything else -> specialist/other. Matched on
# the crosswalk's Grouping / Classification columns (case-insensitive contains).
PRIMARY_CARE_CLASSIFICATIONS = {
    "Family Medicine", "Internal Medicine", "Pediatrics",
    "General Practice", "Geriatric Medicine",
}
# NP/PA primary-care providers (Grouping below) also count as primary care.
PRIMARY_CARE_NPPA_GROUPING = "Physician Assistants & Advanced Practice Nursing Providers"
MENTAL_HEALTH_GROUPING = "Behavioral Health & Social Service Providers"
MENTAL_HEALTH_CLASSIFICATION = "Psychiatry & Neurology"  # narrowed to Psychiatry specialization
PHYSICIAN_GROUPING = "Allopathic & Osteopathic Physicians"

# ---------------------------------------------------------------------------
# Census ACS 5-year (economic / insurance)
# ---------------------------------------------------------------------------
CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY", "")
ACS_BASE_DETAILED = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5"
ACS_BASE_SUBJECT = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5/subject"
ACS_VARS_DETAILED = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5/variables.json"
ACS_VARS_SUBJECT = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5/subject/variables.json"
ACS_ZCTA_PREDICATE = "for=zip%20code%20tabulation%20area:*"  # nation-based since 2019

# Expected detailed-table resolutions (asserted by label, not blindly trusted).
ACS_VAR_MEDIAN_INCOME = "B19013_001E"
ACS_VAR_POVERTY_TOTAL = "B17001_001E"
ACS_VAR_POVERTY_BELOW = "B17001_002E"
ACS_VAR_POPULATION = "B01003_001E"
ACS_VAR_MEDIAN_AGE = "B01002_001E"      # median age (age-mix context, brief 15.8)
ACS_UNINSURED_GROUP = "B27001"            # group() call; sum "No health insurance coverage"
ACS_UNINSURED_LABEL_MATCH = "no health insurance coverage"

# SVI-style rates computed from ACS detailed (B) tables via group() calls.
# name -> (table, [numerator member suffixes] | None, denominator suffix).
# Each rate is a fraction in [0,1]. "pct_minority" is special (1 - white-non-Hispanic).
ACS_SVI = {
    "unemployment_rate":    ("B23025", ["005"], "003"),                    # unemployed / civ labor force
    "no_hs_diploma_rate":   ("B15003", [f"{i:03d}" for i in range(2, 17)], "001"),  # < HS / pop 25+
    "age65_rate":           ("B01001", ["020", "021", "022", "023", "024", "025",
                                        "044", "045", "046", "047", "048", "049"], "001"),
    "age17_rate":           ("B01001", ["003", "004", "005", "006",
                                        "027", "028", "029", "030"], "001"),
    "limited_english_rate": ("C16002", ["004", "007", "010", "013"], "001"),  # limited-English HHs
    "no_vehicle_rate":      ("B25044", ["003", "010"], "001"),
    "crowding_rate":        ("B25014", ["005", "006", "007", "011", "012", "013"], "001"),  # >1/room
    "mobile_home_rate":     ("B25024", ["010"], "001"),
    "multi_unit_rate":      ("B25024", ["007", "008", "009"], "001"),         # 10+ units
    # context only (never scored):
    "pct_minority":         ("B03002", None, "001"),                          # 1 - white non-Hispanic
    "pct_under5":           ("B01001", ["003", "027"], "001"),
}
CENSUS_SENTINELS = (-666666666, -999999999, -888888888, -555555555, -333333333, -222222222)

# ---------------------------------------------------------------------------
# Geometry -- TIGER cartographic boundary (ZCTA)
# ---------------------------------------------------------------------------
TIGER_TMPL = "https://www2.census.gov/geo/tiger/GENZ{year}/shp/cb_{year}_us_zcta520_500k.zip"
TIGER_YEAR_FALLBACKS = [2020]  # only the 2020 vintage publishes ZCTA cartographic boundaries

# ZCTA -> county relationship (2020), for human-readable county labels.
ZCTA_COUNTY_REL = ("https://www2.census.gov/geo/docs/maps-data/data/rel2020/"
                   "zcta520/tab20_zcta520_county20_natl.txt")

# CDC USALEEP census-tract life expectancy (2010-2015) -> the independent OUTCOME
# used for the outcomes layer + empirical weight derivation. US_A.CSV has the 11-digit
# "Tract ID" (leading-zero-stripped) + e(0) = life expectancy at birth.
USALEEP_URL = "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Datasets/NVSS/USALEEP/CSV/US_A.CSV"
# ZCTA <-> census tract relationship (2010), with population in each part (POPPT).
ZCTA_TRACT_REL = "https://www2.census.gov/geo/docs/maps-data/data/rel/zcta_tract_rel_10.txt"

# ZCTA Gazetteer: internal-point lat/lon centroids (for the 2SFCA catchment).
GAZETTEER_TMPL = ("https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
                  "{year}_Gazetteer/{year}_Gaz_zcta_national.zip")
GAZETTEER_YEARS = [2023, 2022, 2021, 2020]

# --- spatial supply: E2SFCA (Luo & Qi 2009) ---
CATCHMENT_KM = 16.0          # ~10 mi catchment radius (urban-calibrated; rural reads low)
DECAY_SIGMA_KM = 8.0         # Gaussian distance-decay scale (weight ~0.6 at half-radius)
EARTH_KM = 6371.0
HPSA_SHORTAGE_RATIO = 3500   # HRSA primary-care shortage threshold (pop : provider)
# chronic-disease columns used to build a demand (need) weight for the need-adjusted variant
NEED_WEIGHT_COLS = ["diabetes_pct", "bphigh_pct", "chd_pct", "copd_pct", "obesity_pct"]
# ZCTA field name varies by vintage; detected at runtime.
TIGER_ZCTA_FIELDS = ["ZCTA5CE20", "ZCTA5CE10"]

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
DEFAULT_WEIGHTS = {"disease": 0.40, "supply": 0.35, "econ": 0.25}
POPULATION_FLOOR = 1000     # low_confidence flag below this
RATE_UNIT = "fraction"      # poverty_rate / uninsured_rate in [0,1] project-wide

# ---------------------------------------------------------------------------
# Frontend basemap (free, no token) -- CARTO Positron (brief 14.1)
# ---------------------------------------------------------------------------
BASEMAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"

# Hosts probed by preflight for reachability.
DATA_HOSTS = [
    "data.cdc.gov", "download.cms.gov", "api.census.gov",
    "www2.census.gov", "www.nucc.org",
]

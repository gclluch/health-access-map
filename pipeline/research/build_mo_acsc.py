"""Missouri ZIP-level preventable-hospitalization panel (MOPHIMS / MICA).

B5f replication input. Read-only; never feeds the composite.

SHELVED BEFORE ANY DATA - NEVER RUN
-----------------------------------
No Missouri counts were ever extracted. B5f existed to rescue B5d's supply-lever estimate when it
looked like a near-significant borderline (-35.5/100k, CI [-71.7, +2.2]); the spatially-honest CI
and the doubly-robust re-estimate landed first and bounded that effect at -4.3/100k, CI
[-38.0, +35.4]. There is no borderline left to rescue, and Missouri's condition definitions differ
from NY's and TX's, so it cannot add N to the existing estimator either way. See VALIDATION §7f.
Reopen only if the paid Florida (~$1,100) or Oklahoma (~$550) panels are bought - both carry
5-digit patient ZIP and do add N. That is a spend decision, not an analysis decision.

TWO UNFIXED DEFECTS IN THE BROWSER PATH - FIX BOTH BEFORE ANY RUN
-----------------------------------------------------------------
The parsing path is tested (24 cases in tests/test_mo_acsc.py) and sound. The browser path was
never executed against the live site, and reading it found two faults:

1. `_counties()` reads `page.locator("select").nth(2)` on a freshly-loaded page - *before*
   Geography = "Zip / ZCTA" is selected. The pickers cascade (see below), so the county list does
   not exist yet and the default all-counties path reads the wrong `<select>`. Passing
   `--counties` explicitly sidesteps it.
2. `_scrape_one()` requests `Statistics: "Counts and Rates"`, but `parse_table_csv` and its
   fixtures assume **one column per year**. With both statistics there are two columns per year,
   both matching the year regex, so the parser emits two rows per (zcta5, year) and `combine()`'s
   `drop_duplicates` silently keeps one - possibly the rate where a count is meant. Select counts
   only, or teach the parser to read the Statistics row and keep the count column explicitly.

WHY A BROWSER, NOT `requests`
-----------------------------
MOPHIMS is a stateful ASP.NET WebForms app. Every control change is a full-page postback
carrying `__VIEWSTATE` / `__EVENTVALIDATION`, and the geography, county and ZIP pickers
*cascade* - the ZIP list does not exist until a county is chosen, which does not exist
until Geography=Zip/ZCTA is chosen. Replicating that by hand means round-tripping opaque
viewstate blobs through ~6 sequential postbacks per county and re-parsing each one. A real
browser does it for free and is far less brittle. The cost is a Playwright dependency and
wall-clock; both are acceptable for a build that runs once.

SHAPE OF THE EXTRACTION
-----------------------
The query builder is driven once per (year_group, county):
  Year Group -> add each year via `Add=>` (they accumulate into a multiselect)
  Geography = "Zip / ZCTA" -> County -> ZIP multiselect "Select all" -> `Add=>`
  Main Row = Geography, Main Column = Year, Statistics = Counts and Rates
  Submit Query -> Save Table As -> CSV
One submit therefore yields a whole ZIP x year matrix, so the job is
~115 counties x 2 modules, not ~22,000 single-cell queries.

THE 2015/2016 DEFINITIONAL BREAK
--------------------------------
MOPHIMS splits into two modules with DIFFERENT condition lists:
  "2015 and Prior"  (2001-2015, ICD-9 era)  - Billings-style: Angina, Cellulitis,
                                              Convulsions, Dehydration, ...
  "2016 and Forward" (2016-2022, ICD-10 era) - AHRQ-PQI-named: Diabetes Long-Term
                                              Complications, Heart Failure, ...
These are NOT the same measure. The `year_group` column preserves which module each row
came from; downstream code MUST NOT pool them without an explicit opt-in - `load_panel()` refuses to hand
back a mixed frame otherwise, and any pooled analysis owes a stated handling of the break.

SUPPRESSION
-----------
Cells are kept as raw text and parsed conservatively: a value is a count only if it parses
as a number. Anything else - blank, '*', 'S', '-', 'NR' - becomes NA with `censored=True`.
Censored cells are NEVER coerced to zero - a suppressed cell is unknown, not small. Note that MOPHIMS does emit
genuine `0`s for low-volume ZIPs; those are real zeros and stay zeros.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..common import die, log

try:                                    # pragma: no cover - config shape varies by checkout
    from .. import config
    PROCESSED = config.PROCESSED
except Exception:                       # pragma: no cover
    PROCESSED = Path("data/processed")

MICA_URL = "https://healthapps.dhss.mo.gov/MoPhims/QueryBuilder?qbc=PHM&q=1&m=1"

YEAR_GROUPS: dict[str, tuple[str, tuple[int, ...]]] = {
    # key -> (radio label on the page, years available in that module)
    "pre2016": ("2015 and Prior", tuple(range(2001, 2016))),
    "post2016": ("2016 and Forward", tuple(range(2016, 2023))),
}

OUT_PARQUET = PROCESSED / "mo_acsc_panel.parquet"
RAW_DIR = Path("data/raw/mo_mica")

# Values MOPHIMS uses for a censored / unavailable cell. Compared case-folded and stripped.
_CENSORED_TOKENS = {"", "*", "**", "s", "n/a", "na", "nr", "-", "--", ".", "suppressed"}


# --------------------------------------------------------------------------------------
# parsing  (pure, unit-testable without a browser or network)
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Cell:
    value: float | None
    censored: bool


def parse_cell(raw: str | None) -> Cell:
    """A MOPHIMS table cell -> (value, censored).

    A real 0 is a real 0. Anything non-numeric is censored, never zero.
    """
    if raw is None:
        return Cell(None, True)
    s = str(raw).strip().replace(",", "")
    if s.casefold() in _CENSORED_TOKENS:
        return Cell(None, True)
    try:
        return Cell(float(s), False)
    except ValueError:
        return Cell(None, True)


_ZIP_RE = re.compile(r"^\d{5}$")


def parse_table_csv(text: str, year_group: str, county: str) -> pd.DataFrame:
    """MOPHIMS 'Save Table As -> CSV' export -> tidy (zcta5, year, count) rows.

    The export carries several preamble lines (title, 'Data selected in addition to...',
    a Year row and a Statistics row) before the real header. We locate the header by
    finding the first row whose leading cell mentions Zip/ZCTA, and read the year labels
    from the Year row above it. Row/column TOTAL columns are dropped.
    """
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return _empty()

    year_row: list[str] | None = None
    header_idx: int | None = None
    for i, r in enumerate(rows):
        if not r:
            continue
        head = (r[0] or "").strip().casefold()
        if head.startswith("year"):
            year_row = r
        if "zip" in head and "zcta" in head:
            header_idx = i
            break
    if header_idx is None:
        return _empty()

    # Year labels: prefer the explicit Year row; else the header row itself.
    label_src = year_row if year_row else rows[header_idx]
    years: dict[int, int] = {}                    # column index -> year
    for ci, lab in enumerate(label_src):
        m = re.search(r"\b(19|20)\d{2}\b", str(lab))
        if m:
            years[ci] = int(m.group(0))
    if not years:
        return _empty()

    out: list[dict] = []
    for r in rows[header_idx + 1:]:
        if not r:
            continue
        z = (r[0] or "").strip()
        if not _ZIP_RE.match(z):        # skips TOTAL / state-total / blank trailer rows
            continue
        for ci, yr in years.items():
            cell = parse_cell(r[ci] if ci < len(r) else None)
            out.append({
                "zcta5": z,
                "year": yr,
                "count": cell.value,
                "censored": cell.censored,
                "year_group": year_group,
                "county": county,
            })
    if not out:
        return _empty()
    df = pd.DataFrame(out)
    return _coerce(df)


def _coerce(df: pd.DataFrame) -> pd.DataFrame:
    """Pin dtypes explicitly.

    Without this, a frame whose `count` column is entirely censored (all-NA) contributes
    no dtype information to pd.concat, which pandas warns about and will eventually
    resolve differently. Pinning here makes concat dtype-stable regardless of content.
    """
    df["zcta5"] = df["zcta5"].astype("string")
    df["year"] = df["year"].astype("int64")
    df["count"] = pd.to_numeric(df["count"], errors="coerce").astype("float64")
    df["censored"] = df["censored"].astype("bool")
    df["year_group"] = df["year_group"].astype("string")
    df["county"] = df["county"].astype("string")
    return df


def _empty() -> pd.DataFrame:
    return pd.DataFrame({
        "zcta5": pd.Series(dtype="string"),
        "year": pd.Series(dtype="int64"),
        "count": pd.Series(dtype="float64"),
        "censored": pd.Series(dtype="bool"),
        "year_group": pd.Series(dtype="string"),
        "county": pd.Series(dtype="string"),
    })


def combine(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate per-county frames and de-duplicate.

    A ZCTA can be listed under more than one county (ZIPs straddle county lines), so the
    same (zcta5, year, year_group) can arrive twice with the SAME statewide value. Keep
    one, preferring an uncensored row over a censored one.
    """
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return _empty()
    df = pd.concat([_coerce(f.copy()) for f in frames], ignore_index=True)
    df = df.sort_values(["zcta5", "year", "year_group", "censored"])
    df = df.drop_duplicates(["zcta5", "year", "year_group"], keep="first")
    return _coerce(df.reset_index(drop=True))


def load_panel(path: Path | None = None, *, allow_mixed_definitions: bool = False,
               year_group: str | None = None) -> pd.DataFrame:
    """Read the built panel.

    Refuses to return both modules at once unless you explicitly opt in, because the
    2015/2016 condition lists are different measures (the ICD-9 -> ICD-10 module break).
    """
    p = Path(path) if path else OUT_PARQUET
    if not p.exists():
        die("mo_acsc", f"{p} not found - run `python -m pipeline.build_mo_acsc` first")
    df = pd.read_parquet(p)
    if year_group:
        return df[df["year_group"] == year_group].reset_index(drop=True)
    groups = set(df["year_group"].dropna().unique())
    if len(groups) > 1 and not allow_mixed_definitions:
        die("mo_acsc",
            f"panel spans {sorted(groups)} - these use DIFFERENT condition definitions "
            f"(2015/16 ICD-9->ICD-10 break; the two MICA modules are different measures). Pass "
            f"year_group=... to pick one, or allow_mixed_definitions=True if you have "
            f"pre-registered how the break is handled.")
    return df


# --------------------------------------------------------------------------------------
# extraction  (browser-driven; imported lazily so parsing stays testable without playwright)
# --------------------------------------------------------------------------------------

def _counties(page) -> list[str]:
    opts = page.locator("select").nth(2).locator("option").all_text_contents()
    return [o.strip() for o in opts if o.strip() and not o.strip().startswith("--")]


def scrape(year_group_key: str, counties: list[str] | None = None,
           headless: bool = True, pause: float = 1.0,
           raw_dir: Path = RAW_DIR) -> list[pd.DataFrame]:
    """Drive the MICA query builder once per county and collect CSV exports.

    Mirrors, step for step, the manual sequence verified against the live site on
    2026-08-01. Raw CSVs are written under `raw_dir` so a re-parse never needs a re-scrape.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:                                  # pragma: no cover
        die("mo_acsc", "playwright not installed. `pip install playwright && playwright install chromium`")

    label, years = YEAR_GROUPS[year_group_key]
    raw_dir.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page = browser.new_page(accept_downloads=True)
        page.goto(MICA_URL, wait_until="networkidle")

        todo = counties if counties is not None else _counties(page)
        log("mo_acsc", f"{year_group_key}: {len(todo)} counties x years {years[0]}-{years[-1]}")

        for n, county in enumerate(todo, 1):
            cached = raw_dir / f"{year_group_key}_{county.replace(' ', '_')}.csv"
            if cached.exists():
                frames.append(parse_table_csv(cached.read_text(), year_group_key, county))
                log("mo_acsc", f"[{n}/{len(todo)}] {county}: cached")
                continue
            try:
                text = _scrape_one(page, label, years, county, pause)
            except Exception as e:                        # noqa: BLE001 - one county must not kill the run
                log("mo_acsc", f"[{n}/{len(todo)}] {county}: FAILED ({type(e).__name__}: {e})")
                continue
            cached.write_text(text)
            frames.append(parse_table_csv(text, year_group_key, county))
            log("mo_acsc", f"[{n}/{len(todo)}] {county}: ok ({len(text)} bytes)")

        browser.close()
    return frames


def _scrape_one(page, year_label: str, years: tuple[int, ...], county: str,
                pause: float) -> str:
    """One (year_group, county) query -> CSV text."""
    page.goto(MICA_URL, wait_until="networkidle")

    page.get_by_role("radio", name=year_label).check()
    page.wait_for_load_state("networkidle"); time.sleep(pause)

    # Years accumulate into a multiselect via the Add=> button, one postback each.
    year_select = page.locator("select").filter(has_text=str(years[0])).first
    for y in years:
        year_select.select_option(label=str(y))
        page.get_by_role("button", name=re.compile(r"^Add=>")).first.click()
        page.wait_for_load_state("networkidle"); time.sleep(pause * 0.5)

    page.locator("select").first.select_option(label="Zip / ZCTA")
    page.wait_for_load_state("networkidle"); time.sleep(pause)

    page.get_by_label(re.compile("Zip / ZCTA County")).select_option(label=county)
    page.wait_for_load_state("networkidle"); time.sleep(pause)

    page.get_by_text("None selected").first.click()
    page.get_by_text("Select all").first.click()
    page.get_by_role("button", name=re.compile(r"^Add=>")).last.click()
    page.wait_for_load_state("networkidle"); time.sleep(pause)

    page.get_by_label("Main Row:").select_option(label="Geography")
    page.get_by_label("Main Column:").select_option(label="Year")
    page.get_by_label("Statistics:").select_option(label="Counts and Rates")

    page.get_by_role("button", name="Submit Query").click()
    page.wait_for_load_state("networkidle"); time.sleep(pause * 2)

    with page.expect_download() as dl:
        page.get_by_role("button", name=re.compile("Save Table As")).click()
        page.get_by_text("CSV", exact=True).click()
    return Path(dl.value.path()).read_text()


def build(year_group_key: str | None = None, headless: bool = True,
          counties: list[str] | None = None) -> str:
    keys = [year_group_key] if year_group_key else list(YEAR_GROUPS)
    all_frames: list[pd.DataFrame] = []
    for k in keys:
        all_frames.extend(scrape(k, counties=counties, headless=headless))

    df = combine(all_frames)
    if df.empty:
        die("mo_acsc", "no rows extracted - check the scrape log above")

    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)

    cens = int(df["censored"].sum())
    for g, sub in df.groupby("year_group"):
        log("mo_acsc", f"{g}: {len(sub)} rows, {sub['zcta5'].nunique()} ZCTAs, "
                       f"years {int(sub['year'].min())}-{int(sub['year'].max())}, "
                       f"{int(sub['censored'].sum())} censored "
                       f"({100 * sub['censored'].mean():.1f}%)")
    log("mo_acsc", f"wrote {OUT_PARQUET.name}: {len(df)} rows, {cens} censored "
                   f"({100 * df['censored'].mean():.1f}%) - censored are NA, not 0")
    return str(OUT_PARQUET)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year-group", choices=sorted(YEAR_GROUPS), default=None,
                    help="default: both modules")
    ap.add_argument("--counties", nargs="*", default=None, help="default: all")
    ap.add_argument("--headed", action="store_true", help="watch the browser work")
    a = ap.parse_args()
    build(a.year_group, headless=not a.headed, counties=a.counties)


if __name__ == "__main__":
    main()

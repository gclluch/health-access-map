"""build_fqhc_openings: HRSA FQHC site openings -> a ZCTA-level staggered-treatment panel for the
B5d New Access Point event study (see proj-ideas/B5d-fqhc-lever-build-plan.md, docs/VALIDATION.md §7).

Each active HRSA site carries a `Site Added to Scope this Date`. Assigned to its nearest ZCTA
centroid (the same approximate geocoding `build_fqhc` uses for the proximity metric), the per-ZCTA
*first* added-year is a dated, located supply shock. The clean treatment is a ZCTA whose FIRST EVER
FQHC opens inside the analyzable window (`newly_served`, a 0->1 transition); a ZCTA that already had
a site but gains another is the looser any-addition dose, kept only for robustness.

This module is READ-ONLY infrastructure: it emits the treatment panel and never feeds the composite.
The downstream estimator (`validate_fqhc_lever`, Callaway-Sant'Anna group-time ATT) joins these
openings to the annual ACSC outcome panels.

`Site Added to Scope this Date` is NOT a pure New Access Point flag - it also fires on relocations and
administrative re-scopings. The 0->1 `newly_served` filter is what makes it a clean first-access
event; the looser `treat_year_loose` is reported as sensitivity, never as the headline.

    python -m pipeline.build_fqhc_openings
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from . import config
from .common import assert_zcta, die, download_file, log, write_provenance

OUT = config.PROCESSED / "fqhc_openings.parquet"

# The analyzable staggered window: a ZCTA whose first FQHC opens in [start, end] has room for a
# pre-period and a post-period inside the available ACSC panels (NY SPARCS 2009-2023; TX PUDF
# ~2011-2019). Matches the window the power gate (validate_fqhc_power) counted treated-N against.
TREATMENT_WINDOW = (2012, 2019)

# The four states with an ACSC outcome panel (annual or pooled). The sanity-check counts are read
# off these; the parquet itself is national so downstream control pools aren't pre-truncated.
PANEL_STATES = ("NY", "TX", "CO", "CA")

DATE_COL = "Site Added to Scope this Date"
STATE_COL = "Site State Abbreviation"


def _load_sites() -> pd.DataFrame:
    """Active, geocoded HRSA sites with a parsed opening year."""
    dest = config.RAW / "hrsa_fqhc_sites.csv"
    download_file(config.FQHC_URL, dest, min_bytes=2_000_000)
    df = pd.read_csv(dest, dtype=str, low_memory=False)
    lon = pd.to_numeric(df[config.FQHC_COL_LON], errors="coerce")
    lat = pd.to_numeric(df[config.FQHC_COL_LAT], errors="coerce")
    status = df[config.FQHC_COL_STATUS].astype("string").str.strip().str.lower()
    year = pd.to_datetime(df[DATE_COL], format="%m/%d/%Y", errors="coerce").dt.year
    sites = pd.DataFrame({"lat": lat, "lon": lon, "status": status,
                          "state": df[STATE_COL].astype("string").str.strip().str.upper(),
                          "open_year": year})
    sites = sites[(sites["status"] == "active") & sites["lat"].between(17, 72)
                  & sites["lon"].between(-180, -64) & sites["open_year"].notna()]
    if len(sites) < 5000:
        die("fqhc-openings", f"only {len(sites)} active, geocoded, dated sites (expected >10k)")
    sites["open_year"] = sites["open_year"].astype(int)
    return sites.reset_index(drop=True)


def _assign_to_zcta(sites: pd.DataFrame, gaz: pd.DataFrame) -> np.ndarray:
    """Nearest-centroid ZCTA index for each site (BallTree/haversine, the build_fqhc pattern,
    inverted: tree on ZCTA centroids, query the sites)."""
    tree = BallTree(np.radians(gaz[["lat", "lon"]].to_numpy()), metric="haversine")
    _, idx = tree.query(np.radians(sites[["lat", "lon"]].to_numpy()), k=1)
    return idx[:, 0]


def build(force: bool = False) -> str:
    if OUT.exists() and not force:
        log("fqhc-openings", f"skip (exists): {OUT.name}")
        return str(OUT)

    sites = _load_sites()
    gaz = pd.read_parquet(config.PROCESSED / "gazetteer.parquet")
    sites["zcta5"] = gaz["zcta5"].to_numpy()[_assign_to_zcta(sites, gaz)]

    start, end = TREATMENT_WINDOW
    g = sites.groupby("zcta5")
    panel = pd.DataFrame({
        "first_open_year": g["open_year"].min(),
        "n_sites": g.size(),
    }).reset_index()

    # the clean 0->1 treatment: the ZCTA's FIRST EVER FQHC arrived inside the window
    panel["newly_served"] = panel["first_open_year"].between(start, end)
    panel["treat_year"] = np.where(panel["newly_served"], panel["first_open_year"], np.nan)

    # looser any-addition dose: earliest site added WITHIN the window, even if a prior site existed
    in_win = sites[sites["open_year"].between(start, end)]
    loose = in_win.groupby("zcta5")["open_year"].min().rename("treat_year_loose")
    panel = panel.merge(loose, on="zcta5", how="left")

    # state for the per-state sanity check / downstream filtering (authoritative ZCTA->state from
    # metrics; fall back to the modal site state for ZCTAs absent from the metrics frame)
    m = pd.read_parquet(config.PROCESSED / "metrics.parquet")[["zcta5", "state"]]
    m["zcta5"] = m["zcta5"].astype(str)
    panel = panel.merge(m, on="zcta5", how="left")
    modal = g["state"].agg(lambda s: s.mode().iloc[0] if not s.mode().empty else np.nan)
    panel["state"] = panel["state"].fillna(panel["zcta5"].map(modal))

    panel["first_open_year"] = panel["first_open_year"].astype(int)
    panel["n_sites"] = panel["n_sites"].astype(int)
    panel = panel.sort_values("zcta5").reset_index(drop=True)

    _validate(panel)
    panel.to_parquet(OUT, index=False)
    _report(sites, panel)
    return str(OUT)


def _validate(df: pd.DataFrame) -> None:
    assert_zcta(df, stage="fqhc-openings")
    if df["first_open_year"].between(1960, 2030).all() is False:
        die("fqhc-openings", "first_open_year out of plausible range")
    if (df["n_sites"] < 1).any():
        die("fqhc-openings", "a ZCTA with zero sites slipped into the panel")
    treated = df[df["newly_served"]]
    if (treated["treat_year"] != treated["first_open_year"]).any():
        die("fqhc-openings", "treat_year disagrees with first_open_year for a newly-served ZCTA")


def _report(sites: pd.DataFrame, panel: pd.DataFrame) -> None:
    start, end = TREATMENT_WINDOW
    win_sites = int(sites["open_year"].between(start, end).sum())
    touched = panel["treat_year_loose"].notna()
    newly = panel["newly_served"]
    log("fqhc-openings", f"{len(sites)} dated sites -> {len(panel)} ZCTAs; "
                         f"{win_sites} openings in {start}-{end} touched {int(touched.sum())} ZCTAs; "
                         f"{int(newly.sum())} newly-served (clean 0->1) nationally")

    sub = panel[panel["state"].isin(PANEL_STATES)]
    by_state = sub[sub["newly_served"]].groupby("state").size()
    parts = ", ".join(f"{s} {int(by_state.get(s, 0))}" for s in PANEL_STATES)
    log("fqhc-openings", f"newly-served in panel states: {parts} "
                         f"(total {int(sub['newly_served'].sum())}); "
                         f"gate expected NY 135 / TX 142, 555 across the four")

    write_provenance({"fqhc_openings": {
        "method": "HRSA 'Site Added to Scope' openings -> nearest-ZCTA, per-ZCTA first-open year; "
                  "newly_served = first ever FQHC inside the window (clean 0->1 staggered treatment)",
        "treatment_window": list(TREATMENT_WINDOW),
        "dated_sites": int(len(sites)),
        "newly_served_national": int(newly.sum()),
        "newly_served_panel_states": {s: int(by_state.get(s, 0)) for s in PANEL_STATES},
        "source": "HRSA Health Center Service Delivery and Look-Alike Sites (Site Added to Scope date)",
        "note": "READ-ONLY treatment panel for the B5d FQHC event study; never feeds the composite",
    }})


if __name__ == "__main__":
    build(force=True)

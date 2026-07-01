"""build_broadband: ACS household internet access -> a digital / telehealth-access barrier.

Telehealth collapses distance - but only for households that can get online, so a ZCTA with
no broadband is cut off from the remote-care channel entirely. This is a genuinely new access
axis (the "Awareness / digital readiness" dimension) absent from provider supply, insurance,
and preventive use. Gate-tested: no-internet rate carries clean signed-r +0.25 vs the
independent death-records outcomes (premature_death +0.35, infant_mortality +0.31, life_exp
+0.23) and KEEPS +0.12 after controlling for BOTH care_access and social_vulnerability - so it
is not merely a deprivation echo. Non-circular: it is infrastructure, not healthcare use.

Source: Census ACS 5-year table B28002 (Presence and Types of Internet Subscriptions),
B28002_001 = total households, B28002_013 = "No Internet access". ZCTA-native, one API call.
Output: broadband.parquet (zcta5, no_internet_rate in [0,1]).
"""
from __future__ import annotations

import pandas as pd

from . import config
from .common import assert_zcta, dev_filter, die, http_client, load_env, log

OUT = config.PROCESSED / "broadband.parquet"
ACS_B28002 = f"https://api.census.gov/data/{config.ACS_YEAR}/acs/acs5"


def build(dev_state: str | None = None, force: bool = False) -> str:
    if OUT.exists() and not force:
        log("broadband", f"skip (exists): {OUT.name}")
        return str(OUT)

    load_env()
    import os
    key = os.environ.get("CENSUS_API_KEY", "")
    params = {"get": "group(B28002)", "for": "zip code tabulation area:*"}
    if key:
        params["key"] = key
    import time
    r = None
    for attempt in range(3):  # retry transient Census 5xx / key-propagation lag before giving up
        with http_client(timeout=180.0) as c:
            r = c.get(ACS_B28002, params=params)
        if r.status_code == 200:
            break
        if attempt < 2:
            log("broadband", f"ACS B28002 HTTP {r.status_code}; retry {attempt + 1}/2")
            time.sleep(2 ** attempt)
    if r is None or r.status_code != 200:
        die("broadband", f"ACS B28002 fetch failed after retries: HTTP {r.status_code if r else 'no response'}")
    j = r.json()
    df = pd.DataFrame(j[1:], columns=j[0])
    tot = pd.to_numeric(df["B28002_001E"], errors="coerce")
    no_net = pd.to_numeric(df["B28002_013E"], errors="coerce")
    out = pd.DataFrame({
        "zcta5": df["zip code tabulation area"].astype(str).str.zfill(5),
        "no_internet_rate": (no_net / tot).where(tot > 0),
    })
    out = dev_filter(out, dev_state)

    assert_zcta(out, stage="broadband")
    floor = 50 if dev_state else 20_000
    if len(out) < floor:
        die("broadband", f"only {len(out)} ZCTAs (expected >= {floor})")
    if not out["no_internet_rate"].dropna().between(0, 1).all():
        die("broadband", "no_internet_rate outside [0,1]")
    # B28002_013 is hard-indexed as "No Internet access"; a future ACS renumber would silently map a
    # different member and pass [0,1]. Guard with a distribution check - a wrong column shifts the median.
    med = out["no_internet_rate"].median()
    if not dev_state and not (0.02 <= med <= 0.45):
        die("broadband", f"no_internet median {med:.3f} implausible - B28002_013 may have been renumbered")
    out.to_parquet(OUT, index=False)
    log("broadband", f"wrote {OUT.name} ({len(out)} ZCTAs, "
                     f"median no-internet {out['no_internet_rate'].median():.1%})")
    return str(OUT)


if __name__ == "__main__":
    import sys
    build(dev_state=sys.argv[1] if len(sys.argv) > 1 else None)

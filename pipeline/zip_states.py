"""ZIP/ZCTA first-3-digit (SCF) -> US state, for state filtering and labels.

Derived from the standard USPS Sectional Center Facility prefix allocations.
A handful of SCF prefixes span a state line; this maps each to its dominant
state, which is sufficient for a UI state filter (not a legal geocoder).
"""
from __future__ import annotations

# state -> list of inclusive (low, high) 3-digit prefix ranges
STATE_RANGES: dict[str, list[tuple[int, int]]] = {
    "MA": [(10, 27), (55, 55)], "RI": [(28, 29)], "NH": [(30, 38)],
    "ME": [(39, 49)], "VT": [(50, 54), (56, 59)], "CT": [(60, 69)],
    "NJ": [(70, 89)], "NY": [(0, 0), (5, 5), (100, 149)], "PR": [(6, 9)],
    "PA": [(150, 196)], "DE": [(197, 199)], "DC": [(200, 205), (569, 569)],
    "MD": [(206, 219)], "VA": [(220, 246)], "WV": [(247, 268)],
    "NC": [(270, 289)], "SC": [(290, 299)], "GA": [(300, 319), (398, 399)],
    "FL": [(320, 349)], "AL": [(350, 369)], "TN": [(370, 385)],
    "MS": [(386, 397)], "KY": [(400, 427)], "OH": [(430, 459)],
    "IN": [(460, 479)], "MI": [(480, 499)], "IA": [(500, 528)],
    "WI": [(530, 549)], "MN": [(550, 567)], "SD": [(570, 577)],
    "ND": [(580, 588)], "MT": [(590, 599)], "IL": [(600, 629)],
    "MO": [(630, 658)], "KS": [(660, 679)], "NE": [(680, 693)],
    "LA": [(700, 714)], "AR": [(716, 729), (755, 755)], "OK": [(730, 749)],
    "TX": [(750, 799), (885, 885)], "CO": [(800, 816)], "WY": [(820, 831)],
    "ID": [(832, 838)], "UT": [(840, 847)], "AZ": [(850, 865)],
    "NM": [(870, 884)], "NV": [(889, 898)], "CA": [(900, 961)],
    "HI": [(967, 968)], "OR": [(970, 979)], "WA": [(980, 994)],
    "AK": [(995, 999)],
}

# build a flat prefix -> state lookup once
_PREFIX_STATE: dict[int, str] = {}
for _st, _ranges in STATE_RANGES.items():
    for _lo, _hi in _ranges:
        for _p in range(_lo, _hi + 1):
            _PREFIX_STATE.setdefault(_p, _st)


STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "PR": "Puerto Rico", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}


# Exact 2-digit state/territory FIPS -> USPS (from a ZCTA's county_fips), unlike the approximate
# SCF-prefix heuristic above.
FIPS_STATE: dict[str, str] = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY", "72": "PR",
}


def zip3_to_state(zcta5: str) -> str | None:
    if not zcta5 or len(zcta5) < 3 or not zcta5[:3].isdigit():
        return None
    return _PREFIX_STATE.get(int(zcta5[:3]))


def fips_to_state(county_fips: str | None) -> str | None:
    """State USPS from the first 2 digits of a 5-digit county FIPS; None if absent/unknown."""
    if not county_fips or len(county_fips) < 2:
        return None
    return FIPS_STATE.get(county_fips[:2])


def state_name(abbr: str | None) -> str | None:
    return STATE_NAMES.get(abbr) if abbr else None

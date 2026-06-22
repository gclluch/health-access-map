"""The hierarchical measure model: 3 dimensions -> 11 sub-scores -> ~50 measures.

Groupings follow established frameworks (CDC PLACES categories, CDC/ATSDR SVI
themes, HRSA/2SFCA for supply) rather than ad-hoc choices.

Each measure carries a `direction`:
  +1  higher value = more need / more gap  (disease, poverty, insecurity, no-vehicle)
  -1  higher value = better                (income, preventive-care use, BP-med use)
Everything is oriented to "higher = worse access" before ranking, so a sub-score's
national percentile reads uniformly: higher = worse.

`source`:
  places  -> from build_places (PLACES <measure>_CrudePrev, as <key>_pct)
  acs     -> from build_acs    (computed rate column)
  supply  -> from build_supply (2SFCA)
"""
from __future__ import annotations

# measure: (column_in_parquet, direction, friendly_label)
M = lambda col, d, label: {"col": col, "dir": d, "label": label}  # noqa: E731

DIMENSIONS: dict = {
    "health_need": {
        "label": "Health need",
        "blurb": "Chronic disease, behavioral risk, mental/social health, and disability burden.",
        "subscores": {
            "chronic_disease": {
                "label": "Chronic disease",
                "source": "places",
                "members": [
                    M("diabetes_pct", 1, "Diabetes"),
                    M("bphigh_pct", 1, "High blood pressure"),
                    M("highchol_pct", 1, "High cholesterol"),
                    M("chd_pct", 1, "Coronary heart disease"),
                    M("stroke_pct", 1, "Stroke"),
                    M("copd_pct", 1, "COPD"),
                    M("casthma_pct", 1, "Asthma"),
                    M("cancer_pct", 1, "Cancer"),
                    M("obesity_pct", 1, "Obesity"),
                    M("arthritis_pct", 1, "Arthritis"),
                    M("teethlost_pct", 1, "All teeth lost"),
                ],
            },
            "behavioral_risk": {
                "label": "Behavioral risk",
                "source": "places",
                "members": [
                    M("csmoking_pct", 1, "Current smoking"),
                    M("lpa_pct", 1, "No leisure physical activity"),
                    M("binge_pct", 1, "Binge drinking"),
                    M("sleep_pct", 1, "Short sleep (<7h)"),
                ],
            },
            "mental_social_health": {
                "label": "Mental & social distress",
                "source": "places",
                "members": [
                    M("depression_pct", 1, "Depression"),
                    M("mhlth_pct", 1, "Frequent poor mental-health days"),
                    M("loneliness_pct", 1, "Loneliness"),
                    M("emotionspt_pct", 1, "Lacks emotional support"),
                ],
            },
            "disability": {
                "label": "Disability",
                "source": "places",
                "members": [
                    M("disability_pct", 1, "Any disability"),
                    M("mobility_pct", 1, "Mobility disability"),
                    M("cognition_pct", 1, "Cognitive disability"),
                    M("vision_pct", 1, "Vision disability"),
                    M("hearing_pct", 1, "Hearing disability"),
                    M("selfcare_pct", 1, "Self-care disability"),
                    M("indeplive_pct", 1, "Independent-living disability"),
                ],
            },
        },
    },
    "social_vulnerability": {
        "label": "Social vulnerability",
        "blurb": "Socioeconomic, household, housing/transport, and unmet social needs.",
        "subscores": {
            "socioeconomic": {
                "label": "Socioeconomic deprivation",
                "source": "acs",
                "members": [
                    M("poverty_rate", 1, "Below poverty"),
                    M("median_income", -1, "Median household income"),
                    M("unemployment_rate", 1, "Unemployment"),
                    M("no_hs_diploma_rate", 1, "No high-school diploma"),
                ],
            },
            # The former "household" sub-score (age 65+, age 17-, limited English) was removed
            # after validation against 6 independent outcomes: age structure is demographic
            # context (signal-less / wrong-signed at the area level - retirement areas read
            # "vulnerable" but have good access) and limited English is wrong-signed vs
            # mortality (the immigrant-health paradox: r=-0.25 vs infant mortality). These
            # remain raw context columns, never scored. See docs/ROADMAP-ACCESS-SIGNAL.md A1.
            "housing_transport": {
                "label": "Housing & transport barriers",
                "source": "acs",
                "members": [
                    M("no_vehicle_rate", 1, "No vehicle"),
                    M("crowding_rate", 1, "Crowded housing"),
                    M("mobile_home_rate", 1, "Mobile homes"),
                    M("multi_unit_rate", 1, "Multi-unit structures"),
                ],
            },
            "social_needs": {
                "label": "Unmet social needs",
                "source": "places",
                "members": [
                    M("foodinsecu_pct", 1, "Food insecurity"),
                    M("housinsecu_pct", 1, "Housing insecurity"),
                    M("lacktrpt_pct", 1, "Lack of transportation"),
                    M("shututility_pct", 1, "Utility shut-off threat"),
                    M("foodstamp_pct", 1, "Receives food stamps/SNAP"),
                ],
            },
        },
    },
    "care_access": {
        "label": "Barriers to care",
        "blurb": "Low provider supply (spatial), lack of insurance, unmet preventive care.",
        "subscores": {
            "provider_supply": {
                "label": "Low provider supply (spatial)",
                "source": "supply",
                "members": [
                    M("primary_2sfca", -1, "Primary-care access (2SFCA)"),
                    M("mental_2sfca", -1, "Mental-health access (2SFCA)"),
                    M("dental_2sfca", -1, "Dental access (2SFCA)"),
                    M("ob_2sfca", -1, "Maternity / OB-GYN access (2SFCA)"),
                ],
            },
            "safetynet_access": {
                "label": "Unmet safety-net need (FQHC desert x poverty)",
                "source": "fqhc",
                # need-relative: the raw E2SFCA FQHC-access score (safetynet_2sfca) is
                # wrong-signed because clinics cluster in high-need areas. safetynet_barrier
                # = FQHC-distance percentile x poverty (computed in join_and_score) is the
                # correctly-signed "unmet need" form. See docs/ROADMAP-ACCESS-SIGNAL.md A2.
                "members": [
                    M("safetynet_barrier", 1, "FQHC desert x poverty (unmet need)"),
                ],
            },
            # Layer C1 (CMS Medicare realized utilization) was BUILT and GATE-TESTED but NOT
            # scored: it failed the honest gate. Its apparent lift came entirely from circular
            # correlation with the flu/mammography validation outcomes (all three are just
            # "engaged with healthcare"); against the independent death-records outcomes it adds
            # noise (life_expectancy r=-0.00, clean-outcome composite mean-r 0.480 -> 0.470).
            # Medicare visit-rates are saturated (~90%), need-endogenous, and 65+-only. The
            # utilization columns still merge (build_utilization) for display/diagnostics; they
            # are deliberately kept OUT of the composite. See docs/ROADMAP-ACCESS-SIGNAL.md C1.
            "insurance": {
                "label": "Lack of insurance",
                "source": "mixed",
                "members": [
                    M("uninsured_rate", 1, "Uninsured (ACS, all ages)"),
                    M("access2_pct", 1, "Uninsured adults 18-64 (PLACES)"),
                ],
            },
            "preventive_use": {
                "label": "Low preventive-care use",
                "source": "places",
                "members": [
                    M("checkup_pct", -1, "Annual checkup"),
                    M("dental_pct", -1, "Dental visit"),
                    M("cholscreen_pct", -1, "Cholesterol screening"),
                    M("mammouse_pct", -1, "Mammography"),
                    M("colon_screen_pct", -1, "Colorectal screening"),
                    M("bpmed_pct", -1, "Taking BP medication"),
                ],
            },
        },
    },
}

# Default dimension weights for the composite (tunable in the UI).
DIMENSION_WEIGHTS = {"health_need": 0.35, "social_vulnerability": 0.30, "care_access": 0.35}

# Context-only fields (shown in the panel, never scored): demographics + health status.
CONTEXT_PLACES = {
    "ghlth_pct": "Fair/poor general health",
    "phlth_pct": "Frequent poor physical-health days",
}
CONTEXT_ACS = {
    "median_age": "Median age",
    "pct_minority": "Racial/ethnic minority",  # context only, never scored (by design)
    "pct_under5": "Under 5",
    "pct_over65_ctx": "65 and older",
}


def all_places_keys() -> list[str]:
    """Every *_pct column the pipeline needs from PLACES (members + context)."""
    keys = set(CONTEXT_PLACES)
    for dim in DIMENSIONS.values():
        for sub in dim["subscores"].values():
            if sub["source"] in ("places", "mixed"):
                for m in sub["members"]:
                    if m["col"].endswith("_pct"):
                        keys.add(m["col"])
    return sorted(keys)


def subscore_specs() -> list[dict]:
    """Flat list of sub-scores with their dimension + members, for scoring."""
    out = []
    for dkey, dim in DIMENSIONS.items():
        for skey, sub in dim["subscores"].items():
            out.append({"dim": dkey, "key": skey, "label": sub["label"],
                        "source": sub["source"], "members": sub["members"]})
    return out

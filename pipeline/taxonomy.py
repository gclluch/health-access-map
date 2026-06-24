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
        "blurb": "Socioeconomic, housing/transport, unmet social needs, and digital/telehealth access.",
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
            # remain raw context columns, never scored. See docs/DECISIONS.md A1.
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
            # Digital / telehealth access (build_broadband, ACS B28002). The telehealth analog of
            # the no-vehicle transport barrier: an enabling barrier to *reaching* care remotely,
            # which is why it lives in social_vulnerability (the enabling-barriers dimension), not
            # care_access. Solo clean signed-r +0.25 (premature_death +0.35, infant_mort +0.31).
            # GATE NOTE: kept as a reliability + completeness addition, NOT a signal win. In
            # care_access it slightly REGRESSED the composite (collinear with supply); in
            # social_vulnerability it holds outcome agreement at 0.495 and raises split-half
            # 0.943->0.955, filling the telehealth axis the index otherwise lacks. It does not
            # lift outcome agreement - broadband overlaps the deprivation gradient already scored.
            "digital_access": {
                "label": "Digital / telehealth access",
                "source": "broadband",
                "members": [
                    M("no_internet_rate", 1, "No household internet (ACS)"),
                ],
            },
        },
    },
    "care_access": {
        "label": "Barriers to care",
        "blurb": "Low provider supply (spatial), official shortage (HPSA), unmet safety-net "
                 "need, lack of insurance, unmet preventive care.",
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
            # HRSA primary-care HPSA designation (build_hpsa). Kept as its OWN sub-score rather
            # than folded into provider_supply because it is NEAR-ORTHOGONAL to the E2SFCA
            # density (corr ~0.05) - averaging it into provider_supply partially washes out its
            # distinct signal. As a separate sub-score it adds the most: clean signed-r +0.20 on
            # its own (premature_death +0.28, life_exp +0.17), lifting FULL 0.486->0.492 and
            # composite agreement 0.488->0.495. HPSA encodes need + travel + safety-net distance
            # a raw provider count cannot see. Mental-health/dental HPSA and the MUA/IMU index
            # were gate-tested and add ~nothing beyond PC-HPSA (subsumed / wrong-signed). See
            # docs/METHODOLOGY.md decision log + DECISIONS.md C5.
            "shortage_designation": {
                "label": "Official provider shortage (HPSA)",
                "source": "hpsa",
                "members": [
                    M("hpsa_pc_score", 1, "HRSA primary-care shortage (HPSA score)"),
                ],
            },
            # COMPUTED + DISPLAYED but NOT SCORED (scored=False). need-relative: a raw FQHC-access
            # (E2SFCA) score is wrong-signed because clinics cluster in high-need areas, so A2
            # reframed it to safetynet_barrier = FQHC-distance percentile x poverty. That form is
            # correctly signed BETWEEN counties (+0.126) but RESOLUTION-DEPENDENT: it is wrong-
            # signed WITHIN counties in 85% of states (NY ACSC + national USALEEP; FQHC-distance
            # tracks suburban-ness, not need, at sub-county scale). Because the tool is ZCTA-native,
            # dropping it from the composite lifts sub-county accuracy (composite within-county
            # +0.583->+0.601) at a negligible county cost (mean-r 0.504->0.503). Kept displayed
            # (the between-county signal is real) but unscored - the same call as `household` (A1).
            # See docs/VALIDATION.md + DECISIONS.md.
            "safetynet_access": {
                "label": "Unmet safety-net need (FQHC desert x poverty)",
                "source": "fqhc",
                "scored": False,
                "members": [
                    M("safetynet_barrier", 1, "FQHC desert x poverty (unmet need)"),
                ],
            },
            # NB: a realized-utilization sub-score (CMS Medicare visit-rates, Layer C1) and a
            # Medicare claims-volume capacity weighting (C2) were both built, gate-tested, and
            # REJECTED - C1's lift was circular with the flu/mammography outcomes, C2 was a wash.
            # The access-signal fix that worked was spatial: the variable catchment (C3). See
            # docs/METHODOLOGY.md "What we tried and rejected" + DECISIONS.md.
            "insurance": {
                "label": "Lack of insurance",
                "source": "mixed",
                "members": [
                    M("uninsured_rate", 1, "Uninsured (ACS, all ages)"),
                    M("access2_pct", 1, "Uninsured adults 18-64 (PLACES)"),
                ],
            },
            # AFFORDABILITY barrier beyond coverage: medical debt in collections (Urban Institute
            # credit-bureau panel). Captures the UNDER-insured / cost-burden population the
            # uninsured rate misses. The first new scored barrier to SURVIVE partial-r: clean
            # signed-r +0.48, partial +0.27 vs need+vulnerability+care_access (corr ~0.4 w/
            # poverty but NOT subsumed). Adding it lifted composite clean-r 0.519->0.549 and
            # care_access 0.393->0.480, widening care-access's marginal value to +0.038. An
            # upstream barrier (cause of care avoidance), not a mediator.
            # RESOLUTION CAVEAT (scored on CONSTRUCT grounds, not sub-county signal): this is a
            # COUNTY-level input broadcast county->ZCTA, so its within-county r is 0.000 (NY ACSC
            # and national USALEEP; validate_subcounty auto-flags it "0 sub-county resolution") -
            # IDENTICAL to shortage_designation (HPSA). Its entire +0.27 partial-r is a
            # COUNTY-resolution signal; it adds nothing at the tool's native ZCTA resolution. It is
            # kept scored for the same reason HPSA is (a real, official, county-level affordability
            # barrier), NOT because it resolves sub-county variance. Unlike safetynet (which was
            # *wrong*-signed within-county and so unscored), county-flat is signal-less, not
            # mis-signed, so it is harmless to keep. See docs/VALIDATION.md §3 + DECISIONS.md.
            "medical_debt": {
                "label": "Medical debt burden",
                "source": "medicaldebt",
                "members": [
                    M("medical_debt", 1, "Medical debt in collections (Urban Institute)"),
                ],
            },
            # REALIZED care use - computed + displayed but NOT SCORED (scored=False). This is
            # utilization (a MEDIATOR between barriers and outcomes / Donabedian "process"),
            # not a barrier (the "cause"). Including a downstream mediator in a cause-construct
            # is endogenous, and `mammouse_pct` is literally the `mammography` validation
            # outcome (criterion contamination). So it moves to the validation/outcome layer:
            # a realized-access process indicator, not a scored barrier. See docs/VALIDATION.md.
            "preventive_use": {
                "label": "Low preventive-care use (realized access)",
                "source": "places",
                "scored": False,
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
    # Acceptability context: the Medicaid population faces provider-acceptance barriers. Shown,
    # not scored - as a barrier it collapses to the poverty gradient (partial -0.064). The true
    # supply-side acceptance signal needs the scrape-to-calibrate build. See docs/DECISIONS.md.
    "medicaid_rate": "Medicaid / means-tested coverage",
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


def scored_places_keys() -> list[str]:
    """PLACES `<base>_pct` columns that actually enter a scored sub-score (excludes
    CONTEXT_PLACES). Used by build_places to scope the Layer-B3 places_input_cv to the
    measures that affect the composite."""
    keys = set()
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
                        "source": sub["source"], "members": sub["members"],
                        "scored": sub.get("scored", True)})
    return out

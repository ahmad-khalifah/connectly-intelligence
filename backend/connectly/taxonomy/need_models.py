"""How each sector's access gap is assessed: which indicators, how much each counts.

Weights sum to 1 per sector. `higher_is_worse` comes from the indicator definition.
A sector with no model (agriculture and transport today) cannot be scored: no open
indicator for it is loaded, and the platform says so instead of guessing.

Change weights here; the method is documented in docs/methodology.md.
"""

NEED_MODELS: dict[str, list[tuple[str, float]]] = {
    "health": [
        ("health.facilities_per_10k", 0.30),
        ("health.nearest_facility_km_ward_point", 0.25),
        ("health.settlements_over_5km_pct", 0.25),
        ("health.births_in_facility_pct", 0.20),
    ],
    "connectivity": [
        ("connectivity.sites_per_10k", 0.35),
        ("connectivity.nearest_tower_km_ward_point", 0.35),
        ("connectivity.households_mobile_phone_pct", 0.30),
    ],
    "finance": [
        ("finance.access_points_per_10k", 0.30),
        ("finance.nearest_access_point_km_ward_point", 0.30),
        ("finance.financially_excluded_adults_pct", 0.40),
    ],
    "education": [
        ("education.schools_per_10k", 0.50),
        ("education.women_literate_pct", 0.50),
    ],
    "energy": [
        ("energy.households_electricity_pct", 1.00),
    ],
    "commerce": [
        ("commerce.markets_per_10k", 1.00),
    ],
}

# How much a value of each type can be relied on, for the confidence measure.
VALUE_TYPE_QUALITY = {
    "measured": 1.0,
    "derived": 0.85,
    "modelled": 0.7,
    "estimated": 0.6,
    "assumed": 0.3,
    "ai_generated": 0.0,
}
VERIFICATION_QUALITY = {
    "field_verified": 1.0,
    "source_verified": 1.0,
    "unverified": 0.9,
    "disputed": 0.5,
    "retired": 0.0,
}

# An indicator is only used to rank when at least this many areas in scope have a value.
MIN_AREAS_TO_RANK = 3
# Below this share of the model's weight, no score is given ("insufficient evidence").
MIN_COVERAGE = 0.34

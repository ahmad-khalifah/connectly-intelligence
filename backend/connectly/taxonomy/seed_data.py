"""Reference data loaded by `connectly seed`.

Everything here is a definition or a documented fact about data availability.
There are no statistics in this file: indicator *values* only ever come from
ingested datasets.
"""

from datetime import date

# The eight sectors and their need categories, as defined in the product brief.
SECTORS: list[dict] = [
    {
        "code": "health",
        "name": "Healthcare",
        "priority": True,
        "description": "Communities with limited healthcare access and opportunities for "
        "digital health.",
        "needs": [
            ("telemedicine", "Telemedicine"),
            ("digital_health_services", "Digital health services"),
            ("diagnostics", "Medical diagnostics technology"),
            ("health_information", "Health information platforms"),
            ("health_records", "Digital health records"),
            ("care_delivery", "Healthcare delivery solutions"),
        ],
    },
    {
        "code": "connectivity",
        "name": "Telecommunications and digital connectivity",
        "priority": True,
        "description": "Communities with limited connectivity and opportunities for "
        "internet access and digital infrastructure.",
        "needs": [
            ("internet_access", "Internet access"),
            ("community_networks", "Community networks"),
            ("digital_infrastructure", "Digital infrastructure"),
            ("connectivity_services", "Connectivity services"),
            ("affordable_broadband", "Affordable broadband solutions"),
        ],
    },
    {
        "code": "finance",
        "name": "Financial services",
        "priority": True,
        "description": "Communities with limited financial access and opportunities for "
        "digital financial services.",
        "needs": [
            ("digital_banking", "Digital banking"),
            ("agent_banking", "Agent banking"),
            ("digital_payments", "Digital payments"),
            ("financial_literacy", "Financial literacy"),
            ("microfinance_tech", "Microfinance technology"),
            ("sme_finance", "SME financial services"),
            ("financial_management", "Digital financial management"),
        ],
    },
    {
        "code": "education",
        "name": "Education",
        "priority": False,
        "description": "Communities with limited educational technology access.",
        "needs": [
            ("digital_learning", "Digital learning platforms"),
            ("edtech", "EdTech solutions"),
            ("school_management", "School management systems"),
            ("online_resources", "Online educational resources"),
            ("digital_skills", "Digital skills training"),
            ("teacher_support", "Teacher support technologies"),
        ],
    },
    {
        "code": "agriculture",
        "name": "Agriculture",
        "priority": False,
        "description": "Agricultural communities and opportunities for agritech.",
        "needs": [
            ("agritech_platforms", "Agritech platforms"),
            ("farm_management", "Farm management systems"),
            ("agri_marketplaces", "Agricultural marketplaces"),
            ("digital_extension", "Digital extension services"),
            ("agri_finance", "Agricultural financing"),
            ("supply_chain", "Supply chain technology"),
            ("market_prices", "Market price intelligence"),
        ],
    },
    {
        "code": "energy",
        "name": "Clean energy",
        "priority": False,
        "description": "Communities with limited energy access.",
        "needs": [
            ("solar", "Solar energy solutions"),
            ("renewable_systems", "Renewable energy systems"),
            ("battery_storage", "Battery storage"),
            ("energy_distribution", "Energy distribution platforms"),
            ("affordable_electricity", "Affordable electricity solutions"),
        ],
    },
    {
        "code": "commerce",
        "name": "Commerce and SMEs",
        "priority": False,
        "description": "Underserved businesses and opportunities for digital commerce.",
        "needs": [
            ("ecommerce", "E-commerce"),
            ("digital_marketplaces", "Digital marketplaces"),
            ("inventory", "Inventory management"),
            ("business_software", "Business management software"),
            ("merchant_payments", "Digital payments"),
            ("automation", "Business automation"),
        ],
    },
    {
        "code": "transport",
        "name": "Transportation and logistics",
        "priority": False,
        "description": "Communities and markets requiring mobility and logistics technology.",
        "needs": [
            ("mobility", "Mobility solutions"),
            ("transport_tech", "Transport technology"),
            ("digital_logistics", "Digital logistics"),
            ("vehicle_finance", "Vehicle financing"),
            ("delivery", "Delivery platforms"),
            ("fleet_management", "Fleet management systems"),
        ],
    },
]

# Indicator definitions planned for the priority sectors. No values are created here.
INDICATORS: list[dict] = [
    {
        "code": "population.modelled_total",
        "name": "Modelled population",
        "sector": None,
        "unit": "people",
        "higher_is_worse": None,
        "description": "Gridded population estimate summed over the area.",
        "method": "Zonal sum of GRID3 NGA Population v3.0. A model output, not a census count.",
    },
    {
        "code": "health.nearest_facility_km",
        "name": "Distance to nearest health facility",
        "sector": "health",
        "unit": "km",
        "higher_is_worse": True,
        "description": "Straight-line distance from a settlement to the nearest health facility.",
        "method": "Derived: nearest-neighbour distance to GRID3 NGA Health Facilities points.",
    },
    {
        "code": "health.facilities_per_10k",
        "name": "Health facilities per 10,000 people",
        "sector": "health",
        "unit": "facilities per 10,000",
        "higher_is_worse": False,
        "description": "Facility count relative to modelled population.",
        "method": "Derived: GRID3 facility count ÷ GRID3 modelled population × 10,000.",
    },
    {
        "code": "connectivity.nearest_tower_km",
        "name": "Distance to nearest mapped cell tower",
        "sector": "connectivity",
        "unit": "km",
        "higher_is_worse": True,
        "description": "Straight-line distance from a settlement to the nearest crowdsourced "
        "cell tower location.",
        "method": "Derived from OpenCelliD (CC BY-SA 4.0). Crowdsourced: absence of a tower "
        "is not proof of no coverage.",
    },
    {
        "code": "connectivity.internet_subscriptions",
        "name": "Active internet subscriptions",
        "sector": "connectivity",
        "unit": "subscriptions",
        "higher_is_worse": False,
        "description": "Active internet subscriptions reported for the state.",
        "method": "Measured: NCC / NBS published state figures.",
    },
    {
        "code": "finance.formal_inclusion_adults_pct",
        "name": "Adults formally financially included",
        "sector": "finance",
        "unit": "% of adults",
        "higher_is_worse": False,
        "description": "Share of adults using formal financial services.",
        "method": "Measured: EFInA Access to Financial Services in Nigeria survey, state estimate.",
    },
]

IDENTIFIED = date(2026, 11, 10)

# Gaps found during the Phase 1 data review. Each is shown in the product.
DATA_GAPS: list[dict] = [
    {
        "code": "geo.wards_not_loaded",
        "sector": None,
        "title": "Ward boundaries not yet loaded",
        "description": "Ward boundaries are published by GRID3 (Operational Wards v4.0, "
        "October 2026) but must be downloaded manually from the GRID3 data hub and loaded "
        "with `connectly ingest load grid3-nga-wards-v4 --file <path>`.",
        "scope": "Adamawa State (then all priority states)",
        "candidates": "GRID3 NGA Operational Wards v4.0",
        "field": False,
    },
    {
        "code": "geo.settlements_not_loaded",
        "sector": None,
        "title": "Settlements not yet loaded",
        "description": "Communities (settlements) are planned for Milestone 2 from GRID3 "
        "Settlement Extents v4.1 and Settlement Names. Until then the explorer stops at LGA.",
        "scope": "Adamawa State",
        "candidates": "GRID3 NGA Settlement Extents v4.1; GRID3 NGA Settlement Names",
        "field": False,
    },
    {
        "code": "population.no_recent_census",
        "sector": None,
        "title": "No population census since 2006",
        "description": "Nigeria's last census was in November 2006. All population figures "
        "are projections or models and are labelled as modelled.",
        "scope": "Nigeria",
        "candidates": "GRID3 NGA Population v3.0 (modelled)",
        "field": False,
    },
    {
        "code": "health.facilities_v3_missing_states",
        "sector": "health",
        "title": "Latest health facility release excludes Taraba and Plateau",
        "description": "GRID3 Health Facilities v3.0 (August 2026) covers 24 states; Taraba "
        "and Plateau must fall back to v2.0 (November 2024).",
        "scope": "Taraba, Plateau",
        "candidates": "GRID3 NGA Health Facilities v2.0; Health Facility Registry (FMoH)",
        "field": False,
    },
    {
        "code": "connectivity.operator_coverage_maps",
        "sector": "connectivity",
        "title": "Operator network coverage maps not openly available",
        "description": "Mobile operators' coverage maps are not published as open data and "
        "GSMA coverage maps are licensed. Coverage can only be approximated from "
        "crowdsourced tower locations.",
        "scope": "Nigeria",
        "candidates": "OpenCelliD (crowdsourced, CC BY-SA 4.0)",
        "field": True,
    },
    {
        "code": "connectivity.speed_tests_noncommercial",
        "sector": "connectivity",
        "title": "Speed-test data is non-commercial only",
        "description": "Ookla open data is licensed CC BY-NC-SA 4.0. It cannot feed "
        "commercial outputs and is excluded until the commercial status is decided.",
        "scope": "Nigeria",
        "candidates": "Ookla Open Data (non-commercial)",
        "field": False,
    },
    {
        "code": "finance.agent_locations",
        "sector": "finance",
        "title": "Agent banking and mobile money agent locations not openly available",
        "description": "No open, geolocated register of banking or mobile money agents was "
        "found. Financial access at community level cannot be measured directly.",
        "scope": "Nigeria",
        "candidates": "OpenStreetMap bank and ATM points (incomplete); field verification",
        "field": True,
    },
    {
        "code": "finance.state_level_only",
        "sector": "finance",
        "title": "Financial inclusion measured only at state level",
        "description": "EFInA's A2F survey is representative at state level. Values must not "
        "be assigned to individual LGAs or communities.",
        "scope": "Nigeria",
        "candidates": "EFInA A2F 2023",
        "field": False,
    },
    {
        "code": "education.school_data_dated",
        "sector": "education",
        "title": "Open school locations date from December 2020",
        "description": "The open GRID3 education facilities file describes December 2020. "
        "Enrolment by school is not openly available.",
        "scope": "Nigeria",
        "candidates": "GRID3 Nigeria Education Facilities (HDX, CC BY)",
        "field": True,
    },
    {
        "code": "agriculture.lga_production",
        "sector": "agriculture",
        "title": "Crop production by LGA not openly available",
        "description": "Open agricultural surveys (GHS-Panel) are representative only at "
        "zone level.",
        "scope": "Nigeria",
        "candidates": "NBS GHS-Panel Wave 5 (zone level)",
        "field": True,
    },
    {
        "code": "energy.settlement_electrification",
        "sector": "energy",
        "title": "Current electrification status by settlement not confirmed",
        "description": "The electrification planning portal launched in 2020 has settlement "
        "data, but current open access and any post-2020 updates are unconfirmed.",
        "scope": "Nigeria",
        "candidates": "REA / NESP electrification portal",
        "field": True,
    },
    {
        "code": "community.economic_activities",
        "sector": None,
        "title": "Main economic activities per community",
        "description": "No open dataset lists economic activities per settlement. This "
        "field needs field verification or partner reports.",
        "scope": "Adamawa State",
        "candidates": "Field verification; partner organisations",
        "field": True,
    },
    {
        "code": "directory.no_open_registry",
        "sector": None,
        "title": "No open directory of technology solutions",
        "description": "There is no open, structured register of Nigerian technology "
        "products and their requirements. The directory is curated manually from company "
        "sources.",
        "scope": "Nigeria",
        "candidates": "Company websites and filings; self-submission (later)",
        "field": False,
    },
]

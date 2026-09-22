"""Shared constants for the ReliefMesh synthetic flood scenario.

Everything here is SIMULATED. Place names, people and incidents are fictional.
The coordinates lie in a real river valley so OSRM routing works in Phase 12.
"""

SCENARIO = {
    "id": "flood-sim-001",
    "name": "Kabul River Flood (SIMULATED)",
    "description": (
        "A simulated monsoon flood. All names, people and incidents are "
        "fictional and exist only for a decision-support prototype demo."
    ),
    "start_time": "2026-08-14T06:00:00+05:00",
    # The demo 'clock'. Report age is always measured against this value,
    # never against the real current time, so results are reproducible.
    "now": "2026-08-14T09:30:00+05:00",
    "timezone": "Asia/Karachi",
    "center": {"lat": 34.0150, "lon": 71.9750},
    "bounding_box": {
        "min_lat": 33.99,
        "max_lat": 34.06,
        "min_lon": 71.94,
        "max_lon": 72.02,
    },
    "disclaimer": (
        "SIMULATED DATA. ReliefMesh AI is a decision-support prototype. "
        "It does not replace emergency services, doctors, rescue "
        "professionals, or government authorities."
    ),
}

REPORT_DATE = "2026-08-14"
TZ_OFFSET = "+05:00"

LANGUAGES = ("en", "roman_ur", "ur")

# How much we trust each kind of source (0 to 1).
# The Verification Agent (Phase 8) will use these numbers.
SOURCE_CONFIDENCE = {
    "field_officer": 0.90,
    "volunteer_form": 0.75,
    "hotline_call": 0.70,
    "whatsapp": 0.60,
    "sms": 0.55,
    "social_media": 0.35,
}

INCIDENT_TYPES = (
    "trapped_residents",
    "medical_emergency",
    "road_blocked",
    "flooded_property",
    "shelter_request",
    "food_water_shortage",
    "structural_damage",
    "missing_person",
    "electrical_hazard",
    "stranded_vehicle",
    "livestock_stranded",
)

PRIORITIES = ("Critical", "High", "Medium", "Low")

# Things an incident can need. Only the first four exist in our inventory.
RESOURCE_TYPES = ("rescue_team", "boat", "ambulance", "medical_team")
RESOURCE_NEEDS = RESOURCE_TYPES + (
    "shelter",
    "relief_supplies",
    "utility_crew",
    "engineering_team",
    "search_team",
    "dewatering_pump",
)
RESOURCE_STATUSES = ("available", "deployed", "maintenance")

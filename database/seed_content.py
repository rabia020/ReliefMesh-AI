"""Hand-written content for the ReliefMesh AI demo scenario (SIMULATED).

Everything here is invented for a demo. Names, numbers and events are not real.
Save this file as UTF-8 because it contains Urdu text.
"""

# The scenario "now". All report ages are measured against this fixed time,
# so the demo gives the same results on any day.
SCENARIO_NOW = "2026-08-15T12:00:00+05:00"

# How much we trust each kind of source (a starting point, used in Phase 8).
SOURCE_CONFIDENCE = {
    "official_field_team": 0.95,
    "field_volunteer": 0.80,
    "hotline_call": 0.75,
    "citizen_sms": 0.60,
    "social_media": 0.40,
}

# ---------------------------------------------------------------------------
# INCIDENTS (20) - the "true" incidents behind the reports
# Fields starting with "expected_" are the ANSWER KEY used only in tests.
# ---------------------------------------------------------------------------
INCIDENT_FIELDS = (
    "incident_id", "title", "incident_type", "location_name",
    "latitude", "longitude", "estimated_affected_people", "vulnerable_people",
    "medical_emergency", "isolated", "required_resources",
    "expected_priority", "expected_confidence_band",
)

INCIDENT_ROWS = [
    ("INC-101", "Families trapped near Daryab Bridge", "trapped_residents", "Daryab Bridge",
     31.6020, 74.3050, 40, 1, True, True, ["rescue_boat", "medical_team"], "Critical", "high"),
    ("INC-102", "Kacha Basti submerged, elderly and children on rooftops", "trapped_residents", "Kacha Basti",
     31.6075, 74.2870, 60, 12, True, True, ["rescue_boat", "ambulance"], "Critical", "high"),
    ("INC-103", "Residents unable to leave Nadeem Colony", "evacuation_needed", "Nadeem Colony",
     31.5960, 74.3120, 35, 6, False, False, ["rescue_boat", "rescue_team"], "High", "high"),
    ("INC-104", "Dialysis patient cannot reach hospital, Green Town Block C", "medical_emergency", "Green Town Block C",
     31.5890, 74.2950, 5, 1, True, False, ["ambulance"], "High", "high"),
    ("INC-105", "Crowd sheltering on Al-Noor School roof", "trapped_residents", "Al-Noor School",
     31.6105, 74.3200, 80, 30, False, True, ["rescue_boat", "rescue_team"], "Critical", "high"),
    ("INC-106", "Minibus stuck in Sabzazar underpass", "stranded_vehicle", "Sabzazar Road Underpass",
     31.5820, 74.3080, 8, 0, False, False, ["rescue_team"], "Medium", "high"),
    ("INC-107", "No drinking water near Bhatti Chowk market", "food_water_shortage", "Bhatti Chowk Market",
     31.5930, 74.3300, 120, 15, False, False, ["food_water_supply"], "Medium", "high"),
    ("INC-108", "Elderly residents with a heart patient trapped in Rahmat Goth", "trapped_residents", "Rahmat Goth",
     31.6150, 74.2780, 25, 8, True, True, ["rescue_boat", "medical_team"], "Critical", "high"),
    ("INC-109", "Fallen tree blocks Old Canal Road", "road_blocked", "Old Canal Road",
     31.5750, 74.3020, 0, 0, False, False, ["debris_clearance"], "Low", "medium"),
    ("INC-110", "Displaced families need shelter, Model Town Extension", "shelter_needed", "Model Town Extension",
     31.5700, 74.2890, 45, 10, False, False, ["shelter"], "Medium", "medium"),
    ("INC-111", "Workers stuck near live wires, Shadman Mill", "electrical_hazard", "Shadman Mill Compound",
     31.6000, 74.2700, 30, 0, False, True, ["electric_utility_team", "rescue_team"], "High", "high"),
    ("INC-112", "Missing 7-year-old boy near Jinnah Park", "missing_person", "Jinnah Park",
     31.5850, 74.3250, 1, 1, False, False, ["rescue_team"], "High", "medium"),
    ("INC-113", "Wall collapse traps four people, Farooq Colony", "structural_damage", "Farooq Colony",
     31.6180, 74.3100, 4, 2, True, False, ["rescue_team", "ambulance"], "Critical", "high"),
    ("INC-114", "Two vans stuck at railway crossing", "stranded_vehicle", "Railway Crossing Mor",
     31.5980, 74.3400, 15, 3, False, False, ["rescue_team"], "Medium", "high"),
    ("INC-115", "Chak 12 village cut off by floodwater", "evacuation_needed", "Chak 12 Village",
     31.6250, 74.2950, 90, 20, False, True, ["rescue_boat", "rescue_team"], "High", "medium"),
    ("INC-116", "Elderly diabetic woman out of insulin, Iqbal Town", "medical_emergency", "Iqbal Town Lane 5",
     31.5780, 74.3200, 1, 1, True, False, ["ambulance"], "High", "medium"),
    ("INC-117", "Conflicting reports about the hospital access road", "road_blocked", "Madina Masjid Road",
     31.5920, 74.2800, 0, 0, False, False, [], "Medium", "medium"),
    ("INC-118", "Flooded families need shelter, Gulshan-e-Amin", "shelter_needed", "Gulshan-e-Amin",
     31.6060, 74.3350, 30, 5, False, False, ["shelter"], "Medium", "high"),
    ("INC-119", "Low food supplies near Power Grid Station Road", "food_water_shortage", "Power Grid Station Road",
     31.5650, 74.3100, 25, 6, False, False, ["food_water_supply"], "Low", "medium"),
    ("INC-120", "Unverified rumour of embankment breach at Chak 9", "unverified_rumor", "Chak 9 Embankment",
     31.6300, 74.3150, 0, 0, False, False, [], "Low", "low"),
]

# ---------------------------------------------------------------------------
# REPORTS (50)
# Column order:
#   incident_id, "DD HH:MM" (August 2026), language, source_type,
#   has_gps (1/0), image_file, label, text
# label: related | conflicting | rumor | correction
# language: en | roman_ur | ur
# ---------------------------------------------------------------------------
REPORT_ROWS = [
    # --- INC-101 Daryab Bridge: 6 reports (the main demo cluster) ---
    ("INC-101", "15 06:40", "roman_ur", "citizen_sms", 1, None, "related",
     "Pul ke paas 10 families phansi hui hain aur ek pregnant woman ko medical help chahiye."),
    ("INC-101", "15 06:48", "en", "social_media", 0, "daryab_bridge_flooded.jpg", "related",
     "Bridge flooded. Water rising fast."),
    ("INC-101", "15 06:55", "roman_ur", "citizen_sms", 0, None, "related",
     "Pul ke paas pani hai, gharon mein pani ghus gaya hai."),
    ("INC-101", "15 07:05", "en", "hotline_call", 0, None, "related",
     "Caller reports about 40 people stuck near Daryab Bridge, including children. "
     "Road near bridge blocked. Requesting boat rescue."),
    ("INC-101", "15 07:20", "ur", "citizen_sms", 0, None, "related",
     "دریاب پل کے قریب لوگ چھتوں پر پھنسے ہوئے ہیں۔ ایک حاملہ خاتون کو فوری طبی مدد چاہیے۔"),
    ("INC-101", "14 22:30", "en", "citizen_sms", 0, None, "conflicting",
     "Daryab Bridge road is still passable for small vehicles. Water only at ankle level."),

    # --- INC-102 Kacha Basti: 3 reports ---
    ("INC-102", "15 07:10", "roman_ur", "field_volunteer", 1, None, "related",
     "Kacha Basti mein 60 ke qareeb log phanse hue hain. Bache aur buzurg zyada hain. "
     "Ek buzurg sugar ki wajah se behosh ho gaye hain. Boat chahiye."),
    ("INC-102", "15 07:35", "en", "hotline_call", 0, None, "related",
     "Kacha Basti low-lying area completely submerged. Many elderly people and children on rooftops. "
     "One elderly man is unconscious. Need boat and ambulance."),
    ("INC-102", "15 07:50", "ur", "citizen_sms", 0, None, "related",
     "کچی بستی میں پانی گھروں کے اندر آ گیا ہے۔ بچے اور بزرگ چھتوں پر ہیں، براہِ کرم کشتی بھیجیں۔"),

    # --- INC-103 Nadeem Colony: 3 reports (conflicting head-counts) ---
    ("INC-103", "15 08:00", "en", "citizen_sms", 1, None, "conflicting",
     "Nadeem Colony street 4: about 15 people cannot leave, water waist-deep."),
    ("INC-103", "15 08:15", "roman_ur", "hotline_call", 0, None, "related",
     "Nadeem Colony mein takreeban 40 log hain jo nikal nahi pa rahe, 6 bache aur buzurg bhi hain. "
     "Pani kamar tak hai."),
    ("INC-103", "15 08:20", "en", "field_volunteer", 1, None, "related",
     "Counted 35 residents in Nadeem Colony streets 3 to 5 needing evacuation. "
     "6 are children or elderly. No injuries."),

    # --- INC-104 Green Town Block C: 3 reports ---
    ("INC-104", "15 08:30", "roman_ur", "citizen_sms", 0, None, "related",
     "Green Town Block C mein ek dialysis ke mareez ko aaj hospital pohunchana hai. "
     "Gali mein ghutnon tak pani hai, ambulance andar nahi aa sakti."),
    ("INC-104", "15 08:45", "en", "hotline_call", 0, None, "related",
     "Kidney patient in Green Town Block C needs dialysis today. "
     "Ambulance cannot enter the flooded street. Family of 5 in the house."),
    ("INC-104", "15 09:00", "ur", "citizen_sms", 0, None, "related",
     "گرین ٹاؤن بلاک سی میں ایک گردوں کے مریض کو ڈائیلاسز کے لیے ہسپتال لے جانا ہے۔ "
     "گلی میں پانی ہے، ایمبولینس اندر نہیں آ سکتی۔"),

    # --- INC-105 Al-Noor School roof: 3 reports ---
    ("INC-105", "15 07:45", "en", "field_volunteer", 1, "school_roof_crowd.jpg", "related",
     "About 80 people, including roughly 30 children, are taking shelter on the roof of Al-Noor School. "
     "Water is still rising. No food since morning."),
    ("INC-105", "15 08:05", "roman_ur", "citizen_sms", 0, None, "related",
     "Al-Noor school ki chhat par bohat se log hain, bache bhi hain. Pani upar aa raha hai."),
    ("INC-105", "15 08:40", "ur", "hotline_call", 0, None, "related",
     "النور اسکول کی چھت پر تقریباً اسّی افراد موجود ہیں، زیادہ تر بچے اور خواتین ہیں۔ پانی بڑھ رہا ہے۔"),

    # --- INC-106 Sabzazar underpass: 3 reports ---
    ("INC-106", "15 09:10", "en", "citizen_sms", 1, "underpass_minibus.jpg", "related",
     "A minibus is stuck in the Sabzazar Road underpass, water up to the windows. "
     "About 8 passengers inside."),
    ("INC-106", "15 09:12", "roman_ur", "social_media", 0, None, "related",
     "Sabzazar underpass mein gaari phans gayi hai, log andar hain."),
    ("INC-106", "15 09:25", "en", "field_volunteer", 1, None, "related",
     "Confirmed: minibus stuck in Sabzazar underpass, 8 passengers climbed onto the roof. "
     "No injuries. Need a rope or boat."),

    # --- INC-107 Bhatti Chowk: 3 reports ---
    ("INC-107", "15 09:00", "roman_ur", "citizen_sms", 0, None, "related",
     "Bhatti Chowk ke gharon mein khana aur peene ka pani khatam ho gaya hai. Takreeban 120 log hain."),
    ("INC-107", "15 09:20", "en", "hotline_call", 0, None, "related",
     "Around 120 residents near Bhatti Chowk market have had no drinking water for 24 hours. "
     "About 15 are infants and elderly."),
    ("INC-107", "15 09:40", "ur", "citizen_sms", 0, None, "related",
     "بھٹی چوک میں پینے کا پانی اور کھانا ختم ہو گیا ہے۔ بچے بھوکے ہیں، تقریباً ایک سو بیس لوگ ہیں۔"),

    # --- INC-108 Rahmat Goth: 2 reports ---
    ("INC-108", "15 07:30", "roman_ur", "field_volunteer", 1, None, "related",
     "Rahmat Goth mein 25 log ghar mein phanse hue hain, 8 buzurg ya maazoor hain. "
     "Ek buzurg ko dil ka dora pada hai. Boat aur doctor chahiye."),
    ("INC-108", "15 08:10", "ur", "hotline_call", 0, None, "related",
     "رحمت گوٹھ میں پچیس افراد پھنسے ہوئے ہیں۔ ایک بزرگ کو دل کی تکلیف ہے۔ راستہ بند ہے، کشتی اور ڈاکٹر بھیجیں۔"),

    # --- INC-109 Old Canal Road: 2 reports ---
    ("INC-109", "15 09:30", "en", "citizen_sms", 1, None, "related",
     "Old Canal Road blocked by a fallen tree and knee-deep water near the petrol pump. Nobody hurt."),
    ("INC-109", "15 09:50", "roman_ur", "social_media", 0, None, "related",
     "Old Canal Road par darakht gir gaya hai, traffic band hai."),

    # --- INC-110 Model Town Extension: 2 reports ---
    ("INC-110", "15 10:00", "en", "hotline_call", 0, None, "related",
     "45 people from Model Town Extension have left their flooded homes and need a shelter. "
     "10 are children or elderly."),
    ("INC-110", "15 10:15", "roman_ur", "citizen_sms", 0, None, "related",
     "Model Town extension ke 45 ke qareeb log bina chhat ke hain, shelter chahiye."),

    # --- INC-111 Shadman Mill: 2 reports ---
    ("INC-111", "15 08:50", "en", "field_volunteer", 1, "mill_live_wires.jpg", "related",
     "About 30 workers at Shadman Mill Compound are stuck. Electric wires are hanging in the floodwater. "
     "Do not send anyone in without a power cut-off."),
    ("INC-111", "15 09:05", "roman_ur", "citizen_sms", 0, None, "related",
     "Shadman Mill ke andar pani mein bijli ki taar gir gayi hai, mazdoor phanse hue hain, current ka khatra hai."),

    # --- INC-112 Jinnah Park missing child: 2 reports ---
    ("INC-112", "15 10:05", "ur", "citizen_sms", 0, None, "related",
     "جناح پارک کے قریب ایک سات سال کا بچہ لاپتہ ہے۔ خدشہ ہے کہ وہ پانی کے بہاؤ میں بہہ گیا ہو۔"),
    ("INC-112", "15 10:20", "en", "hotline_call", 0, None, "related",
     "A 7-year-old boy has been missing since morning near Jinnah Park. "
     "Last seen near the drain. Family is searching."),

    # --- INC-113 Farooq Colony collapse: 2 reports ---
    ("INC-113", "15 09:35", "en", "hotline_call", 0, "collapsed_wall_debris.jpg", "related",
     "House wall collapsed in Farooq Colony. Four people trapped under debris, "
     "at least two injured, including a child."),
    ("INC-113", "15 09:45", "roman_ur", "citizen_sms", 1, None, "related",
     "Farooq Colony mein ghar ki deewar gir gayi hai, malbe ke neeche log dab gaye hain, zakhmi hain."),

    # --- INC-114 Railway crossing Mor: 2 reports ---
    ("INC-114", "15 10:30", "roman_ur", "field_volunteer", 1, None, "related",
     "Railway crossing Mor ke paas 2 vans phansi hui hain, 15 log hain, 3 bache. Koi zakhmi nahi."),
    ("INC-114", "15 10:40", "en", "citizen_sms", 0, None, "related",
     "Two vans stuck at the railway crossing with about 15 people, water rising slowly."),

    # --- INC-115 Chak 12 village: 2 reports (weak sources) ---
    ("INC-115", "15 08:25", "ur", "citizen_sms", 1, None, "related",
     "چک 12 گاؤں کا راستہ کٹ گیا ہے، تقریباً نوّے لوگ گھرے ہوئے ہیں۔"),
    ("INC-115", "15 09:15", "en", "social_media", 0, None, "related",
     "Chak 12 village cut off by floodwater, maybe 90 people, many old people."),

    # --- INC-116 Iqbal Town insulin: 2 reports ---
    ("INC-116", "15 10:45", "roman_ur", "citizen_sms", 1, None, "related",
     "Iqbal Town gali 5 mein ek buzurg khatoon ko insulin chahiye, bijli nahi hai aur fridge band hai."),
    ("INC-116", "15 11:00", "en", "hotline_call", 0, None, "related",
     "Elderly diabetic woman in Iqbal Town lane 5 has run out of insulin. "
     "Power is out. Needs medicine delivery or transfer."),

    # --- INC-117 Hospital access road: 2 reports (open vs blocked) ---
    ("INC-117", "15 10:10", "en", "official_field_team", 1, None, "related",
     "Road from Madina Masjid to City Hospital is blocked by floodwater. Vehicles cannot pass."),
    ("INC-117", "15 10:50", "roman_ur", "citizen_sms", 0, None, "conflicting",
     "Madina Masjid wali sadak khuli hai, gaari guzar rahi hai."),

    # --- INC-118 Gulshan-e-Amin shelter: 2 reports ---
    ("INC-118", "15 10:35", "en", "citizen_sms", 1, None, "related",
     "30 people in Gulshan-e-Amin need shelter tonight, homes are flooded. 5 are children."),
    ("INC-118", "15 10:50", "ur", "field_volunteer", 0, None, "related",
     "گلشنِ امین میں تیس افراد کو رات کے لیے پناہ گاہ چاہیے۔ گھروں میں پانی بھر گیا ہے۔"),

    # --- INC-119 Grid station road: 2 reports ---
    ("INC-119", "15 11:05", "roman_ur", "citizen_sms", 1, None, "related",
     "Grid station road ke qareeb 25 log hain, sirf ek din ka khana bacha hai, 6 chhote bache hain."),
    ("INC-119", "15 11:20", "en", "citizen_sms", 0, None, "related",
     "About 25 people near the power grid station road need food and clean water by tomorrow. "
     "Six small children."),

    # --- INC-120 Chak 9 embankment: rumour + official correction ---
    ("INC-120", "15 11:30", "en", "social_media", 0, None, "rumor",
     "URGENT!!! Embankment at Chak 9 has BROKEN, whole area will drown in 1 hour. Forward to everyone!!!"),
    ("INC-120", "15 11:50", "en", "official_field_team", 1, None, "correction",
     "Field team inspected the Chak 9 embankment at 11:40. It is intact with minor seepage. "
     "No breach observed. Monitoring continues."),
]

# ---------------------------------------------------------------------------
# RESOURCES (10) - 7 available, 2 busy, 1 in maintenance. Exactly 2 boats free.
# ---------------------------------------------------------------------------
RESOURCE_FIELDS = (
    "resource_id", "name", "resource_type", "status", "base_name",
    "latitude", "longitude", "crew_size", "capacity_people", "skills",
)

RESOURCE_ROWS = [
    ("RT-A", "Rescue Team A", "rescue_team", "available", "Civil Defence Depot",
     31.5900, 74.3000, 8, 20, ["water_rescue", "evacuation", "first_aid"]),
    ("RT-B", "Rescue Team B", "rescue_team", "available", "Fire Station East",
     31.5950, 74.3250, 10, 20, ["water_rescue", "evacuation", "heavy_rescue"]),
    ("RT-C", "Rescue Team C", "rescue_team", "busy", "Fire Station West",
     31.5980, 74.2800, 8, 20, ["heavy_rescue", "evacuation"]),
    ("BOAT-1", "Rescue Boat 1", "rescue_boat", "available", "River Ghat Jetty",
     31.6040, 74.3020, 3, 12, ["water_rescue", "evacuation"]),
    ("BOAT-2", "Rescue Boat 2", "rescue_boat", "available", "Northern Boat Ramp",
     31.6120, 74.3120, 3, 10, ["water_rescue", "evacuation"]),
    ("BOAT-3", "Rescue Boat 3", "rescue_boat", "busy", "Kacha Basti Landing",
     31.6010, 74.2900, 3, 15, ["water_rescue", "evacuation"]),
    ("AMB-1", "Ambulance 1", "ambulance", "available", "City Hospital",
     31.5870, 74.3150, 2, 2, ["patient_transport", "first_aid"]),
    ("AMB-2", "Ambulance 2", "ambulance", "available", "Field Medical Camp",
     31.5960, 74.2950, 2, 2, ["patient_transport", "first_aid"]),
    ("AMB-3", "Ambulance 3", "ambulance", "maintenance", "Central Depot",
     31.5800, 74.3000, 2, 2, ["patient_transport", "first_aid"]),
    ("MED-1", "Medical Team 1", "medical_team", "available", "Field Medical Camp",
     31.5940, 74.3050, 5, 0, ["emergency_medicine", "obstetrics", "triage"]),
]

# ---------------------------------------------------------------------------
# SHELTERS (8)
# ---------------------------------------------------------------------------
SHELTER_FIELDS = (
    "shelter_id", "name", "latitude", "longitude", "capacity",
    "current_occupancy", "status", "road_accessible", "facilities",
)

SHELTER_ROWS = [
    ("SH-01", "Girls High School Shelter", 31.5880, 74.3120, 200, 120, "open", True,
     ["water", "food", "medical_corner", "women_section"]),
    ("SH-02", "Community Hall Block A", 31.6000, 74.3200, 80, 75, "open", True,
     ["water", "food"]),
    ("SH-03", "Municipal Stadium Hall", 31.5700, 74.3200, 500, 210, "open", True,
     ["water", "food", "medical_corner", "women_section"]),
    ("SH-04", "Masjid Community Centre", 31.5920, 74.2900, 120, 40, "open", True,
     ["water", "food", "women_section"]),
    ("SH-05", "College Auditorium", 31.5800, 74.2800, 150, 150, "full", True,
     ["water", "food", "medical_corner"]),
    ("SH-06", "Railway Colony School", 31.5990, 74.3380, 100, 55, "open", True,
     ["water", "food"]),
    ("SH-07", "Union Council Office", 31.6070, 74.3000, 60, 0, "closed", False,
     []),
    ("SH-08", "Sports Complex Shelter", 31.5640, 74.3000, 300, 30, "open", True,
     ["water", "food", "medical_corner", "women_section"]),
]

# ---------------------------------------------------------------------------
# HOSPITALS (5)
# ---------------------------------------------------------------------------
HOSPITAL_FIELDS = (
    "hospital_id", "name", "latitude", "longitude", "total_beds",
    "available_beds", "icu_beds_available", "services", "status",
)

HOSPITAL_ROWS = [
    ("HOSP-01", "City Hospital", 31.5860, 74.3160, 300, 40, 6,
     ["emergency", "trauma", "icu", "dialysis", "maternity"], "open"),
    ("HOSP-02", "Riverside General Hospital", 31.6090, 74.3040, 120, 8, 1,
     ["emergency", "maternity"], "open"),
    ("HOSP-03", "Model Town Medical Centre", 31.5710, 74.2950, 80, 25, 2,
     ["emergency", "trauma", "icu"], "open"),
    ("HOSP-04", "Railway Hospital", 31.5985, 74.3420, 150, 0, 0,
     ["emergency", "dialysis", "icu"], "full"),
    ("HOSP-05", "Women and Children Hospital", 31.5820, 74.3050, 100, 30, 3,
     ["emergency", "maternity", "pediatrics", "icu"], "open"),
]

# ---------------------------------------------------------------------------
# BLOCKED ROADS (4) - used by the map (Phase 4) and routing (Phase 12)
# ---------------------------------------------------------------------------
ROAD_FIELDS = (
    "road_id", "name", "start_latitude", "start_longitude",
    "end_latitude", "end_longitude", "reason", "status", "reported_at", "source_type",
)

ROAD_ROWS = [
    ("BR-01", "Daryab Bridge approach road", 31.6015, 74.3030, 31.6025, 74.3070,
     "flooded", "reported", "2026-08-15T07:05:00+05:00", "hotline_call"),
    ("BR-02", "Old Canal Road near petrol pump", 31.5750, 74.3000, 31.5752, 74.3040,
     "fallen_tree_and_water", "reported", "2026-08-15T09:30:00+05:00", "citizen_sms"),
    ("BR-03", "Madina Masjid to City Hospital road", 31.5915, 74.2820, 31.5890, 74.2990,
     "flooded", "confirmed", "2026-08-15T10:10:00+05:00", "official_field_team"),
    ("BR-04", "Sabzazar Road underpass", 31.5820, 74.3070, 31.5822, 74.3095,
     "flooded_underpass", "confirmed", "2026-08-15T09:25:00+05:00", "field_volunteer"),
]
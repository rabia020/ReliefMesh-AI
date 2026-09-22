"""The 50 citizen and field reports (SIMULATED).

Languages: "en" (English), "roman_ur" (Roman Urdu), "ur" (Urdu script).
batch="demo" reports are held back for the live demo injection (INC-001).
The truth_* fields are ground truth. build.py moves them to answer_key.json
so that agents never see them.
"""

from dataset.constants import REPORT_DATE, TZ_OFFSET


def _r(rid, time, lang, source, text, place, incident,
       image=None, structured=None, batch="baseline"):
    return {
        "id": rid,
        "timestamp": f"{REPORT_DATE}T{time}:00{TZ_OFFSET}",
        "language": lang,
        "source_type": source,
        "text": text,
        "image_id": image,
        "structured": structured,
        "batch": batch,
        "truth_place": place,
        "truth_incident": incident,
    }


REPORTS = [
    # ---- INC-001: Kabul River Bridge (DEMO BATCH: 7 reports) ----
    _r("R-001", "08:41", "en", "whatsapp",
       "Bridge flooded, water is rising fast near the river bridge. Cars cannot pass.",
       "L-BRIDGE", "INC-001", batch="demo"),
    _r("R-002", "08:44", "roman_ur", "sms",
       "Pul ke paas pani hai, log phanse hue hain. Jaldi madad bhejein.",
       "L-BRIDGE", "INC-001", batch="demo"),
    _r("R-003", "08:47", "ur", "hotline_call",
       "پل کے قریب سڑک بند ہو گئی ہے اور پانی گھروں میں داخل ہو رہا ہے۔",
       "L-BRIDGE", "INC-001", batch="demo"),
    _r("R-004", "08:52", "roman_ur", "whatsapp",
       "Pul ke paas 10 families phansi hui hain aur ek pregnant woman ko medical help chahiye.",
       "L-BRIDGE", "INC-001", image="IMG-01", batch="demo"),
    _r("R-005", "08:55", "en", "social_media",
       "People stuck near bridge on the east bank, some are on rooftops. Ambulance cannot reach them.",
       "L-BRIDGE", "INC-001", batch="demo"),
    _r("R-006", "09:05", "en", "field_officer",
       "FIELD FORM: Kabul River Bridge, east bank. 40 people stranded including 1 pregnant woman "
       "(about 8 months). Water 3 ft and rising. Boat and medical team required.",
       "L-BRIDGE", "INC-001", batch="demo",
       structured={"location_text": "Kabul River Bridge, east bank", "people_affected": 40,
                   "vulnerable_people": 1, "medical_emergency": True,
                   "needs": ["boat", "medical_team"], "water_depth_ft": 3}),
    _r("R-007", "09:10", "roman_ur", "whatsapp",
       "Bridge wali side pe sirf 15-20 log hain, baqi log nikal gaye hain.",
       "L-BRIDGE", "INC-001", batch="demo"),

    # ---- INC-002: Sadiq Abad rooftops (5 reports) ----
    _r("R-008", "06:20", "en", "whatsapp",
       "Sadiq Abad village is under 5 feet of water. About 60 people are on rooftops. "
       "We need boats urgently. Three small children have high fever.",
       "L-SADIQ", "INC-002"),
    _r("R-009", "06:35", "roman_ur", "sms",
       "Sadiq Abad mein ghar doob gaye hain, log chhaton pe baithe hain. Boat chahiye, bachay bimar hain.",
       "L-SADIQ", "INC-002"),
    _r("R-010", "06:48", "ur", "hotline_call",
       "صادق آباد گاؤں میں پانی چھتوں تک پہنچ گیا ہے۔ تقریباً ساٹھ لوگ پھنسے ہوئے ہیں، فوری کشتی بھیجیں۔",
       "L-SADIQ", "INC-002"),
    _r("R-011", "07:15", "en", "field_officer",
       "FIELD FORM: Sadiq Abad village. 60 people on rooftops, 3 children under 5 with fever. "
       "Water 5 ft. Link road cut. Boats required.",
       "L-SADIQ", "INC-002", image="IMG-02",
       structured={"location_text": "Sadiq Abad village", "people_affected": 60,
                   "vulnerable_people": 3, "medical_emergency": True,
                   "needs": ["boat", "medical_team"], "water_depth_ft": 5}),
    _r("R-012", "07:40", "roman_ur", "whatsapp",
       "Sadiq Abad ka link road bhi band hai, gaari nahi ja sakti. Sirf boat se pahunch sakte hain.",
       "L-SADIQ", "INC-002"),

    # ---- INC-003: Mian Gujjar Basti, dialysis patient (4 reports) ----
    _r("R-013", "07:05", "roman_ur", "whatsapp",
       "Mian Gujjar Basti mein pani ghar mein aa gaya hai. Ek buzurg ko dialysis ke liye hospital "
       "le jana hai, wo chal nahi sakte.",
       "L-GUJJAR", "INC-003"),
    _r("R-014", "07:12", "en", "sms",
       "Mian Gujjar Basti: around 25 people, water knee high, one elderly man needs dialysis today. "
       "No road access.",
       "L-GUJJAR", "INC-003"),
    _r("R-015", "07:30", "ur", "whatsapp",
       "میاں گجر بستی میں تقریباً پچیس لوگ ہیں، ایک بزرگ مریض کو ڈائیلیسس کی ضرورت ہے، پانی بڑھ رہا ہے۔",
       "L-GUJJAR", "INC-003"),
    _r("R-016", "08:00", "en", "field_officer",
       "FIELD FORM: Mian Gujjar Basti. 25 people, 3 vulnerable (2 elderly, 1 dialysis patient). "
       "Water 2 ft, no road access. Boat and ambulance required.",
       "L-GUJJAR", "INC-003",
       structured={"location_text": "Mian Gujjar Basti", "people_affected": 25,
                   "vulnerable_people": 3, "medical_emergency": True,
                   "needs": ["boat", "ambulance"], "water_depth_ft": 2}),

    # ---- INC-004: Old Bus Stand wall collapse (3 reports) ----
    _r("R-017", "07:50", "en", "hotline_call",
       "A boundary wall collapsed near the Old Bus Stand. At least 3 people are injured, one is bleeding badly.",
       "L-BUSSTAND", "INC-004"),
    _r("R-018", "07:53", "roman_ur", "sms",
       "Old bus stand ke paas deewar gir gayi hai, 3-4 log zakhmi hain, ambulance bhejein.",
       "L-BUSSTAND", "INC-004"),
    _r("R-019", "08:01", "ur", "whatsapp",
       "پرانے بس اڈے کے پاس دیوار گر گئی ہے، کچھ لوگ زخمی ہیں، ایمبولینس چاہیے۔",
       "L-BUSSTAND", "INC-004", image="IMG-03"),

    # ---- INC-005: Bus stranded in Tehsil Road underpass (3 reports) ----
    _r("R-020", "07:20", "en", "whatsapp",
       "A passenger bus is stuck in the Tehsil Road underpass, water is up to the windows. "
       "There are women and children inside.",
       "L-TEHSIL", "INC-005"),
    _r("R-021", "07:24", "roman_ur", "sms",
       "Tehsil road underpass mein bus phans gayi hai, andar 30 ke qareeb log hain, pani barh raha hai.",
       "L-TEHSIL", "INC-005"),
    _r("R-022", "07:31", "ur", "hotline_call",
       "تحصیل روڈ انڈر پاس میں بس پھنسی ہوئی ہے، عورتیں اور بچے بھی اندر ہیں، خدا کے لیے جلدی آئیں۔",
       "L-TEHSIL", "INC-005", image="IMG-04"),

    # ---- INC-006: Model Colony, bedridden grandmother (2 reports) ----
    _r("R-023", "06:50", "en", "whatsapp",
       "My grandmother is bedridden on the first floor in Model Colony, street 4. "
       "Water is 4 feet deep outside and we cannot carry her out.",
       "L-MODEL", "INC-006"),
    _r("R-024", "07:10", "ur", "sms",
       "ماڈل کالونی گلی نمبر 4 میں ایک بزرگ خاتون چل پھر نہیں سکتیں، پانی بہت زیادہ ہے، "
       "براہ کرم ریسکیو ٹیم بھیجیں۔",
       "L-MODEL", "INC-006"),

    # ---- INC-007: Gulshan Mohalla, families need shelter (3 reports) ----
    _r("R-025", "06:30", "roman_ur", "whatsapp",
       "Gulshan Mohalla mein taqreeban 15 gharanon ke ground floor mein pani aa gaya hai, "
       "raat kahan guzaren, shelter chahiye.",
       "L-GULSHAN", "INC-007"),
    _r("R-026", "06:55", "ur", "sms",
       "گلشن محلہ میں پندرہ خاندانوں کے گھروں میں پانی بھر گیا ہے، رہنے کی جگہ نہیں ہے۔",
       "L-GULSHAN", "INC-007"),
    _r("R-027", "07:45", "en", "volunteer_form",
       "VOLUNTEER FORM: Gulshan Mohalla. About 15 families (75 people), ground floors flooded, "
       "6 young children. Need shelter and food.",
       "L-GULSHAN", "INC-007",
       structured={"location_text": "Gulshan Mohalla", "people_affected": 75,
                   "vulnerable_people": 6, "medical_emergency": False,
                   "needs": ["shelter", "relief_supplies"], "water_depth_ft": 2}),

    # ---- INC-008: Canal Road embankment (3 reports, CONFLICT) ----
    _r("R-028", "07:00", "en", "social_media",
       "Canal Road embankment has BREACHED! Water is pouring into the colonies. Evacuate now!",
       "L-CANAL", "INC-008", image="IMG-05"),
    _r("R-029", "07:35", "roman_ur", "whatsapp",
       "Canal road ke bund mein daraar hai aur pani rees raha hai, abhi toota nahi. Log bohat dare hue hain.",
       "L-CANAL", "INC-008"),
    _r("R-030", "08:20", "en", "field_officer",
       "Inspected Canal Road embankment at km 2. Seepage and a 3 m crack observed, no breach. "
       "Sandbags requested. Site will be monitored.",
       "L-CANAL", "INC-008"),

    # ---- INC-009: Faisal Town, insulin (2 reports) ----
    _r("R-031", "08:10", "en", "whatsapp",
       "Faisal Town: my 9 year old son has type 1 diabetes and our insulin is finished. "
       "There is water around the house and we cannot reach a pharmacy.",
       "L-FAISAL", "INC-009"),
    _r("R-032", "08:15", "ur", "sms",
       "فیصل ٹاؤن میں ایک بچے کو انسولین کی ضرورت ہے، گھر کے اردگرد پانی ہے، کوئی طبی ٹیم بھیج دیں۔",
       "L-FAISAL", "INC-009"),

    # ---- INC-010: Sheikh Abad, live wire (2 reports) ----
    _r("R-033", "07:55", "roman_ur", "whatsapp",
       "Sheikh Abad mein bijli ka khamba paani mein gir gaya hai, current lag raha hai, "
       "bachay wahan se guzar rahe hain.",
       "L-SHEIKH", "INC-010"),
    _r("R-034", "08:05", "en", "hotline_call",
       "Live electric wire in floodwater on Sheikh Abad main street. Please cut the power supply, "
       "danger of electrocution.",
       "L-SHEIKH", "INC-010"),

    # ---- INC-011: Wapda Colony, no food or water (2 reports) ----
    _r("R-035", "08:25", "ur", "whatsapp",
       "واپڈا کالونی میں دو دن سے پینے کا صاف پانی اور کھانا نہیں ہے، تقریباً دو سو لوگ ہیں۔",
       "L-WAPDA", "INC-011"),
    _r("R-036", "08:30", "en", "sms",
       "Wapda Colony has had no drinking water or food since yesterday. "
       "Around 200 residents including many children.",
       "L-WAPDA", "INC-011"),

    # ---- INC-012: Bazaar Chowk shops (2 reports) ----
    _r("R-037", "06:15", "ur", "whatsapp",
       "بازار چوک میں دکانوں میں پانی بھر گیا ہے اور سڑک بھی بند ہے، بہت نقصان ہوا ہے۔",
       "L-BAZAAR", "INC-012"),
    _r("R-038", "06:40", "en", "social_media",
       "Shops at Bazaar Chowk are flooded and traffic is stuck. No injuries as far as I know.",
       "L-BAZAAR", "INC-012"),

    # ---- INC-013: Old Bus Stand road, blocked or open? (2 reports, CONFLICT) ----
    _r("R-039", "08:35", "en", "whatsapp",
       "Road from Old Bus Stand to Canal Road is blocked by fallen trees and debris.",
       "L-BUSSTAND", "INC-013", image="IMG-06"),
    _r("R-040", "09:00", "ur", "sms",
       "پرانے بس اڈے سے نہر روڈ والی سڑک کھلی ہے، صرف تھوڑا پانی ہے، گاڑیاں گزر رہی ہیں۔",
       "L-BUSSTAND", "INC-013"),

    # ---- INC-014: Farm Colony, missing child (2 reports) ----
    _r("R-041", "08:45", "en", "whatsapp",
       "Missing: 8 year old boy, blue shirt, last seen near the canal in Farm Colony around 8am.",
       "L-FARM", "INC-014"),
    _r("R-042", "08:50", "ur", "sms",
       "فارم کالونی میں آٹھ سال کا بچہ نہر کے پاس سے لاپتہ ہے، نیلی قمیض پہنی ہوئی ہے۔",
       "L-FARM", "INC-014"),

    # ---- INC-015: Chak Village, tents (2 reports) ----
    _r("R-043", "07:00", "roman_ur", "sms",
       "Chak village mein 8 families ke ghar gir gaye hain, khule aasman ke neeche hain, "
       "tent aur kambal chahiye.",
       "L-CHAK", "INC-015"),
    _r("R-044", "08:40", "en", "volunteer_form",
       "VOLUNTEER FORM: Chak Village. 8 families (40 people) with collapsed houses, 12 children. "
       "Need tents and blankets.",
       "L-CHAK", "INC-015",
       structured={"location_text": "Chak Village", "people_affected": 40,
                   "vulnerable_people": 12, "medical_emergency": False,
                   "needs": ["shelter", "relief_supplies"], "water_depth_ft": None}),

    # ---- INC-016 to INC-019: single-report incidents ----
    _r("R-045", "08:55", "en", "whatsapp",
       "Two cars stuck in floodwater near Jinnah Park, five of us are sitting on the roofs. "
       "Water is not too deep. Need help to get out.",
       "L-JINNAH", "INC-016"),
    _r("R-046", "09:15", "roman_ur", "hotline_call",
       "Girls High School ke shelter mein jagah kam pad gayi hai, kambal aur toilet ki kami hai, "
       "aur log bhi aa rahe hain.",
       "S-01", "INC-017"),
    _r("R-047", "08:50", "en", "field_officer",
       "Field check: Rural Health Center basement is flooded and stored medicines are at risk. "
       "Staff are safe. Clinic open for limited hours.",
       "H-05", "INC-018"),
    _r("R-048", "07:20", "ur", "whatsapp",
       "میاں گجر بستی میں ہماری بیس بھینسیں پانی میں پھنسی ہوئی ہیں، کوئی مدد کر دیں۔",
       "L-GUJJAR", "INC-019"),

    # ---- INC-020: dam-burst rumour (2 reports, FALSE ALARM) ----
    _r("R-049", "06:45", "en", "social_media",
       "BREAKING: Dam has burst upstream! Huge wave coming in 30 minutes. "
       "Run to high ground and share with everyone!!!",
       "L-BARRAGE", "INC-020"),
    _r("R-050", "07:10", "en", "field_officer",
       "Field check at upstream barrage: structure intact, discharge within limits. "
       "The dam burst message on social media is false.",
       "L-BARRAGE", "INC-020"),
]

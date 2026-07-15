# settings.py - Configuration constants. All tunables live here.

OUTPUT_FILE     = "earthquake_brief.html"
JS_FILE         = "dashboard_js.js"   # single source of truth for the client-side JS
REFRESH_MINUTES = 10

# HTTP behaviour
SSL             = True                 # TLS certificate verification (set False only behind broken corporate proxies)
HTTP_TIMEOUT    = 15                   # default per-request timeout, seconds
HTTP_RETRIES    = 2                    # automatic retries on connection errors / 5xx
USER_AGENT      = "EQDashboard/2.0 (reinsurance-research)"

# Event query
QUERY_DAYS      = 30                   # look-back window
QUERY_LIMIT     = 5                    # number of events shown
QUERY_MIN_MAG   = 5.5

ALERT_C = {
    "RED":    "#d32f2f",
    "ORANGE": "#e65100",
    "YELLOW": "#f9a825",
    "GREEN":  "#2e7d32",
    "N/A":    "#78909c",
    "":       "#78909c",
}

PAGER_D = {
    "RED":    "Extreme losses expected",
    "ORANGE": "Significant losses likely",
    "YELLOW": "Limited losses likely",
    "GREEN":  "Losses unlikely",
    "N/A":    "Assessment pending",
}

# value: (roman numeral, name, effect, colour)
MMI_SCALE = {
    1:  ("I",    "Not felt",    "Not felt",            "#bdc3c7"),
    2:  ("II",   "Weak",        "Barely felt",         "#9b59b6"),
    3:  ("III",  "Weak",        "Felt indoors",        "#3498db"),
    4:  ("IV",   "Light",       "Windows rattle",      "#1abc9c"),
    5:  ("V",    "Moderate",    "Felt widely",         "#2ecc71"),
    6:  ("VI",   "Strong",      "Felt by all",         "#f1c40f"),
    7:  ("VII",  "Very Strong", "Damage to weak",      "#e67e22"),
    8:  ("VIII", "Severe",      "Considerable damage", "#e74c3c"),
    9:  ("IX",   "Violent",     "Serious damage",      "#c0392b"),
    10: ("X",    "Extreme",     "Major damage",        "#922b21"),
}

MMI_C = [MMI_SCALE[i][3] for i in range(1, 11)]

BUILDING_STOCK = {
    "Venezuela":     {"dominant": "Non-ductile RC + URM",              "vulnerability": "High",         "code_era": "Limited enforcement; pre-1982 code"},
    "Philippines":   {"dominant": "Non-ductile RC + timber/bamboo",    "vulnerability": "High",         "code_era": "NSCP; patchy enforcement"},
    "Japan":         {"dominant": "Modern RC/steel + timber",          "vulnerability": "Low-Moderate", "code_era": "Post-1981 seismic standard"},
    "Turkey":        {"dominant": "Non-ductile RC + URM",              "vulnerability": "High",         "code_era": "Revised post-1999; variable enforcement"},
    "Indonesia":     {"dominant": "URM + bamboo/timber",               "vulnerability": "Very High",    "code_era": "SNI code; limited enforcement"},
    "Peru":          {"dominant": "Adobe + non-ductile RC",            "vulnerability": "Very High",    "code_era": "NTE 030; limited outside Lima"},
    "Chile":         {"dominant": "RC shear walls; confined masonry",  "vulnerability": "Moderate",     "code_era": "Strong codes since 1960"},
    "United States": {"dominant": "Wood frame; steel/RC commercial",   "vulnerability": "Low-Moderate", "code_era": "IBC/ASCE 7; good enforcement"},
    "Mexico":        {"dominant": "Non-ductile RC + URM",              "vulnerability": "High",         "code_era": "Post-1985 Mexico City code"},
    "China":         {"dominant": "Non-ductile RC + URM + adobe",      "vulnerability": "High",         "code_era": "GB 50011; variable enforcement"},
    "India":         {"dominant": "URM + non-ductile RC + adobe",      "vulnerability": "Very High",    "code_era": "IS 1893; limited enforcement"},
    "Iran":          {"dominant": "URM + non-ductile RC + adobe",      "vulnerability": "Very High",    "code_era": "IS 2800; poor enforcement"},
    "Nepal":         {"dominant": "Unreinforced brick masonry + adobe","vulnerability": "Very High",    "code_era": "NBC 105; minimal enforcement"},
    "Afghanistan":   {"dominant": "Adobe + rubble stone",              "vulnerability": "Very High",    "code_era": "No effective code enforcement"},
    "Greece":        {"dominant": "RC frame + URM infill",             "vulnerability": "Moderate",     "code_era": "EAK 2000 + Eurocode 8"},
    "Italy":         {"dominant": "RC frame + historic masonry",       "vulnerability": "Moderate",     "code_era": "NTC 2018 + Eurocode 8"},
    "Romania":       {"dominant": "Pre-1977 non-ductile RC dominant",  "vulnerability": "High",         "code_era": "P100-1/2013; large pre-code stock"},
    "New Zealand":   {"dominant": "Timber + steel + RC shear walls",   "vulnerability": "Low-Moderate", "code_era": "NZS 3101; good enforcement"},
    "Algeria":       {"dominant": "Non-ductile RC + URM",              "vulnerability": "High",         "code_era": "RPA 99/2003"},
    "Morocco":       {"dominant": "URM + non-ductile RC",              "vulnerability": "Very High",    "code_era": "RPS 2000; limited enforcement"},
    "Pakistan":      {"dominant": "URM + adobe + non-ductile RC",      "vulnerability": "Very High",    "code_era": "BCP 2007; minimal enforcement"},
    "Ecuador":       {"dominant": "Non-ductile RC + URM",              "vulnerability": "High",         "code_era": "NEC 2015"},
    "Colombia":      {"dominant": "RC frame + URM",                    "vulnerability": "High",         "code_era": "NSR-10"},
    "DEFAULT":       {"dominant": "Mixed formal and informal",         "vulnerability": "Unknown",      "code_era": "Uncertain"},
}

US_STATES = {
    "California","Alaska","Hawaii","Washington","Oregon","Nevada","Utah","Montana",
    "Idaho","Wyoming","Colorado","New Mexico","Arizona","Texas","Oklahoma","Kansas",
    "Nebraska","South Dakota","North Dakota","Minnesota","Iowa","Missouri","Arkansas",
    "Louisiana","Mississippi","Tennessee","Kentucky","Indiana","Ohio","Michigan",
    "Wisconsin","Illinois","Alabama","Georgia","Florida","South Carolina",
    "North Carolina","Virginia","West Virginia","Pennsylvania","New York","Vermont",
    "New Hampshire","Maine","Massachusetts","Rhode Island","Connecticut","New Jersey",
    "Delaware","Maryland","Puerto Rico","Guam",
}

REGION_WORDS = {"region","area","islands","ridge","rise","zone","trench","basin","sea","waters","ocean"}

NEWS_SOURCE_ORDER = [
    "GEM Foundation","EMSC","Wikipedia","Reuters","AP","BBC",
    "UN GDACS","USGS PAGER","PHIVOLCS","IGP Peru","USGS",
    "UN OCHA","UNICEF","IFRC","World Vision","Seismosoft","UN ReliefWeb","USGS NEIC",
]

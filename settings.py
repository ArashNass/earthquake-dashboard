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
QUERY_DAYS      = 90                   # look-back window
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

# USGS PAGER alert thresholds (estimated fatalities and economic losses; the higher alert is the overall level).
PAGER_THRESHOLDS = {
    "RED":    {"fatalities": "1,000 or more",  "losses": "US$1 billion or more"},
    "ORANGE": {"fatalities": "100 to 999",     "losses": "US$100 million to US$1 billion"},
    "YELLOW": {"fatalities": "1 to 99",        "losses": "US$1 million to US$100 million"},
    "GREEN":  {"fatalities": "none expected",  "losses": "under US$1 million"},
}

# Modified Mercalli Intensity as USGS ShakeMap defines it:
# value: (roman numeral, perceived shaking, potential damage, colour, reference PGA %g, reference PGV cm/s)
MMI_SCALE = {
    1:  ("I",    "Not felt",    "None",              "#bdc3c7", "< 0.05", "< 0.02"),
    2:  ("II",   "Weak",        "None",              "#9b59b6", "0.3",    "0.1 - 1.1"),
    3:  ("III",  "Weak",        "None",              "#3498db", "0.3",    "0.1 - 1.1"),
    4:  ("IV",   "Light",       "None",              "#1abc9c", "2.8",    "1.1 - 3.4"),
    5:  ("V",    "Moderate",    "Very light",        "#2ecc71", "6.2",    "3.4 - 8.1"),
    6:  ("VI",   "Strong",      "Light",             "#f1c40f", "12",     "8.1 - 16"),
    7:  ("VII",  "Very strong", "Moderate",          "#e67e22", "22",     "16 - 31"),
    8:  ("VIII", "Severe",      "Moderate to heavy", "#e74c3c", "40",     "31 - 60"),
    9:  ("IX",   "Violent",     "Heavy",             "#c0392b", "75",     "60 - 116"),
    10: ("X",    "Extreme",     "Very heavy",        "#922b21", "> 139",  "> 116"),
}

MMI_C = [MMI_SCALE[i][3] for i in range(1, 11)]

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

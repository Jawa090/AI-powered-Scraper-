"""US geography helpers for keyword planning.

Blue Book's native geography is primarily its numeric *region* system, with
city (`companylocatedin`) and county-service (`geoareaserviced`) facets on
search pages.  This module translates user-friendly states/cities/counties/
ZIPs into candidate Blue Book regions without pretending that a ZIP code is a
native Blue Book search parameter: ZIPs are mapped to an inferred state and
then to that state's regions, and the ZIP is retained in plan metadata.
"""
from __future__ import annotations

import re

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}
STATE_BY_NAME = {name.lower(): code for code, name in STATES.items()}
STATE_BY_NAME.update({"washington dc": "DC", "washington d.c.": "DC", "district columbia": "DC"})

# Blue Book region names observed on current search / category index pages.
REGIONS = {
    1: "New York - NYC, Long Island, Hudson Valley, Capital District",
    2: "Washington D.C., Maryland & Northern Virginia",
    3: "California - Los Angeles, Santa Barbara, Ventura",
    4: "Florida South - West Palm Beach, Miami, Naples",
    5: "Pennsylvania Eastern & Delaware",
    6: "Massachusetts East, Rhode Island & New Hampshire South",
    7: "California - Orange, Riverside, San Bernardino",
    8: "Illinois - Chicago & Indiana North/West",
    9: "California North - San Francisco, Oakland, San Jose",
    10: "New Jersey North - Newark, Jersey City",
    11: "Georgia North, Central & South",
    12: "Texas East - Dallas, Fort Worth",
    13: "Texas Gulf - Houston",
    14: "Ohio North - Cleveland",
    15: "Ohio South - Cincinnati, Columbus, Dayton & Northern Kentucky",
    16: "Florida North & Central - Tampa, Orlando, Jacksonville",
    17: "Connecticut & Massachusetts West",
    18: "Texas Central - San Antonio, Austin",
    19: "Michigan & Ohio - Toledo",
    20: "Virginia South & Central",
    21: "Arizona",
    22: "Washington West - Seattle, Tacoma, Olympia",
    23: "New Jersey South & Central",
    24: "Minnesota - Minneapolis/St. Paul & Wisconsin West",
    25: "Missouri - St. Louis",
    26: "Pennsylvania - Pittsburgh, Western Pa.",
    27: "Colorado & Wyoming",
    28: "Missouri - Kansas City & Kansas",
    29: "North Carolina & South Carolina Upstate",
    30: "Wisconsin - Milwaukee, Madison, Green Bay",
    31: "Indiana & Kentucky",
    32: "Louisiana",
    33: "California Central Valley - Sacramento, Fresno, Bakersfield",
    34: "Nevada",
    35: "Oregon - Portland & Washington - Vancouver",
    36: "California South - San Diego, Imperial",
    37: "Coastal Carolinas & Georgia - Savannah",
    38: "Tennessee - Nashville, Chattanooga, Knoxville",
    39: "Utah",
    40: "New York - Upstate",
    41: "Maine & Vermont",
    42: "Kentucky - Louisville",
    43: "Alabama",
    44: "Mississippi",
    45: "Arkansas & Tennessee - Memphis",
    46: "North Dakota & South Dakota",
    47: "Oklahoma",
    48: "Texas South",
    49: "Texas West - Odessa, Lubbock, Abilene",
    50: "New Mexico & Texas - El Paso",
    51: "Iowa & Nebraska - Omaha",
    52: "Montana",
    53: "Idaho & Washington Eastern",
    54: "West Virginia",
    55: "Alberta",
    71: "Nebraska",
}

STATE_REGIONS = {
    "AL": (43,), "AK": (), "AZ": (21,), "AR": (45,),
    "CA": (3, 7, 9, 33, 36), "CO": (27,), "CT": (17,), "DE": (5,),
    "FL": (16, 4), "GA": (11, 37), "HI": (), "ID": (53,),
    "IL": (8,), "IN": (31, 8), "IA": (51,), "KS": (28,),
    "KY": (31, 15, 42), "LA": (32,), "ME": (41,), "MD": (2,),
    "MA": (6, 17), "MI": (19,), "MN": (24,), "MS": (44,),
    "MO": (28, 25), "MT": (52,), "NE": (51, 71), "NV": (34,),
    "NH": (6,), "NJ": (10, 23), "NM": (50,), "NY": (1, 40),
    "NC": (29, 37), "ND": (46,), "OH": (14, 15, 19), "OK": (47,),
    "OR": (35,), "PA": (5, 26), "RI": (6,), "SC": (29, 37),
    "SD": (46,), "TN": (38, 45), "TX": (12, 13, 18, 48, 49, 50),
    "UT": (39,), "VT": (41,), "VA": (20, 2), "WA": (22, 53, 35),
    "WV": (54,), "WI": (30, 24), "WY": (27,), "DC": (2,),
}
US_REGION_IDS = tuple(sorted(set().union(*(set(v) for v in STATE_REGIONS.values()))))

# ZIP3 (first three digits) ranges are an inference aid only.  Border ZIPs can
# be exceptions; an explicit --state/--region always overrides this mapping.
_ZIP3_RANGES = [
    (5, 5, "NY"), (10, 27, "MA"), (28, 29, "RI"), (30, 38, "NH"),
    (39, 49, "ME"), (50, 59, "VT"), (60, 69, "CT"), (70, 89, "NJ"),
    (100, 149, "NY"), (150, 196, "PA"), (197, 199, "DE"), (200, 205, "DC"),
    (206, 219, "MD"), (220, 246, "VA"), (247, 268, "WV"), (270, 289, "NC"),
    (290, 299, "SC"), (300, 319, "GA"), (320, 349, "FL"), (350, 369, "AL"),
    (370, 385, "TN"), (386, 397, "MS"), (400, 427, "KY"), (430, 458, "OH"),
    (460, 479, "IN"), (480, 499, "MI"), (500, 528, "IA"), (530, 549, "WI"),
    (550, 567, "MN"), (570, 577, "SD"), (580, 588, "ND"), (590, 599, "MT"),
    (600, 629, "IL"), (630, 658, "MO"), (660, 679, "KS"), (680, 693, "NE"),
    (700, 714, "LA"), (716, 729, "AR"), (730, 749, "OK"), (750, 799, "TX"),
    (800, 816, "CO"), (820, 831, "WY"), (832, 838, "ID"), (840, 847, "UT"),
    (850, 865, "AZ"), (870, 884, "NM"), (889, 898, "NV"), (900, 961, "CA"),
    (967, 968, "HI"), (970, 979, "OR"), (980, 994, "WA"), (995, 999, "AK"),
]
_ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")


def parse_state(value: str) -> str:
    """Return a USPS state/DC code from a code or full state name, else ''."""
    raw = str(value or "").strip().strip(".")
    if not raw:
        return ""
    up = raw.upper()
    if up in STATES:
        return up
    return STATE_BY_NAME.get(" ".join(raw.lower().replace(".", "").split()), "")


def state_name(code: str) -> str:
    return STATES.get((code or "").upper(), "")


def regions_for_state(code: str) -> list[int]:
    return list(STATE_REGIONS.get((code or "").upper(), ()))


def infer_state_from_zip(zip_code: str) -> str:
    m = _ZIP_RE.search(str(zip_code or ""))
    if not m:
        return ""
    prefix = int(m.group(1)[:3])
    for lo, hi, state in _ZIP3_RANGES:
        if lo <= prefix <= hi:
            return state
    return ""


def clean_zip(value: str) -> str:
    m = _ZIP_RE.search(str(value or ""))
    return m.group(1) if m else ""


def _split_state_suffix(text: str, default_state: str = "") -> tuple[str, str, str]:
    """(place,state,zip) from 'Houston, TX 77002', 'Houston_TX', etc."""
    raw = str(text or "").strip()
    zip_code = clean_zip(raw)
    raw = _ZIP_RE.sub("", raw).strip(" ,")
    if "_" in raw:
        parts = [p.strip() for p in raw.rsplit("_", 1)]
        if len(parts) == 2:
            st = parse_state(parts[1])
            if st:
                return parts[0], st, zip_code
    if "," in raw:
        left, right = [p.strip() for p in raw.rsplit(",", 1)]
        st = parse_state(right)
        if st:
            return left, st, zip_code
    # Full state name / abbreviation as the final token(s).
    low = " ".join(raw.lower().replace(".", "").split())
    for name, code in sorted(STATE_BY_NAME.items(), key=lambda kv: -len(kv[0])):
        if low == name:
            return "", code, zip_code
        if low.endswith(" " + name):
            return raw[: len(raw) - len(name)].strip(" ,"), code, zip_code
    tokens = raw.split()
    if tokens:
        st = parse_state(tokens[-1])
        if st and len(tokens) > 1:
            return " ".join(tokens[:-1]), st, zip_code
        if st:
            return "", st, zip_code
    return raw, parse_state(default_state), zip_code


def parse_city(value: str, default_state: str = "") -> dict:
    city, state, zip_code = _split_state_suffix(value, default_state)
    city = " ".join(str(city or "").replace("_", " ").split()).title()
    # .title() harms names such as McKinney / De Soto less often than it helps
    # all-caps input; Blue Book's city facet is case-insensitive in practice.
    return {"city": city, "state": state, "zip": zip_code,
            "label": f"{city}, {state}" if city and state else city}


def parse_county(value: str, default_state: str = "") -> dict:
    raw = str(value or "").strip()
    m = re.search(r"\(([A-Za-z]{2})\)\s*$", raw)
    if m:
        state = parse_state(m.group(1))
        raw = raw[: m.start()].strip()
    else:
        raw, state, _zip = _split_state_suffix(raw, default_state)
    county = " ".join(str(raw or "").replace("_", " ").split()).title()
    if county and not re.search(r"\b(county|parish|borough|census area)$", county, re.I):
        county += " County"
    return {"county": county, "state": state,
            "label": f"{county}, {state}" if county and state else county,
            "facet": f"{county}({state})" if county and state else county}


def parse_location(value: str, default_state: str = "") -> dict:
    """Parse a free-form location into state/city/county/ZIP components."""
    raw = str(value or "").strip()
    if not raw:
        return {"state": "", "city": "", "county": "", "zip": "", "label": ""}
    if re.fullmatch(r"\d{5}(?:-\d{4})?", raw):
        return {"state": infer_state_from_zip(raw), "city": "", "county": "",
                "zip": clean_zip(raw), "label": raw}
    if re.search(r"\b(county|parish|borough)\b", raw, re.I):
        c = parse_county(raw, default_state)
        return {"state": c["state"], "city": "", "county": c["county"],
                "zip": clean_zip(raw), "label": c["label"]}
    city = parse_city(raw, default_state)
    if city["city"]:
        return {"state": city["state"], "city": city["city"], "county": "",
                "zip": city["zip"], "label": city["label"]}
    state = parse_state(raw)
    return {"state": state, "city": "", "county": "", "zip": clean_zip(raw),
            "label": state_name(state) or raw}

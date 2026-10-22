"""Keyword/trade resolution and Blue Book search planning.

The public Blue Book directory is organized primarily by numeric trade
``class`` + numeric ``region``.  This module turns reusable user input such as
"roofing contractors", "Denver, CO", "Harris County, TX" or a ZIP code into
an auditable plan of search URLs.  The built-in catalog is a curated starter
set verified against live Blue Book search/category URLs; it is not all 560+
Blue Book classifications.  Users can add mappings with a JSON/CSV catalog,
pass class codes directly, or let bounded dynamic expansion learn related
class links from result pages during ingestion.
"""
from __future__ import annotations

import csv
import difflib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlencode

from . import geo
from .urls import BASE, canonical

EXPANSIONS = ("off", "conservative", "balanced", "broad")


@dataclass(frozen=True)
class Trade:
    name: str
    class_code: str
    aliases: tuple[str, ...] = ()
    related: tuple[str, ...] = ()

    @property
    def code(self) -> str:
        return str(int(self.class_code)) if str(self.class_code).isdigit() else str(self.class_code)


def _t(name, code, aliases=(), related=()):
    return Trade(name, str(code), tuple(aliases), tuple(related))


# Popular/core trades first: this order is the tie-breaker for short keywords.
BUILTIN_TRADES = [
    _t("General Contractors", 2200, ("general contractor", "GC", "general contracting", "building contractors"),
       ("Building Alterations", "Construction Management", "Design Build--General Contractors", "Tenant Improvement")),
    _t("Electrical Contractors", 1680, ("electricians", "electrical contractor", "electrical construction"),
       ("Cabling Contractors--Fiber Optic, Network, Etc.", "Electrical Testing Service", "Access Control Systems")),
    _t("Plumbing Contractors", 3370, ("plumbers", "plumbing", "plumbing contractor"),
       ("Heating Contractors", "Sewer Contractors", "Mechanical Contractors")),
    _t("Roofing Contractors", 3580, ("roofers", "roofing", "roofing contractor", "commercial roofing"),
       ("Waterproofing Contractors", "Sheet Metal Contractors & Fabricators", "Siding Contractors")),
    _t("Demolition Contractors", 4850, ("demolition", "demo contractors", "wrecking contractors"),
       ("Excavating Contractors", "Site Development")),
    _t("Excavating Contractors", 1760, ("excavation", "excavating", "earthwork contractors"),
       ("Site Development", "Underground Utilities--Contractors", "Demolition Contractors")),
    _t("Building Alterations", 407, ("renovation", "remodeling", "building renovation", "alterations"),
       ("General Contractors", "Tenant Improvement", "Interiors-Offices, Stores, Etc.")),
    _t("Construction Management", 800, ("construction managers", "construction management companies"),
       ("General Contractors", "Design Build--General Contractors")),
    _t("Design Build--General Contractors", 4664, ("design build", "design-build", "design build contractors"),
       ("General Contractors", "Construction Management")),
    _t("Mechanical Contractors", 2844, ("mechanical contracting", "mechanical contractor"),
       ("Air Conditioning Contractors", "Heating Contractors", "Sheet Metal Contractors & Fabricators", "Plumbing Contractors")),
    _t("Air Conditioning Contractors", 60, ("air conditioning", "AC contractors", "cooling contractors"),
       ("Heating Contractors", "Mechanical Contractors")),
    _t("Heating Contractors", 2370, ("heating", "heating and air", "furnace contractors"),
       ("Air Conditioning Contractors", "Mechanical Contractors", "Plumbing Contractors")),
    _t("Paving Contractors", 3110, ("asphalt paving", "paving", "asphalt contractors", "pavement contractors"),
       ("Road Construction--Heavy & Highway", "Concrete Contractors--Sidewalks/Floors/Flatwork", "Site Development")),
    _t("Concrete Contractors--Sidewalks/Floors/Flatwork", 720, ("concrete flatwork", "flatwork contractors", "sidewalk contractors"),
       ("Concrete Contractors--Reinforced Concrete Structures", "Foundation Contractors--Concrete & Block", "Paving Contractors")),
    _t("Concrete Contractors--Reinforced Concrete Structures", 710, ("structural concrete", "reinforced concrete contractors"),
       ("Concrete Contractors--Tilt-Up Construction", "Foundation Contractors--Concrete & Block", "Concrete Contractors--Sidewalks/Floors/Flatwork")),
    _t("Concrete Contractors--Tilt-Up Construction", 725, ("tilt up construction", "tilt-up contractors"),
       ("Concrete Contractors--Reinforced Concrete Structures", "General Contractors")),
    _t("Concrete Repair & Restoration Contractors", 715, ("concrete repair", "concrete restoration"),
       ("Concrete Contractors--Sidewalks/Floors/Flatwork", "Waterproofing Contractors", "Mason Contractors")),
    _t("Foundation Contractors--Concrete & Block", 2130, ("foundation contractors", "foundations", "concrete foundations"),
       ("Concrete Contractors--Reinforced Concrete Structures", "Excavating Contractors", "Mason Contractors")),
    _t("Mason Contractors", 390, ("masonry", "masonry contractors", "brick contractors", "stone contractors"),
       ("Concrete Contractors--Sidewalks/Floors/Flatwork", "Stucco Contractors", "Stone Masons")),
    _t("Carpentry Contractors", 510, ("carpentry", "carpenters", "framing contractors"),
       ("Framing Systems--Light Gauge", "Drywall Contractors", "Millwork")),
    _t("Drywall Contractors", 1640, ("drywall", "sheetrock", "gypsum contractors"),
       ("Painting Contractors", "Carpentry Contractors", "Insulation Contractors--Cold & Heat")),
    _t("Painting Contractors", 2997, ("painters", "painting", "commercial painting"),
       ("Drywall Contractors", "Waterproofing Contractors")),
    _t("Resilient Floor Contractors", 1990, ("resilient flooring", "vinyl flooring contractors", "flooring installers"),
       ("Tile Contractors", "Concrete Polishing")),
    _t("Tile Contractors", 4390, ("tile", "ceramic tile contractors", "tile installers"),
       ("Resilient Floor Contractors", "Terrazzo Contractors")),
    _t("Landscape Construction", 2610, ("landscaping", "landscape contractors", "landscapers", "landscape construction"),
       ("Excavating Contractors", "Paving Contractors", "Fences")),
    _t("Structural Steel Fabricators & Contractors", 4200, ("structural steel", "steel fabricators", "steel contractors", "steel erectors"),
       ("Sheet Metal Contractors & Fabricators", "Architectural Metal")),
    _t("Sheet Metal Contractors & Fabricators", 3810, ("sheet metal", "sheet metal fabricators"),
       ("Mechanical Contractors", "Roofing Contractors", "Structural Steel Fabricators & Contractors")),
    _t("Waterproofing Contractors", 4660, ("waterproofing", "waterproofing contractor"),
       ("Roofing Contractors", "Caulking Contractors", "Concrete Repair & Restoration Contractors")),
    _t("Insulation Contractors--Cold & Heat", 2490, ("insulation", "insulation contractors", "spray foam contractors"),
       ("Drywall Contractors", "Mechanical Contractors")),
    _t("Fire Sprinkler Systems", 3990, ("fire sprinkler", "fire protection contractors", "fire suppression contractors"),
       ("Plumbing Contractors", "Mechanical Contractors")),
    _t("Site Development", 7931, ("site development", "sitework", "site work contractors", "land development contractors"),
       ("Excavating Contractors", "Underground Utilities--Contractors", "Paving Contractors", "Demolition Contractors")),
    _t("Underground Utilities--Contractors", 4500, ("underground utilities", "utility contractors", "underground utility contractors"),
       ("Sewer Contractors", "Excavating Contractors", "Pipeline Contractors")),
    _t("Sewer Contractors", 3790, ("sewer", "sewer construction", "sanitary sewer contractors"),
       ("Underground Utilities--Contractors", "Plumbing Contractors", "Excavating Contractors")),
    _t("Road Construction--Heavy & Highway", 3520, ("road construction", "highway contractors", "heavy civil contractors"),
       ("Paving Contractors", "Site Development", "General Engineering Contractors")),
    _t("Glass & Glazing Contractors", 2230, ("glass contractors", "glazing", "glaziers"),
       ("Storefronts", "Curtain Walls", "Metal Windows")),
    _t("Storefronts", 4170, ("storefront", "storefront contractors"), ("Glass & Glazing Contractors", "Architectural Metal", "Curtain Walls")),
    _t("Curtain Walls", 1360, ("curtain wall", "curtain walls contractors"), ("Glass & Glazing Contractors", "Storefronts", "Architectural Metal")),
    _t("Fences", 1830, ("fencing", "fence contractors", "fence companies"), ("Landscape Construction", "Site Development")),
    _t("Siding Contractors", 3885, ("siding", "siding contractor"), ("Roofing Contractors", "Building Alterations")),
    _t("Access Control Systems", 8, ("access control", "security access systems"), ("Electrical Contractors", "Cabling Contractors--Fiber Optic, Network, Etc.")),
    _t("Architects", 175, ("architect", "architectural firms"), ()),
    _t("Architectural Metal", 190, ("architectural metal contractors", "architectural metals"),
       ("Structural Steel Fabricators & Contractors", "Sheet Metal Contractors & Fabricators", "Storefronts")),
    _t("Building Maintenance Contractors", 430, ("building maintenance", "facilities maintenance"), ("General Contractors",)),
    _t("Cabling Contractors--Fiber Optic, Network, Etc.", 492, ("cabling", "fiber optic contractors", "network cabling", "low voltage contractors"),
       ("Electrical Contractors", "Access Control Systems")),
    _t("Caulking Contractors", 540, ("caulking", "sealant contractors"), ("Waterproofing Contractors", "Mason Contractors")),
    _t("Concrete Pumping Service", 784, ("concrete pumping", "concrete pump"), ("Ready Mixed Concrete",)),
    _t("Ready Mixed Concrete", 785, ("ready mix concrete", "ready mixed concrete suppliers"), ("Concrete Pumping Service",)),
    _t("Construction Estimating Services", 810, ("construction estimating", "estimators"), ("Construction Management",)),
    _t("Contractors Equipment - Rental, Sales & Service", 830, ("equipment rental", "construction equipment"), ()),
    _t("Underground Utility Location, GPR", 335, ("utility locating", "gpr", "ground penetrating radar"), ("Underground Utilities--Contractors",)),
    _t("Safety Nets & Fall Protection", 1200, ("fall protection", "safety nets"), ("Scaffolding",)),
    _t("Doors (Alum/Bronze/SS)", 1470, ("commercial doors", "door contractors"), ("Storefronts", "Architectural Metal")),
    _t("Drilling Contractors & Equipment", 1632, ("drilling contractors", "drilling"), ("Excavating Contractors", "Foundation Contractors--Concrete & Block")),
    _t("Framing Systems--Light Gauge", 2145, ("light gauge framing", "metal framing"), ("Carpentry Contractors", "Drywall Contractors")),
    _t("Interiors-Offices, Stores, Etc.", 2520, ("interior construction", "office interiors", "retail interiors"),
       ("Tenant Improvement", "Building Alterations", "General Contractors")),
    _t("Millwork", 2848, ("millwork", "cabinetry contractors"), ("Carpentry Contractors",)),
    _t("Pavers--Interlocking & Unit", 3104, ("paver contractors", "interlocking pavers"), ("Paving Contractors", "Landscape Construction")),
    _t("Pipeline Contractors", 3310, ("pipeline", "pipeline construction"), ("Underground Utilities--Contractors",)),
    _t("Sand & Gravel", 3650, ("sand and gravel", "aggregates"), ("Excavating Contractors",)),
    _t("Scaffolding", 3670, ("scaffold", "scaffolding contractors"), ("Safety Nets & Fall Protection",)),
    _t("Septic Tanks--Installation & Service", 3760, ("septic", "septic contractors"), ("Excavating Contractors", "Plumbing Contractors")),
    _t("Signs", 3890, ("sign contractors", "signage", "commercial signs"), ("Electrical Contractors",)),
    _t("Solar Systems-Sales, Cleaning & Maintenance", 3960, ("solar contractors", "solar installers", "solar"),
       ("Electrical Contractors", "Roofing Contractors")),
    _t("Stone Masons", 4128, ("stone masonry", "stone mason"), ("Mason Contractors",)),
    _t("Stucco Contractors", 4210, ("stucco", "stucco contractor"), ("Mason Contractors", "Siding Contractors")),
    _t("Tenant Improvement", 4336, ("tenant improvements", "TI contractors", "commercial build out", "build outs"),
       ("Building Alterations", "General Contractors", "Interiors-Offices, Stores, Etc.")),
    _t("Terrazzo Contractors", 4360, ("terrazzo", "terrazzo flooring"), ("Tile Contractors", "Concrete Polishing")),
    _t("Metal Windows", 4770, ("metal windows", "window contractors"), ("Glass & Glazing Contractors", "Storefronts")),
    _t("Concrete Polishing", 5425, ("polished concrete", "concrete polishing"), ("Resilient Floor Contractors", "Tile Contractors")),
    _t("Glass Manufacturers & Distributors", 5560, ("glass manufacturers", "glass distributors"), ("Glass & Glazing Contractors",)),
    _t("General Engineering Contractors", 8178, ("general engineering", "civil engineering contractors"),
       ("Road Construction--Heavy & Highway", "Site Development", "General Contractors")),
    _t("Electrical Testing Service", 8616, ("electrical testing",), ("Electrical Contractors",)),
]

KEYWORD_GROUPS = {
    "construction": (("General Contractors",), "representative"),
    "construction contractor": (("General Contractors",), "representative"),
    "construction company": (("General Contractors",), "representative"),
    "commercial construction": (("General Contractors",), "representative"),
    "builder": (("General Contractors",), "representative"),
    "contractor": (("General Contractors",), "representative"),
    "hvac": (("Air Conditioning Contractors", "Heating Contractors", "Mechanical Contractors"), "group"),
    "concrete": (("Concrete Contractors--Sidewalks/Floors/Flatwork", "Concrete Contractors--Reinforced Concrete Structures",
                  "Concrete Contractors--Tilt-Up Construction", "Concrete Repair & Restoration Contractors",
                  "Foundation Contractors--Concrete & Block"), "group"),
    "concrete contractor": (("Concrete Contractors--Sidewalks/Floors/Flatwork", "Concrete Contractors--Reinforced Concrete Structures",
                             "Concrete Contractors--Tilt-Up Construction", "Concrete Repair & Restoration Contractors",
                             "Foundation Contractors--Concrete & Block"), "group"),
    "flooring": (("Resilient Floor Contractors", "Tile Contractors", "Concrete Polishing"), "group"),
    "flooring contractor": (("Resilient Floor Contractors", "Tile Contractors", "Concrete Polishing"), "group"),
    "earthwork": (("Excavating Contractors", "Site Development", "Underground Utilities--Contractors"), "group"),
    "sitework": (("Site Development", "Excavating Contractors", "Underground Utilities--Contractors"), "group"),
    "utilities": (("Underground Utilities--Contractors", "Sewer Contractors", "Pipeline Contractors"), "group"),
    "renovation": (("Building Alterations", "Tenant Improvement", "Interiors-Offices, Stores, Etc."), "group"),
    "remodeling": (("Building Alterations", "Tenant Improvement", "Interiors-Offices, Stores, Etc."), "group"),
    "window and glass": (("Glass & Glazing Contractors", "Storefronts", "Curtain Walls", "Metal Windows"), "group"),
    "steel contractor": (("Structural Steel Fabricators & Contractors",), "representative"),
}


def normalize_keyword(value: str) -> str:
    s = str(value or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    tokens = []
    for tok in s.split():
        if tok == "contractors":
            tok = "contractor"
        elif tok == "companies":
            tok = "company"
        elif tok == "services":
            tok = "service"
        elif tok == "systems":
            tok = "system"
        elif tok == "fences":
            tok = "fence"
        elif tok.endswith("s") and len(tok) > 4 and tok not in {"glass", "business"}:
            tok = tok[:-1]
        tokens.append(tok)
    return " ".join(tokens).strip()


def _catalog_index(catalog: list[Trade]):
    by_name, by_code, keys = {}, {}, {}
    for i, trade in enumerate(catalog):
        by_name.setdefault(normalize_keyword(trade.name), trade)
        by_code.setdefault(trade.code, trade)
        keys.setdefault(normalize_keyword(trade.name), (trade, i))
        for alias in trade.aliases:
            keys.setdefault(normalize_keyword(alias), (trade, i))
    return by_name, by_code, keys


def load_custom_catalog(path: str | Path | None, base: list[Trade] | None = None) -> list[Trade]:
    catalog = list(base or BUILTIN_TRADES)
    if not path:
        return catalog
    p = Path(path)
    rows: list[dict] = []
    if p.suffix.lower() == ".csv":
        with p.open(newline="", encoding="utf-8-sig") as fh:
            rows = [{str(k).lower().strip(): v for k, v in r.items()} for r in csv.DictReader(fh)]
    else:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            for keyword, val in data.items():
                if isinstance(val, dict):
                    rows.append({"keyword": keyword, **{str(k).lower(): v for k, v in val.items()}})
                else:
                    rows.append({"keyword": keyword, "class_code": val})
        elif isinstance(data, list):
            rows = [{str(k).lower(): v for k, v in r.items()} for r in data if isinstance(r, dict)]
        else:
            raise ValueError("Custom catalog must be a JSON object/list or CSV")

    def split(v) -> tuple[str, ...]:
        if isinstance(v, (list, tuple)):
            return tuple(str(x).strip() for x in v if str(x).strip())
        return tuple(x.strip() for x in re.split(r"[;|]", str(v or "")) if x.strip())

    for row in rows:
        code = str(row.get("class_code") or row.get("class") or row.get("code") or "").strip()
        keyword = str(row.get("keyword") or "").strip()
        name = str(row.get("trade") or row.get("name") or keyword).strip()
        if not code or not name:
            continue
        aliases = split(row.get("aliases") or row.get("alias"))
        if keyword and normalize_keyword(keyword) != normalize_keyword(name):
            aliases = (keyword,) + aliases
        new_trade = Trade(name, str(int(code)) if code.isdigit() else code, aliases, split(row.get("related")))
        replaced = False
        for i, old in enumerate(catalog):
            if normalize_keyword(old.name) == normalize_keyword(new_trade.name) or old.code == new_trade.code:
                merged_aliases = tuple(dict.fromkeys(old.aliases + new_trade.aliases))
                merged_related = tuple(dict.fromkeys(old.related + new_trade.related))
                catalog[i] = Trade(new_trade.name, new_trade.class_code, merged_aliases, merged_related)
                replaced = True
                break
        if not replaced:
            catalog.append(new_trade)
    return catalog


@dataclass
class ResolvedTrade:
    trade: Trade
    relation: str = "primary"
    depth: int = 0
    confidence: float = 1.0


@dataclass
class KeywordResolution:
    keyword: str
    trades: list[ResolvedTrade] = field(default_factory=list)
    unresolved: bool = False
    suggestions: list[str] = field(default_factory=list)


def resolve_keyword(keyword: str, catalog: list[Trade] | None = None,
                    expansion: str = "balanced") -> KeywordResolution:
    catalog = catalog or BUILTIN_TRADES
    expansion = (expansion or "balanced").lower()
    if expansion not in EXPANSIONS:
        raise ValueError(f"expansion must be one of {EXPANSIONS}")
    by_name, _by_code, keys = _catalog_index(catalog)
    key = normalize_keyword(keyword)
    primary: list[ResolvedTrade] = []
    suggestions: list[str] = []

    if key in KEYWORD_GROUPS:
        names, mode = KEYWORD_GROUPS[key]
        for name in names:
            trade = by_name.get(normalize_keyword(name))
            if trade:
                primary.append(ResolvedTrade(trade, "group_primary" if mode == "group" else "primary"))
    elif key in keys:
        trade, _idx = keys[key]
        primary.append(ResolvedTrade(trade, "primary"))
    else:
        # Distinctive token-overlap match ("roofing", "commercial roofing",
        # "structural steel fabrication") with catalog order as tie-breaker.
        tokens = {t for t in key.split() if len(t) >= 4 and t not in {"commercial", "contractor", "company", "service"}}
        scored = []
        if tokens:
            for cand_key, (trade, idx) in keys.items():
                cand_tokens = set(cand_key.split())
                overlap = len(tokens & cand_tokens)
                if overlap:
                    scored.append((overlap, -idx, trade))
            scored.sort(reverse=True)
            if scored and scored[0][0] >= min(2, len(tokens)):
                primary.append(ResolvedTrade(scored[0][2], "token_match", confidence=0.82))
        if not primary:
            close = difflib.get_close_matches(key, list(keys), n=5, cutoff=0.78)
            suggestions = [keys[c][0].name for c in close]
            if close and difflib.SequenceMatcher(None, key, close[0]).ratio() >= 0.9:
                primary.append(ResolvedTrade(keys[close[0]][0], "fuzzy_match", confidence=0.75))

    if not primary:
        if not suggestions:
            suggestions = [t.name for t in catalog[:5]]
        return KeywordResolution(keyword, [], True, suggestions)

    resolved = list(primary)
    if expansion in ("balanced", "broad"):
        max_depth = 1 if expansion == "balanced" else 2
        limit = 4 if expansion == "balanced" else 10
        seen = {r.trade.code for r in resolved}
        frontier = [(r.trade, 1) for r in primary]
        added = 0
        while frontier and added < limit:
            trade, depth = frontier.pop(0)
            if depth > max_depth:
                continue
            for rel_name in trade.related:
                rel = by_name.get(normalize_keyword(rel_name))
                if not rel or rel.code in seen:
                    continue
                seen.add(rel.code)
                resolved.append(ResolvedTrade(rel, "related", depth, 0.9 if depth == 1 else 0.78))
                frontier.append((rel, depth + 1))
                added += 1
                if added >= limit:
                    break
    return KeywordResolution(keyword, resolved, False, suggestions)


def trade_by_code(code: str, catalog: list[Trade] | None = None, label: str = "") -> Trade:
    code = str(int(code)) if str(code).isdigit() else str(code)
    _n, by_code, _k = _catalog_index(catalog or BUILTIN_TRADES)
    return by_code.get(code) or Trade(label or f"Blue Book class {code}", code)


def parse_region(value: str) -> int | None:
    raw = str(value or "").strip()
    if raw.isdigit() and int(raw) in geo.REGIONS:
        return int(raw)
    key = normalize_keyword(raw)
    for rid, name in geo.REGIONS.items():
        if normalize_keyword(name) == key:
            return rid
    return None


@dataclass
class SearchSpec:
    url: str
    keyword: str
    trade: str = ""
    class_code: str = ""
    relation: str = "primary"
    depth: int = 0
    region: int | None = None
    region_name: str = ""
    state: str = ""
    city: str = ""
    county: str = ""
    zip: str = ""
    location_label: str = ""
    category: str = ""
    priority: int = 10
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchPlan:
    specs: list[SearchSpec] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    resolutions: list[KeywordResolution] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "searches": [s.to_dict() for s in self.specs],
            "warnings": self.warnings,
            "resolutions": [{
                "keyword": r.keyword, "unresolved": r.unresolved,
                "suggestions": r.suggestions,
                "trades": [{"name": x.trade.name, "class_code": x.trade.code,
                            "relation": x.relation, "depth": x.depth,
                            "confidence": x.confidence} for x in r.trades],
            } for r in self.resolutions],
            "count": len(self.specs),
        }


@dataclass
class _GeoTarget:
    kind: str
    region: int | None = None
    state: str = ""
    city: str = ""
    county: str = ""
    county_facet: str = ""
    zip: str = ""
    label: str = ""
    priority: int = 10


def _flatten(values) -> list[str]:
    out: list[str] = []
    for v in values or []:
        out.extend([x.strip() for x in str(v).split(",") if x.strip()])
    return out


def _candidate_regions(state: str, explicit: list[int], warnings: list[str]) -> list[int]:
    mapped = geo.regions_for_state(state) if state else []
    if explicit:
        overlap = [r for r in explicit if r in mapped]
        if state and mapped and not overlap:
            warnings.append(
                f"Explicit region(s) {explicit} do not overlap the mapped regions for {state} {mapped}; "
                "using the explicit regions as requested.")
            return explicit
        return overlap or explicit
    return mapped


def build_plan(keywords=(), *, states=(), regions=(), cities=(), counties=(), zips=(), locations=(),
               class_codes=(), trade_label: str = "", catalog: list[Trade] | None = None,
               expansion: str = "balanced", location_mode: str = "auto",
               filters: dict[str, list[str]] | None = None,
               nationwide: bool = False, include_name_search: bool = False,
               include_search_term: bool = True, search_path: str = "search",
               dynamic_expansion: bool | None = None, max_related: int | None = None,
               max_searches: int = 1000) -> SearchPlan:
    catalog = catalog or BUILTIN_TRADES
    expansion = (expansion or "balanced").lower()
    if expansion not in EXPANSIONS:
        raise ValueError(f"expansion must be one of {EXPANSIONS}")
    location_mode = (location_mode or "auto").lower()
    if location_mode not in ("auto", "located", "servicing", "both"):
        raise ValueError("location_mode must be auto, located, servicing, or both")
    filters = {k: list(v) for k, v in (filters or {}).items() if v}
    warnings: list[str] = []

    state_codes: list[str] = []
    for raw in _flatten(states):
        st = geo.parse_state(raw)
        if st and st not in state_codes:
            state_codes.append(st)
        elif not st:
            warnings.append(f"Unrecognized state ignored: {raw!r}")

    explicit_regions: list[int] = []
    for raw in _flatten(regions):
        rid = parse_region(raw)
        if rid and rid not in explicit_regions:
            explicit_regions.append(rid)
        elif not rid:
            warnings.append(f"Unrecognized Blue Book region ignored: {raw!r}")

    city_rows, county_rows, zip_codes = [], [], []
    default_state = state_codes[0] if len(state_codes) == 1 else ""
    for raw in cities or []:
        row = geo.parse_city(str(raw), default_state)
        if row["city"]:
            city_rows.append(row)
        else:
            warnings.append(f"Unrecognized city ignored: {raw!r}")
    for raw in counties or []:
        row = geo.parse_county(str(raw), default_state)
        if row["county"]:
            county_rows.append(row)
        else:
            warnings.append(f"Unrecognized county ignored: {raw!r}")
    for raw in _flatten(zips):
        z = geo.clean_zip(raw)
        if z and z not in zip_codes:
            zip_codes.append(z)
        elif not z:
            warnings.append(f"Invalid ZIP ignored: {raw!r}")
    for raw in locations or []:
        loc = geo.parse_location(str(raw), default_state)
        if loc["county"]:
            county_rows.append({"county": loc["county"], "state": loc["state"],
                                "label": loc["label"], "facet": f"{loc['county']}({loc['state']})" if loc["state"] else loc["county"]})
        elif loc["city"]:
            city_rows.append({"city": loc["city"], "state": loc["state"], "zip": loc["zip"], "label": loc["label"]})
        elif loc["zip"]:
            zip_codes.append(loc["zip"])
            if loc["state"] and loc["state"] not in state_codes:
                state_codes.append(loc["state"])
        elif loc["state"] and loc["state"] not in state_codes:
            state_codes.append(loc["state"])

    geo_targets: list[_GeoTarget] = []

    def add_base(region, state="", zip_code="", label="", priority=10):
        geo_targets.append(_GeoTarget("region", region, state, "", "", "", zip_code,
                                      label or geo.REGIONS.get(region, "Nationwide / unscoped"), priority))

    if nationwide:
        for rid in geo.US_REGION_IDS:
            add_base(rid, label=geo.REGIONS[rid], priority=40)
        warnings.append("Nationwide planning creates one search per mapped US Blue Book region per resolved trade.")
    else:
        targeted = bool(city_rows or county_rows)
        for row in city_rows:
            cand = _candidate_regions(row["state"], explicit_regions, warnings)
            if len(cand) > 1 and not explicit_regions:
                warnings.append(
                    f"City {row['label']} is planned across {len(cand)} candidate Blue Book regions for its state ({cand}); "
                    "Blue Book does not expose a general city->region lookup in these URLs, and the located-in facet makes non-matching regions self-filter.")
            if location_mode in ("auto", "located", "both"):
                if cand:
                    for rid in cand:
                        geo_targets.append(_GeoTarget("city", rid, row["state"], row["city"], "", "", row.get("zip", ""), row["label"], 5))
                else:
                    geo_targets.append(_GeoTarget("city", None, row["state"], row["city"], "", "", row.get("zip", ""), row["label"], 5))
            if location_mode in ("servicing", "both"):
                for rid in cand:
                    add_base(rid, row["state"], row.get("zip", ""), f"{geo.REGIONS[rid]} (servicing region for {row['label']})", 10)
        for row in county_rows:
            cand = _candidate_regions(row["state"], explicit_regions, warnings)
            if len(cand) > 1 and not explicit_regions:
                warnings.append(
                    f"County {row['label']} is planned across {len(cand)} candidate Blue Book regions for its state ({cand}); "
                    "the county-service facet makes non-matching regions self-filter. Add --region to narrow it.")
            if location_mode in ("auto", "located", "servicing", "both"):
                # County facets express area serviced; they are the county-targeted form.
                if cand:
                    for rid in cand:
                        geo_targets.append(_GeoTarget("county", rid, row["state"], "", row["county"], row["facet"], "", row["label"], 5))
                else:
                    geo_targets.append(_GeoTarget("county", None, row["state"], "", row["county"], row["facet"], "", row["label"], 5))
            if location_mode == "both":
                for rid in cand:
                    add_base(rid, row["state"], "", f"{geo.REGIONS[rid]} (region containing {row['label']})", 10)
        if not targeted or (state_codes and not city_rows and not county_rows):
            for st in state_codes:
                cand = _candidate_regions(st, explicit_regions, warnings)
                if cand:
                    for rid in cand:
                        add_base(rid, st, "", geo.REGIONS[rid], 10)
                else:
                    geo_targets.append(_GeoTarget("unscoped", None, st, "", "", "", "", geo.state_name(st), 30))
                    if st:
                        warnings.append(f"No mapped Blue Book region for {st}; using an unscoped class search and retaining the state in metadata.")
        if explicit_regions and not targeted and not state_codes:
            for rid in explicit_regions:
                add_base(rid, "", "", geo.REGIONS[rid], 10)
        if zip_codes and not city_rows and not county_rows and not state_codes and not explicit_regions:
            for z in zip_codes:
                st = geo.infer_state_from_zip(z)
                cand = geo.regions_for_state(st) if st else []
                if cand:
                    for rid in cand:
                        add_base(rid, st, z, f"{geo.REGIONS[rid]} (ZIP {z} inferred as {st})", 12)
                else:
                    geo_targets.append(_GeoTarget("unscoped", None, st, "", "", "", z, f"ZIP {z}", 30))
            warnings.append("Blue Book does not expose a verified native ZIP query parameter in the observed search URLs; "
                            "ZIPs are mapped to an inferred state's Blue Book regions and retained in metadata for reporting/filter review.")
        elif zip_codes:
            warnings.append("ZIP code(s) retained in plan metadata; Blue Book geography is driven by the city/county/state/region parameters above.")
        if not geo_targets:
            geo_targets.append(_GeoTarget("unscoped", None, "", "", "", "", "", "Nationwide / unscoped", 35))
            warnings.append("No location was supplied. Blue Book discovery is region-oriented; add --state/--city/--county/--region "
                            "or --nationwide for auditable coverage instead of relying on a class-only search.")

    resolutions: list[KeywordResolution] = []
    resolved_items: list[tuple[str, ResolvedTrade | None]] = []
    for keyword in keywords or []:
        resolution = resolve_keyword(str(keyword), catalog, expansion)
        resolutions.append(resolution)
        if resolution.unresolved:
            resolved_items.append((str(keyword), None))
            warnings.append(f"Keyword {keyword!r} is not in the built-in/custom catalog; planning a text searchTerm fallback. "
                            f"Closest catalog suggestions: {', '.join(resolution.suggestions[:5])}")
        else:
            resolved_items.extend((str(keyword), item) for item in resolution.trades)
    for code in class_codes or []:
        trade = trade_by_code(str(code), catalog, trade_label)
        resolved_items.append((trade_label or trade.name, ResolvedTrade(trade, "class_code", 0, 1.0)))

    if not resolved_items:
        warnings.append("No keywords or class codes were supplied; no searches planned.")
        return SearchPlan([], warnings, resolutions)

    if filters:
        warnings.append("Search facet filters narrow every planned search; omit them (or run a second unfiltered plan) when maximum discovery is more important than precision.")

    dyn = (expansion in ("balanced", "broad")) if dynamic_expansion is None else bool(dynamic_expansion)
    dyn_depth = 0 if not dyn else (2 if expansion == "broad" else 1)
    dyn_limit = max_related if max_related is not None else (15 if expansion == "broad" else 5)

    specs_by_url: dict[str, SearchSpec] = {}
    path_by_target = {"search": "/search.html", "search-build": "/search-build/search.html"}
    base_path = path_by_target.get(search_path, "/search.html")
    for keyword, item in resolved_items:
        trade = item.trade if item else None
        relation = item.relation if item else "text_search"
        depth = item.depth if item else 0
        for target in geo_targets:
            variants = [False, True] if include_name_search and trade else [False]
            for name_search in variants:
                params: list[tuple[str, str]] = []
                if target.region:
                    params.append(("region", str(target.region)))
                if trade:
                    params.append(("class", trade.code))
                if include_search_term:
                    params.append(("searchTerm", trade.name if trade else str(keyword)))
                path = base_path
                if target.kind == "city":
                    path = "/city-search.html"
                    city_val = target.city + (f"_{target.state}" if target.state else "")
                    params.append(("companylocatedin", city_val))
                elif target.kind == "county":
                    params.append(("geoareaserviced", target.county_facet))
                for fkey, vals in filters.items():
                    for val in vals:
                        params.append((fkey, str(val)))
                if name_search:
                    params.append(("nameSearch", "true"))
                url = canonical(f"{BASE}{path}?{urlencode(params)}")
                if not url:
                    continue
                relation_priority = {"primary": 0, "group_primary": 1, "class_code": 0,
                                     "token_match": 2, "fuzzy_match": 3}.get(relation, 15 + depth * 5 if relation == "related" else 25)
                priority = min(95, target.priority + relation_priority + (8 if name_search else 0))
                trade_name = trade.name if trade else ""
                class_code = trade.code if trade else ""
                category = f"{keyword} -> {trade_name}" if trade_name else f"Keyword text: {keyword}"
                if class_code:
                    category += f" ({class_code})"
                category += f" | {target.label}"
                metadata = {
                    "keywords": [str(keyword)], "keyword": str(keyword), "trade": trade_name,
                    "class_code": class_code, "relation": relation, "depth": depth,
                    "expansion": expansion, "dynamic_expansion": dyn,
                    "dynamic_max_depth": dyn_depth, "dynamic_max_related": dyn_limit,
                    "include_diversity_variants": expansion == "broad",
                    "location_kind": target.kind, "location_label": target.label,
                    "filters": filters,
                }
                spec = SearchSpec(url=url, keyword=str(keyword), trade=trade_name, class_code=class_code,
                                  relation=relation, depth=depth, region=target.region,
                                  region_name=geo.REGIONS.get(target.region, "") if target.region else "",
                                  state=target.state, city=target.city, county=target.county,
                                  zip=target.zip, location_label=target.label, category=category,
                                  priority=priority, metadata=metadata)
                old = specs_by_url.get(url)
                if old is None:
                    specs_by_url[url] = spec
                else:
                    kws = list(dict.fromkeys(old.metadata.get("keywords", []) + [str(keyword)]))
                    old.metadata["keywords"] = kws
                    old.keyword = "; ".join(kws)
                    if spec.priority < old.priority:
                        old.priority = spec.priority
                        old.category = spec.category
                        old.trade = old.trade or spec.trade
                        old.class_code = old.class_code or spec.class_code
                        old.metadata.update({k: v for k, v in spec.metadata.items() if k != "keywords"})
                        old.metadata["keywords"] = kws
    specs = sorted(specs_by_url.values(), key=lambda s: (s.priority, s.trade, s.location_label, s.url))
    if max_searches and len(specs) > max_searches:
        warnings.append(f"Plan contains {len(specs)} searches, above max_searches={max_searches}; queueing commands may refuse it until the limit is raised.")
    return SearchPlan(specs, warnings, resolutions)

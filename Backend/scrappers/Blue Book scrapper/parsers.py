"""Layered HTML extractors for Blue Book listing / profile / contacts pages.

Extraction order (highest trust first), every phone tagged with provenance:
  1. tel: links (number is in the href even when the label says "View Phone")
  2. schema.org JSON-LD whose business name/id matches this company
  3. microdata (itemprop telephone/address/name, Person scopes)
  4. semantic sections located by heading ("What We Do", "Key Contacts", ...)
     and by the stable ids both prior repos relied on
     (#companyInfoSection, #keyContactSection, #locationsPage-*, card class
     .single_result_wrapper with data-proview-url)
  5. explicitly labelled text ("Phone: ...") inside the cleaned main scope

Navigation, headers, footers, sponsor/ad/related blocks are removed before
any text-level extraction (Repo B's rule) so another company's number can
never be attributed to this one.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup, Tag

from . import phones as phonelib
from .geo import STATE_BY_NAME, STATES
from .names import normalize_person_name
from .urls import (canonical, company_id, domain_of, normalize_external_url,
                   profile_root_url, profile_url, query_params, same_search,
                   strip_tracking)

CERTS = ["MBE", "WBE", "DBE", "SBE", "VOSB", "SDVOSB", "WOSB", "EDWOSB", "DVBE", "8(a)", "HUBZone", "MWBE"]
CERT_PHRASES = {
    "minority business enterprise": "MBE",
    "women business enterprise": "WBE",
    "woman business enterprise": "WBE",
    "disadvantaged business enterprise": "DBE",
    "small business enterprise": "SBE",
    "minority women business enterprise": "MWBE",
    "minority woman business enterprise": "MWBE",
    "veteran owned small business": "VOSB",
    "service disabled veteran owned": "SDVOSB",
}
SOCIAL_DOMAINS = {
    "facebook.com", "fb.com", "fb.me", "linkedin.com", "instagram.com",
    "instagr.am", "youtube.com", "youtu.be", "twitter.com", "x.com",
}
CHALLENGE_PHRASES = [
    "verify you are human", "verify that you are human", "robot verification",
    "checking your browser", "performing security verification", "just a moment",
]
BLOCK_PHRASES = [
    "request blocked",
    "access denied",
    "access restricted",
    "unavailable from your location",
    "the content you are trying to access is unavailable",
]
_SKIP_CLASSES = re.compile(
    r"(^|[-_ ])(sponsor(?:ed|ship)?|advert|ad-|related|people[-_ ]also|also[-_ ]view|promo|regional[-_ ]sponsor)([-_ ]|$)",
    re.I)
_ADDR_RE = re.compile(r"^(.+?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$")
_CITY_STATE_RE = re.compile(r"([A-Z][A-Za-z.\- ]+),\s*([A-Z]{2})\b(?:\s+(\d{5}(?:-\d{4})?))?")
_EMAIL_RE = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+")
_HEADINGS = ["h1", "h2", "h3", "h4"]
_NAME_BLACKLIST = {
    "view phone", "view alt phone", "main location", "website", "contact us",
    "request a quote", "key contacts", "principal contacts", "company management",
    "management team", "company leadership", "leadership", "our team", "team members",
    "company contacts", "contacts", "contact information", "locations", "our story", "what we do",
    "business hours", "owners principals and senior executives",
    "owners, principals & senior executives", "operations", "sales", "estimating",
}
_CONTACT_SECTION_NAMES = (
    "Key Contacts", "Principal Contacts", "Company Management", "Management Team",
    "Company Leadership", "Leadership Team", "Leadership", "Our Team", "Team Members",
    "Meet Our Team", "Company Contacts", "Contacts", "Contact Information",
)
_DEPARTMENT_SECTION_NAMES = (
    "Owners, Principals & Senior Executives", "Owners and Principals", "Owners",
    "Principals", "Senior Executives", "Executives", "Estimating, Purchasing & Preconstruction",
    "Estimating", "Project Managers", "Project Management", "Operations", "Sales", "Accounting",
)
_PERSON_ROLE_LABELS = (
    "Owners, Principals & Senior Executives", "Principal Contact", "Principal Contacts",
    "Chief Executive Officer", "Chief Operating Officer", "Chief Financial Officer",
    "President", "Vice President", "Senior Vice President", "Executive Vice President",
    "Owner", "Owners", "Co-Owner", "Principal", "Principals", "Founder", "Co-Founder",
    "Partner", "Managing Partner", "Senior Partner", "Estimator", "Senior Estimator",
    "Chief Estimator", "Project Manager", "Senior Project Manager", "Operations Manager",
    "General Manager", "Manager", "Executive", "Director", "Contact Person", "Primary Contact",
    "Contact", "CEO", "COO", "CFO",
)


# --------------------------------------------------------------------------- utils
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _clean_text(s: str) -> str:
    return " ".join(str(s or "").split())


def _lines(el) -> list[str]:
    if el is None:
        return []
    raw = el.get_text("\n") if hasattr(el, "get_text") else str(el)
    seen, out = set(), []
    for line in raw.splitlines():
        t = _clean_text(line)
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def soup_from(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html or "", "lxml")
    except Exception:
        return BeautifulSoup(html or "", "html.parser")


def _clean_scope(soup: BeautifulSoup):
    """Main content with nav/header/footer/ads/sponsors removed."""
    for bad in list(soup.find_all(["script", "style", "noscript", "header", "footer", "nav", "aside"])):
        if getattr(bad, "attrs", None) is None:
            continue
        # Some profile layouts place Company Info/Key Contacts/Locations in a
        # sidebar; preserve an aside containing those stable section ids or contact links.
        if bad.name == "aside":
            if bad.find(id=re.compile(r"companyInfoSection|keyContactSection|locationsPage-", re.I)):
                continue
            if bad.find("a", href=re.compile(r"^tel:", re.I)):
                continue
            if any(
                any(d in (a.get("href") or "").lower() for d in ("facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com"))
                for a in bad.find_all("a", href=True)
            ):
                continue
        bad.decompose()
    for el in list(soup.find_all(True)):
        if getattr(el, "attrs", None) is None:  # already removed with an ancestor
            continue
        cls = " ".join(el.get("class") or []) + " " + (el.get("id") or "")
        if _SKIP_CLASSES.search(cls):
            el.decompose()
    return soup.find("main") or soup.body or soup


def detect_access(html_or_text: str, status: int = 200) -> str:
    """'' | 'challenge' | 'blocked' — challenge = a human may proceed."""
    text = BeautifulSoup(html_or_text or "", "html.parser").get_text(" ").lower() \
        if "<" in (html_or_text or "") else str(html_or_text or "").lower()
    if status == 403 or any(p in text for p in BLOCK_PHRASES):
        # A challenge page can also be served with 403; prefer 'challenge'
        # when the copy invites verification so the runner pauses for a human.
        if any(p in text for p in CHALLENGE_PHRASES):
            return "challenge"
        return "blocked"
    if any(p in text for p in CHALLENGE_PHRASES):
        return "challenge"
    return ""


# --------------------------------------------------------------------------- phones in DOM
def _tel_links(scope, source: str = "tel_link") -> list[dict]:
    """Phone/fax dicts from tel: anchors: {**normalize, 'is_fax', 'source'}."""
    out: dict[str, dict] = {}
    if scope is None:
        return []
    for a in scope.find_all("a", href=re.compile(r"^tel:", re.I)):
        n = phonelib.normalize(a.get("href", "")[4:]) or phonelib.normalize(a.get_text(" "))
        if not n:
            continue
        is_fax = phonelib.is_fax_context(a.get("title", ""), a.get("aria-label", ""), a.get_text(" "))
        key = n["e164"] + ("-fax" if is_fax else "") + n["ext"]
        out.setdefault(key, {**n, "is_fax": is_fax, "source": source})
    return list(out.values())


def _first_phone(items: list[dict], fax: bool = False) -> dict | None:
    for it in items:
        if it.get("is_fax") == fax:
            return it
    return None


def _phone_display(item: dict | None) -> str:
    return phonelib.display(item) if item else ""


def _valid_email(raw: str) -> str:
    email = str(raw or "").strip().strip("<>\"'").rstrip(".,;:)")
    m = _EMAIL_RE.fullmatch(email)
    if not m:
        return ""
    local, domain = email.rsplit("@", 1)
    domain = domain.lower()
    if domain in {"thebluebook.com", "example.com", "example.org", "example.net", "domain.com"}:
        return ""
    if domain.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
        return ""
    return f"{local}@{domain}"


def _extract_emails(scope, text: str = "") -> list[dict]:
    """Public emails from mailto links first, then scoped visible text."""
    out: dict[str, dict] = {}
    if scope is not None and hasattr(scope, "find_all"):
        for a in scope.find_all("a", href=re.compile(r"^mailto:", re.I)):
            raw = a.get("href", "")[7:].split("?", 1)[0]
            email = _valid_email(raw) or _valid_email(a.get_text(" "))
            if email:
                out.setdefault(email.lower(), {"email": email, "source": "mailto_link"})
    blob = text or (scope.get_text(" ") if scope is not None and hasattr(scope, "get_text") else "")
    for m in _EMAIL_RE.finditer(str(blob or "")):
        email = _valid_email(m.group(0))
        if email:
            out.setdefault(email.lower(), {"email": email, "source": "visible_text"})
    return list(out.values())


def _json_ld_businesses(html: str) -> list[dict]:
    found = []
    for raw in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                            html or "", re.S | re.I):
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue

        def walk(v):
            if isinstance(v, dict):
                if v.get("name") or v.get("telephone") or v.get("email") or v.get("address"):
                    found.append(v)
                for child in v.values():
                    walk(child)
            elif isinstance(v, list):
                for child in v:
                    walk(child)

        walk(data)
    return found


def _match_json_ld(html: str, expected_name: str, cid: str) -> dict | None:
    for biz in _json_ld_businesses(html):
        urls = " ".join(str(biz.get(k, "")) for k in ("url", "@id", "sameAs"))
        if (cid and cid in urls) or (expected_name and _norm(biz.get("name", "")) == _norm(expected_name)):
            return biz
    return None


def _state_code(value: str) -> str:
    raw = str(value or "").strip()
    return raw.upper() if raw.upper() in STATES else STATE_BY_NAME.get(raw.lower(), "")


def _address_from_node(node) -> dict:
    """Normalize a Schema.org PostalAddress-ish node."""
    if isinstance(node, str):
        parsed = _parse_address_lines([node])
        return parsed if parsed.get("address_raw") else {"address_raw": node}
    if not isinstance(node, dict):
        return {}
    street = str(node.get("streetAddress") or node.get("street") or "").strip()
    city = str(node.get("addressLocality") or node.get("city") or "").strip()
    state = _state_code(str(node.get("addressRegion") or node.get("state") or ""))
    zipc = str(node.get("postalCode") or node.get("zip") or "").strip()
    pieces = [p for p in [street, f"{city}, {state} {zipc}".strip()] if p.strip(", ")]
    out = {}
    if pieces:
        out["address_raw"] = " ".join(pieces)
    if street:
        out["street"] = street
    if city:
        out["city"] = city
    if state:
        out["state"] = state
    if zipc:
        out["zip"] = zipc
    if city and state:
        out["city_state"] = f"{city}, {state}"
    return out


def _node_addresses(nodes: list[dict]) -> list[dict]:
    out = []
    for node in nodes:
        addr = node.get("address") if isinstance(node, dict) else None
        if isinstance(addr, list):
            out.extend(_address_from_node(a) for a in addr)
        elif addr:
            out.append(_address_from_node(addr))
    return [a for a in out if a]


def _external_links(scope) -> tuple[str, list[str]]:
    """(company website, social urls) from anchors in scope."""
    website, socials = "", []
    if scope is None:
        return website, socials
    for a in scope.find_all("a", href=True):
        href = normalize_external_url(a["href"].strip())
        if not href:
            continue
        dom = domain_of(href)
        if not dom or "thebluebook.com" in dom:
            continue
        low_href = href.lower()
        if dom in SOCIAL_DOMAINS:
            if (href not in socials and "intent/" not in low_href and "sharer" not in low_href
                    and "share-offsite" not in low_href and "/share" not in low_href):
                socials.append(href)
            continue
        label = (_clean_text(a.get_text(" ")) + " " + (a.get("title") or "")).lower()
        cls_and_id = (" ".join(a.get("class") or []) + " " + (a.get("id") or "")).lower()
        if not website:
            if (
                "website" in label
                or "our website" in label
                or "web site" in label
                or "homepage" in label
                or "visit site" in label
                or "company site" in label
                or label.strip() == dom
                or dom in label
                or "website" in cls_and_id
            ):
                website = strip_tracking(href)
            elif a.find(["i", "svg", "img"]):
                icon_cls = " ".join([c for tag in a.find_all(["i", "svg", "img"]) for c in (tag.get("class") or [])]).lower()
                if any(k in icon_cls for k in ("globe", "website", "world", "link", "external")):
                    website = strip_tracking(href)
    return website, socials


def _heading(scope, *names: str):
    wanted = {_norm(n) for n in names}
    for h in scope.find_all(_HEADINGS):
        if _norm(h.get_text(" ")) in wanted:
            return h
    return None


def _section_container(scope, *names: str, ids: tuple[str, ...] = ()):
    for i in ids:
        el = scope.find(id=i)
        if el is not None:
            return el
    h = _heading(scope, *names)
    if h is None:
        return None
    # Smallest ancestor that holds the heading plus substantive siblings,
    # without swallowing the next major section.
    best = h
    for anc in h.parents:
        if not isinstance(anc, Tag) or anc is scope:
            break
        heads = [x for x in anc.find_all(_HEADINGS, recursive=False)]
        if len(anc.find_all(_HEADINGS)) > 6:
            break
        best = anc
        if anc.name in ("section", "article"):
            break
    return best


def _segment_lines(scope, *names: str, ids: tuple[str, ...] = ()) -> list[str]:
    box = _section_container(scope, *names, ids=ids)
    return _lines(box) if box is not None else []


def _block_for(marker: Tag, root, markers: list) -> Tag:
    """Highest ancestor of marker (within root) containing exactly one marker."""
    best = marker
    cur = marker
    while isinstance(cur.parent, Tag) and cur.parent is not root.parent:
        parent = cur.parent
        inside = [m for m in markers if parent in list(m.parents) or m is parent]
        if len(inside) == 1:
            best = parent
            cur = parent
        else:
            break
    return best


def _looks_like_person(text: str, company_name: str = "") -> bool:
    t = _clean_text(text)
    if not t or t.lower() in _NAME_BLACKLIST or _norm(t) == _norm(company_name):
        return False
    if len(t) > 60 or any(ch.isdigit() for ch in t) or ":" in t:
        return False
    # Scoped partial surname forms observed on Blue Book (e.g. "Donna .").
    if re.fullmatch(r"[A-Z][A-Za-z'’.-]+\s+(?:[A-Z]\.|\.)", t):
        return True
    words = t.replace(".", " ").split()
    if not (2 <= len(words) <= 5):
        return False
    title_words = {"owner", "president", "manager", "estimator", "sales", "operations",
                   "principal", "executive", "director", "coordinator", "representative",
                   "superintendent", "foreman", "engineer", "purchasing", "accounts"}
    if all(w.lower() in title_words or w.lower() in {"and", "&", "senior", "chief"} for w in words):
        return False
    if t.lower() in {"owners, principals & senior executives"} or t.lower().startswith("owners,"):
        return False
    # Mostly capitalized alphabetic tokens (initials/suffixes allowed).
    caps = sum(1 for w in words if w[:1].isupper())
    return caps >= max(2, len(words) - 1) and sum(c.isalpha() for c in t) >= 3


_TITLE_WORDS = {
    "owner", "president", "principal", "executive", "estimator", "manager", "director",
    "founder", "partner", "ceo", "coo", "cfo", "superintendent", "coordinator",
    "representative", "engineer", "supervisor", "foreman",
}
_DEPARTMENT_WORDS = {
    "estimating", "purchasing", "preconstruction", "operations", "sales", "accounting",
    "administration", "executives", "owners", "principals", "management", "leadership",
    "safety", "resources", "field", "project",
}


def _split_person_title(text: str, company_name: str = "") -> tuple[str, str]:
    """Split a card heading such as 'Jane Doe, President' when safe."""
    t = _clean_text(text)
    m = re.match(r"^(.+?)\s*(?:,|[-–—]|\|)\s*(.+)$", t)
    if m:
        name, title = _clean_text(m.group(1)), _clean_text(m.group(2))
        title_tokens = {w.strip(".,").lower() for w in title.split()}
        if _looks_like_person(name, company_name) and title_tokens & _TITLE_WORDS:
            return name, title
    return t, ""


def _is_department_heading(text: str) -> bool:
    t = _clean_text(text)
    low = t.lower()
    if low in _NAME_BLACKLIST or low in {x.lower() for x in _DEPARTMENT_SECTION_NAMES}:
        return True
    tokens = {w.strip(".,").lower() for w in t.replace("&", " ").split()}
    if tokens & {"estimating", "purchasing", "preconstruction", "operations", "sales",
                 "accounting", "administration", "executives", "owners", "principals"}:
        return True
    return low.endswith((" management", " leadership")) and not _looks_like_person(t)


def _merge_contact_candidates(contacts: list[dict]) -> list[dict]:
    """Merge parser candidates that are demonstrably the same listed person.

    Exact duplicates always merge.  Cross-section repeats merge when the
    normalized name matches and there is no conflicting direct phone/email, or
    when a phone/email identifier is shared.  Conflicting variants remain as
    evidence rows internally; the exact person-level export applies the final
    one-row-per-individual consolidation required for that deliverable.
    """
    out: list[dict] = []
    for raw in contacts:
        if not raw.get("name"):
            continue
        c = dict(raw)
        name_key = normalize_person_name(c["name"])
        match = None
        for old in out:
            if normalize_person_name(old.get("name", "")) != name_key:
                continue
            phone_same = bool(old.get("phone_e164") and c.get("phone_e164") and old["phone_e164"] == c["phone_e164"])
            email_same = bool(old.get("email") and c.get("email") and str(old["email"]).lower() == str(c["email"]).lower())
            phone_conflict = bool(old.get("phone_e164") and c.get("phone_e164") and old["phone_e164"] != c["phone_e164"])
            email_conflict = bool(old.get("email") and c.get("email") and str(old["email"]).lower() != str(c["email"]).lower())
            if phone_same or email_same or not (phone_conflict or email_conflict):
                match = old
                break
        if match is None:
            out.append(c)
            continue
        for f in ("title", "department", "phone", "phone_e164", "phone_source", "fax", "email"):
            if not str(match.get(f) or "").strip() and str(c.get(f) or "").strip():
                match[f] = c[f]
        for f in ("extra_phones", "extra_emails"):
            vals = list(match.get(f) or [])
            for v in c.get(f) or []:
                if v not in vals:
                    vals.append(v)
            match[f] = vals
        # If a shared identifier proved the match but the other channel
        # conflicts, retain it as an alternate rather than overwriting.
        if c.get("phone") and match.get("phone_e164") and c.get("phone_e164") != match["phone_e164"]:
            if c["phone"] not in match["extra_phones"]:
                match["extra_phones"].append(c["phone"])
        if c.get("email") and match.get("email") and str(c["email"]).lower() != str(match["email"]).lower():
            if c["email"] not in match["extra_emails"]:
                match["extra_emails"].append(c["email"])
    return out


def _department_for_role(label: str) -> str:
    low = label.lower()
    if "estimat" in low:
        return "Estimating"
    if "project" in low:
        return "Project Management"
    if any(x in low for x in ("owner", "principal", "president", "executive", "founder", "partner", "ceo", "coo", "cfo")):
        return "Owners, Principals & Senior Executives"
    if "operat" in low:
        return "Operations"
    return ""


def _contacts_from_labelled_lines(lines: list[str], company_name: str,
                                  default_department: str = "") -> list[dict]:
    labels = sorted(_PERSON_ROLE_LABELS, key=len, reverse=True)
    label_re = "|".join(re.escape(x) for x in labels)
    contacts: list[dict] = []

    def add_people(names_text: str, label: str, phone=None, email: str = ""):
        pieces = []
        for chunk in re.split(r"\s*;\s*", names_text or ""):
            pieces.extend(re.split(r"\s+(?:&|and)\s+", chunk))
        for piece in pieces:
            name, inline_title = _split_person_title(piece, company_name)
            name = re.sub(r"^(?:contact\s+)?", "", name, flags=re.I).strip()
            if not _looks_like_person(name, company_name):
                continue
            contacts.append({
                "name": name, "title": inline_title or label,
                "department": _department_for_role(label) or default_department,
                "phone": _phone_display(phone), "phone_e164": phone["e164"] if phone else "",
                "phone_source": phone.get("source", "labelled_text") if phone else "",
                "extra_phones": [], "fax": "", "email": email, "extra_emails": [],
            })

    for i, raw_line in enumerate(lines):
        line = _clean_text(raw_line)
        if not line or len(line) > 220:
            continue
        emails = _extract_emails(None, line)
        email = emails[0]["email"] if emails else ""
        phones = phonelib.find_in_text(line)
        phone = {**phones[0], "source": "labelled_text"} if phones else None
        clean_line = _EMAIL_RE.sub("", line)
        clean_line = re.sub(
            r"(?<!\d)(?:\+?1[\s.\-]?)?\(?[2-9]\d{2}\)?[\s.\-]?[2-9]\d{2}[\s.\-]?\d{4}(?!\d)"
            r"(?:\s*(?:ext\.?|x|extension)\s*\d{1,6})?", "", clean_line, flags=re.I)
        clean_line = re.sub(r"(?i)\b(view\s+)?(phone|tel|call)\b\s*[:.-]?\s*", "", clean_line).strip(" -–—,")
        m = re.match(rf"^({label_re})\s*[:\-–—]\s*(.+)$", clean_line, re.I)
        if m:
            add_people(m.group(2), m.group(1), phone, email)
            continue
        m = re.match(rf"^(.+?)\s*(?:,|[-–—]|\|)\s*({label_re})\b.*$", clean_line, re.I)
        if m:
            add_people(m.group(1), m.group(2), phone, email)
            continue
        # Adjacent "President" / "Jane Doe" label-value lines.
        if re.fullmatch(label_re, clean_line, re.I) and i + 1 < len(lines):
            nxt = _clean_text(lines[i + 1])
            if not phonelib.find_in_text(nxt) and not _EMAIL_RE.search(nxt):
                add_people(nxt, clean_line)
    return contacts


def _find_city_state(lines: list[str], text: str = "") -> str:
    """City, ST from a card/block without swallowing the company name."""
    for line in lines:
        m = re.fullmatch(r"([A-Z][A-Za-z.\- ]{1,40}?),\s*([A-Z]{2})", line)
        if m:
            return f"{m.group(1).strip()}, {m.group(2)}"
    m = re.search(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+){0,2}),\s*([A-Z]{2})\b", text or " ".join(lines))
    return f"{m.group(1)}, {m.group(2)}" if m else ""


def _is_probable_street(line: str) -> bool:
    s = str(line or "").strip().lower()
    if not s or len(s) < 3 or len(s) > 100:
        return False
    if s in {
        "website", "contact us", "contact", "view phone", "view alt phone",
        "view fax", "locations", "email", "request a quote", "get directions",
        "directions", "main location",
    }:
        return False
    if s.startswith("http://") or s.startswith("https://") or "@" in s or "www." in s:
        return False
    if phonelib.find_in_text(line):
        return False
    if re.search(r"^\d+", s) or re.search(r"\bp\.?o\.?\s*box\b", s):
        return True
    if re.search(r"\b(street|st|avenue|ave|road|rd|boulevard|blvd|highway|hwy|drive|dr|lane|ln|court|ct|place|pl|way|suite|ste|floor|fl|building|bldg)\b", s):
        return True
    return False


def _parse_address_lines(lines: list[str]) -> dict:
    """Find 'City, ST ZIP' line; street = lines between heading and it."""
    for i, line in enumerate(lines):
        m = _ADDR_RE.match(line)
        if m:
            candidate_streets = [l for l in lines[max(0, i - 2):i] if _is_probable_street(l)]
            street = ", ".join(candidate_streets)
            # Drop a repeated company-name first line from the street part.
            return {"street": street, "city": m.group(1).strip(), "state": m.group(2),
                    "zip": m.group(3), "address_raw": ", ".join(x for x in [street, line] if x)}
    for line in lines:  # fallback: embedded city/state/zip anywhere
        m = _CITY_STATE_RE.search(line)
        if m and m.group(3):
            return {"street": "", "city": m.group(1).strip(), "state": m.group(2),
                    "zip": m.group(3), "address_raw": line}
    return {"street": "", "city": "", "state": "", "zip": "", "address_raw": ""}


def _related_searches(soup, current_url: str) -> list[dict]:
    """Blue Book's own Related Searches / Did You Mean class links."""
    box = _section_container(soup, "Related Searches", "Did You Mean", "Did you mean one of these?")
    if box is None:
        return []
    out: dict[str, dict] = {}
    current = canonical(current_url)
    for a in box.find_all("a", href=True):
        u = canonical(a["href"])
        if not u or u == current:
            continue
        from .urls import kind_of
        if kind_of(u) != "listing":
            continue
        params = query_params(u)
        name = _clean_text(a.get_text(" ")) or (params.get("searchterm") or [""])[0]
        out[u] = {"name": name, "url": u, "class_code": (params.get("class") or [""])[0]}
    return list(out.values())


def is_not_found_page(html: str, final_url: str = "") -> bool:
    low = str(html or "").lower()
    return ("file not found" in low[:8000] or "proview does not exist" in low
            or "/main/invalidproview" in str(final_url).lower())


# --------------------------------------------------------------------------- listing pages
def parse_listing(html: str, url: str, category: str = "") -> dict:
    soup = soup_from(html)
    text = _clean_text(soup.get_text(" "))
    expected = None
    for pat in (r"([\d,]+)\s+Companies Found", r"([\d,]+)\s+Companies (?:are )?listed",
                r"Showing[^.]{0,40}of\s+([\d,]+)", r"([\d,]+)\s+results"):
        m = re.search(pat, text, re.I)
        if m:
            expected = int(m.group(1).replace(",", ""))
            break
    no_results = expected == 0 or bool(re.search(
        r"\b(no companies found|no results(?: found)?|0 companies found)\b", text, re.I))
    # Pagination/related links can live in nav/aside furniture: harvest first.
    pages: dict[int, str] = {}
    for a in soup.find_all("a", href=True):
        u = canonical(a["href"])
        if u and "page=" in u and same_search(url, u):
            from .urls import page_number
            pages.setdefault(page_number(u), u)
    mp = re.search(r"Page\s+\d+\s+of\s+([\d,]+)", text, re.I)
    max_page = int(mp.group(1).replace(",", "")) if mp else (max(pages) if pages else None)
    related = _related_searches(soup, url)
    scope = _clean_scope(soup)

    companies: dict[str, dict] = {}
    skipped = 0
    counters = {"rows": 0, "skipped": 0, "duplicate_rows": 0}

    def add(entry: dict):
        cid = entry.get("company_id", "")
        if not cid:
            counters["skipped"] += 1
            return
        counters["rows"] += 1
        old = companies.get(cid)
        if old is None:
            companies[cid] = entry
            return
        counters["duplicate_rows"] += 1
        # Blue Book can repeat one company for multiple associated locations.
        # Merge rather than discard the second card's branch data/phones.
        for f in ("website", "fax", "city_state", "city", "state", "zip", "street", "address_raw"):
            if not old.get(f) and entry.get(f):
                old[f] = entry[f]
        if entry.get("name") and (not old.get("name") or len(entry["name"]) > len(old["name"])):
            if old.get("name") and _norm(old["name"]) != _norm(entry["name"]):
                old.setdefault("name_aliases", []).append(old["name"])
            old["name"] = entry["name"]
        phones = {_phone_display({"pretty": p}) for p in old.get("extra_phones") or []}
        phones.update(entry.get("extra_phones") or [])
        if old.get("phone"):
            phones.add(old["phone"])
        if entry.get("phone"):
            phones.add(entry["phone"])
        if not old.get("phone") and entry.get("phone"):
            old["phone"] = entry["phone"]
            old["phone_e164"] = entry.get("phone_e164", "")
            old["phone_source"] = entry.get("phone_source", "")
        phones.discard(old.get("phone", ""))
        old["extra_phones"] = sorted(p for p in phones if p)
        emails = set(old.get("extra_emails") or []) | set(entry.get("extra_emails") or [])
        if old.get("email") and entry.get("email") and old["email"].lower() != entry["email"].lower():
            emails.add(entry["email"])
        if not old.get("email") and entry.get("email"):
            old["email"] = entry["email"]
            old["email_source"] = entry.get("email_source", "")
        old["extra_emails"] = sorted(emails)
        for f in ("listing_trades", "trades", "locations"):
            merged = list(old.get(f) or [])
            for v in entry.get(f) or []:
                if v not in merged:
                    merged.append(v)
            old[f] = merged
        best = profile_root_url(entry.get("pretty_url", ""))
        if best and len(best) > len(old.get("pretty_url", "")):
            old["pretty_url"] = best
            old["profile_url"] = best

    nonlocal_skipped = [0]
    def entry_from_block(block, raw_url: str = "") -> dict:
        anchors = block.find_all("a", href=re.compile(r"/iProView/\d+", re.I)) if hasattr(block, "find_all") else []
        if not raw_url and anchors:
            raw_url = anchors[0].get("href", "")
        pretty_any = canonical(raw_url)
        cid = company_id(pretty_any)
        root = profile_root_url(pretty_any) or pretty_any
        name = ""
        name_el = block.find(attrs={"itemprop": "name"}) if hasattr(block, "find") else None
        if name_el is not None:
            name = _clean_text(name_el.get("content") or name_el.get_text(" "))
        if not name:
            candidates = []
            for a in anchors:
                txt = _clean_text(a.get_text(" "))
                if txt and txt.lower() not in _NAME_BLACKLIST:
                    candidates.append(txt)
                img = a.find("img", alt=True)
                if img:
                    alt = _clean_text(img.get("alt") or "")
                    alt = re.sub(r"^logo for\s+", "", alt, flags=re.I)
                    if alt:
                        candidates.append(alt)
            heading = block.find(_HEADINGS) if hasattr(block, "find") else None
            if heading:
                candidates.insert(0, _clean_text(heading.get_text(" ")))
            name = max((c for c in candidates if c), key=len, default="")
        tels = _tel_links(block)
        phone_items = [t for t in tels if not t.get("is_fax")]
        phone = phone_items[0] if phone_items else None
        fax_item = _first_phone(tels, fax=True)
        website, _socials = _external_links(block)
        emails = _extract_emails(block)
        lines = _lines(block)
        addr_lines = [l for l in lines if _norm(l) != _norm(name)
                      and not l.lower().startswith(("view phone", "view alt phone", "view fax"))]
        address = _parse_address_lines(addr_lines)
        city_state = _find_city_state(lines, _clean_text(block.get_text(" ")))
        city, state, zipc = address.get("city", ""), address.get("state", ""), address.get("zip", "")
        if (not city or not state) and city_state:
            m = re.match(r"(.+),\s*([A-Z]{2})$", city_state)
            if m:
                city, state = city or m.group(1).strip(), state or m.group(2)
        if address.get("street") and _norm(address["street"]) == _norm(name):
            address["street"] = ""
            address["address_raw"] = ", ".join(x for x in [address.get("city", ""), address.get("state", ""), zipc] if x)
        trades = []
        for li in block.find_all("li") if hasattr(block, "find_all") else []:
            t = _clean_text(li.get_text(" "))
            if t and len(t) <= 80 and t not in trades:
                trades.append(t)
        locations = []
        if address.get("address_raw") or city or state or zipc:
            locations.append({
                "label": "Search result location", "address_raw": address.get("address_raw", ""),
                "street": address.get("street", ""), "city": city, "state": state, "zip": zipc,
                "phone": _phone_display(phone), "phone_e164": phone["e164"] if phone else "",
                "phone_source": phone["source"] if phone else "", "fax": _phone_display(fax_item),
                "website": website, "is_main": False,
            })
        return {
            "company_id": cid, "name": name,
            "profile_url": root or profile_url(cid), "pretty_url": root,
            "phone": _phone_display(phone), "phone_e164": phone["e164"] if phone else "",
            "phone_source": phone["source"] if phone else "",
            "extra_phones": [_phone_display(t) for t in phone_items[1:]],
            "fax": _phone_display(fax_item),
            "email": emails[0]["email"] if emails else "",
            "email_source": emails[0]["source"] if emails else "",
            "extra_emails": [e["email"] for e in emails[1:]],
            "website": website, "socials": _socials, "city_state": city_state, "city": city, "state": state, "zip": zipc,
            "street": address.get("street", ""), "address_raw": address.get("address_raw", ""),
            "category": category, "source_url": canonical(url),
            "listing_trades": trades[:15], "locations": locations,
        }

    cards = scope.find_all(class_="single_result_wrapper")
    for card in cards:
        add(entry_from_block(card, card.get("data-proview-url") or ""))

    if not companies:
        headings = [h for h in scope.find_all(_HEADINGS) if h.find("a", href=re.compile(r"/iProView/\d+", re.I))]
        for heading in headings:
            add(entry_from_block(_block_for(heading, scope, headings)))
    if not companies:  # last-resort: profile anchors only
        for a in scope.find_all("a", href=re.compile(r"/iProView/\d+", re.I)):
            pretty = canonical(a["href"])
            cid = company_id(pretty)
            name = _clean_text(a.get_text(" "))
            if cid and name and name.lower() not in _NAME_BLACKLIST:
                root = profile_root_url(pretty) or pretty
                add({"company_id": cid, "name": name, "profile_url": root,
                     "pretty_url": root, "phone": "", "phone_e164": "", "phone_source": "",
                     "website": "", "city_state": "", "category": category,
                     "source_url": canonical(url), "listing_trades": [], "locations": []})

    rows = list(companies.values())
    result_rows = counters["rows"]
    return {"companies": rows, "pagination": [pages[k] for k in sorted(pages)],
            "expected_count": expected,
            # per_page is raw listing rows, not unique companies: Blue Book's
            # expected count and page size count repeated associated-location
            # cards even when they resolve to the same company_id.
            "per_page": result_rows, "result_rows": result_rows,
            "duplicate_rows": counters["duplicate_rows"], "max_page": max_page,
            "related_searches": related, "no_results": no_results,
            "skipped_no_id": counters["skipped"] + nonlocal_skipped[0] + skipped}


# --------------------------------------------------------------------------- profile root
def parse_profile(html: str, url: str, expected_name: str = "") -> dict:
    cid = company_id(url)
    soup = soup_from(html)
    ld = _match_json_ld(html, expected_name, cid)
    scope = _clean_scope(soup)
    full_text = _clean_text(scope.get_text(" "))

    # Name: og:title / <title> "Name - City, ST | ProView" / first heading / JSON-LD
    name = ""
    name_from_page = False
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        name = _clean_text(og["content"].split("|")[0].rsplit("-", 1)[0])
        name_from_page = bool(name)
    if not name and soup.title:
        name = _clean_text(soup.title.get_text(" ").split("|")[0].rsplit("-", 1)[0])
        name_from_page = bool(name)
    if ld and ld.get("name"):
        name = _clean_text(str(ld["name"])) or name
        name_from_page = bool(name)
    if not name:
        h = scope.find(_HEADINGS)
        name = _clean_text(h.get_text(" ")) if h else ""
        name_from_page = bool(name)
        name = name or expected_name
    if ld is None and name:
        # Title/heading identity can safely select the company's JSON-LD node
        # when the structured URL is the company's own website, not ProView.
        ld = _match_json_ld(html, name, cid)

    # Title city/state ("Name - Freeport, New York | ProView") and any
    # Schema.org address exposed in JSON-LD.
    title_raw = ""
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        title_raw = str(og["content"])
    elif soup.title:
        title_raw = soup.title.get_text(" ")
    title_city = title_state = ""
    tm = re.search(r"-\s*([^,-]+),\s*([A-Za-z .]+)\s*(?:\||$)", title_raw)
    if tm:
        title_state = _state_code(tm.group(2))
        if title_state:
            title_city = _clean_text(tm.group(1))
    ld_addresses = _node_addresses([ld]) if ld else []
    address = ld_addresses[0] if ld_addresses else {}

    website, socials = _external_links(scope)
    if ld:
        for cand in ([ld.get("url", "")] + list(ld.get("sameAs") or [])):
            dom = domain_of(str(cand))
            if dom in SOCIAL_DOMAINS and str(cand) not in socials:
                socials.append(str(cand))
            elif dom and "thebluebook.com" not in dom and not website:
                website = strip_tracking(str(cand))

    # Trades: classification links + "What We Do" list + story sentence.
    trades: list[str] = []
    trade_codes: list[str] = []
    for a in scope.find_all("a", href=True):
        u = canonical(a.get("href", ""))
        if not u:
            continue
        params = query_params(u)
        code = (params.get("class") or [""])[0]
        label = _clean_text(a.get_text(" "))
        if code and label and len(label) <= 90:
            if label not in trades:
                trades.append(label)
            if code not in trade_codes:
                trade_codes.append(code)
    services: list[str] = []
    for line in _segment_lines(scope, "What We Do"):
        if line.lower() != "what we do" and len(line) <= 90:
            if line not in services:
                services.append(line)
            if line not in trades:
                trades.append(line)
    m = re.search(r"main lines of business include:\s*(.+?)\.\s", full_text, re.I)
    if m:
        for t in m.group(1).split(","):
            t = _clean_text(t)
            if t and t not in trades:
                trades.append(t)

    # Service areas. Blue Book groups county links under state headings; keep
    # that state context instead of emitting ambiguous bare county names.
    areas: list[str] = []
    current_state = ""
    for raw_line in _segment_lines(scope, "Regions & Counties Serviced", "Regions and Counties Serviced",
                                   "Service Area", "Areas Serviced"):
        low = raw_line.lower()
        if low.startswith("regions") or low in {"service area", "areas serviced"}:
            continue
        line = re.sub(r"\s*\(\d+\)\s*$", "", raw_line).strip()
        line = re.sub(r"(?<=[A-Za-z])\d+$", "", line).strip()  # 'Missouri1' artefacts
        st = _state_code(line)
        if st and _norm(line) == _norm(STATES[st]):
            current_state = st
            value = STATES[st]
        elif re.search(r"\b(county|parish|borough)\b", line, re.I) and current_state \
                and STATES[current_state].lower() not in line.lower():
            value = f"{line}, {STATES[current_state]}"
        else:
            value = line
        if value and len(value) <= 80 and value not in areas:
            areas.append(value)

    # CSI codes
    csi_text = " \n".join(_segment_lines(scope, "Our CSI Codes", "CSI Codes"))
    csi = []
    for cm in re.finditer(r"\b\d{2} \d{2} \d{2}(?:\.\d{2})*(?: - [A-Za-z][^\n]{0,80})?", csi_text):
        code = _clean_text(cm.group(0))
        if code not in csi:
            csi.append(code)
        if len(csi) >= 500:
            break

    story_lines = [l for l in _segment_lines(scope, "Our Story") if l.lower() != "our story"]
    story = " ".join(story_lines)[:4000]
    listed = ""
    m = re.search(r"listed in the Blue Book since (\d{4})", full_text, re.I)
    if m:
        listed = m.group(1)

    # Company-info label:value list (#companyInfoSection in both prior repos)
    info: dict[str, str] = {}
    info_box = _section_container(scope, "Company Info", ids=("companyInfoSection",))
    if info_box is not None:
        lines = _lines(info_box)
        known = {_norm(x) for x in (
            "Established", "Year Established", "Founded", "Company Size", "Employees",
            "Number of Employees", "Size", "Annual Volume", "Annual Revenue", "Volume",
            "Revenue", "Email", "Website", "Phone", "Address")}
        for i, line in enumerate(lines):
            if ":" in line:
                k, v = line.split(":", 1)
                if v.strip():
                    info[_norm(k)] = v.strip()
                    continue
                # Label and value may be adjacent lines rather than "Label: Value".
                if i + 1 < len(lines):
                    info[_norm(k)] = lines[i + 1]
            elif _norm(line) in known and i + 1 < len(lines):
                info[_norm(line)] = lines[i + 1]
        for row in info_box.find_all("tr"):
            cells = [_clean_text(c.get_text(" ")) for c in row.find_all(["th", "td"])]
            if len(cells) >= 2 and cells[0] and cells[1]:
                info[_norm(cells[0].rstrip(":"))] = cells[1]

    def info_get(*keys: str) -> str:
        for k in keys:
            if _norm(k) in info:
                return info[_norm(k)]
        return ""

    # Company-level phone candidates on the root page (locations page wins on merge)
    tels = _tel_links(scope)
    phone_items = [t for t in tels if not t.get("is_fax")]
    phone = phone_items[0] if phone_items else None
    fax_item = _first_phone(tels, fax=True)
    phone_source = phone["source"] if phone else ""
    if ld and ld.get("telephone"):
        vals = ld["telephone"] if isinstance(ld["telephone"], list) else [ld["telephone"]]
        for val in vals:
            n = phonelib.normalize(str(val))
            if n and all(n["e164"] != t.get("e164") for t in phone_items):
                phone_items.append({**n, "is_fax": False, "source": "json_ld"})
        if not phone and phone_items:
            phone, phone_source = phone_items[0], "json_ld"
    if not phone:
        micro = scope.find(attrs={"itemprop": "telephone"})
        if micro is not None:
            n = phonelib.normalize(micro.get("content") or micro.get_text(" "))
            if n:
                phone, phone_source = {**n, "is_fax": False}, "microdata"
                phone_items.insert(0, phone)

    emails: list[dict] = []
    if ld and ld.get("email"):
        for val in (ld["email"] if isinstance(ld["email"], list) else [ld["email"]]):
            e = _valid_email(str(val).replace("mailto:", "", 1))
            if e:
                emails.append({"email": e, "source": "json_ld"})
    seen_emails = {e["email"].lower() for e in emails}
    for e in _extract_emails(scope, full_text):
        if e["email"].lower() not in seen_emails:
            emails.append(e)
            seen_emails.add(e["email"].lower())
    if info_get("Email"):
        e = _valid_email(info_get("Email"))
        if e and e.lower() not in seen_emails:
            emails.insert(0, {"email": e, "source": "company_info"})

    certs = [c for c in CERTS if re.search(r"(?<![A-Za-z])" + re.escape(c) + r"(?![A-Za-z])", full_text)]
    if "M/WBE" in full_text.upper() and "MWBE" not in certs:
        certs.append("MWBE")
    low_text = full_text.lower()
    for phrase, code in CERT_PHRASES.items():
        if phrase in low_text and code not in certs:
            certs.append(code)

    # Sub-page discovery (same company only). Profile tabs may live in a
    # <nav>, which cleaning removes — search the uncleaned document.
    contacts_u, projects_u = "", ""
    for a in soup.find_all("a", href=True):
        u = canonical(a["href"])
        if not u or (cid and company_id(u) not in ("", cid)):
            continue
        if "/locations-contacts" in u:
            contacts_u = contacts_u or u
        if "/completed-projects" in u:
            projects_u = projects_u or u

    # Pretty/canonical profile URL (redirect target or <link rel=canonical>)
    pretty = profile_root_url(url) or canonical(url)
    link = soup.find("link", rel="canonical")
    if link and link.get("href"):
        c = profile_root_url(link["href"])
        if c and company_id(c) in ("", cid) and len(c) >= len(pretty):
            pretty = c

    # Profile roots and tab variants may embed management/key-contact/team
    # sections or role-labelled people in Company Info.  Extract them here as
    # well as on the dedicated locations-contacts page; store/export dedupe
    # handles the same person appearing in both places.
    contacts = _extract_contacts(scope, name)

    extra_phones = []
    for item in phone_items:
        disp = _phone_display(item)
        if disp and disp != _phone_display(phone) and disp not in extra_phones:
            extra_phones.append(disp)
    return {
        "company_id": cid, "name": name, "name_from_page": name_from_page,
        "pretty_url": pretty, "profile_url": pretty,
        "website": website, "socials": socials,
        "phone": _phone_display(phone), "phone_e164": phone["e164"] if phone else "",
        "phone_source": phone_source, "extra_phones": extra_phones,
        "fax": _phone_display(fax_item),
        "email": emails[0]["email"] if emails else "",
        "email_source": emails[0]["source"] if emails else "",
        "extra_emails": [e["email"] for e in emails[1:]],
        "address_raw": address.get("address_raw", ""), "street": address.get("street", ""),
        "city": address.get("city", "") or title_city, "state": address.get("state", "") or title_state,
        "zip": address.get("zip", ""),
        "city_state": address.get("city_state", "") or (f"{title_city}, {title_state}" if title_city and title_state else ""),
        "trades": trades, "trade_codes": trade_codes, "services": services,
        "certifications": certs, "service_areas": areas, "csi_codes": csi,
        "story": story, "listed_since": listed,
        "established": info_get("Established", "Year Established", "Founded"),
        "company_size": info_get("Company Size", "Employees", "Number of Employees", "Size"),
        "annual_volume": info_get("Annual Volume", "Annual Revenue", "Volume", "Revenue"),
        "contacts": contacts, "contacts_url": contacts_u, "projects_url": projects_u,
    }


# --------------------------------------------------------------------------- locations-contacts
def _extract_locations(scope, company_name: str) -> list[dict]:
    boxes = scope.find_all(id=re.compile(r"^locationsPage-", re.I))
    if not boxes:
        box = _section_container(scope, "Locations")
        boxes = [box] if box is not None else []
    locations: list[dict] = []
    for box in boxes:
        heads = [h for h in box.find_all(["h3", "h4"]) if _clean_text(h.get_text(" "))]
        markers = heads or [box]
        for h in markers:
            block = _block_for(h, box, markers) if heads else box
            lines = _lines(block)
            tels = _tel_links(block)
            phone, fax = _first_phone(tels), _first_phone(tels, fax=True)
            if not phone:  # labelled-text fallback, still scoped to this block
                for n in phonelib.find_labelled(block.get_text(" ")):
                    phone = {**n, "is_fax": False, "source": "labelled_text"}
                    break
            addr = _parse_address_lines([l for l in lines if _norm(l) != _norm(company_name)])
            website, _s = _external_links(block)
            person, person_title = "", ""
            for el in block.find_all(["strong", "b", "button"]):
                t = _clean_text(el.get_text(" "))
                if _looks_like_person(t, company_name):
                    person = t
                    idx = lines.index(t) if t in lines else -1
                    if 0 <= idx + 1 < len(lines) and lines[idx + 1].lower() != "main location":
                        person_title = lines[idx + 1]
                    break
            if not (addr["address_raw"] or phone or website):
                continue
            locations.append({
                "label": _clean_text(h.get_text(" ")) if heads else company_name,
                **addr,
                "phone": _phone_display(phone), "phone_e164": phone["e164"] if phone else "",
                "phone_source": phone.get("source", "") if phone else "",
                "extra_phones": [_phone_display(t) for t in tels
                                 if not t.get("is_fax") and (not phone or t.get("e164") != phone.get("e164"))],
                "fax": _phone_display(fax), "website": website,
                "contact_name": person, "contact_title": person_title,
                "is_main": "main location" in block.get_text(" ").lower(),
            })
    # Merge repeated location blocks by address (not volatile label), while
    # retaining alternate phones and the main-location flag.
    def merge_key(loc: dict):
        addr_key = _norm(" ".join(str(loc.get(f) or "") for f in ("street", "city", "state", "zip")))
        return addr_key or _norm(loc.get("address_raw", "")) or loc.get("phone_e164", "") or _norm(loc.get("label", ""))

    by_key: dict[str, dict] = {}
    for loc in locations:
        key = merge_key(loc)
        old = by_key.get(key)
        if old is None:
            by_key[key] = loc
            continue
        extras = set(old.get("extra_phones") or []) | set(loc.get("extra_phones") or [])
        if old.get("phone") and loc.get("phone") and old["phone_e164"] != loc["phone_e164"]:
            extras.add(loc["phone"])
        old["extra_phones"] = sorted(extras)
        old["is_main"] = bool(old.get("is_main") or loc.get("is_main"))
        for f in ("phone", "phone_e164", "phone_source", "fax", "website", "contact_name", "contact_title"):
            if not old.get(f) and loc.get(f):
                old[f] = loc[f]
    return list(by_key.values())


def _contact_boxes(scope) -> list[tuple[Tag, str]]:
    """All non-overlapping contact/management/team sections in scope."""
    boxes: list[tuple[Tag, str]] = []

    def add(box, default_dept: str = ""):
        if box is None:
            return
        for i, (old, _dept) in enumerate(boxes):
            if box is old or box in list(old.parents):
                return  # already covered by a broader section
            if old in list(box.parents):
                boxes[i] = (box, default_dept)
                return
        boxes.append((box, default_dept))

    add(scope.find(id="keyContactSection") if hasattr(scope, "find") else None)
    for name in _CONTACT_SECTION_NAMES:
        add(_section_container(scope, name))
    for name in _DEPARTMENT_SECTION_NAMES:
        add(_section_container(scope, name), name)
    return boxes


def _extract_contacts_from_box(box, company_name: str, default_department: str = "",
                               window: tuple[int, int] | None = None) -> list[dict]:
    if box is None or not hasattr(box, "find_all"):
        return []
    order = list(box.descendants)
    pos = {id(el): i for i, el in enumerate(order)}
    lo, hi = window if window else (-1, 10 ** 12)

    def in_window(el) -> bool:
        return lo <= pos.get(id(el), -1) <= hi

    main_names = {_norm(x) for x in _CONTACT_SECTION_NAMES}
    dept_heads = []
    for h in box.find_all(["h2", "h3", "h4", "h5"]):
        if not in_window(h):
            continue
        text = _clean_text(h.get_text(" "))
        if _norm(text) in main_names:
            continue
        name_candidate, _title = _split_person_title(text, company_name)
        if _is_department_heading(text) or not _looks_like_person(name_candidate, company_name):
            if text:
                dept_heads.append(h)

    candidates: list[Tag] = []
    inline_titles: dict[int, str] = {}
    for el in box.find_all(["button", "strong", "b", "h3", "h4", "h5", "h6"]):
        if not in_window(el) or el in dept_heads:
            continue
        raw_text = _clean_text(el.get_text(" "))
        name_text, inline_title = _split_person_title(raw_text, company_name)
        if _looks_like_person(name_text, company_name):
            # Adjacent same-name blocks can be legitimate alternate phone/title
            # evidence. Only suppress nested duplicate markup for one element.
            nested_duplicate = any(
                normalize_person_name(_split_person_title(_clean_text(c.get_text(" ")), company_name)[0])
                == normalize_person_name(name_text)
                and (el in list(c.parents) or c in list(el.parents))
                for c in candidates)
            if not nested_duplicate:
                candidates.append(el)
                if inline_title:
                    inline_titles[id(el)] = inline_title

    # Schema.org Person microdata, including a repeat name in another section;
    # candidate merging below decides whether it is a duplicate evidence row.
    for person in box.find_all(attrs={"itemtype": re.compile(r"/Person$")}):
        if not in_window(person):
            continue
        nm = person.find(attrs={"itemprop": "name"})
        if nm is None:
            continue
        name_text = _clean_text(nm.get("content") or nm.get_text(" "))
        if not _looks_like_person(name_text, company_name):
            continue
        if any(nm is c or nm in list(c.parents) or c in list(nm.parents) for c in candidates):
            continue
        candidates.append(nm)

    contacts: list[dict] = []
    for cand in candidates:
        raw_name = _clean_text(cand.get_text(" "))
        name, inline_title = _split_person_title(raw_name, company_name)
        inline_title = inline_titles.get(id(cand), inline_title)
        person_scope = cand.find_parent(attrs={"itemtype": re.compile(r"/Person$")}) \
            if hasattr(cand, "find_parent") else None
        block = person_scope or _block_for(cand, box, candidates)
        dept = default_department
        for dh in dept_heads:
            if pos.get(id(dh), 10 ** 9) < pos.get(id(cand), -1):
                dept = _clean_text(dh.get_text(" "))
        tels = _tel_links(block)
        phone, fax = _first_phone(tels), _first_phone(tels, fax=True)
        if not phone:
            labelled = phonelib.find_labelled(block.get_text(" "))
            if labelled:
                phone = {**labelled[0], "is_fax": False, "source": "labelled_text"}
        title = inline_title
        title_el = block.find(attrs={"itemprop": "jobTitle"}) if hasattr(block, "find") else None
        if title_el is not None:
            title = title or _clean_text(title_el.get_text(" "))
        if not title:
            for line in _lines(block):
                low = line.lower()
                if line in (name, raw_name) or low in _NAME_BLACKLIST or "view phone" in low or "view fax" in low:
                    continue
                if phonelib.find_in_text(line) or _EMAIL_RE.search(line) or line == dept:
                    continue
                if len(line) <= 80:
                    title = line
                    break
        emails = _extract_emails(block)
        email = emails[0]["email"] if emails else ""
        contact_phones = [t for t in tels if not t.get("is_fax")]
        contacts.append({
            "name": name, "title": title, "department": dept,
            "phone": _phone_display(phone), "phone_e164": phone["e164"] if phone else "",
            "phone_source": phone.get("source", "") if phone else "",
            "extra_phones": [_phone_display(t) for t in contact_phones[1:] if phone],
            "fax": _phone_display(fax), "email": email,
            "extra_emails": [e["email"] for e in emails[1:]],
        })
    return _merge_contact_candidates(contacts)


def _extract_contacts(scope, company_name: str) -> list[dict]:
    boxes = _contact_boxes(scope)
    contacts: list[dict] = []
    for box, default_dept in boxes:
        contacts.extend(_extract_contacts_from_box(box, company_name, default_dept))

    # Heading-segment fallback for layouts where the semantic ancestor logic
    # cannot isolate a large contacts/team section.  Limit candidate elements
    # to the document window after a relevant heading and before the next
    # clearly non-contact major section.
    if not contacts and hasattr(scope, "find_all"):
        order = list(scope.descendants)
        pos = {id(el): i for i, el in enumerate(order)}
        relevant = {_norm(x) for x in _CONTACT_SECTION_NAMES + _DEPARTMENT_SECTION_NAMES}
        stop = {_norm(x) for x in ("Locations", "What We Do", "Our Story", "Project Experience",
                                   "Completed Projects", "Gallery", "Reviews", "Testimonials",
                                   "Regions & Counties Serviced", "Our CSI Codes")}
        start = None
        end = 10 ** 12
        for h in scope.find_all(_HEADINGS):
            key = _norm(h.get_text(" "))
            if start is None and key in relevant:
                start = pos.get(id(h), 0)
            elif start is not None and key in stop:
                end = pos.get(id(h), end)
                break
        if start is not None:
            contacts.extend(_extract_contacts_from_box(scope, company_name, window=(start, end)))

    # Explicit role-labelled people in Company Info / contact sections, e.g.
    # "President: Jane Doe" or adjacent label/value lines.  This catches
    # owners, executives, estimators, project managers, and principal contacts
    # even when they are not rendered as Key Contacts cards.
    labelled_scopes = [box for box, _dept in boxes]
    info_box = _section_container(scope, "Company Info", ids=("companyInfoSection",))
    if info_box is not None and all(info_box is not b for b in labelled_scopes):
        labelled_scopes.append(info_box)
    for box in labelled_scopes:
        contacts.extend(_contacts_from_labelled_lines(_lines(box), company_name))
    return _merge_contact_candidates(contacts)


def parse_contacts(html: str, url: str, expected_name: str = "") -> dict:
    cid = company_id(url)
    soup = soup_from(html)
    ld = _match_json_ld(html, expected_name, cid)
    scope = _clean_scope(soup)

    name = expected_name
    name_from_page = False
    if soup.title:
        t = _clean_text(soup.title.get_text(" ").split("|")[0].rsplit("-", 1)[0])
        name = t or name
        name_from_page = bool(t)
    if ld and ld.get("name"):
        name = _clean_text(str(ld["name"])) or name
        name_from_page = bool(name)
    if ld is None and name:
        ld = _match_json_ld(html, name, cid)

    locations = _extract_locations(scope, name)
    contacts = _extract_contacts(scope, name)
    # A person named inside a location block is still an individual contact.
    # Do not assign the location's phone as that person's direct number; the
    # person-level export can apply the company/main-location fallback.
    for loc in locations:
        person = _clean_text(loc.get("contact_name") or "")
        if person and _looks_like_person(person, name):
            contacts.append({
                "name": person, "title": loc.get("contact_title", ""),
                "department": "Location Contact", "phone": "", "phone_e164": "",
                "phone_source": "", "extra_phones": [], "fax": "", "email": "",
                "extra_emails": [],
            })
    contacts = _merge_contact_candidates(contacts)

    website, socials = _external_links(scope)
    ld_addresses = _node_addresses([ld]) if ld else []
    if not locations and ld_addresses:
        for i, addr in enumerate(ld_addresses):
            locations.append({
                "label": name or "Main Location", **addr,
                "phone": "", "phone_e164": "", "phone_source": "", "fax": "",
                "website": website, "contact_name": "", "contact_title": "",
                "is_main": i == 0, "extra_phones": [],
            })
    if ld and ld.get("telephone") and locations and not locations[0].get("phone"):
        vals = ld["telephone"] if isinstance(ld["telephone"], list) else [ld["telephone"]]
        n = phonelib.normalize(str(vals[0])) if vals else None
        if n:
            locations[0]["phone"] = _phone_display(n)
            locations[0]["phone_e164"] = n["e164"]
            locations[0]["phone_source"] = "json_ld"
    if ld:
        for cand in ([ld.get("url", "")] + list(ld.get("sameAs") or [])):
            dom = domain_of(str(cand))
            if dom in SOCIAL_DOMAINS and str(cand) not in socials and "/share" not in str(cand).lower():
                socials.append(str(cand))
            elif dom and "thebluebook.com" not in dom and not website:
                website = strip_tracking(str(cand))
    main_phone, main_source = "", ""
    for loc in locations:
        if loc["phone"] and (loc["is_main"] or not main_phone):
            main_phone, main_source = loc["phone"], loc["phone_source"]
            if loc["is_main"]:
                break
    if not main_phone and contacts:
        for c in contacts:
            if c.get("phone"):
                main_phone, main_source = c["phone"], c.get("phone_source", "")
                break
    main_loc = next((l for l in locations if l["is_main"]), locations[0] if locations else {})
    extra_phones: list[str] = []
    for loc in locations:
        for p in [loc.get("phone", ""), *(loc.get("extra_phones") or [])]:
            if p and p != main_phone and p not in extra_phones:
                extra_phones.append(p)
    for c in contacts:
        for p in c.get("extra_phones") or []:
            if p and p != main_phone and p not in extra_phones:
                extra_phones.append(p)
    emails: list[dict] = []
    if ld and ld.get("email"):
        for val in (ld["email"] if isinstance(ld["email"], list) else [ld["email"]]):
            e = _valid_email(str(val).replace("mailto:", "", 1))
            if e:
                emails.append({"email": e, "source": "json_ld"})
    seen_emails = {e["email"].lower() for e in emails}
    for e in _extract_emails(scope):
        if e["email"].lower() not in seen_emails:
            emails.append(e)
            seen_emails.add(e["email"].lower())
    for c in contacts:
        if c.get("email") and c["email"].lower() not in seen_emails:
            emails.append({"email": c["email"], "source": "key_contact"})
            seen_emails.add(c["email"].lower())
    normalized_main = phonelib.normalize(main_phone) if main_phone else None
    return {
        "company_id": cid, "name": name, "name_from_page": name_from_page,
        "locations": locations, "contacts": contacts,
        "pretty_url": profile_root_url(url), "profile_url": profile_root_url(url),
        "website": website or (main_loc.get("website", "") if main_loc else ""),
        "socials": socials, "phone": main_phone, "phone_source": main_source,
        "phone_e164": normalized_main["e164"] if normalized_main else "",
        "extra_phones": extra_phones,
        "email": emails[0]["email"] if emails else "",
        "email_source": emails[0]["source"] if emails else "",
        "extra_emails": [e["email"] for e in emails[1:]],
        "address_raw": main_loc.get("address_raw", "") if main_loc else "",
        "street": main_loc.get("street", "") if main_loc else "",
        "city": main_loc.get("city", "") if main_loc else "",
        "state": main_loc.get("state", "") if main_loc else "",
        "zip": main_loc.get("zip", "") if main_loc else "",
        "fax": main_loc.get("fax", "") if main_loc else "",
    }


# --------------------------------------------------------------------------- projects (optional)
def parse_projects(html: str, url: str) -> dict:
    soup = soup_from(html)
    scope = _clean_scope(soup)
    box = _section_container(scope, "Completed Projects", "Project Experience", "Projects") or scope
    heads = [h for h in box.find_all(["h3", "h4"]) if _clean_text(h.get_text(" "))]
    projects, seen = [], set()
    for h in heads:
        name = _clean_text(h.get_text(" "))
        if name.lower() in _NAME_BLACKLIST or name in seen:
            continue
        seen.add(name)
        block = _block_for(h, box, heads)
        lines = _lines(block)
        loc = ""
        fields = {"type": "", "status": "", "date": "", "gc_name": ""}
        for line in lines:
            m = _CITY_STATE_RE.search(line)
            if m and not loc:
                loc = f"{m.group(1)}, {m.group(2)}"
            lm = re.match(r"(type|status|date|year|completed|general contractor|gc)\s*[:\-]\s*(.+)$", line, re.I)
            if lm:
                label = lm.group(1).lower()
                key = "gc_name" if label in ("general contractor", "gc") else (
                    "date" if label in ("year", "completed") else label)
                fields[key] = fields[key] or lm.group(2).strip()
        a = block.find("a", href=True)
        projects.append({"name": name, "location": loc, **fields,
                         "url": canonical(a["href"]) if a else "",
                         "raw": " | ".join(lines[:6])[:400]})
    return {"company_id": company_id(url), "projects": projects}


def parse_index(html: str, url: str) -> dict:
    """Category/top-list index: complete-search links plus any profile rows."""
    soup = soup_from(html)
    links: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        u = canonical(a.get("href", ""))
        if not u:
            continue
        from .urls import kind_of
        if kind_of(u) != "listing":
            continue
        params = query_params(u)
        name = _clean_text(a.get_text(" ")) or (params.get("searchterm") or [""])[0]
        links[u] = {"url": u, "name": name, "class_code": (params.get("class") or [""])[0],
                    "region": (params.get("region") or [""])[0]}
    listing = parse_listing(html, canonical(url) or url)
    return {"search_links": list(links.values()), "companies": listing.get("companies", []),
            "result_rows": listing.get("result_rows", 0)}


# --------------------------------------------------------------------------- page markers
def has_profile_markers(html: str) -> bool:
    h = html or ""
    return any(k in h for k in ("companyInfoSection", "keyContactSection", "locationsPage-",
                                 "What We Do", "Our Story", "Locations", "Key Contacts"))

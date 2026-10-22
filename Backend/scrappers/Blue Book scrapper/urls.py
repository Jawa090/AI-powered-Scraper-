"""URL canonicalization and Blue Book URL-shape helpers.

Lessons baked in:
- Repo B canonicalized by full slug URL -> slug/category variants of the same
  company could duplicate, and canonical('') returned the homepage (its own
  bundled data contains a bogus homepage 'lead'). Here the company's identity
  is the numeric iProView id; empty/non-Blue-Book input returns ''.
- Supported seed shapes include /search.html, /search-build/search.html,
  /city-search.html, /iSearch/results/..., SEO city pages, category/top-list
  index pages, and /iProView/{id}/... profile pages.
- Query canonicalization preserves legitimate multi-value facets while
  removing exact duplicates, normalizes class codes such as 0830 -> 830, and
  treats page=1 as the seed URL.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

BASE = "https://www.thebluebook.com"
HOSTS = {"www.thebluebook.com", "thebluebook.com"}
_ID_RE = re.compile(r"/iProView/(\d+)(?:/|$)", re.I)
_KEY_CASE = {
    "searchterm": "searchTerm",
    "searchsrc": "searchsrc",
    "namesearch": "nameSearch",
    "csi-group": "csi-group",
}
_PROFILE_TABS_TO_ROOT = {
    "key-contacts", "locations", "geographic-service-area", "images", "gallery",
}
_PROFILE_SUBPAGES = {"locations-contacts", "completed-projects"}
_SEARCH_PATHS = {"/search.html", "/search-build/search.html", "/city-search.html"}
_INDEX_DENY_FIRST = {
    "products", "company", "landing-pages", "project-solutions", "assets",
    "globalassets", "images", "tools", "main", "wsnsa.dll",
}


def _absolute(url: str) -> str:
    raw = str(url or "").strip().strip("<>\"'")
    if not raw:
        return ""
    if raw.startswith("//"):
        return "https:" + raw
    low = raw.lower()
    if low.startswith(("www.thebluebook.com", "thebluebook.com")):
        return "https://" + raw
    return urljoin(BASE + "/", raw)


def _normalize_query(query: str, *, listing: bool = False) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen = set()
    for key, value in parse_qsl(query, keep_blank_values=False):
        if value == "":
            continue
        k = _KEY_CASE.get(key.lower(), key.lower())
        v = value.strip()
        if k.lower() == "class" and v.isdigit():
            v = str(int(v))
        if listing and k.lower() == "page" and v.isdigit() and int(v) <= 1:
            continue
        pair = (k, v)
        if pair not in seen:
            seen.add(pair)
            out.append(pair)
    return sorted(out)


def _normalize_path(path: str) -> str:
    p = re.sub(r"/+", "/", path or "/")
    parts = [s for s in p.split("/") if s]
    if len(parts) >= 2 and parts[0].lower() == "iproview" and parts[1].isdigit():
        cid = parts[1]
        if len(parts) == 2:
            return f"/iProView/{cid}"
        if len(parts) == 3:
            return f"/iProView/{cid}/{parts[2]}/"
        if len(parts) == 4:
            return f"/iProView/{cid}/{parts[2]}/{parts[3]}/"
        last = parts[-1].lower()
        if last in _PROFILE_TABS_TO_ROOT:
            return f"/iProView/{cid}/{parts[2]}/{parts[3]}/"
        if last in _PROFILE_SUBPAGES:
            return f"/iProView/{cid}/{parts[2]}/{parts[3]}/{parts[-1]}/"
        # Longer profile paths (gallery items, project types) are preserved.
        return "/iProView/" + "/".join(parts[1:]) + "/"
    return p


def canonical(url: str) -> str:
    """Absolute, https, www host, sorted query, no fragment. '' if invalid."""
    if not url or not str(url).strip():
        return ""
    p = urlsplit(_absolute(url))
    if (p.hostname or "").lower() not in HOSTS:
        return ""
    if p.scheme not in ("http", "https"):
        return ""
    path = _normalize_path(p.path or "/")
    parts = [s for s in path.split("/") if s]
    is_profile = len(parts) >= 2 and parts[0].lower() == "iproview"
    listing = path.lower() in _SEARCH_PATHS or "/isearch/results/" in path.lower()
    # Profile tracking/ref/region/class query parameters do not identify a
    # different page; stripping them prevents duplicate profile jobs.
    query = "" if is_profile else urlencode(_normalize_query(p.query, listing=listing))
    return urlunsplit(("https", "www.thebluebook.com", path, query, ""))


def company_id(url: str) -> str:
    """Numeric iProView id from any profile URL variant, else ''."""
    if not url:
        return ""
    m = _ID_RE.search(str(url))
    return m.group(1) if m else ""


def profile_url(cid: str) -> str:
    return f"{BASE}/iProView/{cid}" if cid else ""


def profile_root_url(url: str) -> str:
    """Best profile-root URL from any profile/sub-page URL.

    A slugged root is preferred over the bare-ID form because sub-page URLs
    (locations-contacts/completed-projects) can be constructed from it.
    """
    u = canonical(url)
    cid = company_id(u)
    if not cid:
        return ""
    parts = [s for s in urlsplit(u).path.split("/") if s]
    if len(parts) >= 4:
        return f"{BASE}/iProView/{cid}/{parts[2]}/{parts[3]}/"
    if len(parts) == 3:
        return f"{BASE}/iProView/{cid}/{parts[2]}/"
    return profile_url(cid)


def contacts_url(pretty_url: str) -> str:
    """Append locations-contacts/ to a slugged profile URL.

    Only constructible when the URL carries slug/category segments
    (/iProView/{id}/{slug}/{category}/). For a bare /iProView/{id} the
    contacts URL must be discovered from the profile page's redirect/links.
    """
    root = profile_root_url(pretty_url)
    if not root:
        return ""
    parts = [s for s in urlsplit(root).path.split("/") if s]
    if len(parts) < 4:
        return ""
    path = "/" + "/".join(parts[:4]) + "/locations-contacts/"
    return urlunsplit(("https", "www.thebluebook.com", path, "", ""))


def projects_url(pretty_url: str) -> str:
    u = contacts_url(pretty_url)
    return u.replace("/locations-contacts/", "/completed-projects/") if u else ""


def kind_of(url: str) -> str:
    """Classify a Blue Book URL: listing|profile|contacts|projects|index|other."""
    u = canonical(url)
    if not u:
        return "other"
    path = urlsplit(u).path
    low = path.lower()
    if low.rstrip("/").endswith("/locations-contacts"):
        return "contacts"
    if low.rstrip("/").endswith("/completed-projects"):
        return "projects"
    if _ID_RE.search(path):
        return "profile"
    if re.fullmatch(r"/cl/all\d+\.htm", low) or re.fullmatch(r"/construction/\d+-[^/]+/\d+-[^/]+/?", low):
        return "index"
    if low in _SEARCH_PATHS or "/isearch/results/" in low:
        return "listing"
    parts = [s for s in path.split("/") if s]
    if len(parts) == 2 and parts[0].lower() not in _INDEX_DENY_FIRST:
        # SEO city pages look like /Roofing-Contractors/Philadelphia-PA
        if re.fullmatch(r"[A-Za-z0-9.-]+-[A-Z]{2}", parts[1]) and "-" in parts[0]:
            return "listing"
    return "other"


def is_search_url(url: str) -> bool:
    return kind_of(url) == "listing"


def query_params(url: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for k, v in _normalize_query(urlsplit(canonical(url)).query, listing=True):
        out.setdefault(k.lower(), []).append(v)
    return out


def search_start(url: str) -> str:
    """Seed form of a search URL: page parameter removed (page 1)."""
    u = canonical(url)
    if not u or kind_of(u) != "listing":
        raise ValueError(f"Not a Blue Book search/profile URL: {url!r}")
    p = urlsplit(u)
    q = [(k, v) for k, v in _normalize_query(p.query, listing=True) if k.lower() != "page"]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))


def with_page(url: str, page: int) -> str:
    """Same search, explicit page=N. Preserves multi-value facets."""
    p = urlsplit(canonical(url))
    q = [(k, v) for k, v in _normalize_query(p.query, listing=True) if k.lower() != "page"]
    if page > 1:
        q.append(("page", str(page)))
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(sorted(q)), ""))


_BENIGN_EXTRA_PARAMS = {"searchterm", "searchsrc", "bkid", "ref", "sortfacets"}


def _path_family(path: str) -> str:
    low = path.lower()
    return "/search.html" if low in _SEARCH_PATHS else low


def same_search(a: str, b: str) -> bool:
    """True if b is a pagination sibling of a.

    Every seed parameter must match exactly (class numbers are normalized by
    canonicalization); candidate extras must be benign display/tracking
    parameters.  The three observed search endpoints are treated as one path
    family because the site links/redirects between them.
    """
    pa, pb = urlsplit(canonical(a)), urlsplit(canonical(b))
    if not pa.path or _path_family(pa.path) != _path_family(pb.path):
        return False
    qa = {k.lower(): tuple(v for kk, v in _normalize_query(pa.query, listing=True) if kk.lower() == k.lower())
          for k, _v in _normalize_query(pa.query, listing=True) if k.lower() != "page"}
    qb = {k.lower(): tuple(v for kk, v in _normalize_query(pb.query, listing=True) if kk.lower() == k.lower())
          for k, _v in _normalize_query(pb.query, listing=True) if k.lower() != "page"}
    if any(qb.get(k) != v for k, v in qa.items()):
        return False
    return set(qb) - set(qa) <= _BENIGN_EXTRA_PARAMS


def page_number(url: str) -> int:
    q = dict(parse_qsl(urlsplit(url).query))
    try:
        return max(1, int(q.get("page", "1")))
    except ValueError:
        return 1


def normalize_external_url(url: str) -> str:
    """Normalize a company website/social URL (scheme optional); strip tracking."""
    if not url:
        return ""
    raw = str(url).strip().strip("<>\"'").rstrip(";,")
    if raw.lower().startswith("mailto:") or raw.lower().startswith("tel:"):
        return ""
    if raw.startswith("//"):
        raw = "https:" + raw
    elif not re.match(r"https?://", raw, re.I):
        # Treat bare domains (example.com/path) as websites; leave relative
        # paths to the caller/urljoin cases.
        if re.match(r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+(/.*)?$", raw):
            raw = "https://" + raw
        else:
            return ""
    p = urlsplit(raw)
    if p.scheme not in ("http", "https") or not p.netloc:
        return ""
    q = [(k, v) for k, v in parse_qsl(p.query)
         if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, urlencode(q), ""))


def strip_tracking(url: str) -> str:
    """Remove tracking params from outbound company-website URLs."""
    return normalize_external_url(url)


def domain_of(url: str) -> str:
    host = (urlsplit(normalize_external_url(url)).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host

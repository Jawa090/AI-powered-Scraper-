"""
Backend/scrappers/Blue Book scrapper/crawler.py
───────────────────────────────────────────────
Email and social media crawler for Blue Book contractor listings.

Features:
- Visits contractor websites to discover emails and social links.
- Deep internal crawling: checks homepage, /contact, /contact-us, /about, /about-us, /reach-us.
- Cloudflare XOR email deobfuscation (both data-cfemail cipher and email-protection#HEX links).
- Mailto link parsing (including multi-recipient links), HTML entity unescaping, unicode entity decoding,
  and bot-obfuscation ([at] / [dot]) decoding.
- Social profile crawling (Instagram, Facebook, LinkedIn, Twitter/X, YouTube) for email discovery.
- Instagram bio / metadata extraction (og:description, JSON-LD, script payloads, bot preview headers).
- Facebook public page extraction (Googlebot / Mobile UA bypass for login walls, unicode \\u0040 decoding, /about page probe).
- Strict non-blocking timeouts (4-5s) to ensure scraping never stalls on unresponsive sites.
- Strict email validation (excludes assets, fonts, dummy domains, subdomains, tracking prefixes).
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit, urlunsplit

import requests
import urllib3

# Suppress insecure SSL warnings for contractor websites with self-signed / expired certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("scrappers.bluebook.crawler")

DEFAULT_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

GOOGLEBOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

FACEBOOK_BOT_UA = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"
)

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+",
    re.IGNORECASE,
)

IGNORED_EMAIL_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js",
    ".woff", ".woff2", ".ttf", ".eot", ".ico", ".mp4", ".mp3", ".pdf",
    ".zip", ".tar", ".gz", ".bmp", ".tif", ".tiff",
)

DENIED_EMAIL_DOMAINS = {
    "thebluebook.com", "example.com", "example.org", "example.net",
    "domain.com", "yourdomain.com", "company.com", "yourcompany.com",
    "sitename.com", "website.com", "email.com", "test.com", "mysite.com",
    "sentry.io", "wixpress.com", "wix.com", "schema.org", "wordpress.org",
    "wordpress.com", "gravatar.com", "cloudflare.com", "apple.com", "google.com",
    "facebook.com", "instagram.com", "meta.com", "twitter.com", "x.com",
    "linkedin.com", "youtube.com", "bbb.org", "godaddy.com", "squarespace.com",
    "weebly.com", "shopify.com",
}

DENIED_EMAIL_PREFIXES = {
    "sentry", "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply",
    "mailer-daemon", "postmaster",
}

SOCIAL_PATTERNS = {
    "facebook": [
        re.compile(r"^https?://(?:www\.|m\.)?(?:facebook\.com|fb\.com|fb\.me)/(?:pg/|people/[^/]+/|p/)?([a-zA-Z0-9.\-_]+)(?:[/?].*)?$", re.I),
        re.compile(r"^https?://(?:www\.|m\.)?(?:facebook\.com|fb\.com|fb\.me)/pages/[^/]+/(\d+)(?:[/?].*)?$", re.I),
        re.compile(r"^https?://(?:www\.|m\.)?(?:facebook\.com|fb\.com|fb\.me)/profile\.php\?id=(\d+)", re.I),
    ],
    "instagram": [
        re.compile(r"^https?://(?:www\.)?(?:instagram\.com|instagr\.am)/([a-zA-Z0-9._]+)(?:[/?].*)?$", re.I),
    ],
    "linkedin": [
        re.compile(r"^https?://(?:www\.)?linkedin\.com/(?:company|in)/([a-zA-Z0-9.\-_]+)(?:[/?].*)?$", re.I),
    ],
    "twitter": [
        re.compile(r"^https?://(?:www\.)?(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)(?:[/?].*)?$", re.I),
    ],
    "youtube": [
        re.compile(r"^https?://(?:www\.)?(?:youtube\.com|youtu\.be)/(@[a-zA-Z0-9.\-_]+|channel/[a-zA-Z0-9.\-_]+|c/[a-zA-Z0-9.\-_]+|user/[a-zA-Z0-9.\-_]+)(?:[/?].*)?$", re.I),
    ],
}

IGNORED_SOCIAL_PATHS = {
    "sharer", "share", "intent", "share-offsite", "dialog", "plugins",
    "hashtag", "login", "signup", "policies", "terms", "help", "about",
    "pages", "p", "reel", "reels", "stories", "home", "privacy",
    "legal", "explore", "directory", "tr",
}

CONTACT_KEYWORDS = (
    "contact", "contact-us", "contact_us", "contactus",
    "about", "about-us", "about_us", "aboutus",
    "reach-us", "reach_us", "get-in-touch", "getintouch",
    "our-team", "team", "meet-the-team", "staff",
    "location", "locations", "touch",
)


def _strip_www(host: str) -> str:
    h = (host or "").lower().split(":", 1)[0]
    return h[4:] if h.startswith("www.") else h


def clean_email(raw_email: Optional[str]) -> Optional[str]:
    """Validate and clean an email string; return normalized lowercase or None."""
    if not raw_email:
        return None
    raw = str(raw_email).strip().strip("<>\"'()[],;:").rstrip(".,;:)")
    if not raw or "@" not in raw:
        return None
    m = EMAIL_REGEX.fullmatch(raw)
    if not m:
        search_m = EMAIL_REGEX.search(raw)
        if not search_m:
            return None
        raw = search_m.group(0)

    try:
        local_part, domain_part = raw.rsplit("@", 1)
    except ValueError:
        return None

    local_clean = local_part.strip().lower()
    domain_clean = domain_part.strip().lower()

    if not local_clean or not domain_clean or "." not in domain_clean:
        return None

    tld = domain_clean.rsplit(".", 1)[-1]
    if len(tld) < 2 or not tld.isalpha():
        return None

    if any(domain_clean.endswith(ext) for ext in IGNORED_EMAIL_EXTENSIONS):
        return None

    # Check denied domains (exact or subdomains)
    if any(domain_clean == d or domain_clean.endswith("." + d) for d in DENIED_EMAIL_DOMAINS):
        return None

    # Check denied prefixes
    if any(
        local_clean == p or local_clean.startswith(f"{p}-") or local_clean.startswith(f"{p}_") or local_clean.startswith(f"{p}.")
        for p in DENIED_EMAIL_PREFIXES
    ):
        return None

    return f"{local_clean}@{domain_clean}"


def decode_cloudflare_email(cf_hex: str) -> Optional[str]:
    """Decode Cloudflare data-cfemail XOR cipher."""
    if not cf_hex or len(cf_hex) < 4 or len(cf_hex) % 2 != 0:
        return None
    try:
        key = int(cf_hex[:2], 16)
        email = "".join(
            chr(int(cf_hex[i:i + 2], 16) ^ key)
            for i in range(2, len(cf_hex), 2)
        )
        return clean_email(email)
    except Exception:
        return None


def extract_emails_from_html(html_text: str, base_url: str = "") -> List[str]:
    """Extract and validate all emails from HTML content."""
    if not html_text:
        return []

    discovered: List[str] = []
    seen: Set[str] = set()

    def add_email(em: Optional[str]) -> None:
        cleaned = clean_email(em)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            discovered.append(cleaned)

    # 1. Cloudflare encoded emails
    for m in re.finditer(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html_text):
        cf_decoded = decode_cloudflare_email(m.group(1))
        if cf_decoded:
            add_email(cf_decoded)

    for m in re.finditer(r'/cdn-cgi/l/email-protection#([a-fA-F0-9]+)', html_text):
        cf_decoded = decode_cloudflare_email(m.group(1))
        if cf_decoded:
            add_email(cf_decoded)

    # 2. BeautifulSoup parsing for mailto: links and meta tags
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_text, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if href.lower().startswith("mailto:"):
                raw_cand = unquote(href.split("mailto:", 1)[1].split("?", 1)[0].strip())
                for candidate in re.split(r"[,;]+", raw_cand):
                    add_email(candidate.strip())

        for meta in soup.find_all("meta"):
            content = meta.get("content", "")
            if content and ("@" in content or "&#64;" in content or "&#x40;" in content):
                unescaped_meta = html.unescape(content)
                for match in EMAIL_REGEX.finditer(unescaped_meta):
                    add_email(match.group(0))
    except Exception:
        pass

    # 3. Decoded text regex fallback:
    unescaped = html.unescape(html_text)
    normalized_text = unescaped.replace(r"\u0040", "@").replace("%40", "@").replace(r"\u002e", ".").replace("%2e", ".")
    normalized_text = re.sub(r"\s*\[at\]\s*", "@", normalized_text, flags=re.I)
    normalized_text = re.sub(r"\s*\(at\)\s*", "@", normalized_text, flags=re.I)
    normalized_text = re.sub(r"\s*\[dot\]\s*", ".", normalized_text, flags=re.I)
    normalized_text = re.sub(r"\s*\(dot\)\s*", ".", normalized_text, flags=re.I)

    for match in EMAIL_REGEX.finditer(normalized_text):
        add_email(match.group(0))

    return discovered


def detect_social_platform(url: str) -> Optional[str]:
    """Determine social platform name for a given URL using exact netloc domain."""
    if not url:
        return None
    p = urlsplit(url)
    host = _strip_www(p.hostname or "")
    if not host:
        return None

    if host in ("facebook.com", "fb.com", "fb.me") or host.endswith((".facebook.com", ".fb.com", ".fb.me")):
        return "facebook"
    if host in ("instagram.com", "instagr.am") or host.endswith((".instagram.com", ".instagr.am")):
        return "instagram"
    if host in ("linkedin.com",) or host.endswith(".linkedin.com"):
        return "linkedin"
    if host in ("twitter.com", "x.com") or host.endswith((".twitter.com", ".x.com")):
        return "twitter"
    if host in ("youtube.com", "youtu.be") or host.endswith((".youtube.com", ".youtu.be")):
        return "youtube"
    return None


def clean_website_url(url: Optional[str]) -> Optional[str]:
    """Normalize a website URL, prepending https:// if scheme is missing."""
    if not url:
        return None
    raw = str(url).strip().strip("<>\"'").rstrip(";,")
    if not raw:
        return None
    if not raw.startswith(("http://", "https://")):
        if raw.startswith("//"):
            raw = "https:" + raw
        else:
            raw = "https://" + raw

    p = urlsplit(raw)
    if not p.netloc:
        return None
    return f"{p.scheme}://{p.netloc.lower()}{p.path.rstrip('/')}"


def clean_social_url(url: str) -> Optional[str]:
    """Normalize a social media profile URL and strip tracking parameters."""
    if not url:
        return None
    raw = str(url).strip().strip("<>\"'").rstrip(";,")
    if not raw.startswith(("http://", "https://")):
        if raw.startswith("//"):
            raw = "https:" + raw
        else:
            raw = "https://" + raw

    p = urlsplit(raw)
    if not p.netloc:
        return None

    low_path = p.path.lower()
    if any(ig in low_path for ig in ["/sharer", "/share", "/intent", "/dialog", "/plugins"]):
        return None

    filtered_query = [
        (k, v) for k, v in parse_qsl(p.query)
        if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid", "locale"}
    ]
    query_str = ("?" + "&".join(f"{k}={v}" for k, v in filtered_query)) if filtered_query else ""
    return f"{p.scheme}://{p.netloc.lower()}{p.path.rstrip('/')}{query_str}"


def extract_social_links_from_html(html_text: str, base_url: str = "") -> Dict[str, List[str]]:
    """Extract categorized social media profile URLs from HTML content."""
    socials: Dict[str, List[str]] = {
        "facebook": [],
        "instagram": [],
        "linkedin": [],
        "twitter": [],
        "youtube": [],
    }
    if not html_text:
        return socials

    seen: Set[str] = set()
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_text, "html.parser")
        for a in soup.find_all("a", href=True):
            raw_href = a.get("href", "").strip()
            if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            full_url = urljoin(base_url, raw_href) if base_url else raw_href
            clean_url = clean_social_url(full_url)
            if not clean_url or clean_url in seen:
                continue

            platform = detect_social_platform(clean_url)
            if not platform:
                continue

            matched = False
            for pat in SOCIAL_PATTERNS.get(platform, []):
                m = pat.match(clean_url)
                if m:
                    slug = m.group(1).lower().rstrip("/")
                    if slug not in IGNORED_SOCIAL_PATHS and len(slug) >= 2:
                        matched = True
                        break

            if matched:
                seen.add(clean_url)
                socials[platform].append(clean_url)
    except Exception:
        pass

    return socials


def find_internal_contact_links(html_text: str, base_url: str) -> List[str]:
    """Find candidate contact / about subpage URLs within the contractor's website."""
    if not html_text or not base_url:
        return []

    base_domain = _strip_www(urlsplit(base_url).hostname or "")
    if not base_domain:
        return []

    contact_candidates: List[str] = []
    other_candidates: List[str] = []
    seen: Set[str] = {base_url.rstrip("/")}

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            full_url = urljoin(base_url, href)
            p = urlsplit(full_url)
            target_domain = _strip_www(p.hostname or "")

            if target_domain != base_domain and not target_domain.endswith("." + base_domain):
                continue

            path_and_query = (p.path + " " + p.query).lower()
            anchor_text = a.get_text(" ").lower()

            clean_target = urlunsplit((p.scheme, p.netloc, p.path.rstrip("/"), "", ""))
            if not clean_target or clean_target in seen:
                continue

            is_contact = any(k in path_and_query for k in ("contact", "reach", "touch")) or any(
                k in anchor_text for k in ("contact", "reach us", "get in touch")
            )
            is_about = any(k in path_and_query for k in ("about", "team", "staff", "location")) or any(
                k in anchor_text for k in ("about", "our team", "staff")
            )

            if is_contact:
                seen.add(clean_target)
                contact_candidates.append(clean_target)
            elif is_about:
                seen.add(clean_target)
                other_candidates.append(clean_target)

            if len(contact_candidates) + len(other_candidates) >= 8:
                break
    except Exception:
        pass

    combined = contact_candidates + other_candidates

    if not combined:
        for fallback_path in ("/contact", "/contact-us", "/about", "/about-us"):
            probe = urljoin(base_url, fallback_path)
            if probe not in seen:
                combined.append(probe)

    return combined[:3]


def crawl_website_for_email_and_social(
    website_url: Optional[str],
    timeout: float = 8.0,
) -> Tuple[Optional[str], Dict[str, List[str]]]:
    """
    Crawls a contractor's website (homepage + contact/about subpages).
    Returns (discovered_email, discovered_socials).
    """
    empty_socials: Dict[str, List[str]] = {
        "facebook": [], "instagram": [], "linkedin": [], "twitter": [], "youtube": []
    }
    valid_url = clean_website_url(website_url)
    if not valid_url:
        return None, empty_socials
    website_url = valid_url

    headers = {
        "User-Agent": DEFAULT_CHROME_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    discovered_email: Optional[str] = None
    all_socials: Dict[str, List[str]] = {k: [] for k in empty_socials}

    session = requests.Session()
    session.verify = False
    session.headers.update(headers)

    try:
        resp = None
        try:
            resp = session.get(website_url, timeout=timeout, allow_redirects=True)
        except Exception as first_exc:
            alt_url = None
            if website_url.startswith("http://"):
                alt_url = "https://" + website_url[7:]
            elif website_url.startswith("https://"):
                alt_url = "http://" + website_url[8:]
            if alt_url:
                try:
                    resp = session.get(alt_url, timeout=timeout, allow_redirects=True)
                    website_url = alt_url
                except Exception:
                    logger.debug("Failed crawling both %s and fallback %s", website_url, alt_url)

        if resp is not None and resp.status_code == 200 and resp.text:
            home_html = resp.text
            final_home_url = resp.url or website_url

            emails = extract_emails_from_html(home_html, final_home_url)
            if emails:
                discovered_email = emails[0]

            home_socials = extract_social_links_from_html(home_html, final_home_url)
            for plat, links in home_socials.items():
                for l in links:
                    if l not in all_socials[plat]:
                        all_socials[plat].append(l)

            if not discovered_email:
                contact_links = find_internal_contact_links(home_html, final_home_url)
                for contact_url in contact_links:
                    try:
                        sub_resp = session.get(contact_url, timeout=timeout, allow_redirects=True)
                        if sub_resp.status_code == 200 and sub_resp.text:
                            sub_emails = extract_emails_from_html(sub_resp.text, sub_resp.url or contact_url)
                            if sub_emails:
                                discovered_email = sub_emails[0]

                            sub_socials = extract_social_links_from_html(sub_resp.text, sub_resp.url or contact_url)
                            for plat, links in sub_socials.items():
                                for l in links:
                                    if l not in all_socials[plat]:
                                        all_socials[plat].append(l)

                            if discovered_email:
                                break
                    except Exception:
                        continue
    except Exception as e:
        logger.debug("Error crawling contractor website %s: %s", website_url, e)
    finally:
        session.close()

    return discovered_email, all_socials


def crawl_social_profile_for_email(
    platform: str,
    social_url: str,
    timeout: float = 6.0,
) -> Optional[str]:
    """
    Crawls a specific social media profile (Instagram, Facebook, LinkedIn, Twitter/X, YouTube)
    to extract contractor email address.
    """
    if not social_url or not str(social_url).startswith("http"):
        return None

    if platform == "facebook":
        ua = GOOGLEBOT_UA
    elif platform == "instagram":
        ua = DEFAULT_CHROME_UA
    else:
        ua = DEFAULT_CHROME_UA

    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        resp = requests.get(social_url, headers=headers, timeout=timeout, allow_redirects=True, verify=False)
        if resp.status_code == 200 and resp.text:
            emails = extract_emails_from_html(resp.text, resp.url or social_url)
            if emails:
                return emails[0]

        if platform == "instagram":
            try:
                bot_resp = requests.get(
                    social_url,
                    headers={"User-Agent": FACEBOOK_BOT_UA, "Accept": "text/html"},
                    timeout=timeout,
                    allow_redirects=True,
                    verify=False,
                )
                if bot_resp.status_code == 200 and bot_resp.text:
                    bot_emails = extract_emails_from_html(bot_resp.text, bot_resp.url or social_url)
                    if bot_emails:
                        return bot_emails[0]
            except Exception:
                pass

        if platform == "facebook":
            clean_soc = social_url.rstrip("/")
            if not clean_soc.endswith("/about"):
                about_url = f"{clean_soc}/about"
                try:
                    sub_resp = requests.get(about_url, headers=headers, timeout=timeout, allow_redirects=True, verify=False)
                    if sub_resp.status_code == 200 and sub_resp.text:
                        sub_emails = extract_emails_from_html(sub_resp.text, sub_resp.url or about_url)
                        if sub_emails:
                            return sub_emails[0]
                except Exception:
                    pass

            p = urlsplit(social_url)
            mobile_url = urlunsplit(("https", "m.facebook.com", p.path, p.query, ""))
            try:
                mob_resp = requests.get(
                    mobile_url,
                    headers={"User-Agent": MOBILE_UA, "Accept": "text/html"},
                    timeout=timeout,
                    allow_redirects=True,
                    verify=False,
                )
                if mob_resp.status_code == 200 and mob_resp.text:
                    mob_emails = extract_emails_from_html(mob_resp.text, mob_resp.url or mobile_url)
                    if mob_emails:
                        return mob_emails[0]
            except Exception:
                pass

    except Exception as e:
        logger.debug("Error crawling %s profile %s: %s", platform, social_url, e)

    return None


def crawl_contractor_for_email(
    website_url: Optional[str] = None,
    social_urls: Optional[List[str]] = None,
    timeout: float = 8.0,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Enhanced contractor email crawl workflow conforming strictly to requirements:
    1. Check if the contractor website is provided. If so, visit the website and crawl
       homepage + contact/about pages for email.
    2. Collect any social media profiles (Facebook, Instagram, LinkedIn, etc.) found
       on the website or on the Blue Book contractor page.
    3. If email is not found on the website, crawl discovered social media profiles
       to extract the contractor's email.

    Returns:
        (email, metadata) where metadata contains:
        - "email_source": str describing provenance (e.g. 'website_crawl', 'social_crawl:instagram')
        - "socials": list of all discovered social profile URLs
        - "website": validated official website URL
    """
    valid_web_url = clean_website_url(website_url)
    metadata: Dict[str, Any] = {
        "email_source": None,
        "socials": [],
        "website": valid_web_url,
    }

    discovered_email: Optional[str] = None
    all_social_set: Set[str] = set()

    if social_urls:
        for s in social_urls:
            cleaned_s = clean_social_url(s)
            if cleaned_s:
                all_social_set.add(cleaned_s)

    if valid_web_url:
        logger.debug("Visiting contractor website: %s", valid_web_url)
        web_email, web_socials = crawl_website_for_email_and_social(valid_web_url, timeout=timeout)
        if web_email:
            discovered_email = web_email
            metadata["email_source"] = "website_crawl"
            logger.info("Email discovered on contractor website %s: %s", valid_web_url, discovered_email)

        for plat, links in web_socials.items():
            for link in links:
                all_social_set.add(link)

    if not discovered_email and all_social_set:
        logger.info("No email on website. Crawling %d social profile(s) for email...", len(all_social_set))

        def platform_priority(url: str) -> int:
            plat = detect_social_platform(url)
            if plat == "instagram":
                return 0
            if plat == "facebook":
                return 1
            if plat == "linkedin":
                return 2
            if plat == "twitter":
                return 3
            return 4

        sorted_socials = sorted(list(all_social_set), key=platform_priority)

        for s_url in sorted_socials[:3]:
            platform = detect_social_platform(s_url) or "social"
            logger.debug("Crawling %s profile for email: %s", platform, s_url)
            soc_email = crawl_social_profile_for_email(platform, s_url, timeout=timeout)
            if soc_email:
                discovered_email = soc_email
                metadata["email_source"] = f"social_crawl:{platform}"
                logger.info("Email discovered on %s profile (%s): %s", platform, s_url, discovered_email)
                break

    metadata["socials"] = sorted(list(all_social_set))
    return discovered_email, metadata

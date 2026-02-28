import csv
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
import tldextract
from bs4 import BeautifulSoup

EVIDENCE_DIR = "evidence_packs"
SNAPSHOT_DIR = "snapshots"
REPORT_JSON = "docs/report.json"
DISCOVERY_JSON = "docs/discovery.json"

USER_AGENT = "NumeLeadEngine/1.0"
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)

CONTACT_PATHS = [
    "/contact", "/contact-us", "/contactus",
    "/help", "/support",
    "/press", "/pr",
    "/wholesale", "/stockists",
    "/about"
]

WATCH_PATH_HINTS = [
    "/products", "/shop", "/collections",
    "/press", "/journal", "/blog",
    "/careers", "/jobs",
    "/contact"
]

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def ensure_dirs():
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    os.makedirs("docs", exist_ok=True)

def fetch(url: str, timeout: int = 25) -> str:
    if not url:
        return ""
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.text

def clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:120000]

def slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", (s or "").lower()).strip("_")

def same_registered_domain(a: str, b: str) -> bool:
    try:
        ea = tldextract.extract(a)
        eb = tldextract.extract(b)
        return (ea.domain, ea.suffix) == (eb.domain, eb.suffix)
    except Exception:
        return False

def extract_external_links(html: str, base_url: str):
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        u = urljoin(base_url, href)
        if u.startswith("mailto:"):
            continue
        if u.startswith("http://") or u.startswith("https://"):
            links.add(u)
    return list(links)

def guess_official_site_from_article(article_url: str):
    """
    Opens the news article and attempts to find an external link that looks like a brand site.
    Heuristic: first external link that's not the publisher's registered domain.
    """
    try:
        html = fetch(article_url)
        links = extract_external_links(html, article_url)

        pub_domain = urlparse(article_url).netloc
        pub_base = f"https://{pub_domain}"

        for u in links:
            # skip same publisher domain
            if same_registered_domain(u, pub_base):
                continue

            # skip obvious social / trackers
            low = u.lower()
            if any(x in low for x in ["facebook.com", "instagram.com", "linkedin.com", "tiktok.com", "twitter.com", "x.com", "youtube.com", "pinterest.com"]):
                continue
            if any(x in low for x in ["doubleclick", "utm_", "google.com", "goo.gl"]):
                continue

            # accept first plausible
            return u.split("#")[0].split("?")[0].rstrip("/")
    except Exception:
        return ""
    return ""

def find_contact_methods(site_url: str):
    """
    def find_contact_methods(site_url: str):
    """
    Legal + brand-owned only:
    - crawls a few internal pages likely to contain contact/pr emails
    - uses sitemap.xml when available
    - extracts normal + obfuscated emails
    - finds contact page URLs even when forms are embedded externally
    """
    out = {"primary_email": "", "other_emails": [], "contact_form_url": "", "checked_pages": []}
    if not site_url:
        return out

    base = site_url.rstrip("/")
    found = set()

    def add_emails_from_text(text: str):
        OBFUSCATED_AT_RE = re.compile(r"([A-Z0-9._%+-]+)\s*(?:\[at\]|\(at\)|\sat\s)\s*([A-Z0-9.-]+)\s*(?:\[dot\]|\(dot\)|\sdot\s|\.)\s*([A-Z]{2,})", re.IGNORECASE)
CONTACT_KEYWORDS = ["contact", "press", "pr", "media", "wholesale", "stockist", "support", "help", "partnership", "collab"]

    def is_internal(u: str) -> bool:
        return same_registered_domain(u, base)

    def norm(u: str) -> str:
        return u.split("#")[0].strip()

    candidates = []

    # 1) Known likely paths
    for p in CONTACT_PATHS:
        candidates.append(urljoin(base + "/", p.lstrip("/")))

    # 2) Homepage scan: pick up footer/header internal links with contact-ish words
    try:
        html = fetch(base)
        soup = BeautifulSoup(html, "html.parser")

        add_emails_from_text(html)

        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            if not href:
                continue

            if href.startswith("mailto:"):
                email = href.replace("mailto:", "").split("?")[0].strip()
                if email:
                    found.add(email)
                continue

            u = norm(urljoin(base, href))
            anchor = (a.get_text(" ") or "").strip().lower()

            # If link text or URL looks contact-ish, add it
            if is_internal(u) and any(k in (u.lower() + " " + anchor) for k in CONTACT_KEYWORDS):
                candidates.append(u)

    except Exception:
        pass

    # 3) Sitemap: super reliable for finding hidden contact/press URLs
    sitemap_urls = [urljoin(base + "/", "sitemap.xml"), urljoin(base + "/", "sitemap_index.xml")]
    for sm in sitemap_urls:
        try:
            xml = fetch(sm)
            out["checked_pages"].append(sm)
            # quick parse: find <loc> URLs
            locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", xml, flags=re.IGNORECASE)
            for u in locs[:800]:  # cap
                u = norm(u)
                low = u.lower()
                if is_internal(u) and any(k in low for k in ["contact", "press", "pr", "media", "wholesale", "stockist", "support"]):
                    candidates.append(u)
            break
        except Exception:
            continue

    # Deduplicate + cap work
    uniq = []
    for u in candidates:
        u = norm(u)
        if u and u not in uniq and is_internal(u):
            uniq.append(u)
    candidates = uniq[:14]  # increase a bit; still polite

    contact_page_candidate = ""

    # 4) Crawl candidate pages and extract emails / find contact page URL
    for url in candidates:
        try:
            html = fetch(url)
            out["checked_pages"].append(url)

            add_emails_from_text(html)

            soup = BeautifulSoup(html, "html.parser")
            # mailto links on that page
            for a in soup.select("a[href^='mailto:']"):
                href = a.get("href", "")
                email = href.replace("mailto:", "").split("?")[0].strip()
                if email:
                    found.add(email)

            # Mark a contact page even if no <form> tag
            # Many sites embed forms via external scripts. If page has typical “contact” cues, we accept the page URL.
            low = url.lower()
            page_text = (soup.get_text(" ") or "").lower()
            if not contact_page_candidate and ("contact" in low or "contact" in page_text):
                contact_page_candidate = url

            time.sleep(0.6)
        except Exception:
            continue

    emails = sorted(found)

    # Prefer role-based inboxes (what you want for outreach)
    preferred_order = [
        "press@", "pr@", "media@", "partnership", "collab",
        "hello@", "info@", "contact@", "wholesale", "sales@",
        "support@", "care@", "team@"
    ]

    primary = ""
    for pref in preferred_order:
        for e in emails:
            if pref in e.lower():
                primary = e
                break
        if primary:
            break
    if not primary and emails:
        primary = emails[0]

    out["primary_email"] = primary
    out["other_emails"] = [e for e in emails if e != primary][:10]
    out["contact_form_url"] = contact_page_candidate  # treat as contact route even if form is embedded

    return out

    # also add any footer/header contact-ish links from homepage
    try:
        html = fetch(base)
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            if href.startswith("mailto:"):
                email = href.replace("mailto:", "").split("?")[0].strip()
                if email:
                    out["other_emails"].append(email)
            else:
                u = urljoin(base, href)
                if same_registered_domain(u, base) and any(k in u.lower() for k in ["contact", "press", "support", "help", "wholesale"]):
                    candidates.append(u)
    except Exception:
        pass

    # de-dupe, limit
    uniq = []
    for c in candidates:
        if c and c not in uniq and same_registered_domain(c, base):
            uniq.append(c)
    candidates = uniq[:10]

    found = set(out["other_emails"])
    contact_form = ""

    for url in candidates:
        try:
            html = fetch(url)
            out["checked_pages"].append(url)

            for m in EMAIL_RE.findall(html):
                found.add(m)

            soup = BeautifulSoup(html, "html.parser")
            for a in soup.select("a[href^='mailto:']"):
                href = a.get("href", "")
                email = href.replace("mailto:", "").split("?")[0].strip()
                if email:
                    found.add(email)

            if not contact_form and any(k in url.lower() for k in ["contact", "support", "help"]):
                if soup.select("form"):
                    contact_form = url

            time.sleep(0.6)
        except Exception:
            continue

    emails = sorted(found)
    preferred_order = ["hello@", "info@", "press@", "pr@", "partnership", "collab", "wholesale", "support@", "care@", "team@"]

    primary = ""
    for pref in preferred_order:
        for e in emails:
            if pref in e.lower():
                primary = e
                break
        if primary:
            break
    if not primary and emails:
        primary = emails[0]

    others = [e for e in emails if e != primary][:8]
    out["primary_email"] = primary
    out["other_emails"] = others
    out["contact_form_url"] = contact_form
    return out

def build_page_set(site_url: str):
    """
    Try a few standard pages without being too heavy.
    """
    if not site_url:
        return {}

    base = site_url.rstrip("/")
    pages = {"homepage": base}

    # add some likely pages
    for p in WATCH_PATH_HINTS:
        url = urljoin(base + "/", p.lstrip("/"))
        pages[p.strip("/").replace("-", "_")] = url

    # de-dupe by url
    seen = set()
    final = {}
    for k, u in pages.items():
        if u not in seen:
            seen.add(u)
            final[k] = u
    # limit total fetches
    keys = list(final.keys())[:6]
    return {k: final[k] for k in keys}

def hash_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

def load_snapshot(brand: str, label: str):
    path = os.path.join(SNAPSHOT_DIR, f"{slug(brand)}__{label}.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_snapshot(brand: str, label: str, data: dict):
    path = os.path.join(SNAPSHOT_DIR, f"{slug(brand)}__{label}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def score_brand(evidence: dict) -> dict:
    """
    Free-only scoring:
    - has_contact is weighted heavily
    - news count matters
    - site fetched pages that exist matters
    - change detection matters for brands already seen (snapshots)
    """
    score = 0
    reasons = []

    contact = evidence.get("contact", {})
    has_contact = bool(contact.get("primary_email") or contact.get("contact_form_url"))
    if has_contact:
        score += 35
        reasons.append("Contact method found")

    news = evidence.get("news_mentions", [])
    if news:
        score += min(25, 6 * len(news))
        reasons.append(f"{len(news)} news mention(s)")

    site = evidence.get("site", {})
    fetched = site.get("fetched_pages", {})
    if fetched:
        score += min(20, 4 * len(fetched))
        reasons.append(f"{len(fetched)} site page(s) captured")

    changes = site.get("change_flags", [])
    if changes:
        score += min(20, 10 * len(changes))
        reasons.append("Site changed since last check")

    evidence["score"] = min(100, score)
    evidence["score_reasons"] = reasons
    evidence["has_contact"] = has_contact
    return evidence

def load_discovery_candidates():
    if not os.path.exists(DISCOVERY_JSON):
        return []
    with open(DISCOVERY_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("candidates", [])

def load_watchlist():
    watch = []
    if not os.path.exists("brands.csv"):
        return watch
    with open("brands.csv", "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            brand = (row.get("brand") or "").strip()
            site = (row.get("website") or "").strip()
            if brand and site:
                watch.append({"brand_guess": brand, "website": site, "evidence_link": "", "matched_query": "watchlist"})
    return watch

def run():
    ensure_dirs()

    candidates = load_discovery_candidates()
    watchlist = load_watchlist()

    # Merge (watchlist first)
    merged = []
    seen_brand = set()
    for item in watchlist + candidates:
        brand = (item.get("brand_guess") or item.get("brand") or "").strip()
        if not brand:
            continue
        key = slug(brand)
        if key in seen_brand:
            continue
        seen_brand.add(key)
        merged.append(item)

    report = {
        "generated_at": now_iso(),
        "brands": []
    }

    # Limit how many articles we open for website guessing
    with open("discovery.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)
    max_articles_to_open = int(cfg.get("limits", {}).get("max_articles_to_open", 30))
    opened_articles = 0

    for item in merged:
        brand_guess = (item.get("brand_guess") or item.get("brand") or "").strip()
        evidence_link = (item.get("evidence_link") or "").strip()
        matched_query = (item.get("matched_query") or "watchlist").strip()

        website = (item.get("website") or "").strip()
        if not website and evidence_link and opened_articles < max_articles_to_open:
            website = guess_official_site_from_article(evidence_link)
            opened_articles += 1

        # Normalize website root
        if website:
            try:
                p = urlparse(website)
                website = f"{p.scheme}://{p.netloc}".rstrip("/")
            except Exception:
                pass

        evidence = {
            "brand_name": brand_guess,
            "matched_query": matched_query,
            "evidence_link": evidence_link,
            "website": website,
            "news_mentions": [],
            "contact": {"primary_email": "", "other_emails": [], "contact_form_url": "", "checked_pages": []},
            "site": {"pages": {}, "fetched_pages": {}, "change_flags": []},
            "generated_at": now_iso()
        }

        # News mentions: reuse discovery evidence_link + a couple more items would be nice,
        # but free-only: keep it light and just include the evidence_link as the "recent" mention.
        if evidence_link:
            evidence["news_mentions"].append({"title": item.get("title", ""), "link": evidence_link, "published": item.get("published", "")})

        # Site evidence + change detection
        if website:
            pages = build_page_set(website)
            evidence["site"]["pages"] = pages

            for label, url in pages.items():
                try:
                    html = fetch(url)
                    text = clean_text(html)
                    h = hash_text(text)

                    prev = load_snapshot(brand_guess, label)
                    prev_hash = prev.get("hash")
                    changed = (prev_hash is not None and prev_hash != h)
                    if changed:
                        evidence["site"]["change_flags"].append(label)

                    save_snapshot(brand_guess, label, {
                        "brand": brand_guess,
                        "label": label,
                        "url": url,
                        "hash": h,
                        "updated_at": now_iso()
                    })

                    # store short snippet for LLM pack
                    evidence["site"]["fetched_pages"][label] = {
                        "url": url,
                        "snippet": text[:700]
                    }

                    time.sleep(0.8)
                except Exception:
                    continue

            # Contacts
            try:
                evidence["contact"] = find_contact_methods(website)
            except Exception:
                pass

        # Score
        evidence = score_brand(evidence)

        # Save evidence pack file
        pack_path = os.path.join(EVIDENCE_DIR, f"{slug(brand_guess)}.json")
        with open(pack_path, "w", encoding="utf-8") as f:
            json.dump(evidence, f, ensure_ascii=False, indent=2)

        report["brands"].append(evidence)

        time.sleep(0.2)

    # Sort by score (desc)
    report["brands"].sort(key=lambda x: (x.get("has_contact", False), x.get("score", 0)), reverse=True)

    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Wrote {REPORT_JSON} with {len(report['brands'])} evidence pack(s). Opened {opened_articles} article(s).")

if __name__ == "__main__":
    run()

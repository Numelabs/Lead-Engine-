import csv
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus, urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

USER_AGENT = "NumeLeadEngine/1.0"
SNAPSHOT_DIR = "snapshots"
OUTPUT_JSON = os.path.join("docs", "report.json")

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)

CONTACT_PATHS = [
    "/contact", "/contact-us", "/contactus",
    "/help", "/support",
    "/press", "/pr",
    "/wholesale", "/stockists", "/retailers",
    "/about", "/company"
]

def ensure_dirs():
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    os.makedirs("docs", exist_ok=True)

def fetch_url(url: str, timeout: int = 25) -> str:
    if not url:
        return ""
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text

def clean_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:200000]

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

def safe_slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", s.lower()).strip("_")

def snapshot_path(brand: str, label: str) -> str:
    return os.path.join(SNAPSHOT_DIR, f"{safe_slug(brand)}__{label}.json")

def load_snapshot(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_snapshot(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def google_news_rss(query: str, max_items: int = 5):
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-GB&gl=GB&ceid=GB:en"
    feed = feedparser.parse(url)
    items = []
    for e in feed.entries[:max_items]:
        items.append({
            "title": getattr(e, "title", ""),
            "link": getattr(e, "link", ""),
            "published": getattr(e, "published", "")
        })
    return items

def same_domain(url: str, base: str) -> bool:
    try:
        return urlparse(url).netloc.endswith(urlparse(base).netloc)
    except Exception:
        return False

def extract_contact_methods(base_url: str):
    """
    Only checks brand-owned pages on same domain.
    Extracts:
      - role-based emails if present
      - contact form URL
    """
    if not base_url:
        return {"primary_email": "", "other_emails": [], "contact_form_url": "", "checked_pages": []}

    checked = []
    found_emails = set()
    contact_form = ""

    # candidate URLs
    candidates = [base_url.rstrip("/")]
    for p in CONTACT_PATHS:
        candidates.append(urljoin(base_url.rstrip("/") + "/", p.lstrip("/")))

    # also check homepage footer links
    try:
        html = fetch_url(base_url)
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a[href]"):
            href = a.get("href", "").strip()
            if not href:
                continue
            if href.startswith("mailto:"):
                email = href.replace("mailto:", "").split("?")[0].strip()
                if email:
                    found_emails.add(email)
            else:
                u = urljoin(base_url, href)
                if same_domain(u, base_url) and any(k in u.lower() for k in ["contact", "press", "support", "help", "wholesale"]):
                    candidates.append(u)
    except Exception:
        pass

    # Deduplicate, limit work
    uniq = []
    for c in candidates:
        if c and c not in uniq:
            uniq.append(c)
    candidates = uniq[:8]  # keep it light

    for url in candidates:
        if not same_domain(url, base_url):
            continue
        try:
            html = fetch_url(url)
            checked.append(url)

            # emails in text + mailto
            for m in EMAIL_RE.findall(html):
                found_emails.add(m)

            soup = BeautifulSoup(html, "html.parser")
            for a in soup.select("a[href^='mailto:']"):
                href = a.get("href", "")
                email = href.replace("mailto:", "").split("?")[0].strip()
                if email:
                    found_emails.add(email)

            # contact form heuristic
            if not contact_form:
                for form in soup.select("form[action]"):
                    # if there is a form on a contact-ish page, treat page as form URL
                    if any(k in url.lower() for k in ["contact", "support", "help"]):
                        contact_form = url
                        break

            time.sleep(0.8)
        except Exception:
            continue

    # Prefer role-based inboxes
    preferred_order = ["hello@", "info@", "press@", "pr@", "partnership", "collab", "wholesale", "support@", "care@", "team@"]

    emails = sorted(found_emails)
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

    return {
        "primary_email": primary,
        "other_emails": others,
        "contact_form_url": contact_form,
        "checked_pages": checked
    }

def score_signals(changes: list, news_items: list, has_ads: bool):
    score = 0
    reasons = []

    for c in changes:
        if c.get("changed"):
            if c["label"] == "homepage":
                score += 25; reasons.append("Homepage changed")
            elif c["label"] == "product":
                score += 30; reasons.append("Product page changed")
            elif c["label"] == "careers":
                score += 20; reasons.append("Careers changed")
            elif c["label"] == "press":
                score += 15; reasons.append("Press changed")
            else:
                score += 10; reasons.append(f"{c['label']} changed")

    if news_items:
        score += min(25, 8 * len(news_items))
        reasons.append(f"{len(news_items)} news mention(s)")

    if has_ads:
        score += 25
        reasons.append("Meta ads likely active")

    return min(100, score), reasons

def meta_ads_signal_stub(brand_name: str) -> bool:
    """
    Free-only version: we won't call paid APIs.
    For now, this is a placeholder you can later upgrade.
    We'll keep it False in v1 to avoid pretending.
    """
    return False

def pitch_from_signals(changes, news_items, has_ads):
    if has_ads:
        return "Performance creative refresh: new ad-ready variants + testing angles."
    if any(c.get("label") == "product" and c.get("changed") for c in changes):
        return "Launch moment: fast asset sprint (hero + macro + routine tiles + paid crops)."
    if any(c.get("label") == "homepage" and c.get("changed") for c in changes):
        return "Campaign refresh: unify site visuals into a cohesive direction pack."
    if news_items:
        return "PR moment: convert attention into conversion-ready campaign assets."
    return "Creative uplift: stronger product truth + brand-safe visual system."

def run():
    ensure_dirs()
    now_iso = datetime.now(timezone.utc).isoformat()

    brands = []
    with open("brands.csv", "r", encoding="utf-8") as f:
        brands = list(csv.DictReader(f))

    results = []

    for row in brands:
        brand = (row.get("brand") or "").strip()
        homepage = (row.get("homepage") or "").strip()
        product = (row.get("product_page") or "").strip()
        careers = (row.get("careers") or "").strip()
        press = (row.get("press") or "").strip()
        keywords = (row.get("keywords") or "").strip()

        # Change detection
        changes = []
        for label, url in [("homepage", homepage), ("product", product), ("careers", careers), ("press", press)]:
            if not url:
                continue
            snap_file = snapshot_path(brand, label)
            prev = load_snapshot(snap_file)
            prev_hash = prev.get("hash")

            try:
                html = fetch_url(url)
                text = clean_visible_text(html)
                h = sha256_text(text)
                changed = (prev_hash is not None and prev_hash != h)

                save_snapshot(snap_file, {
                    "brand": brand,
                    "label": label,
                    "url": url,
                    "hash": h,
                    "updated_at": now_iso,
                })

                changes.append({"label": label, "url": url, "changed": changed})
                time.sleep(1.0)
            except Exception as ex:
                changes.append({"label": label, "url": url, "changed": False, "error": str(ex)})

        # News mentions
        news_query = brand if not keywords else f"{brand} {keywords}"
        try:
            news_items = google_news_rss(news_query, max_items=5)
        except Exception as ex:
            news_items = [{"title": "News fetch error", "link": "", "published": "", "error": str(ex)}]

        # Meta ads signal (free-only stub right now)
        has_ads = meta_ads_signal_stub(brand)

        # Contact methods
        contact = extract_contact_methods(homepage) if homepage else {"primary_email":"","other_emails":[],"contact_form_url":"","checked_pages":[]}
        has_contact = bool(contact.get("primary_email") or contact.get("contact_form_url"))

        score, reasons = score_signals(changes, news_items, has_ads)
        pitch = pitch_from_signals(changes, news_items, has_ads)

        dm = f"Hi {brand} team. I noticed signals you’re in a campaign/launch window (site/news movement). I run Nume Labs and can deliver a brand-safe asset sprint fast: hero + macro + routine tiles + paid-social crops. If I send 2 tailored visual directions for your current product page, who’s best to speak to?"
        email_subject = f"{brand} | quick campaign sprint idea"
        email = f"""Hi {brand} team,

I’m Numi from Nume Labs. I noticed signs you may be in a campaign/launch window (site/news activity), and I had a quick idea.

I can deliver a tight asset sprint:
- 1 hero direction + alternates
- macro/texture set + routine tiles
- paid-social crops (optional short motion cutdowns)

If you share your priority product + audience, I’ll send 2 tailored creative directions.

Best,
Numi
"""

        results.append({
            "brand": brand,
            "score": score,
            "reasons": reasons,
            "pitch": pitch,
            "links": {"homepage": homepage, "product": product, "careers": careers, "press": press},
            "changes": changes,
            "news": news_items,
            "contact": contact,
            "has_contact": has_contact,
            "outreach": {
                "dm": dm,
                "email_subject": email_subject,
                "email_body": email,
                "preferred_email": contact.get("primary_email", "")
            }
        })

    # sort by score, prefer contact
    results.sort(key=lambda x: (x["has_contact"], x["score"]), reverse=True)

    report = {
        "generated_at": now_iso,
        "top5": results[:5],
        "all": results
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUTPUT_JSON} with {len(results)} brands.")

if __name__ == "__main__":
    run()

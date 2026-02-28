import json
import csv
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser

DISCOVERY_OUT_JSON = "docs/discovery.json"
CANDIDATES_CSV = "candidates.csv"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def google_news_rss(query: str, max_items: int = 10):
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

def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip())

def guess_brand_from_title(title: str) -> str:
    """
    Very light heuristic: take the left side before separators.
    This won't be perfect, but we only need candidates for evidence stage.
    """
    t = normalize_title(title)
    # common separators in headlines
    parts = re.split(r"\s[-–|:]\s", t, maxsplit=1)
    left = parts[0].strip()
    # remove quotes
    left = left.strip("“”\"'")
    # if left is too long, fallback to first 3-5 words
    words = left.split()
    if len(words) > 6:
        left = " ".join(words[:5])
    return left

def run():
    with open("discovery.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    queries = cfg.get("queries", [])
    limits = cfg.get("limits", {})
    per_query = int(limits.get("per_query", 10))
    max_candidates = int(limits.get("max_candidates_per_run", 50))

    seen_links = set()
    candidates = []

    for q in queries:
        items = google_news_rss(q, max_items=per_query)
        for it in items:
            link = it.get("link", "")
            if not link or link in seen_links:
                continue
            seen_links.add(link)

            title = it.get("title", "")
            brand_guess = guess_brand_from_title(title)

            candidates.append({
                "brand_guess": brand_guess,
                "matched_query": q,
                "title": title,
                "evidence_link": link,
                "published": it.get("published", "")
            })

            if len(candidates) >= max_candidates:
                break

        if len(candidates) >= max_candidates:
            break

        time.sleep(0.2)

    payload = {
        "generated_at": now_iso(),
        "candidate_count": len(candidates),
        "candidates": candidates
    }

    # write discovery.json for dashboard
    with open(DISCOVERY_OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # write candidates.csv for quick review
    with open(CANDIDATES_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["brand_guess", "matched_query", "title", "evidence_link", "published"])
        w.writeheader()
        for c in candidates:
            w.writerow(c)

    print(f"Wrote {DISCOVERY_OUT_JSON} and {CANDIDATES_CSV} with {len(candidates)} candidates.")

if __name__ == "__main__":
    run()

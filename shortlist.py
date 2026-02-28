import json
import os
from datetime import datetime, timezone

REPORT_JSON = "docs/report.json"
SHORTLIST_JSON = "docs/shortlist.json"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def has_website(b: dict) -> bool:
    site = (b.get("website") or "").strip()
    return bool(site) and site.startswith(("http://", "https://"))

def has_contact(b: dict) -> bool:
    c = b.get("contact") or {}
    email = (c.get("primary_email") or "").strip()
    form = (c.get("contact_form_url") or "").strip()
    return bool(email or form)

def run():
    if not os.path.exists(REPORT_JSON):
        raise SystemExit("Missing docs/report.json. Run discovery.py then evidence.py first.")

    with open(REPORT_JSON, "r", encoding="utf-8") as f:
        report = json.load(f)

    brands = report.get("brands", [])

    # HARD FILTER: must have website + contact
    actionable = [b for b in brands if has_website(b) and has_contact(b)]

    # Rank by score (desc)
    actionable.sort(key=lambda x: x.get("score", 0), reverse=True)

    top = actionable[:10]

    out = {
        "generated_at": now_iso(),
        "rules": {
            "requires_website": True,
            "requires_contact": True
        },
        "total_seen": len(brands),
        "total_actionable": len(actionable),
        "count": len(top),
        "shortlist": top
    }

    with open(SHORTLIST_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {SHORTLIST_JSON} with {len(top)} actionable brands (out of {len(brands)}).")

if __name__ == "__main__":
    run()

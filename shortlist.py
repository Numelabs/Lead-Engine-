import json
import os
from datetime import datetime, timezone

REPORT_JSON = "docs/report.json"
SHORTLIST_JSON = "docs/shortlist.json"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def run():
    if not os.path.exists(REPORT_JSON):
        raise SystemExit("Missing docs/report.json. Run discovery.py then evidence.py first.")

    with open(REPORT_JSON, "r", encoding="utf-8") as f:
        report = json.load(f)

    brands = report.get("brands", [])

    # Shortlist rules:
    # - Prefer contact present
    # - High score
    # - Keep it to top 10
    top = brands[:10]

    out = {
        "generated_at": now_iso(),
        "count": len(top),
        "shortlist": top
    }

    with open(SHORTLIST_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {SHORTLIST_JSON} with {len(top)} brands.")

if __name__ == "__main__":
    run()

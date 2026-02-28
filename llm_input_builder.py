import json
import os
from datetime import datetime, timezone

SHORTLIST_JSON = "docs/shortlist.json"
DISCOVERY_CFG = "discovery.json"
OFFERS_JSON = "offers.json"
LLM_MD = "docs/LLM_INPUT.md"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def run():
    if not os.path.exists(SHORTLIST_JSON):
        raise SystemExit("Missing docs/shortlist.json. Run shortlist.py first.")

    with open(SHORTLIST_JSON, "r", encoding="utf-8") as f:
        shortlist = json.load(f).get("shortlist", [])

    with open(DISCOVERY_CFG, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    with open(OFFERS_JSON, "r", encoding="utf-8") as f:
        offers = json.load(f).get("offers", [])

    # Your strategist meta-prompt (kept stable)
    meta_prompt = f"""You are a senior cultural strategist + creative director hired to spot brand opportunities worth £1K–£5K. You combine market intelligence, aesthetic literacy, and AI-assisted execution speed. Your tone is that of a London-level creative agency: concise, culturally aware, insight-led, never “prompty.”

USER INPUT VARIABLES
{{industry}} Beauty (skincare, makeup, fragrance, fashion where relevant)
{{region}} London / UK
{{target_budget}} £1K–£2K
{{offer}} AI-enabled visual campaigns / creative direction

INSTRUCTION SET
Step 1 – Identify Budget-Qualified Brands (use the evidence provided; do not browse)
Pick 10 brands from the shortlist. They must:
- show recent activity (site changes and/or press/news)
- display production value suggesting £1K–£2K creative spends
- have a strong identity but visible creative gaps (repetition, weak emotion, weak cultural alignment)

Output for each brand:
• Brand Name • Website • Instagram (if known) • Recent Campaign/Activity (from evidence) • Est. Budget Tier • Why they’re a fit

Step 2 – Brand Intelligence Summary
For each brand:
- Audience & positioning snapshot
- Visual identity notes (tone, palette, aesthetic codes)
- Cultural relevance notes (what they’re referencing or missing)
- One clear brand tension (e.g., “minimalism vs sensuality,” “heritage vs future”)

Step 3 – Cultural Intervention Ideas (3 per brand)
Generate three high-level creative directions. Each should read like a campaign platform, not a moodboard:
1️⃣ Concept Title (2–4 words, evocative & ownable)
⚡ Cultural Insight (real behaviour/tension)
💡 Brand Opportunity
🎨 Expression Direction (photography/motion/material/symbolism)
🧰 Execution Hint (a 10–15 min AI visual you could build)

Step 4 – Strategic Outreach Message
One message per brand (DM or email):
- Observation (specific to evidence)
- Cultural opportunity
- Vision tease (use one concept title)
- CTA (low friction)

Step 5 – Prioritisation
Rank 1–10 for:
- Budget fit
- Creative gap size
- Ease of contact
Highlight top 3 + recommended channel (email/DM/LinkedIn) with justification.

STYLE GUIDE
Write like a strategist, not a prompt engineer.
Reference culture (wellness economy, digital intimacy, luxury signalling, ritual behaviour, post-influencer aesthetics, etc.)
Avoid generic phrasing (“futuristic,” “vibrant,” “moody”).
Keep language punchy, clear, senior.
"""

    # Offer presets (so the strategist output stays grounded)
    offer_block = "OFFER PRESETS (choose the best fit per brand):\n"
    for o in offers:
        offer_block += f"- {o['name']}: {o['best_for']} Timeline: {o['timeline']}. Deliverables: {', '.join(o['deliverables'])}\n"

    # Evidence packs (compact, consistent)
    evidence_block = "EVIDENCE SHORTLIST (do not browse; only use this):\n\n"
    for i, b in enumerate(shortlist, start=1):
        contact = b.get("contact", {})
        site = b.get("site", {})
        fetched = site.get("fetched_pages", {})
        change_flags = site.get("change_flags", [])

        evidence_block += f"=== BRAND {i} ===\n"
        evidence_block += f"Name: {b.get('brand_name','')}\n"
        evidence_block += f"Website: {b.get('website','')}\n"
        evidence_block += f"Discovery query: {b.get('matched_query','')}\n"
        evidence_block += f"Evidence link: {b.get('evidence_link','')}\n"
        evidence_block += f"Score: {b.get('score',0)} Reasons: {', '.join(b.get('score_reasons',[]))}\n"
        evidence_block += f"Site changed flags: {', '.join(change_flags) if change_flags else 'None'}\n"

        primary_email = contact.get("primary_email", "")
        form = contact.get("contact_form_url", "")
        evidence_block += f"Contact: email={primary_email or 'None'} form={form or 'None'}\n"

        news = b.get("news_mentions", [])
        if news:
            evidence_block += "News mentions:\n"
            for n in news[:3]:
                evidence_block += f"- {n.get('title','')}\n  {n.get('link','')}\n"
        else:
            evidence_block += "News mentions: None\n"

        # include up to 2 page snippets
        snips = []
        for k in ["homepage", "products", "press", "careers", "contact"]:
            if k in fetched:
                snips.append((k, fetched[k].get("url",""), fetched[k].get("snippet","")))
        if snips:
            evidence_block += "Site snippets:\n"
            for k, url, sn in snips[:2]:
                evidence_block += f"- {k} ({url})\n  {sn}\n"
        evidence_block += "\n"

    final = f"""# Nume Lead Engine → LLM Input
Generated at: {now_iso()}

{meta_prompt}

{offer_block}

{evidence_block}
"""

    with open(LLM_MD, "w", encoding="utf-8") as f:
        f.write(final)

    print(f"Wrote {LLM_MD} (copy-paste this into ChatGPT).")

if __name__ == "__main__":
    run()

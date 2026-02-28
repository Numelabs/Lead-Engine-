# Nume Lead Engine (Free-Only)

This repo runs a daily pipeline (free) using GitHub Actions and shows a dark dashboard on GitHub Pages.

## What it does
1) Discover UK/London beauty/fashion/makeup/fragrance brands via Google News RSS queries
2) Build evidence packs by:
   - extracting a likely official website
   - fetching key pages (home/product/press/careers/contact)
   - extracting public contact emails/contact forms
   - collecting news mentions
3) Rank + shortlist top 10 leads
4) Generate docs/LLM_INPUT.md to paste into ChatGPT for strategist-grade output

## How to run manually
GitHub repo → Actions → "Daily Run" → Run workflow.

## GitHub Pages
Repo Settings → Pages → Deploy from branch → main → /docs

## Inputs you edit
- discovery.json (your queries)
- offers.json (your offer presets)
- brands.csv (optional: approved brands you always want monitored)

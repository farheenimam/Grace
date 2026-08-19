# Grace

A full-stack hackathon aggregator PWA. Scrapes multiple hackathon platforms, stores results in a Postgres database, and notifies users when new hackathons are announced.

**Live:** https://sparkling-caramel-f4396e.netlify.app or https://farheenimam.github.io/grace/
**Repo:** https://github.com/farheenimam/grace

---

## Features

**Aggregation**
- Pulls hackathons from 8 platforms: Devpost, dev.to, lablab.ai, MLH, HackerEarth, DoraHacks, Google Developers, Kaggle
- Matches against 100+ keywords beyond "hackathon" — catches non-standard names like game jams, GSoC, build challenges, Imagine Cup, Code Jam
- URL-hash deduplication — no repeat entries across scraper runs
- Automated scraping every 4 hours via GitHub Actions cron

**Frontend (PWA)**
- Installable as a native-like app (install prompt)
- Offline support via service worker + caching
- Responsive layout — bottom nav on mobile, sidebar on desktop
- No framework — pure HTML/CSS/JS, fast load times

**Backend / Data**
- Native Python handler on Netlify Functions (no FastAPI/Mangum — avoids serverless cold-start/routing issues)
- Supabase Postgres via Transaction Pooler for connection efficiency
- REST-style JSON API serving live scraped data

**Notifications**
- Email alerts via Gmail SMTP
- Push notifications via Firebase

---

## Architecture

```
GitHub Actions (cron, every 4h)
        │
        ▼
   7 scrapers ──► Supabase Postgres (dedup via URL hash)
        │
        ▼
Netlify Function (api.py, native handler) ──► JSON API
        │
        ▼
Frontend PWA ──► fetch + render ──► service worker cache (offline)
```

---

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python (native handler), Netlify Functions |
| Database | Supabase Postgres (Transaction Pooler) |
| Frontend | HTML/CSS/JS, Service Worker, Web App Manifest |
| Hosting | Netlify (static + serverless) |
| Automation | GitHub Actions |
| Email | Gmail SMTP |
| Push | Firebase |

---

## Setup

**Prerequisites:** Python 3.9+, Supabase project, Netlify account, GitHub repo with Actions enabled

**1. Clone**
```bash
git clone https://github.com/farheenimam/Grace.git
cd Grace
```

**2. Install deps**
```bash
pip install -r requirements.txt
```

**3. Env vars** — set in both GitHub Secrets and Netlify Environment Variables:
```
DATABASE_URL=postgresql://postgres.[project-id]:[PASSWORD]@aws-1-ap-south-1.pooler.supabase.com:5432/postgres
```

**4. Run scrapers locally**
```bash
python scrapers/run_all.py
```

**5. Deploy**
Push to `main` — Netlify auto-builds frontend and functions. GitHub Actions handles the scraper cron independently.

---

## Project structure

```
Grace/
├── netlify/
│   └── functions/
│       └── api.py          # serverless API, native Python handler
├── scrapers/
│   ├── devpost.py
│   ├── devto.py
│   ├── lablab.py
│   ├── mlh.py
│   ├── hackerearth.py
│   ├── dorahacks.py
│   ├── google_dev.py
│   └── run_all.py
├── frontend/
│   ├── index.html
│   ├── sw.js                # service worker
│   ├── manifest.json
│   ├── css/
│   └── js/
├── .github/
│   └── workflows/
│       └── scrape.yml       # cron job, every 4h
├── requirements.txt
└── README.md
```

---

## API

Base: `/api`

| Endpoint | Method | Description |
|---|---|---|
| `/api/hackathons` | GET | List all active hackathons |
| `/api/hackathons?source=devpost` | GET | Filter by platform |

Returns JSON array of hackathon objects (title, url, platform, deadline, tags).

---

## Known issues

- MLH scraper occasionally surfaces ended events — needs date-filtering fix
- Stale/ended hackathons require periodic manual cleanup via Supabase SQL Editor

## Roadmap

- Fix MLH scraper to filter active-only events
- Automate stale-record cleanup (scheduled SQL job)
- Add more platforms

## Requirements

```
psycopg2-binary==2.9.9
```

## License

MIT

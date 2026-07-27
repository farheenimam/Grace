import requests, os

USERNAME = os.getenv("KAGGLE_USERNAME", "")
API_KEY = os.getenv("KAGGLE_KEY", "")
HEADERS = {"User-Agent": "HackTracker/2.0", "Accept": "application/json"}

def scrape_kaggle():
    hackathons = []
    if not USERNAME or not API_KEY:
        print("[Kaggle] Skipped — KAGGLE_USERNAME/KAGGLE_KEY not set")
        return hackathons
    seen = set()
    for page in range(1, 6):
        try:
            r = requests.get(
                "https://www.kaggle.com/api/v1/competitions/list",
                auth=(USERNAME, API_KEY),
                headers=HEADERS,
                params={"page": page, "sortBy": "latestDeadline"},
                timeout=15,
            )
            r.raise_for_status()
            items = r.json()
            if not items or not isinstance(items, list):
                break
            for c in items:
                ref = c.get("ref") or c.get("id") or ""
                title = c.get("title") or ""
                if not ref or not title:
                    continue
                url = f"https://www.kaggle.com/competitions/{ref}" if not str(ref).startswith("http") else ref
                if url in seen:
                    continue
                seen.add(url)
                deadline = (c.get("deadline") or "")[:10] or "TBD"
                reward = c.get("reward") or "See competition page"
                desc = c.get("description") or "Kaggle competition"
                hackathons.append({
                    "source": "Kaggle",
                    "title": title,
                    "url": url,
                    "deadline": deadline,
                    "prize": reward,
                    "thumbnail": "",
                    "description": desc[:200],
                    "status": "open",
                })
            if len(items) < 20:
                break
        except Exception as e:
            print(f"[Kaggle] page {page}: {e}")
            break
    print(f"[Kaggle] {len(hackathons)} competitions")
    return hackathons

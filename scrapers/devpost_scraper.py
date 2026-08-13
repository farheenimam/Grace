import requests, time
from bs4 import BeautifulSoup

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Referer": "https://devpost.com/hackathons",
}
JSON_HEADERS = {**BASE_HEADERS, "Accept": "application/json, text/javascript, */*; q=0.01", "X-Requested-With": "XMLHttpRequest"}


def _session():
    s = requests.Session()
    s.headers.update(BASE_HEADERS)
    s.get("https://devpost.com/hackathons", timeout=15)
    return s


def _fetch_page(session, page, retries=3):
    params = [("challenge_type[]", "online"), ("status[]", "open"), ("status[]", "upcoming"), ("order_by", "deadline"), ("page", str(page))]
    for attempt in range(retries):
        r = session.get("https://devpost.com/hackathons.json", headers=JSON_HEADERS, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (403, 429):
            time.sleep(1.5 * (attempt + 1))
            continue
        r.raise_for_status()
    return None


def _parse_html_fallback():
    hackathons = []
    try:
        s = _session()
        r = s.get("https://devpost.com/hackathons", headers=BASE_HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("div.hackathon-tile"):
            link = card.select_one("a.tile-anchor")
            title_el = card.select_one("h3")
            deadline_el = card.select_one(".submission-period")
            if not link or not title_el:
                continue
            hackathons.append({
                "source": "Devpost", "title": title_el.get_text(strip=True), "url": link.get("href", ""),
                "deadline": deadline_el.get_text(strip=True) if deadline_el else "TBD",
                "prize": "N/A", "thumbnail": "", "description": "", "status": "open",
            })
    except Exception as e:
        print(f"[Devpost] HTML fallback failed: {e}")
    return hackathons


def scrape_devpost():
    hackathons, seen = [], set()
    session = _session()
    for page in range(1, 8):
        try:
            data = _fetch_page(session, page)
            if not data:
                print(f"[Devpost] page {page}: blocked after retries")
                break
            items = data.get("hackathons", [])
            if not items:
                break
            for h in items:
                url = h.get("url", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                status = h.get("open_state", "")
                if status not in ("open", "upcoming"):
                    continue
                period = h.get("submission_period_dates", "") or ""
                deadline = period.split(" - ")[-1].strip() if " - " in period else period
                hackathons.append({"source": "Devpost", "title": h.get("title", ""), "url": url, "deadline": deadline or "TBD", "prize": h.get("prize_amount", "N/A") or "N/A", "thumbnail": h.get("thumbnail_url", "") or "", "description": h.get("tagline", "") or "", "status": status})
            meta = data.get("meta", {})
            if len(hackathons) >= meta.get("total_count", 0):
                break
            time.sleep(0.6)
        except Exception as e:
            print(f"[Devpost] page {page}: {e}")
            break

    if not hackathons:
        print("[Devpost] JSON API returned nothing, trying HTML fallback")
        hackathons = _parse_html_fallback()

    print(f"[Devpost] {len(hackathons)} hackathons")
    return hackathons

import requests, re, json, time
from datetime import datetime, timezone

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
}
JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)

def _jsonld_nodes(html):
    for block in JSONLD_RE.findall(html):
        try:
            data = json.loads(block)
        except Exception:
            continue
        yield from (data.get("@graph", [data]) if isinstance(data, dict) else data)

def _extract_items(html):
    for node in _jsonld_nodes(html):
        if isinstance(node, dict) and node.get("@type") == "ItemList":
            return node.get("itemListElement", [])
    return []

def _event_dates(html):
    for node in _jsonld_nodes(html):
        if isinstance(node, dict) and "Event" in str(node.get("@type", "")):
            return node.get("startDate"), node.get("endDate")
    return None, None

def _fetch_event_dates(url, title):
    for attempt in (1, 2):
        try:
            er = requests.get(url, headers=HEADERS, timeout=15)
            er.raise_for_status()
            return _event_dates(er.text)
        except Exception as e:
            if attempt == 2:
                print(f"[lablab.ai] date check failed for '{title}' after retry: {e}")
            else:
                time.sleep(1)
    return None, None

def scrape_lablab():
    hackathons = []
    excluded = []
    seen = set()
    now = datetime.now(timezone.utc)
    for page in range(1, 8):
        url = "https://lablab.ai/ai-hackathons" if page == 1 else f"https://lablab.ai/ai-hackathons?page={page}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            items = _extract_items(r.text)
            if not items:
                break
            new_on_page = 0
            for item in items:
                full_url = item.get("url", "")
                title = item.get("name", "")
                if not full_url or not title or full_url in seen:
                    continue
                seen.add(full_url)
                new_on_page += 1
                time.sleep(0.4)  # avoid tripping rate-limiting from rapid sequential requests
                start_date, end_date = _fetch_event_dates(full_url, title)
                compare_date = end_date or start_date
                if compare_date is None:
                    # Couldn't determine dates (fetch failed even after retry) - exclude
                    # rather than risk showing an ended event with no way to check.
                    excluded.append(f"{title} (unknown - fetch failed)")
                    continue
                dt = datetime.fromisoformat(compare_date.replace("Z", "+00:00"))
                if dt < now:
                    excluded.append(title)
                    continue
                hackathons.append({"source":"lablab.ai","title":title,"url":full_url,"deadline":compare_date[:10],"prize":"See event page","thumbnail":"","description":"AI hackathon on lablab.ai","status":"open"})
            if new_on_page == 0:
                break
        except Exception as e:
            print(f"[lablab.ai] page {page}: {e}")
            break
    if excluded:
        print(f"[lablab.ai] Excluded {len(excluded)} ended event(s): {excluded}")
    print(f"[lablab.ai] {len(hackathons)} events")
    return hackathons

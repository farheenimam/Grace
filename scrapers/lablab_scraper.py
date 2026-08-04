import requests
import re
import json
import time
from datetime import datetime, timezone

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

JSONLD_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>',
    re.S,
)


def jsonld_nodes(html):
    """Yield all JSON-LD nodes from the page."""
    for block in JSONLD_RE.findall(html):
        try:
            data = json.loads(block)
        except Exception:
            continue

        if isinstance(data, dict) and "@graph" in data:
            for node in data["@graph"]:
                yield node
        elif isinstance(data, list):
            for node in data:
                yield node
        else:
            yield data


def extract_items(html):
    """Extract hackathon items from ItemList JSON-LD."""
    for node in jsonld_nodes(html):
        if isinstance(node, dict) and node.get("@type") == "ItemList":
            return node.get("itemListElement", [])
    return []


def extract_event_dates(html):
    """Extract Event start/end dates from a hackathon page."""
    for node in jsonld_nodes(html):
        if not isinstance(node, dict):
            continue

        t = node.get("@type", "")

        if t == "Event" or (isinstance(t, list) and "Event" in t):
            return node.get("startDate"), node.get("endDate")

    return None, None


def parse_iso(dt_str):
    """Safely parse ISO date strings."""
    if not dt_str:
        return None

    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None


def fetch_event_dates(url):
    """Fetch a hackathon page and return its dates."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return extract_event_dates(r.text)
    except Exception as e:
        print(f"[date fetch failed] {url}: {e}")
        return None, None


def scrape_lablab(max_pages=8):
    now = datetime.now(timezone.utc)

    results = []
    seen = set()

    for page in range(1, max_pages + 1):
        listing_url = (
            "https://lablab.ai/ai-hackathons"
            if page == 1
            else f"https://lablab.ai/ai-hackathons?page={page}"
        )

        print(f"Checking page {page}...")

        try:
            r = requests.get(listing_url, headers=HEADERS, timeout=15)
            r.raise_for_status()
        except Exception as e:
            print(f"[page failed] {listing_url}: {e}")
            break

        items = extract_items(r.text)

        if not items:
            break

        for item in items:
            title = item.get("name", "").strip()
            url = item.get("url", "").strip()

            if not title or not url or url in seen:
                continue

            seen.add(url)

            # polite delay
            time.sleep(0.3)

            start_raw, end_raw = fetch_event_dates(url)

            start_dt = parse_iso(start_raw)
            end_dt = parse_iso(end_raw)

            # Skip events with no usable date
            if not start_dt and not end_dt:
                continue

            # Determine status
            if start_dt and start_dt > now:
                status = "upcoming"
            elif end_dt and end_dt >= now:
                status = "open"
            else:
                # ended event
                continue

            deadline_raw = end_raw or start_raw

            results.append({
                "source": "lablab.ai",
                "title": title,
                "url": url,
                "deadline": deadline_raw[:10] if deadline_raw else "TBD",
                "prize": "See event page",
                "thumbnail": "",
                "description": "AI hackathon on lablab.ai",
                "status": status,
                "start_date": start_raw,
                "end_date": end_raw,
            })

    # Sort by start date
    results.sort(key=lambda x: x["start_date"] or "9999")

    return results


if __name__ == "__main__":
    events = scrape_lablab()

    print(f"\nFound {len(events)} live/upcoming hackathons:\n")

    for e in events:
        print(f"[{e['status'].upper()}] {e['title']}")
        print(f"Start: {e['start_date']}")
        print(f"End:   {e['end_date']}")
        print(f"URL:   {e['url']}\n")
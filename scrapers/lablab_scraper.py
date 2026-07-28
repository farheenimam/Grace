import requests, re, json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
}
JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
TITLE_RE = re.compile(r'<title>(.*?)</title>', re.S | re.I)
ISO_DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}[^"\\]*')

def _extract_items(html):
    for m in JSONLD_RE.finditer(html):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
        for node in nodes:
            if isinstance(node, dict) and node.get("@type") == "ItemList":
                return node.get("itemListElement", [])
    return []

def _has_ended(url, debug_label=None):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        m = TITLE_RE.search(r.text)
        page_title = m.group(1) if m else "(no <title> found)"
        title_says_ended = bool(m and "[recap]" in m.group(1).lower())
        banner_says_ended = "this event has finished" in r.text.lower()
        if debug_label:
            event_types = []
            for block in JSONLD_RE.findall(r.text):
                try:
                    data = json.loads(block)
                except Exception:
                    continue
                nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
                for node in nodes:
                    if isinstance(node, dict) and "Event" in str(node.get("@type", "")):
                        event_types.append({k: v for k, v in node.items() if k in
                            ("@type", "startDate", "endDate", "eventStatus", "name")})
            iso_dates = ISO_DATE_RE.findall(r.text)[:5]
            print(f"[lablab.ai] DEBUG '{debug_label}' title={page_title!r} "
                  f"title_ended={title_says_ended} banner_ended={banner_says_ended} "
                  f"event_jsonld={event_types} iso_dates_found={iso_dates}")
        return title_says_ended or banner_says_ended
    except Exception as e:
        if debug_label:
            print(f"[lablab.ai] DEBUG '{debug_label}' fetch failed: {e}")
        return False

def scrape_lablab():
    hackathons = []
    excluded = []
    seen = set()
    for page in range(1, 8):
        url = "https://lablab.ai/ai-hackathons" if page == 1 else f"https://lablab.ai/ai-hackathons?page={page}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            items = _extract_items(r.text)
            if not items:
                break
            new_on_page = 0
            for idx, item in enumerate(items):
                full_url = item.get("url", "")
                title = item.get("name", "")
                if not full_url or not title or full_url in seen:
                    continue
                seen.add(full_url)
                new_on_page += 1
                debug_label = title if (page == 1 and idx < 3) else None
                if _has_ended(full_url, debug_label):
                    excluded.append(title)
                    continue
                hackathons.append({"source":"lablab.ai","title":title,"url":full_url,"deadline":"TBD","prize":"See event page","thumbnail":"","description":"AI hackathon on lablab.ai","status":"open"})
            if new_on_page == 0:
                break
        except Exception as e:
            print(f"[lablab.ai] page {page}: {e}")
            break
    if excluded:
        print(f"[lablab.ai] Excluded {len(excluded)} ended event(s): {excluded}")
    print(f"[lablab.ai] {len(hackathons)} events")
    return hackathons

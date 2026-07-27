import requests, re, json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
}
JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
ENDED_MARKERS = ("finished", "ended")

def _extract_items(html):
    for m in JSONLD_RE.finditer(html):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
        for node in nodes:
            if isinstance(node, dict) and node.get("@type") == "ItemList":
                return node.get("itemListElement", []), m.end()
    return [], 0

def _is_ended(html, href, search_from):
    idx = html.find(href, search_from)
    if idx == -1:
        idx = html.find(href)
    if idx == -1:
        return False
    window = html[max(0, idx - 500):idx + 500].lower()
    return any(marker in window for marker in ENDED_MARKERS)

def scrape_lablab():
    hackathons = []
    excluded = []
    seen = set()
    for page in range(1, 8):
        url = "https://lablab.ai/ai-hackathons" if page == 1 else f"https://lablab.ai/ai-hackathons?page={page}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            items, jsonld_end = _extract_items(r.text)
            if not items:
                break
            if page == 1 and items:
                dbg_title = items[0].get("name", "")
                dbg_href = items[0].get("url", "").replace("https://lablab.ai", "")
                print(f"[lablab.ai] DEBUG item0='{dbg_title}' href='{dbg_href}' jsonld_end={jsonld_end}")
                positions = [i for i in range(len(r.text)) if r.text.startswith(dbg_href, i)]
                print(f"[lablab.ai] DEBUG all occurrences of href at positions: {positions}")
                for p in positions:
                    print(f"[lablab.ai] DEBUG window @ {p}: ...{r.text[max(0,p-300):p+300]}...")
            new_on_page = 0
            for item in items:
                full_url = item.get("url", "")
                title = item.get("name", "")
                if not full_url or not title or full_url in seen:
                    continue
                seen.add(full_url)
                new_on_page += 1
                href = full_url.replace("https://lablab.ai", "")
                if _is_ended(r.text, href, jsonld_end):
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

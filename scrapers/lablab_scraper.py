import requests, re, json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
}
JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)

def _extract_items(html):
    for block in JSONLD_RE.findall(html):
        try:
            data = json.loads(block)
        except Exception:
            continue
        nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
        for node in nodes:
            if isinstance(node, dict) and node.get("@type") == "ItemList":
                return node.get("itemListElement", [])
    return []

def scrape_lablab():
    hackathons = []
    seen = set()
    for page in range(1, 8):
        url = "https://lablab.ai/ai-hackathons" if page == 1 else f"https://lablab.ai/ai-hackathons?page={page}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            items = _extract_items(r.text)
            if not items: break
            new_on_page = 0
            for item in items:
                full_url = item.get("url", "")
                title = item.get("name", "")
                if not full_url or not title or full_url in seen: continue
                seen.add(full_url)
                new_on_page += 1
                hackathons.append({"source":"lablab.ai","title":title,"url":full_url,"deadline":"TBD","prize":"See event page","thumbnail":"","description":"AI hackathon on lablab.ai","status":"open"})
            if new_on_page == 0: break
        except Exception as e:
            print(f"[lablab.ai] page {page}: {e}"); break
    print(f"[lablab.ai] {len(hackathons)} events")
    return hackathons

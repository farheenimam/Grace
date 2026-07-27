import requests, re, json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
}
JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
CARD_ANCHOR_RE = re.compile(r'<a class="flex h-full flex-col justify-between" href="(/ai-hackathons/[^"]+)"')
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

def _card_chunks(html, search_from):
    matches = [m for m in CARD_ANCHOR_RE.finditer(html) if m.start() >= search_from]
    chunks = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
        chunks.setdefault(m.group(1), html[m.start():end])
    return chunks

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
            chunks = _card_chunks(r.text, jsonld_end)
            new_on_page = 0
            for item in items:
                full_url = item.get("url", "")
                title = item.get("name", "")
                if not full_url or not title or full_url in seen:
                    continue
                seen.add(full_url)
                new_on_page += 1
                href = full_url.replace("https://lablab.ai", "")
                chunk = chunks.get(href, "").lower()
                if chunk and any(marker in chunk for marker in ENDED_MARKERS):
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

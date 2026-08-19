import re, time
import feedparser
import requests
from datetime import datetime
from bs4 import BeautifulSoup

KEYWORDS = ["hackathon","challenge","solution challenge","devfest","build with google",
            "gemini","google hack","competition","code jam","kickstart"]

DEADLINE_PATTERNS = [
    r"(?:deadline|submission deadline|application deadline|registration deadline)"
    r"\s*(?:is|:|-|–|—|on)?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
    r"(?:deadline|submission deadline|application deadline|registration deadline)"
    r"\s*(?:is|:|-|–|—|on)?\s*(\d{4}-\d{2}-\d{2})",
    r"(?:submissions?|applications?|registration)\s+(?:close|closes|ends|end)"
    r"(?:\s+(?:on|at))?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
    r"(?:submit|register)\s+(?:by|before)\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
]

DATE_FORMATS = ["%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y", "%Y-%m-%d"]


def _extract_deadline(title, summary, url):
    """Only trust an explicit deadline mention in the article. Never use
    the RSS published date — that's when the post went live, not when
    the hackathon closes."""
    text_parts = [title, summary]
    if url:
        try:
            r = requests.get(url, headers={"User-Agent": "HackTracker/2.0"}, timeout=10)
            r.raise_for_status()
            html = re.sub(r"<script\b[^>]*>.*?</script>", " ", r.text, flags=re.I | re.S)
            html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.I | re.S)
            html = re.sub(r"<[^>]+>", " ", html)
            text_parts.append(html)
        except Exception:
            pass
    text = re.sub(r"\s+", " ", " ".join(text_parts)).strip()
    for pattern in DEADLINE_PATTERNS:
        for value in re.findall(pattern, text, flags=re.I):
            for fmt in DATE_FORMATS:
                try:
                    return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
    return "TBD"


def scrape_google_dev_events():
    hackathons = []; seen = set()
    def add(h):
        if h.get("url") and h["url"] not in seen and h.get("title"):
            seen.add(h["url"]); hackathons.append(h)
    try:
        feed = feedparser.parse("https://developers.googleblog.com/feeds/posts/default?alt=rss")
        for entry in feed.entries[:50]:
            title = entry.get("title","")
            summary = BeautifulSoup(entry.get("summary",""),"lxml").get_text()
            if not any(k in (title+" "+summary).lower() for k in KEYWORDS): continue
            url = entry.get("link","")
            add({"source":"Google Developers","title":title,"url":url,
                 "deadline":_extract_deadline(title, summary, url),
                 "prize":"See post","thumbnail":"","description":summary[:200],"status":"open"})
        time.sleep(0.3)
    except Exception as e:
        print(f"[Google Dev] RSS: {e}")
    add({"source":"Google Developers","title":"GDSC Solution Challenge 2026","url":"https://developers.google.com/community/gdsc-solution-challenge","deadline":"April 2026","prize":"Trip to Google HQ + mentorship","thumbnail":"","description":"Annual challenge for GDSC members. Solve UN SDG problems using Google tech.","status":"open"})
    add({"source":"Google Developers","title":"Google Code Jam 2026","url":"https://codingcompetitions.withgoogle.com/codejam","deadline":"TBD","prize":"$15,000","thumbnail":"","description":"Annual algorithmic programming competition by Google.","status":"open"})
    print(f"[Google Dev] {len(hackathons)} items")
    return hackathons

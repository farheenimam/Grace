import requests, time, re
from datetime import datetime

BASE = "https://dev.to/api"
HEADERS = {"User-Agent":"HackTracker/2.0","Accept":"application/vnd.forem.api-v1+json"}

KEYWORDS = ["hackathon","hack ","hacks","challenge","competition","contest","build challenge",
            "game jam","game off","imagine cup","code for good","code jam","kickstart",
            "solution challenge","summer of code","gsoc","sprint","buildathon","win prizes",
            "prize pool","devpost","lablab"," mlh ","dorahacks","build with","code with","bounty program",
            "hackathon","hacktoberfest","hack week","global hack","battlecode","technica"]

TAGS = ["hackathon","hackathons","hacktoberfest","challenge","webdev","opensource","competition","gamedev","showdev"]


def _matches(a):
    combined = " ".join([a.get("title",""), a.get("description",""),
        ", ".join(a["tag_list"]) if isinstance(a.get("tag_list"),list) else str(a.get("tag_list",""))]).lower()
    return any(k in combined for k in KEYWORDS)


def _false_positive(a):
    combined = (a.get("title","")+" "+a.get("description","")).lower()
    return any(fp in combined for fp in ["how to win","tips for","tutorial","introduction to",
        "getting started","bug bounty guide","agile sprint","sprint planning"])


def _extract_deadline(a):
    """
    Extract a real hackathon deadline from the DEV.to article text.

    IMPORTANT:
    published_at is the article publication date, NOT the hackathon deadline,
    so it must never be used as the deadline.

    Returns:
        YYYY-MM-DD when a reliable deadline is found.
        "TBD" otherwise.
    """

    # DEV's article-list endpoint only gives us the short description.
    # We therefore fetch the complete article when possible.
    text_parts = [
        a.get("title", ""),
        a.get("description", "")
    ]

    # Try the article URL because the list endpoint does not contain
    # the complete article body.
    url = a.get("url", "")

    if url:
        try:
            r = requests.get(
                url,
                headers={"User-Agent": "HackTracker/2.0"},
                timeout=10
            )
            r.raise_for_status()

            html = r.text

            # Strip HTML so date extraction works against readable text.
            html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html,
                          flags=re.IGNORECASE | re.DOTALL)
            html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html,
                          flags=re.IGNORECASE | re.DOTALL)
            html = re.sub(r"<[^>]+>", " ", html)

            text_parts.append(html)

        except Exception:
            # Failure to fetch the article is fine.
            # We simply fall back to TBD rather than inventing a deadline.
            pass

    text = " ".join(text_parts)
    text = re.sub(r"\s+", " ", text).strip()

    # We only accept dates that occur near language indicating
    # an actual event/submission deadline.
    deadline_patterns = [
        r"(?:deadline|submission deadline|application deadline|registration deadline)"
        r"\s*(?:is|:|-|–|—|on)?\s*"
        r"([A-Za-z]+\s+\d{1,2},?\s+\d{4})",

        r"(?:deadline|submission deadline|application deadline|registration deadline)"
        r"\s*(?:is|:|-|–|—|on)?\s*"
        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})",

        r"(?:deadline|submission deadline|application deadline|registration deadline)"
        r"\s*(?:is|:|-|–|—|on)?\s*"
        r"(\d{4}-\d{2}-\d{2})",

        r"(?:submissions?|applications?|registration)"
        r"\s+(?:close|closes|ends|end)"
        r"(?:\s+(?:on|at))?\s*"
        r"([A-Za-z]+\s+\d{1,2},?\s+\d{4})",

        r"(?:submissions?|applications?|registration)"
        r"\s+(?:close|closes|ends|end)"
        r"(?:\s+(?:on|at))?\s*"
        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})",

        r"(?:submit|register)"
        r"\s+(?:by|before)"
        r"\s*"
        r"([A-Za-z]+\s+\d{1,2},?\s+\d{4})",

        r"(?:submit|register)"
        r"\s+(?:by|before)"
        r"\s*"
        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
    ]

    for pattern in deadline_patterns:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)

        for value in matches:
            value = value.strip()

            for fmt in [
                "%B %d, %Y",
                "%B %d %Y",
                "%b %d, %Y",
                "%b %d %Y",
                "%d %B %Y",
                "%d %b %Y",
                "%Y-%m-%d",
            ]:
                try:
                    return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue

    # No reliable deadline found.
    # NEVER substitute published_at here.
    return "TBD"


def scrape_devto():
    hackathons = []; seen = set()

    for tag in TAGS:
        for page in range(1, 4):
            try:
                r = requests.get(f"{BASE}/articles", headers=HEADERS,
                    params={"tag":tag,"per_page":30,"page":page,"top":365}, timeout=15)

                r.raise_for_status()
                articles = r.json()

                if not articles:
                    break

                for a in articles:
                    url = a.get("url","")

                    if not url or url in seen or not _matches(a) or _false_positive(a):
                        continue

                    seen.add(url)

                    deadline = _extract_deadline(a)

                    hackathons.append({
                        "source":"dev.to",
                        "title":a.get("title",""),
                        "url":url,
                        "deadline":deadline,
                        "prize":"See article",
                        "thumbnail":a.get("cover_image") or a.get("social_image") or "",
                        "description":a.get("description","") or "",
                        "status":"open"
                    })

                time.sleep(0.25)

            except Exception as e:
                print(f"[dev.to] tag={tag} page={page}: {e}")
                break

    print(f"[dev.to] {len(hackathons)} items")
    return hackathons

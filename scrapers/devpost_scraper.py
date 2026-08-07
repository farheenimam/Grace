import math
import re
import requests
import time
from datetime import datetime

# Devpost's load balancer rejects bare/short User-Agent strings with a 403
# before the request ever reaches the app, so send a full browser UA.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://devpost.com/hackathons",
}

API_URL = "https://devpost.com/api/hackathons"

# Devpost clamps per_page to 40 server-side; it reports the real value back
# in meta.per_page, which is what we paginate on.
PER_PAGE = 40

# Runaway guard. ~170 open/upcoming hackathons at 40/page is 5 pages, so this
# is generous headroom without ever walking the full 13k-record archive.
MAX_PAGES = 30

MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"

# "May 07 - Aug 08, 2026" / "Dec 20, 2026 - Jan 10, 2027"
CROSS_MONTH = re.compile(
    r"(?:%s)\w*\s+\d{1,2}(?:,\s*\d{4})?\s*[-–]\s*(%s)\w*\s+(\d{1,2}),\s*(\d{4})"
    % (MONTHS, MONTHS)
)

# "Aug 05 - 07, 2026"
SAME_MONTH = re.compile(
    r"(%s)\w*\s+\d{1,2}\s*[-–]\s*(\d{1,2}),\s*(\d{4})" % MONTHS
)

# "Aug 09, 2026"
SINGLE_DATE = re.compile(r"(%s)\w*\s+(\d{1,2}),\s*(\d{4})" % MONTHS)


def clean_prize(text):
    if not text:
        return "N/A"
    return re.sub(r"<.*?>", "", text).strip()


def parse_end_date(text):
    """Convert Devpost's display date range into an ISO end date.

    Devpost's API exposes no structured date field — only the display string
    in submission_period_dates. The runner's purge_ended() can only expire
    rows whose deadline parses as %Y-%m-%d, so we normalize here or the row
    never gets deleted.
    """
    if not text:
        return None

    for pattern in (CROSS_MONTH, SAME_MONTH, SINGLE_DATE):
        m = pattern.search(text)

        if not m:
            continue

        month, day, year = m.group(1), m.group(2), m.group(3)

        try:
            parsed = datetime.strptime(f"{month} {day} {year}", "%b %d %Y")
        except ValueError:
            return None

        return parsed.strftime("%Y-%m-%d")

    return None


def scrape_devpost():

    hackathons = []
    seen = set()

    page = 1
    total_pages = None

    while True:

        # Filter server-side: ask Devpost for only open/upcoming events,
        # soonest deadline first, instead of paging the whole archive.
        params = [
            ("status[]", "open"),
            ("status[]", "upcoming"),
            ("order_by", "deadline"),
            ("per_page", PER_PAGE),
            ("page", page),
        ]

        r = requests.get(API_URL, headers=HEADERS, params=params, timeout=20)

        r.raise_for_status()

        data = r.json()

        if total_pages is None:
            meta = data["meta"]
            per_page = meta["per_page"] or PER_PAGE
            total_pages = math.ceil(meta["total_count"] / per_page)
            print(f"{total_pages} pages available")

        items = data["hackathons"]

        if not items:
            break

        for h in items:

            if h["url"] in seen:
                continue

            seen.add(h["url"])

            # Safety net — the status[] params should already exclude these.
            if h["open_state"] not in ("open", "upcoming"):
                continue

            raw_dates = h["submission_period_dates"]

            hackathons.append({
                "source": "Devpost",
                "title": h["title"],
                "url": h["url"],
                "deadline": parse_end_date(raw_dates) or "TBD",
                "submission_period": raw_dates,
                "time_left": h["time_left_to_submission"],
                "status": h["open_state"],
                "organization": h["organization_name"],
                "thumbnail": h["thumbnail_url"] or "",
                "prize": clean_prize(h["prize_amount"]),
                "description": ", ".join(
                    theme["name"] for theme in h["themes"]
                ),
            })

        print(f"Finished page {page}")

        page += 1

        if page > total_pages or page > MAX_PAGES:
            break

        time.sleep(0.3)

    print(f"Found {len(hackathons)} active hackathons")

    return hackathons


if __name__ == "__main__":
    for h in scrape_devpost():
        print(f"[{h['status'].upper()}] {h['deadline']} | {h['title']}")

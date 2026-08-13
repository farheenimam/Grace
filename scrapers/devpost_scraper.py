import math
import re
import requests
import time
from datetime import datetime


API_URL = "https://devpost.com/api/hackathons"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Referer": "https://devpost.com/hackathons",
}

PER_PAGE = 40
MAX_PAGES = 30


# --------------------------------------------------
# Prize cleaning
# --------------------------------------------------

def clean_prize(text):
    if not text:
        return "N/A"

    text = re.sub(r"<[^>]+>", "", str(text))

    return text.strip() or "N/A"


# --------------------------------------------------
# Date parsing
# --------------------------------------------------

MONTHS = (
    "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|"
    "Sep|Oct|Nov|Dec"
)


# Example:
# Dec 20, 2026 - Jan 10, 2027
CROSS_MONTH = re.compile(
    rf"(?:{MONTHS})\w*\s+\d{{1,2}}"
    rf"(?:,\s*\d{{4}})?"
    rf"\s*[-–]\s*"
    rf"({MONTHS})\w*\s+"
    rf"(\d{{1,2}}),\s*(\d{{4}})"
)


# Example:
# Aug 05 - 07, 2026
SAME_MONTH = re.compile(
    rf"({MONTHS})\w*\s+\d{{1,2}}"
    rf"\s*[-–]\s*"
    rf"(\d{{1,2}}),\s*(\d{{4}})"
)


# Example:
# Aug 09, 2026
SINGLE_DATE = re.compile(
    rf"({MONTHS})\w*\s+"
    rf"(\d{{1,2}}),\s*(\d{{4}})"
)


def parse_end_date(text):

    if not text:
        return None

    for pattern in (
        CROSS_MONTH,
        SAME_MONTH,
        SINGLE_DATE
    ):

        match = pattern.search(text)

        if not match:
            continue

        month = match.group(1)
        day = match.group(2)
        year = match.group(3)

        try:
            date = datetime.strptime(
                f"{month} {day} {year}",
                "%b %d %Y"
            )

            return date.strftime("%Y-%m-%d")

        except ValueError:
            return None

    return None


# --------------------------------------------------
# Devpost scraper
# --------------------------------------------------

def scrape_devpost():

    hackathons = []
    seen = set()

    page = 1
    total_pages = None

    while True:

        if page > MAX_PAGES:
            print(
                f"[Devpost] Reached MAX_PAGES={MAX_PAGES}"
            )
            break

        # ------------------------------------------
        # IMPORTANT:
        # Devpost accepts repeated status[] params.
        # This means:
        #
        # open OR upcoming
        # ------------------------------------------

        params = [
            ("status[]", "open"),
            ("status[]", "upcoming"),
            ("order_by", "deadline"),
            ("per_page", PER_PAGE),
            ("page", page),
        ]

        try:

            r = requests.get(
                API_URL,
                headers=HEADERS,
                params=params,
                timeout=20,
            )

            print(
                f"[Devpost] page={page} "
                f"status={r.status_code}"
            )

            r.raise_for_status()

            data = r.json()

        except requests.RequestException as e:

            print(
                f"[Devpost] Request failed: {e}"
            )

            if "r" in locals():
                print(
                    f"[Devpost] Content-Type: "
                    f"{r.headers.get('Content-Type')}"
                )

                print(
                    f"[Devpost] Response: "
                    f"{r.text[:300]}"
                )

            break

        except ValueError as e:

            print(
                f"[Devpost] Invalid JSON: {e}"
            )

            break

        # ------------------------------------------
        # Extract items
        # ------------------------------------------

        items = data.get("hackathons", [])

        if not items:
            print(
                f"[Devpost] No results on page {page}"
            )
            break

        # ------------------------------------------
        # Pagination
        # ------------------------------------------

        meta = data.get("meta", {})

        total_count = meta.get(
            "total_count",
            0
        )

        # IMPORTANT:
        # Devpost may clamp per_page.
        #
        # We requested 40.
        # Devpost currently returns 40.
        #
        # But we use the returned value rather
        # than assuming it.
        actual_per_page = meta.get(
            "per_page",
            len(items)
        )

        if total_pages is None:

            total_pages = math.ceil(
                total_count / actual_per_page
            )

            print(
                f"[Devpost] "
                f"total_count={total_count}"
            )

            print(
                f"[Devpost] "
                f"per_page={actual_per_page}"
            )

            print(
                f"[Devpost] "
                f"total_pages={total_pages}"
            )

        # ------------------------------------------
        # Process hackathons
        # ------------------------------------------

        for h in items:

            url = h.get("url", "")

            if not url:
                continue

            if url in seen:
                continue

            seen.add(url)

            # Safety check
            status = (
                h.get("open_state") or ""
            ).lower()

            if status not in (
                "open",
                "upcoming"
            ):
                continue

            # --------------------------------------
            # Dates
            # --------------------------------------

            raw_dates = (
                h.get("submission_period_dates")
                or ""
            )

            deadline = (
                parse_end_date(raw_dates)
                or "TBD"
            )

            # --------------------------------------
            # Thumbnail
            # --------------------------------------

            thumbnail = (
                h.get("thumbnail_url")
                or ""
            )

            if thumbnail.startswith("//"):
                thumbnail = (
                    "https:" + thumbnail
                )

            # --------------------------------------
            # Themes
            # --------------------------------------

            themes = h.get("themes") or []

            theme_names = [
                theme.get("name", "")
                for theme in themes
                if isinstance(theme, dict)
                and theme.get("name")
            ]

            # --------------------------------------
            # Description
            # --------------------------------------

            description = (
                h.get("tagline")
                or ", ".join(theme_names)
                or "Devpost hackathon"
            )

            # --------------------------------------
            # Final object
            # --------------------------------------

            hackathons.append({

                "source": "Devpost",

                "title": h.get(
                    "title",
                    ""
                ),

                "url": url,

                "deadline": deadline,

                "submission_period": raw_dates,

                "time_left": h.get(
                    "time_left_to_submission",
                    ""
                ),

                "status": status,

                "organization": h.get(
                    "organization_name",
                    ""
                ),

                "thumbnail": thumbnail,

                "prize": clean_prize(
                    h.get("prize_amount")
                ),

                "description": description,
            })

        print(
            f"[Devpost] Finished "
            f"page {page}/{total_pages}"
        )

        # ------------------------------------------
        # Stop when all pages are processed
        # ------------------------------------------

        if total_pages and page >= total_pages:
            break

        page += 1

        time.sleep(0.4)

    print(
        f"[Devpost] Found "
        f"{len(hackathons)} active/upcoming hackathons"
    )

    return hackathons


# --------------------------------------------------
# Test
# --------------------------------------------------

if __name__ == "__main__":

    results = scrape_devpost()

    for h in results:

        print(
            f"[{h['status'].upper()}] "
            f"{h['deadline']} | "
            f"{h['title']}"
        )

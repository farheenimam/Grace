import requests
import time
from datetime import datetime, timezone


API_URL = "https://dorahacks.io/api/v1/hub/hackathons"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Content-Language": "en-US",
    "Referer": "https://dorahacks.io/hackathon",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


def unix_to_date(timestamp):
    if not timestamp:
        return "TBD"

    try:
        return datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc
        ).strftime("%Y-%m-%d")
    except (ValueError, TypeError, OSError):
        return "TBD"


def scrape_dorahacks():
    hackathons = []
    seen = set()

    page = 1
    page_size = 24

    now = datetime.now(timezone.utc).timestamp()

    while True:

        params = {
            "page": page,
            "page_size": page_size,
        }

        try:
            response = requests.get(
                API_URL,
                headers=HEADERS,
                params=params,
                timeout=20,
            )

            print(
                f"[DoraHacks] page={page} "
                f"status={response.status_code}"
            )

            response.raise_for_status()

            data = response.json()

        except requests.RequestException as e:
            print(
                f"[DoraHacks] page {page}: "
                f"request failed: {e}"
            )
            break

        except ValueError as e:
            print(
                f"[DoraHacks] page {page}: "
                f"invalid JSON: {e}"
            )
            break

        results = data.get("results", [])

        if not results:
            break

        for h in results:

            hackathon_id = h.get("id")

            if not hackathon_id:
                continue

            if hackathon_id in seen:
                continue

            seen.add(hackathon_id)

            start = h.get("timeline_start")
            end = h.get("timeline_end")

            # No end date -> skip because we cannot safely
            # determine whether the hackathon is still active.
            if not end:
                continue

            # Remove already-ended hackathons.
            if end < now:
                continue

            # Determine whether it is upcoming or currently running.
            if start and start > now:
                status = "upcoming"
            else:
                status = "open"

            uname = h.get("uname")

            if uname:
                url = f"https://dorahacks.io/hackathon/{uname}"
            else:
                url = f"https://dorahacks.io/hackathon/{hackathon_id}"

            owner = h.get("owner") or {}

            tags = h.get("tags") or ""
            ecosystem = h.get("ecosystem") or ""

            description_parts = []

            if ecosystem:
                description_parts.append(ecosystem)

            if tags:
                description_parts.append(tags)

            description = ", ".join(description_parts)

            bonus_price = h.get("bonus_price")
            bonus_token = h.get("bonus_token")

            if bonus_price:
                prize = (
                    f"{bonus_price} "
                    f"{bonus_token or ''}"
                ).strip()
            else:
                prize = "See event page"

            hackathons.append({
                "source": "DoraHacks",
                "title": h.get("title", ""),
                "url": url,
                "deadline": unix_to_date(end),
                "start_date": unix_to_date(start),
                "prize": prize,
                "thumbnail": h.get("image_url") or "",
                "description": description,
                "status": status,
                "organization": owner.get("name", ""),
                "hackers_count": h.get("hackers_count", 0),
                "buidls_count": h.get("buidls_count", 0),
                "venue": h.get("venue_form", ""),
            })

        print(
            f"[DoraHacks] page {page}: "
            f"{len(results)} received, "
            f"{len(hackathons)} active/upcoming"
        )

        # The API gives us the next URL.
        if not data.get("next"):
            break

        page += 1

        time.sleep(0.3)

    # Soonest deadline first.
    hackathons.sort(
        key=lambda h: (
            h["deadline"] == "TBD",
            h["deadline"]
        )
    )

    print(
        f"[DoraHacks] Found "
        f"{len(hackathons)} live/upcoming hackathons"
    )

    return hackathons


if __name__ == "__main__":
    for h in scrape_dorahacks():
        print(
            f"[{h['status'].upper()}] "
            f"{h['deadline']} | "
            f"{h['title']}"
        )

"""
HackTracker — GitHub Actions scraper runner

Runs all scrapers, saves/refreshes hackathons in Supabase,
purges ended/stale hackathons according to each individual
scraper's source rules, and sends notifications for newly
discovered hackathons.
"""

import os
import sys
import hashlib
import calendar

from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras


sys.path.insert(0, os.path.dirname(__file__))


# ============================================================
# SCRAPERS
# ============================================================

from scrapers.devpost_scraper import scrape_devpost
from scrapers.devto_scraper import scrape_devto
from scrapers.lablab_scraper import scrape_lablab
from scrapers.mlh_scraper import scrape_mlh
from scrapers.hackerearth_scraper import scrape_hackerearth
from scrapers.dorahacks_scraper import scrape_dorahacks
from scrapers.google_dev_scraper import scrape_google_dev_events
from scrapers.kaggle_scraper import scrape_kaggle

from notifier import (
    send_email_notification,
    send_push_notification,
)


# ============================================================
# CONFIGURATION
# ============================================================

DATABASE_URL = os.environ.get("DATABASE_URL", "")


SCRAPERS = [
    ("Devpost", scrape_devpost),
    ("dev.to", scrape_devto),
    ("lablab.ai", scrape_lablab),
    ("MLH", scrape_mlh),
    ("HackerEarth", scrape_hackerearth),
    ("DoraHacks", scrape_dorahacks),
    ("Google Dev", scrape_google_dev_events),
    ("Kaggle", scrape_kaggle),
]


# ============================================================
# ID
# ============================================================

def make_id(h):
    """
    Generate a stable ID from the URL.

    Falls back to title if URL is unavailable.
    """

    return hashlib.md5(
        (h.get("url") or h.get("title", "")).encode()
    ).hexdigest()


# ============================================================
# DATABASE
# ============================================================

def get_conn():
    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require"
    )


def ensure_tables():

    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS hackathons (
            id TEXT PRIMARY KEY,
            source TEXT,
            title TEXT,
            url TEXT UNIQUE,
            deadline TEXT,
            prize TEXT,
            thumbnail TEXT,
            description TEXT,
            status TEXT DEFAULT 'open',
            first_seen TIMESTAMPTZ DEFAULT NOW(),
            notified BOOLEAN DEFAULT FALSE
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE,
            fcm_token TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    conn.commit()
    conn.close()


def get_existing_ids():

    conn = get_conn()
    c = conn.cursor()

    c.execute(
        "SELECT id FROM hackathons"
    )

    ids = {
        r[0]
        for r in c.fetchall()
    }

    conn.close()

    return ids


# ============================================================
# SAVE / UPDATE
# ============================================================

def save_all(hackathons):
    """
    Insert new hackathons and refresh existing ones.

    Existing records are updated using the stable ID.
    """

    if not hackathons:
        return

    conn = get_conn()
    c = conn.cursor()

    for h in hackathons:

        try:

            c.execute(
                """
                INSERT INTO hackathons
                (
                    id,
                    source,
                    title,
                    url,
                    deadline,
                    prize,
                    thumbnail,
                    description,
                    status
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )

                ON CONFLICT (id)
                DO UPDATE SET

                    source = EXCLUDED.source,
                    title = EXCLUDED.title,
                    deadline = EXCLUDED.deadline,
                    prize = EXCLUDED.prize,
                    thumbnail = EXCLUDED.thumbnail,
                    description = EXCLUDED.description,
                    status = EXCLUDED.status
                """,
                (
                    make_id(h),
                    h.get("source", ""),
                    h.get("title", ""),
                    h.get("url", ""),
                    h.get("deadline", "TBD"),
                    h.get("prize", "N/A"),
                    h.get("thumbnail", ""),
                    h.get("description", ""),
                    h.get("status", "open"),
                )
            )

        except Exception as e:

            print(
                f"  Insert error: {e}"
            )

    conn.commit()
    conn.close()


# ============================================================
# DEADLINE PARSING
# ============================================================

# Formats containing a real day.
DEADLINE_FORMATS = [
    "%Y-%m-%d",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
]


# Month + year only.
MONTH_ONLY_FORMATS = [
    "%B %Y",
    "%b %Y",
]


def parse_deadline(deadline):

    if not deadline:
        return None

    deadline = str(deadline).strip()

    if deadline.upper() in (
        "TBD",
        "N/A",
        "NONE",
        "NULL",
    ):
        return None

    # --------------------------------------------------------
    # Full dates
    # --------------------------------------------------------

    for fmt in DEADLINE_FORMATS:

        try:

            return datetime.strptime(
                deadline,
                fmt
            )

        except ValueError:

            continue

    # --------------------------------------------------------
    # Month + year
    # --------------------------------------------------------

    for fmt in MONTH_ONLY_FORMATS:

        try:

            dt = datetime.strptime(
                deadline,
                fmt
            )

            last_day = calendar.monthrange(
                dt.year,
                dt.month
            )[1]

            return dt.replace(
                day=last_day
            )

        except ValueError:

            continue

    return None


# ============================================================
# SOURCE NORMALIZATION
# ============================================================

def normalize_source(source):

    source = (
        str(source or "")
        .strip()
        .lower()
    )

    aliases = {
        "devpost": "devpost",

        "dev.to": "dev.to",
        "devto": "dev.to",

        "lablab.ai": "lablab.ai",
        "lablab": "lablab.ai",

        "dorahacks": "dorahacks",
        "dora hacks": "dorahacks",

        "kaggle": "kaggle",

        "mlh": "mlh",

        "hackerearth": "hackerearth",

        "google dev": "google dev",
        "google developers": "google dev",
    }

    return aliases.get(
        source,
        source
    )


# ============================================================
# PURGE
# ============================================================

def purge_ended(
    grace_days=3,
    successful_sources=None,
    source_results=None
):
    """
    Purge hackathons according to the rules of their
    individual scraper.

    IMPORTANT:

    A source is only purged if its scraper successfully
    returned at least one result.

    This prevents an API failure such as HTTP 403 from
    deleting all existing records for that source.

    --------------------------------------------------------
    Devpost
    --------------------------------------------------------

    Devpost itself returns only open/upcoming hackathons.

    Therefore:

        returned by Devpost -> keep

        no longer returned -> remove

    --------------------------------------------------------
    lablab.ai
    --------------------------------------------------------

    The lablab scraper itself checks the start/end dates.

        returned by lablab -> keep

        no longer returned -> remove

    --------------------------------------------------------
    DoraHacks
    --------------------------------------------------------

    The DoraHacks scraper itself checks timeline_end.

        returned by DoraHacks -> keep

        no longer returned -> remove

    --------------------------------------------------------
    Kaggle
    --------------------------------------------------------

    Uses the deadline returned by Kaggle.

    --------------------------------------------------------
    dev.to
    --------------------------------------------------------

    Uses its extracted deadline.

    --------------------------------------------------------
    Other sources
    --------------------------------------------------------

    Uses the generic deadline/status fallback.
    """

    if successful_sources is None:
        successful_sources = set()

    if source_results is None:
        source_results = {}

    # Normalize successful source names.
    successful_sources = {
        normalize_source(source)
        for source in successful_sources
    }

    # --------------------------------------------------------
    # Build current IDs returned by each scraper.
    # --------------------------------------------------------

    current_ids_by_source = {}

    for source, results in source_results.items():

        normalized_source = normalize_source(
            source
        )

        current_ids_by_source[
            normalized_source
        ] = {print(     f"  ✓ {len(results)} items" )
            make_id(h)
            for h in results
            if h.get("url")
            or h.get("title")
        }

    # --------------------------------------------------------
    # Database
    # --------------------------------------------------------

    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        SELECT
            id,
            source,
            title,
            url,
            deadline,
            status
        FROM hackathons
    """)

    rows = c.fetchall()

    cutoff = (
        datetime.now()
        - timedelta(days=grace_days)
    )

    to_delete = []

    # ========================================================
    # PROCESS EACH DATABASE ROW
    # ========================================================

    for (
        rid,
        source,
        title,
        url,
        deadline,
        status
    ) in rows:

        source_name = normalize_source(
            source
        )

        current_status = (
            str(status or "")
            .strip()
            .lower()
        )

        # ====================================================
        # DEVPOST
        # ====================================================

        if source_name == "devpost":

            # Never purge if Devpost scraper failed
            # or returned zero results.

            if "devpost" not in successful_sources:

                continue

            current_ids = current_ids_by_source.get(
                "devpost",
                set()
            )

            # Devpost no longer returned this hackathon.
            if rid not in current_ids:

                to_delete.append(rid)

                print(
                    "[Purge] Devpost no longer returned | "
                    f"{title} | {url}"
                )

            continue

        # ====================================================
        # LABLAB.AI
        # ====================================================

        if source_name == "lablab.ai":

            if "lablab.ai" not in successful_sources:

                continue

            current_ids = current_ids_by_source.get(
                "lablab.ai",
                set()
            )

            # Lablab scraper itself determines whether an
            # event is live/upcoming.
            #
            # Therefore, if it successfully ran and did not
            # return this event, remove the old record.

            if rid not in current_ids:

                to_delete.append(rid)

                print(
                    "[Purge] lablab.ai no longer returned | "
                    f"{title} | {url}"
                )

            continue

        # ====================================================
        # DORAHACKS
        # ====================================================

        if source_name == "dorahacks":

            if "dorahacks" not in successful_sources:

                continue

            current_ids = current_ids_by_source.get(
                "dorahacks",
                set()
            )

            # DoraHacks scraper already checks timeline_end.
            #
            # If successfully scraped and no longer returned,
            # remove the stale database record.

            if rid not in current_ids:

                to_delete.append(rid)

                print(
                    "[Purge] DoraHacks no longer returned | "
                    f"{title} | {url}"
                )

            continue

        # ====================================================
        # KAGGLE
        # ====================================================

        if source_name == "kaggle":

            if "kaggle" not in successful_sources:

                continue

            dt = parse_deadline(
                deadline
            )

            if dt and dt < cutoff:

                to_delete.append(rid)

                print(
                    "[Purge] Kaggle | "
                    f"{title} | "
                    f"deadline={deadline} | "
                    f"status={status} | "
                    f"{url}"
                )

            continue

        # ====================================================
        # DEV.TO
        # ====================================================

        if source_name == "dev.to":

            if "dev.to" not in successful_sources:

                continue

            # The dev.to scraper currently uses the article's
            # published date as deadline.
            #
            # Do NOT purge TBD/N/A.

            if not deadline:

                continue

            if str(deadline).strip().upper() in (
                "TBD",
                "N/A"
            ):

                continue

            dt = parse_deadline(
                deadline
            )

            if dt and dt < cutoff:

                to_delete.append(rid)

                print(
                    "[Purge] dev.to | "
                    f"{title} | "
                    f"deadline={deadline} | "
                    f"status={status} | "
                    f"{url}"
                )

            continue

        # ====================================================
        # ALL OTHER SOURCES
        # ====================================================

        # Never purge a source whose scraper failed.

        if source_name not in successful_sources:

            continue

        # Explicit active statuses are protected.

        if current_status in (
            "open",
            "upcoming",
            "active",
            "live"
        ):

            continue

        dt = parse_deadline(
            deadline
        )

        if dt and dt < cutoff:

            to_delete.append(rid)

            print(
                f"[Purge] {source} | "
                f"{title} | "
                f"deadline={deadline} | "
                f"status={status} | "
                f"{url}"
            )

    # ========================================================
    # DELETE
    # ========================================================

    if to_delete:

        c.execute(
            """
            DELETE FROM hackathons
            WHERE id = ANY(%s)
            """,
            (to_delete,)
        )

        conn.commit()

    conn.close()

    return len(to_delete)


# ============================================================
# DEDUPLICATION
# ============================================================

def dedupe_by_url():
    """
    Remove exact duplicate URLs only.

    Do NOT deduplicate solely by title because two different
    hackathons can legitimately have the same title.
    """

    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        DELETE FROM hackathons a
        USING hackathons b
        WHERE a.url = b.url
          AND a.id <> b.id
          AND a.first_seen < b.first_seen
    """)

    removed = c.rowcount

    conn.commit()
    conn.close()

    return removed


# ============================================================
# SUBSCRIBERS
# ============================================================

def get_subscribers():

    conn = get_conn()

    c = conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    )

    c.execute(
        "SELECT email, fcm_token FROM subscribers"
    )

    rows = c.fetchall()

    conn.close()

    return rows


# ============================================================
# MAIN
# ============================================================

def main():

    # ========================================================
    # DATABASE URL
    # ========================================================

    if not DATABASE_URL:

        print(
            "ERROR: DATABASE_URL not set "
            "in GitHub Secrets."
        )

        sys.exit(1)

    # ========================================================
    # HEADER
    # ========================================================

    print("=" * 55)

    print(
        "  HackTracker Scraper — GitHub Actions"
    )

    print(
        f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )

    print("=" * 55)

    # ========================================================
    # DATABASE
    # ========================================================

    ensure_tables()

    # ========================================================
    # SCRAPER RESULTS
    # ========================================================

    all_results = []

    # IMPORTANT:
    #
    # Stores the individual scraper results.
    #
    # Example:
    #
    # {
    #     "Devpost": [...],
    #     "lablab.ai": [...],
    #     "DoraHacks": [...],
    #     "Kaggle": [...]
    # }

    source_results = {}

    # Sources that successfully returned usable results.

    successful_sources = set()

    # ========================================================
    # RUN EVERY SCRAPER
    # ========================================================

    for name, fn in SCRAPERS:

        try:

            print(
                f"\n→ {name}..."
            )

            results = fn()

            # Safety: make sure the scraper returned a list.
            if results is None:

                results = []

            if not isinstance(results, list):

                print(
                    f"  ⚠ {name} returned an invalid "
                    f"result type: {type(results).__name__}"
                )

                results = []

            print(
                f"  ✓ {len(results)} items"
            )
            # Show the actual hackathons returned by the scraper.
            print(f"  [{name}] Hackathons:")
            
            for h in results:
                print(
                    f"      - {h.get('title', 'Untitled')} "
                    f"| deadline={h.get('deadline', 'TBD')} "
                    f"| status={h.get('status', 'unknown')} "
                    f"| {h.get('url', '')}"
                )

            # ------------------------------------------------
            # Store results by source.
            # ------------------------------------------------

            source_results[name] = results

            # ------------------------------------------------
            # IMPORTANT:
            #
            # An empty result is NOT considered successful.
            #
            # This prevents API failures from causing a
            # source-wide purge.
            # ------------------------------------------------

            if results:

                successful_sources.add(
                    normalize_source(name)
                )

            else:

                print(
                    f"  ⚠ {name} returned 0 items — "
                    f"existing records for this source "
                    f"will NOT be purged"
                )

            # ------------------------------------------------
            # Add to global collection.
            # ------------------------------------------------

            all_results.extend(
                results
            )

        except Exception as e:

            # ------------------------------------------------
            # CRITICAL:
            #
            # A scraper failure must NEVER cause its old
            # database records to be deleted.
            # ------------------------------------------------

            print(
                f"  ✗ Error: {e}"
            )

            print(
                f"  ⚠ {name} failed — "
                f"existing records for this source "
                f"will NOT be purged"
            )

    # ========================================================
    # TOTAL
    # ========================================================

    print(
        f"\n[Total] "
        f"{len(all_results)} hackathons collected"
    )

    # ========================================================
    # SUCCESSFUL SOURCES
    # ========================================================

    print(
        "\n[Successful sources]"
    )

    for source in sorted(
        successful_sources
    ):

        print(
            f"  ✓ {source}"
        )

    # ========================================================
    # FAILED / EMPTY SOURCES
    # ========================================================

    all_source_names = {
        normalize_source(name)
        for name, _ in SCRAPERS
    }

    skipped_sources = (
        all_source_names
        - successful_sources
    )

    if skipped_sources:

        print(
            "\n[Protected sources]"
        )

        for source in sorted(
            skipped_sources
        ):

            print(
                f"  ⚠ {source} "
                f"(existing records protected)"
            )

    # ========================================================
    # EXISTING IDS
    # ========================================================

    existing = get_existing_ids()

    # ========================================================
    # NEW HACKATHONS
    # ========================================================

    new = [
        h
        for h in all_results
        if make_id(h) not in existing
    ]

    print(
        f"[New]   "
        f"{len(new)} unseen hackathons"
    )

    # ========================================================
    # SAVE / REFRESH
    # ========================================================

    save_all(
        all_results
    )

    # ========================================================
    # DEDUPLICATE
    # ========================================================

    deduped = dedupe_by_url()

    if deduped:

        print(
            f"[Dedupe] Removed "
            f"{deduped} exact duplicate URL record(s)"
        )

    # ========================================================
    # SOURCE-AWARE PURGE
    # ========================================================

    purged = purge_ended(
        successful_sources=successful_sources,
        source_results=source_results
    )

    print(
        f"[Purge] Removed "
        f"{purged} ended/stale hackathon(s)"
    )

    # ========================================================
    # NOTIFICATIONS
    # ========================================================

    if new:

        subs = get_subscribers()

        emails = [
            s["email"]
            for s in subs
            if s.get("email")
        ]

        tokens = [
            s["fcm_token"]
            for s in subs
            if s.get("fcm_token")
        ]

        # ----------------------------------------------------
        # EMAIL
        # ----------------------------------------------------

        if emails:

            send_email_notification(
                emails,
                new
            )

            print(
                f"[Email] Sent to "
                f"{len(emails)} subscriber(s)"
            )

        # ----------------------------------------------------
        # PUSH
        # ----------------------------------------------------

        if tokens:

            send_push_notification(
                tokens,
                new
            )

            print(
                f"[Push]  Sent to "
                f"{len(tokens)} device(s)"
            )

    else:

        print(
            "[Done]  No new hackathons — "
            "no notifications sent"
        )

    # ========================================================
    # FINISHED
    # ========================================================

    print(
        f"\nFinished: "
        f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()

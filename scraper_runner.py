"""
HackTracker — GitHub Actions scraper runner
Runs all scrapers, saves/refreshes hackathons in Supabase, purges ended
ones, and sends notifications for newly discovered hackathons.
"""

import os, sys, hashlib
from datetime import datetime, timedelta
import psycopg2, psycopg2.extras

sys.path.insert(0, os.path.dirname(__file__))

from scrapers.devpost_scraper import scrape_devpost
from scrapers.devto_scraper import scrape_devto
from scrapers.lablab_scraper import scrape_lablab
from scrapers.mlh_scraper import scrape_mlh
from scrapers.hackerearth_scraper import scrape_hackerearth
from scrapers.dorahacks_scraper import scrape_dorahacks
from scrapers.google_dev_scraper import scrape_google_dev_events
from scrapers.kaggle_scraper import scrape_kaggle
from notifier import send_email_notification, send_push_notification


DATABASE_URL = os.environ.get("DATABASE_URL", "")


SCRAPERS = [
    ("Devpost",       scrape_devpost),
    ("dev.to",        scrape_devto),
    ("lablab.ai",     scrape_lablab),
    ("MLH",           scrape_mlh),
    ("HackerEarth",   scrape_hackerearth),
    ("DoraHacks",     scrape_dorahacks),
    ("Google Dev",    scrape_google_dev_events),
    ("Kaggle",        scrape_kaggle),
]


def make_id(h):
    return hashlib.md5(
        (h.get("url") or h.get("title", "")).encode()
    ).hexdigest()


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

    c.execute("SELECT id FROM hackathons")

    ids = {
        r[0]
        for r in c.fetchall()
    }

    conn.close()

    return ids


def save_all(hackathons):
    """
    Insert new hackathons and refresh existing ones.

    Each scraper's status is preserved. The runner does not replace
    a scraper's status with a generic deadline-based status.
    """

    if not hackathons:
        return

    conn = get_conn()
    c = conn.cursor()

    for h in hackathons:

        try:

            c.execute("""
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
                    %s,%s,%s,%s,%s,%s,%s,%s,%s
                )

                ON CONFLICT (id) DO UPDATE SET

                    title = EXCLUDED.title,
                    source = EXCLUDED.source,
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
            ))

        except Exception as e:

            print(
                f"  Insert error: {e}"
            )

    conn.commit()
    conn.close()


import calendar


# Formats with a real day component.
DEADLINE_FORMATS = [
    "%Y-%m-%d",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y"
]


MONTH_ONLY_FORMATS = [
    "%B %Y",
    "%b %Y"
]


def parse_deadline(deadline):

    if not deadline:
        return None

    if deadline.strip().upper() in (
        "TBD",
        "N/A"
    ):
        return None

    deadline = deadline.strip()

    for fmt in DEADLINE_FORMATS:

        try:
            return datetime.strptime(
                deadline,
                fmt
            )

        except ValueError:
            continue

    # Month + year only.
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


def purge_ended(grace_days=3):
    """
    Purge hackathons according to the semantics of their individual source.

    IMPORTANT:

    Devpost:
        Trust Devpost's open/upcoming status.

    lablab.ai:
        Trust lablab's open/upcoming status.

    DoraHacks:
        Trust DoraHacks' open/upcoming status.

    Kaggle:
        Kaggle currently returns status='open' for every competition,
        so its actual deadline is used.

    dev.to:
        Only a real extracted deadline is considered.
        TBD is never purged.

    Other sources:
        Status is respected first, with the old deadline fallback.
    """

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

    cutoff = datetime.now() - timedelta(
        days=grace_days
    )

    to_delete = []

    for (
        rid,
        source,
        title,
        url,
        deadline,
        status
    ) in rows:

        source_name = (
            (source or "")
            .strip()
            .lower()
        )

        current_status = (
            (status or "")
            .strip()
            .lower()
        )

        # ==========================================================
        # DEVPOST
        # ==========================================================
        #
        # Devpost scraper explicitly requests:
        #
        #   status[]=open
        #   status[]=upcoming
        #
        # and also performs a safety check against open/upcoming.
        #
        # Therefore DO NOT use the deadline to delete an item that
        # Devpost itself says is open/upcoming.
        #
        if source_name == "devpost":

            if current_status in (
                "open",
                "upcoming"
            ):
                continue

            # Only fall back to deadline if the stored status is
            # somehow not a recognized Devpost status.
            dt = parse_deadline(deadline)

            if dt and dt < cutoff:

                to_delete.append(rid)

                print(
                    f"[Purge] {source} | {title} | "
                    f"deadline={deadline} | "
                    f"status={status} | {url}"
                )

            continue


        # ==========================================================
        # LABLAB.AI
        # ==========================================================
        #
        # lablab scraper explicitly removes ended events and only
        # returns:
        #
        #   open
        #   upcoming
        #
        # Therefore trust its status.
        #
        if source_name in (
            "lablab.ai",
            "lablab"
        ):

            if current_status in (
                "open",
                "upcoming"
            ):
                continue

            dt = parse_deadline(deadline)

            if dt and dt < cutoff:

                to_delete.append(rid)

                print(
                    f"[Purge] {source} | {title} | "
                    f"deadline={deadline} | "
                    f"status={status} | {url}"
                )

            continue


        # ==========================================================
        # DORAHACKS
        # ==========================================================
        #
        # DoraHacks explicitly checks timeline_end against now
        # before returning the hackathon.
        #
        if source_name == "dorahacks":

            if current_status in (
                "open",
                "upcoming"
            ):
                continue

            dt = parse_deadline(deadline)

            if dt and dt < cutoff:

                to_delete.append(rid)

                print(
                    f"[Purge] {source} | {title} | "
                    f"deadline={deadline} | "
                    f"status={status} | {url}"
                )

            continue


        # ==========================================================
        # KAGGLE
        # ==========================================================
        #
        # Kaggle scraper currently assigns status='open' to every
        # competition, so status cannot tell us whether it ended.
        #
        # Kaggle's deadline field is an actual competition deadline,
        # therefore use that.
        #
        if source_name == "kaggle":

            dt = parse_deadline(deadline)

            if dt and dt < cutoff:

                to_delete.append(rid)

                print(
                    f"[Purge] {source} | {title} | "
                    f"deadline={deadline} | "
                    f"status={status} | {url}"
                )

            continue


        # ==========================================================
        # DEV.TO
        # ==========================================================
        #
        # dev.to article publication dates MUST NOT be used.
        #
        # The new dev.to scraper returns:
        #
        #   actual deadline -> YYYY-MM-DD
        #
        # or:
        #
        #   TBD
        #
        # TBD means we don't know the event deadline, so KEEP it.
        #
        if source_name == "dev.to":

            if not deadline:
                continue

            if deadline.strip().upper() in (
                "TBD",
                "N/A"
            ):
                continue

            dt = parse_deadline(deadline)

            if dt and dt < cutoff:

                to_delete.append(rid)

                print(
                    f"[Purge] {source} | {title} | "
                    f"deadline={deadline} | "
                    f"status={status} | {url}"
                )

            continue


        # ==========================================================
        # ALL OTHER SOURCES
        # ==========================================================
        #
        # If the scraper says open/upcoming, trust it.
        #
        if current_status in (
            "open",
            "upcoming",
            "active",
            "live"
        ):
            continue

        # Otherwise use the old deadline fallback.
        dt = parse_deadline(deadline)

        if dt and dt < cutoff:

            to_delete.append(rid)

            print(
                f"[Purge] {source} | {title} | "
                f"deadline={deadline} | "
                f"status={status} | {url}"
            )


    # ==============================================================
    # DELETE ONLY THE VERIFIED EXPIRED ROWS
    # ==============================================================

    if to_delete:

        c.execute(
            "DELETE FROM hackathons WHERE id = ANY(%s)",
            (to_delete,)
        )

        conn.commit()

    conn.close()

    return len(to_delete)


def dedupe_by_url():
    """
    One-off cleanup: if a source changed its URL scheme
    (e.g. DoraHacks switching to uname-based URLs), old rows
    for the same hackathon can end up orphaned under a stale
    id/url and never get refreshed by ON CONFLICT.

    This keeps only the most recently first_seen row per
    (source, title).
    """

    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        DELETE FROM hackathons a
        USING hackathons b

        WHERE a.source = b.source
          AND a.title = b.title
          AND a.id <> b.id
          AND a.first_seen < b.first_seen
    """)

    removed = c.rowcount

    conn.commit()
    conn.close()

    return removed


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


def main():

    if not DATABASE_URL:

        print(
            "ERROR: DATABASE_URL not set in GitHub Secrets."
        )

        sys.exit(1)


    print("=" * 55)

    print(
        "  HackTracker Scraper — GitHub Actions"
    )

    print(
        f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )

    print("=" * 55)


    ensure_tables()


    all_results = []


    for name, fn in SCRAPERS:

        try:

            print(
                f"\n→ {name}..."
            )

            results = fn()

            print(
                f"  ✓ {len(results)} items"
            )

            all_results.extend(results)

        except Exception as e:

            print(
                f"  ✗ Error: {e}"
            )


    print(
        f"\n[Total] "
        f"{len(all_results)} hackathons collected"
    )


    existing = get_existing_ids()


    new = [
        h
        for h in all_results
        if make_id(h) not in existing
    ]


    print(
        f"[New]   "
        f"{len(new)} unseen hackathons"
    )


    # Save every scraper's results.
    save_all(all_results)


    # Remove only genuine duplicate rows.
    deduped = dedupe_by_url()

    if deduped:

        print(
            f"[Dedupe] Removed "
            f"{deduped} orphaned duplicate(s) "
            f"from URL-scheme changes"
        )


    # Source-aware purge.
    purged = purge_ended()

    print(
        f"[Purge] Removed "
        f"{purged} ended hackathon(s)"
    )


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


        if emails:

            send_email_notification(
                emails,
                new
            )

            print(
                f"[Email] Sent to "
                f"{len(emails)} subscriber(s)"
            )


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


    print(
        f"\nFinished: "
        f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )


if __name__ == "__main__":
    main()

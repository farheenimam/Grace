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
    return hashlib.md5((h.get("url") or h.get("title","")).encode()).hexdigest()

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def ensure_tables():
    conn = get_conn(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS hackathons (
        id TEXT PRIMARY KEY, source TEXT, title TEXT, url TEXT UNIQUE,
        deadline TEXT, prize TEXT, thumbnail TEXT, description TEXT,
        status TEXT DEFAULT 'open', first_seen TIMESTAMPTZ DEFAULT NOW(),
        notified BOOLEAN DEFAULT FALSE)""")
    c.execute("""CREATE TABLE IF NOT EXISTS subscribers (
        id SERIAL PRIMARY KEY, email TEXT UNIQUE,
        fcm_token TEXT, created_at TIMESTAMPTZ DEFAULT NOW())""")
    conn.commit(); conn.close()

def get_existing_ids():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT id FROM hackathons")
    ids = {r[0] for r in c.fetchall()}
    conn.close(); return ids

def save_all(hackathons):
    """Insert new hackathons, and refresh deadline/status/etc. on ones we've already seen."""
    if not hackathons: return
    conn = get_conn(); c = conn.cursor()
    for h in hackathons:
        try:
            c.execute("""INSERT INTO hackathons
                (id,source,title,url,deadline,prize,thumbnail,description,status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET
                    title=EXCLUDED.title, deadline=EXCLUDED.deadline,
                    prize=EXCLUDED.prize, thumbnail=EXCLUDED.thumbnail,
                    description=EXCLUDED.description, status=EXCLUDED.status""",
                (make_id(h), h.get("source",""), h.get("title",""), h.get("url",""),
                 h.get("deadline","TBD"), h.get("prize","N/A"), h.get("thumbnail",""),
                 h.get("description",""), h.get("status","open")))
        except Exception as e:
            print(f"  Insert error: {e}")
    conn.commit(); conn.close()

DEADLINE_FORMATS = ["%Y-%m-%d", "%B %d, %Y", "%B %Y"]

def parse_deadline(deadline):
    if not deadline or deadline.strip().upper() in ("TBD", "N/A"):
        return None
    for fmt in DEADLINE_FORMATS:
        try:
            return datetime.strptime(deadline.strip(), fmt)
        except ValueError:
            continue
    return None

def purge_ended(grace_days=1):
    """Delete rows whose deadline is a real, parseable date more than
    grace_days in the past. Unparseable deadlines (TBD, etc.) are left alone."""
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT id, deadline FROM hackathons")
    rows = c.fetchall()
    cutoff = datetime.now() - timedelta(days=grace_days)
    to_delete = []
    for rid, deadline in rows:
        dt = parse_deadline(deadline)
        if dt and dt < cutoff:
            to_delete.append(rid)
    if to_delete:
        c.execute("DELETE FROM hackathons WHERE id = ANY(%s)", (to_delete,))
        conn.commit()
    conn.close()
    return len(to_delete)

def get_subscribers():
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("SELECT email, fcm_token FROM subscribers")
    rows = c.fetchall(); conn.close()
    return rows

def main():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set in GitHub Secrets.")
        sys.exit(1)

    print("=" * 55)
    print("  HackTracker Scraper — GitHub Actions")
    print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 55)

    ensure_tables()

    all_results = []
    for name, fn in SCRAPERS:
        try:
            print(f"\n→ {name}...")
            results = fn()
            print(f"  ✓ {len(results)} items")
            all_results.extend(results)
        except Exception as e:
            print(f"  ✗ Error: {e}")

    print(f"\n[Total] {len(all_results)} hackathons collected")

    existing = get_existing_ids()
    new = [h for h in all_results if make_id(h) not in existing]
    print(f"[New]   {len(new)} unseen hackathons")

    save_all(all_results)  # inserts new rows, refreshes deadline/status on existing ones

    purged = purge_ended()
    print(f"[Purge] Removed {purged} ended hackathon(s)")

    if new:
        subs = get_subscribers()
        emails = [s["email"] for s in subs if s.get("email")]
        tokens = [s["fcm_token"] for s in subs if s.get("fcm_token")]
        if emails:
            send_email_notification(emails, new)
            print(f"[Email] Sent to {len(emails)} subscriber(s)")
        if tokens:
            send_push_notification(tokens, new)
            print(f"[Push]  Sent to {len(tokens)} device(s)")
    else:
        print("[Done]  No new hackathons — no notifications sent")

    print(f"\nFinished: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

if __name__ == "__main__":
    main()

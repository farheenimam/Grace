import json
import os
import ssl
from urllib.request import urlopen, Request
from urllib.parse import urlencode


SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


# ============================================================
# RESPONSE
# ============================================================

def respond(data, code=200):

    return {
        "statusCode": code,
        "headers": _HEADERS,
        "body": json.dumps(
            data,
            default=str
        )
    }


# ============================================================
# SUPABASE GET
# ============================================================

def sb_get(table, params=None):

    qs = (
        "?" + urlencode(params)
        if params
        else ""
    )

    url = (
        f"{SUPABASE_URL}"
        f"/rest/v1/{table}"
        f"{qs}"
    )

    req = Request(
        url,
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": (
                f"Bearer {SUPABASE_ANON_KEY}"
            ),
        }
    )

    with urlopen(
        req,
        context=SSL_CTX,
        timeout=15
    ) as r:

        return json.loads(
            r.read()
        )


# ============================================================
# SUPABASE POST
# ============================================================

def sb_post(table, data):

    body = json.dumps(
        data
    ).encode()

    url = (
        f"{SUPABASE_URL}"
        f"/rest/v1/{table}"
    )

    req = Request(
        url,
        data=body,
        method="POST",
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": (
                f"Bearer {SUPABASE_ANON_KEY}"
            ),
            "Content-Type": (
                "application/json"
            ),
            "Prefer": (
                "resolution=merge-duplicates"
            ),
        }
    )

    with urlopen(
        req,
        context=SSL_CTX,
        timeout=15
    ) as r:

        return r.status


# ============================================================
# HEALTH
# ============================================================

def handle_health():

    db_ok = False

    if (
        SUPABASE_URL
        and SUPABASE_ANON_KEY
    ):

        try:

            sb_get(
                "hackathons",
                {
                    "select": "id",
                    "limit": "1"
                }
            )

            db_ok = True

        except Exception as e:

            print(
                f"[Health] DB error: {e}"
            )

    return respond({
        "status": "healthy",
        "db": (
            "connected"
            if db_ok
            else "disconnected"
        )
    })


# ============================================================
# SOURCE NORMALIZATION
# ============================================================

def normalize_source(source):

    source = str(
        source or ""
    ).strip().lower()

    aliases = {
        "devpost": "Devpost",

        "dev.to": "dev.to",
        "devto": "dev.to",

        "lablab.ai": "lablab.ai",
        "lablab": "lablab.ai",

        "mlh": "MLH",

        "hackerearth": "HackerEarth",

        "dorahacks": "DoraHacks",
        "dora hacks": "DoraHacks",

        "google dev": "Google Dev",
        "google developers": "Google Dev",

        "kaggle": "Kaggle",
    }

    return aliases.get(
        source,
        source
    )


# ============================================================
# HACKATHONS
# ============================================================

def handle_hackathons(params):
    if not SUPABASE_URL:
        return respond({
            "count": 0,
            "hackathons": [],
            "error": "SUPABASE_URL not configured"
        })

    try:
        # --------------------------------------------------
        # Get requested limit
        # --------------------------------------------------

        requested_limit = params.get("limit", "1000")

        try:
            limit = int(requested_limit)
        except (ValueError, TypeError):
            limit = 1000

        # Database currently has 588+ records.
        # Allow enough room for ALL sources.
        limit = max(1, min(limit, 2000))

        # --------------------------------------------------
        # Base query
        # --------------------------------------------------

        sb_params = {
            "select": (
                "id,"
                "source,"
                "title,"
                "url,"
                "deadline,"
                "prize,"
                "thumbnail,"
                "description,"
                "status,"
                "first_seen"
            ),

            # Newest records first.
            "order": "first_seen.desc",

            "limit": str(limit),
        }

        # --------------------------------------------------
        # SOURCE FILTER
        # --------------------------------------------------

        source = params.get("source")

        if source:
            source = source.strip()

            # Exact case-insensitive source match.
            sb_params["source"] = f"ilike.{source}"

        # --------------------------------------------------
        # STATUS FILTER
        # --------------------------------------------------

        status = params.get("status")

        if status:
            status = status.strip().lower()
            sb_params["status"] = f"eq.{status}"

        # --------------------------------------------------
        # Fetch
        # --------------------------------------------------

        rows = sb_get(
            "hackathons",
            sb_params
        )

        # --------------------------------------------------
        # Safety: never return None
        # --------------------------------------------------

        if not isinstance(rows, list):
            rows = []

        # --------------------------------------------------
        # Debug source counts
        # --------------------------------------------------

        source_counts = {}

        for row in rows:
            source_name = row.get(
                "source",
                "unknown"
            )

            source_counts[source_name] = (
                source_counts.get(source_name, 0) + 1
            )

        print(
            "[API] Returned "
            f"{len(rows)} hackathons"
        )

        print(
            "[API] Sources: "
            f"{source_counts}"
        )

        return respond({
            "count": len(rows),
            "hackathons": rows,
            "by_source": source_counts
        })

    except Exception as e:

        print(
            f"[API] Hackathon query failed: {e}"
        )

        return respond({
            "count": 0,
            "hackathons": [],
            "by_source": {},
            "error": str(e)
        })
        
def handle_stats():

    if not SUPABASE_URL:

        return respond({
            "total": 0,
            "by_source": {}
        })


    try:

        rows = sb_get(
            "hackathons",
            {
                "select": "source"
            }
        )


        by_source = {}


        for row in rows:

            source = (
                row.get(
                    "source",
                    "unknown"
                )
            )

            by_source[source] = (
                by_source.get(
                    source,
                    0
                ) + 1
            )


        return respond({

            "total": sum(
                by_source.values()
            ),

            "by_source": by_source

        })


    except Exception as e:

        return respond({

            "total": 0,

            "by_source": {},

            "error": str(e)

        }, 500)


# ============================================================
# SOURCES
# ============================================================

def handle_sources():
    return respond({
        "sources": [
            "Devpost",
            "dev.to",
            "lablab.ai",
            "MLH",
            "HackerEarth",
            "DoraHacks",
            "Google Dev",
            "Kaggle"
        ]
    })


# ============================================================
# SUBSCRIBE
# ============================================================

def handle_subscribe(body):

    email = body.get(
        "email"
    )

    fcm_token = body.get(
        "fcm_token"
    )


    if not email and not fcm_token:

        return respond({
            "error": (
                "Provide email "
                "or fcm_token"
            )
        }, 400)


    if not SUPABASE_URL:

        return respond({
            "status": "error",
            "message": (
                "SUPABASE_URL "
                "not configured"
            )
        })


    try:

        sb_post(
            "subscribers",
            {
                "email": email,
                "fcm_token": fcm_token
            }
        )


        return respond({

            "status": "subscribed",

            "email": email

        })


    except Exception as e:

        return respond({

            "status": "error",

            "message": str(e)

        }, 500)


# ============================================================
# HANDLER
# ============================================================

def handler(
    event,
    context
):

    method = (
        event
        .get(
            "httpMethod",
            "GET"
        )
        .upper()
    )


    path = event.get(
        "path",
        "/"
    )


    params = (
        event.get(
            "queryStringParameters"
        )
        or {}
    )


    # --------------------------------------------------------
    # OPTIONS
    # --------------------------------------------------------

    if method == "OPTIONS":

        return {
            "statusCode": 200,
            "headers": _HEADERS,
            "body": ""
        }


    # --------------------------------------------------------
    # /api prefix
    # --------------------------------------------------------

    if path.startswith(
        "/api"
    ):

        path = (
            path[4:]
            or "/"
        )


    # --------------------------------------------------------
    # ROOT
    # --------------------------------------------------------

    if path in (
        "/",
        ""
    ):

        return respond({

            "status": "ok",

            "version": "2.1.0",

            "supabase": (
                "configured"
                if SUPABASE_URL
                else "not configured"
            )

        })


    # ========================================================
    # GET
    # ========================================================

    if method == "GET":

        if path == "/health":

            return handle_health()


        if path == "/hackathons":

            return handle_hackathons(
                params
            )


        if path == "/hackathons/stats":

            return handle_stats()


        if path == "/hackathons/sources":

            return handle_sources()


    # ========================================================
    # POST
    # ========================================================

    if (
        method == "POST"
        and path == "/subscribe"
    ):

        try:

            body = json.loads(
                event.get(
                    "body"
                )
                or "{}"
            )

        except Exception:

            body = {}


        return handle_subscribe(
            body
        )


    # ========================================================
    # NOT FOUND
    # ========================================================

    return respond({

        "error": "Not found"

    }, 404)

import json
import os
import ssl
from urllib.request import urlopen, Request
from urllib.parse import urlparse, urlencode

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


def respond(data, code=200):
    return {"statusCode": code, "headers": _HEADERS, "body": json.dumps(data, default=str)}


def sb_get(table, params=None):
    qs = "?" + urlencode(params) if params else ""
    url = f"{SUPABASE_URL}/rest/v1/{table}{qs}"
    req = Request(url, headers={
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    })
    with urlopen(req, context=SSL_CTX, timeout=8) as r:
        return json.loads(r.read())


def sb_post(table, data):
    body = json.dumps(data).encode()
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    req = Request(url, data=body, method="POST", headers={
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    })
    with urlopen(req, context=SSL_CTX, timeout=8) as r:
        return r.status


def handle_health():
    db_ok = False
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        try:
            sb_get("hackathons", {"limit": "1"})
            db_ok = True
        except Exception:
            pass
    return respond({"status": "healthy", "db": "connected" if db_ok else "disconnected"})


def handle_hackathons(params):
    if not SUPABASE_URL:
        return respond({
            "count": 0,
            "hackathons": [],
            "error": "SUPABASE_URL not configured"
        })

    try:
        limit = min(
            int(params.get("limit", 500)),
            500
        )

        offset = max(
            int(params.get("offset", 0)),
            0
        )

        sb_params = {
            "select": (
                "source,title,url,deadline,prize,"
                "thumbnail,description,status,first_seen"
            ),
            "order": "first_seen.desc",
            "limit": str(limit),
            "offset": str(offset),
        }

        if params.get("source"):
            sb_params["source"] = (
                f"ilike.{params['source']}"
            )

        if params.get("status"):
            sb_params["status"] = (
                f"eq.{params['status']}"
            )

        rows = sb_get(
            "hackathons",
            sb_params
        )

        return respond({
            "count": len(rows),
            "offset": offset,
            "limit": limit,
            "hackathons": rows
        })

    except Exception as e:

        return respond({
            "count": 0,
            "hackathons": [],
            "error": str(e)
        })


def handle_stats():
    if not SUPABASE_URL:
        return respond({"total": 0, "by_source": {}})
    try:
        rows = sb_get("hackathons", {"select": "source"})
        by_source = {}
        for r in rows:
            s = r.get("source", "unknown")
            by_source[s] = by_source.get(s, 0) + 1
        return respond({"total": sum(by_source.values()), "by_source": by_source})
    except Exception as e:
        return respond({"total": 0, "by_source": {}, "error": str(e)})


def handle_sources():
    return respond({
        "sources": ["Devpost", "dev.to", "lablab.ai", "MLH",
                    "HackerEarth", "DoraHacks", "Google Developers"]
    })


def handle_subscribe(body):
    email = body.get("email")
    fcm_token = body.get("fcm_token")
    if not email and not fcm_token:
        return respond({"error": "Provide email or fcm_token"}, 400)
    if not SUPABASE_URL:
        return respond({"status": "error", "message": "SUPABASE_URL not configured"})
    try:
        sb_post("subscribers", {"email": email, "fcm_token": fcm_token})
        return respond({"status": "subscribed", "email": email})
    except Exception as e:
        return respond({"status": "error", "message": str(e)})


def handler(event, context):
    method = event.get("httpMethod", "GET").upper()
    path = event.get("path", "/")
    params = event.get("queryStringParameters") or {}

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": _HEADERS, "body": ""}

    # Normalize: strip /api prefix
    if path.startswith("/api"):
        path = path[4:] or "/"

    if path in ("/", ""):
        return respond({"status": "ok", "version": "2.0.0",
                        "supabase": "configured" if SUPABASE_URL else "not configured"})

    if method == "GET":
        if path == "/health":
            return handle_health()
        if path == "/hackathons":
            return handle_hackathons(params)
        if path == "/hackathons/stats":
            return handle_stats()
        if path == "/hackathons/sources":
            return handle_sources()

    if method == "POST" and path == "/subscribe":
        try:
            body = json.loads(event.get("body") or "{}")
        except Exception:
            body = {}
        return handle_subscribe(body)

    return respond({"error": "Not found"}, 404)

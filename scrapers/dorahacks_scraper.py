import requests
import json

URL = "https://dorahacks.io/api/hackathon/list"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Origin": "https://dorahacks.io",
    "Referer": "https://dorahacks.io/hackathon",
}

params = {
    "type": "hackathon",
    "status": "open",
    "limit": 20,
    "offset": 0,
}

r = requests.get(
    URL,
    headers=HEADERS,
    params=params,
    timeout=20,
)

print("STATUS:", r.status_code)
print("CONTENT TYPE:", r.headers.get("content-type"))
print("URL:", r.url)

print("\nRESPONSE:")
print(r.text[:5000])

if r.status_code == 200:
    try:
        data = r.json()

        print("\nTOP LEVEL KEYS:")
        print(data.keys() if isinstance(data, dict) else type(data))

        print("\nJSON:")
        print(json.dumps(data, indent=2)[:10000])

    except Exception as e:
        print("JSON ERROR:", e)

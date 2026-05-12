import json
import urllib.error
import urllib.request


def test_cors(url, method, origin, extra_headers=None):
    headers = {
        "Origin": origin,
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, method=method, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        print(f"=== {method} {url} ===")
        print(f"Origin: {origin}")
        print(f"Status: {resp.status}")
        print("CORS-related headers:")
        for k, v in resp.headers.items():
            if any(x in k.lower() for x in ["access-control", "origin", "vary"]):
                print(f"  {k}: {v}")
        try:
            body = resp.read().decode()
            print(f"Body: {body[:300]}")
        except:
            pass
    except urllib.error.HTTPError as e:
        print(f"=== {method} {url} ===")
        print(f"Origin: {origin}")
        print(f"Status: {e.code}")
        print("CORS-related headers:")
        for k, v in e.headers.items():
            if any(x in k.lower() for x in ["access-control", "origin", "vary"]):
                print(f"  {k}: {v}")
        body = e.read().decode()[:500]
        print(f"Body: {body}")
    except Exception as e:
        print(f"Error: {e}")


origin = "http://localhost:60231"

# 1. Preflight OPTIONS for tryon v2
test_cors(
    "http://127.0.0.1:8010/api/v2/tryon/garment",
    "OPTIONS",
    origin,
    {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization, content-type",
    },
)
print()

# 2. Preflight OPTIONS for profile
test_cors(
    "http://127.0.0.1:8010/api/v1/profile",
    "OPTIONS",
    origin,
    {
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization, content-type",
    },
)
print()

# 3. Preflight OPTIONS for health (no auth)
test_cors(
    "http://127.0.0.1:8010/health", "OPTIONS", origin, {"Access-Control-Request-Method": "GET"}
)
print()

# 4. Preflight OPTIONS for tryon v1
test_cors(
    "http://127.0.0.1:8010/api/v1/tryon/garment",
    "OPTIONS",
    origin,
    {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization, content-type",
    },
)
print()

# 5. Actual POST to tryon v2 (without auth - should get 401)
test_cors(
    "http://127.0.0.1:8010/api/v2/tryon/garment",
    "POST",
    origin,
    {"Content-Type": "application/json", "Authorization": "Bearer invalid_token"},
)
print()

# 6. Actual GET to profile (without auth - should get 401/403)
test_cors(
    "http://127.0.0.1:8010/api/v1/profile", "GET", origin, {"Authorization": "Bearer invalid_token"}
)

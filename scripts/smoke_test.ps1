<#
.SYNOPSIS
  Smoke test for Smart Outfit Assistant backend APIs.

.DESCRIPTION
  Runs a minimal end-to-end check against a running backend:
  - /health
  - auth register/login
  - /predict (score + recommendations + explanation)
  - /api/v1/tryon/garment without auth must be 401

  Requires Python with httpx installed (backend deps include httpx).

.PARAMETER BaseUrl
  Base URL of app.main, e.g. http://127.0.0.1:8010

.EXAMPLE
  .\scripts\smoke_test.ps1 -BaseUrl http://127.0.0.1:8010
#>

param(
  [string] $BaseUrl = "http://127.0.0.1:8010"
)

$ErrorActionPreference = "Stop"

Write-Host "Smoke testing backend at $BaseUrl" -ForegroundColor Cyan

python - <<'PY'
import os
import sys
import time
import uuid

import httpx

base = os.environ.get("SMOKE_BASE_URL", "").strip() or sys.argv[1]
base = base.rstrip("/")

def assert_(cond, msg):
    if not cond:
        raise AssertionError(msg)

client = httpx.Client(base_url=base, timeout=15.0)

# health
r = client.get("/health")
assert_(r.status_code == 200, f"/health status={r.status_code} body={r.text}")
print("✓ /health")

# register/login
u = f"smoke_{uuid.uuid4().hex[:8]}"
email = f"{u}@example.com"
pwd = "Smoke123!@#"

reg = client.post("/api/v1/auth/register", json={"username": u, "email": email, "password": pwd})
assert_(reg.status_code in (200, 201), f"/auth/register status={reg.status_code} body={reg.text}")
print("✓ register")

login = client.post("/api/v1/auth/login", json={"username": u, "password": pwd})
assert_(login.status_code == 200, f"/auth/login status={login.status_code} body={login.text}")
token = login.json().get("access_token")
assert_(isinstance(token, str) and token, "missing access_token")
print("✓ login")

# predict contract
predict = client.post(
    "/predict",
    json={
        "top": "T-shirt",
        "bottom": "Jeans",
        "color_top": "white",
        "color_bottom": "navy",
        "season": "summer",
        "occasion": "casual",
    },
)
assert_(predict.status_code == 200, f"/predict status={predict.status_code} body={predict.text}")
pj = predict.json()
assert_("score" in pj and isinstance(pj["score"], (int, float)), "predict missing/invalid score")
assert_("recommendations" in pj and isinstance(pj["recommendations"], list), "predict missing recommendations")
assert_(len(pj["recommendations"]) >= 1, "predict recommendations empty")
assert_("explanation" in pj and isinstance(pj["explanation"], str) and pj["explanation"].strip(), "predict missing explanation")
print("✓ /predict contract")

# tryon should be protected (no auth)
tryon = client.post("/api/v1/tryon/garment")
assert_(tryon.status_code == 401, f"/tryon/garment expected 401 got {tryon.status_code} body={tryon.text}")
print("✓ try-on requires auth")

print("\nSmoke test OK")
PY
  "$BaseUrl"

"""Send a test request to the tryon API."""

import json
import os

import requests

BASE = "http://127.0.0.1:8010"

# Login
login_resp = requests.post(
    f"{BASE}/api/v1/auth/login",
    json={"username": "testuser2", "password": "testpass123"},  # pragma: allowlist secret
    timeout=10,
)
if login_resp.status_code != 200:
    print(f"Login failed: {login_resp.status_code} - {login_resp.text[:300]}")
    exit(1)

token = login_resp.json()["data"]["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Test with correct multipart
with (
    open(r"D:\Users\omen\OneDrive\桌面\clothing-assistant\data\test_garment.jpg", "rb") as gf,
    open(r"D:\Users\omen\OneDrive\桌面\clothing-assistant\data\test_person.jpg", "rb") as pf,
):
    files = [
        ("garment_file", ("garment.jpg", gf, "image/jpeg")),
        ("person_file", ("person.jpg", pf, "image/jpeg")),
    ]
    data = {"mode": "realistic", "debug_mode": "preprocess_only"}
    resp = requests.post(
        f"{BASE}/api/v2/tryon/garment",
        files=files,
        data=data,
        headers=headers,
        timeout=60,
    )

print(f"Status: {resp.status_code}")
result = resp.json()
print(json.dumps(result, indent=2, ensure_ascii=False))

# Check debug files
data_field = result.get("data", {})
debug_dir = data_field.get("debug_session_dir")
if debug_dir:
    print(f"\nDebug session dir: {debug_dir}")
    if os.path.exists(debug_dir):
        files_in_dir = os.listdir(debug_dir)
        print(f"Files ({len(files_in_dir)}):")
        for f in sorted(files_in_dir):
            fp = os.path.join(debug_dir, f)
            print(f"  {f} ({os.path.getsize(fp)//1024}KB)")
    else:
        print("  Directory does NOT exist!")
else:
    print(f"\nNo debug_session_dir in response.")
    print(f"Keys in data: {list(data_field.keys())}")

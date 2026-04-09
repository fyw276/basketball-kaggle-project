"""
Test suitability analysis API
"""

import io

import requests
from PIL import Image

BASE_URL = "http://127.0.0.1:8010/api/v1"

# Login
print("1. Logging in...")
response = requests.post(
    f"{BASE_URL}/auth/login", json={"username": "test_simple_user", "password": "Test123!@#"}
)

if response.status_code != 200:
    print(f"✗ Login failed: {response.status_code}")
    exit(1)

token = response.json()["access_token"]
print(f"✓ Login successful")

headers = {"Authorization": f"Bearer {token}"}

# Check if user has profile
print("\n2. Checking user profile...")
response = requests.get(f"{BASE_URL}/profile", headers=headers)
print(f"  Status: {response.status_code}")

if response.status_code == 404:
    print("✗ User profile not found!")
    print("  Creating profile...")

    # Create profile
    profile_data = {
        "height": 170,
        "body_type": "偏瘦",
        "skin_tone": "冷白",
        "style_preference": ["通勤"],
        "budget_range": "中等",  # Fixed: should be "中等" not "中等价位"
    }

    response = requests.post(f"{BASE_URL}/profile", headers=headers, json=profile_data)
    if response.status_code == 201:
        print("✓ Profile created successfully")
    else:
        print(f"✗ Profile creation failed: {response.status_code}")
        print(f"  Response: {response.text}")
        exit(1)
elif response.status_code == 200:
    print("✓ Profile exists")
    print(f"  Profile: {response.json()}")

# Create test image
print("\n3. Creating test image...")
img = Image.new("RGB", (100, 100), color="blue")
img_bytes = io.BytesIO()
img.save(img_bytes, format="JPEG")
img_bytes.seek(0)

# Test suitability analysis
print("\n4. Testing suitability analysis...")
files = {"file": ("test.jpg", img_bytes, "image/jpeg")}

try:
    response = requests.post(f"{BASE_URL}/analysis/suitability", headers=headers, files=files)
    print(f"  Status: {response.status_code}")
    if response.status_code == 200:
        print(f"✓ Suitability analysis successful!")
        result = response.json()
        print(f"  Overall score: {result['suitability_score']}")
        print(f"  Color score: {result['color_score']}")
        print(f"  Fit score: {result['fit_score']}")
        print(f"  Style score: {result['style_score']}")
    else:
        print(f"✗ Suitability analysis failed")
        print(f"  Response: {response.text}")
except Exception as e:
    print(f"✗ Request error: {e}")

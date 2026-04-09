"""
Test wardrobe API with actual image upload
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

# Create a simple test image
print("\n2. Creating test image...")
img = Image.new("RGB", (100, 100), color="red")
img_bytes = io.BytesIO()
img.save(img_bytes, format="JPEG")
img_bytes.seek(0)

# Upload image
print("\n3. Uploading image to /wardrobe/simple/garments...")
files = {"file": ("test.jpg", img_bytes, "image/jpeg")}

try:
    response = requests.post(f"{BASE_URL}/wardrobe/simple/garments", headers=headers, files=files)
    print(f"  Status: {response.status_code}")
    if response.status_code == 201:
        print(f"✓ Upload successful!")
        print(f"  Response: {response.json()}")
    else:
        print(f"✗ Upload failed")
        print(f"  Response: {response.text}")
except Exception as e:
    print(f"✗ Upload error: {e}")

print("\n4. Getting garments list...")
response = requests.get(f"{BASE_URL}/wardrobe/simple/garments", headers=headers)
print(f"  Status: {response.status_code}")
print(f"  Total garments: {response.json()['total']}")

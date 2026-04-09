"""
Diagnose wardrobe API errors
"""

import json

import requests

BASE_URL = "http://127.0.0.1:8010/api/v1"

# Use existing test user
username = "test_simple_user"
password = "Test123!@#"

print("=" * 60)
print("Diagnosing Wardrobe API Error")
print("=" * 60)

# Login
print("\n1. Logging in...")
response = requests.post(
    f"{BASE_URL}/auth/login", json={"username": username, "password": password}
)

if response.status_code != 200:
    print(f"✗ Login failed: {response.status_code}")
    print(f"  Response: {response.text}")
    exit(1)

token = response.json()["access_token"]
print(f"✓ Login successful")

headers = {"Authorization": f"Bearer {token}"}

# Test GET request
print("\n2. Testing GET /wardrobe/simple/garments...")
response = requests.get(f"{BASE_URL}/wardrobe/simple/garments", headers=headers)
print(f"  Status: {response.status_code}")
print(f"  Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

# Check if user has profile
print("\n3. Checking user profile...")
response = requests.get(f"{BASE_URL}/profile", headers=headers)
print(f"  Status: {response.status_code}")
if response.status_code == 200:
    print(f"✓ Profile exists")
    print(f"  Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
elif response.status_code == 404:
    print(f"✗ Profile not found - this might cause issues!")
    print(f"  Response: {response.text}")
else:
    print(f"  Response: {response.text}")

print("\n" + "=" * 60)

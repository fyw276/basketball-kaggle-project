"""
Test script for simplified wardrobe API
"""

import sys

import requests

# Configuration
BASE_URL = "http://127.0.0.1:8010/api/v1"


def test_simple_api():
    """Test the simplified wardrobe API"""
    print("=" * 60)
    print("Testing Simplified Wardrobe API")
    print("=" * 60)

    # Step 1: Register a test user
    print("\n1. Registering test user...")
    register_data = {
        "username": "test_simple_user",
        "email": "test_simple@example.com",
        "password": "Test123!@#",
    }

    try:
        response = requests.post(f"{BASE_URL}/auth/register", json=register_data)
        if response.status_code == 201:
            print("✓ User registered successfully")
        elif response.status_code == 400 and "already exists" in response.text:
            print("✓ User already exists, continuing...")
        else:
            print(f"✗ Registration failed: {response.status_code}")
            print(f"  Response: {response.text}")
    except Exception as e:
        print(f"✗ Registration error: {e}")
        return False

    # Step 2: Login
    print("\n2. Logging in...")
    login_data = {"username": "test_simple_user", "password": "Test123!@#"}

    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        if response.status_code == 200:
            token = response.json()["access_token"]
            print("✓ Login successful")
            print(f"  Token: {token[:20]}...")
        else:
            print(f"✗ Login failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ Login error: {e}")
        return False

    headers = {"Authorization": f"Bearer {token}"}

    # Step 3: Test GET /wardrobe/simple/garments
    print("\n3. Testing GET /wardrobe/simple/garments...")
    try:
        response = requests.get(f"{BASE_URL}/wardrobe/simple/garments", headers=headers)
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✓ GET request successful")
            print(f"  Total garments: {data.get('total', 0)}")
        else:
            print(f"✗ GET request failed")
            print(f"  Response: {response.text}")
    except Exception as e:
        print(f"✗ GET request error: {e}")

    # Step 4: Test POST /wardrobe/simple/garments (without file)
    print("\n4. Testing POST /wardrobe/simple/garments (checking endpoint)...")
    try:
        # Just test if endpoint exists (will fail without file, but should not be 500)
        response = requests.post(f"{BASE_URL}/wardrobe/simple/garments", headers=headers)
        print(f"  Status: {response.status_code}")
        if response.status_code == 422:
            print("✓ Endpoint exists (422 = missing file parameter, expected)")
        elif response.status_code == 500:
            print("✗ Server error (500) - there's a bug in the endpoint!")
            print(f"  Response: {response.text}")
        else:
            print(f"  Response: {response.text}")
    except Exception as e:
        print(f"✗ POST request error: {e}")

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)

    return True


if __name__ == "__main__":
    try:
        test_simple_api()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        sys.exit(1)

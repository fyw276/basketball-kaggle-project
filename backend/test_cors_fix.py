"""
Test script to verify CORS configuration allows Flutter Web connections
"""

import json

import requests


def test_cors_from_different_ports():
    """Test CORS from different localhost ports"""
    base_url = "http://127.0.0.1:8010"

    # Simulate requests from different ports (like Flutter Web would send)
    test_origins = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:50850",  # Flutter Web random port
        "http://localhost:54321",  # Another random port
        "http://127.0.0.1:8010",
    ]

    print("Testing CORS configuration...")
    print("=" * 60)

    for origin in test_origins:
        try:
            # Send OPTIONS preflight request
            headers = {
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            }

            response = requests.options(
                f"{base_url}/api/v1/auth/register", headers=headers, timeout=5
            )

            cors_header = response.headers.get("Access-Control-Allow-Origin", "NOT SET")

            if cors_header == origin or cors_header == "*":
                print(f"✓ {origin}: ALLOWED")
            else:
                print(f"✗ {origin}: BLOCKED (got: {cors_header})")

        except requests.exceptions.RequestException as e:
            print(f"✗ {origin}: ERROR - {str(e)}")

    print("=" * 60)


def test_registration_and_login():
    """Test user registration and login"""
    base_url = "http://127.0.0.1:8010/api/v1"

    print("\nTesting Registration and Login...")
    print("=" * 60)

    # Test data
    test_user = {
        "username": "cors_test_user",
        "email": "cors_test@example.com",
        "password": "Test123!@#",
    }

    try:
        # 1. Register
        print("1. Registering user...")
        register_response = requests.post(
            f"{base_url}/auth/register",
            json=test_user,
            headers={"Origin": "http://localhost:50850"},  # Simulate Flutter Web
            timeout=10,
        )

        if register_response.status_code == 201:
            print(f"   ✓ Registration successful")
            print(f"   User ID: {register_response.json().get('id')}")
        elif register_response.status_code == 400:
            error_detail = register_response.json().get("detail", "Unknown error")
            if "already exists" in error_detail.lower():
                print(f"   ℹ User already exists (this is OK for testing)")
            else:
                print(f"   ✗ Registration failed: {error_detail}")
        else:
            print(f"   ✗ Registration failed: {register_response.status_code}")
            print(f"   Response: {register_response.text}")

        # 2. Login
        print("\n2. Logging in...")
        login_data = {"username": test_user["username"], "password": test_user["password"]}

        login_response = requests.post(
            f"{base_url}/auth/login",
            json=login_data,
            headers={"Origin": "http://localhost:50850"},  # Simulate Flutter Web
            timeout=10,
        )

        if login_response.status_code == 200:
            token = login_response.json().get("access_token")
            print(f"   ✓ Login successful")
            print(f"   Token: {token[:20]}..." if token else "   No token received")
        else:
            print(f"   ✗ Login failed: {login_response.status_code}")
            print(f"   Response: {login_response.text}")

    except requests.exceptions.RequestException as e:
        print(f"   ✗ Request failed: {str(e)}")

    print("=" * 60)


def check_backend_health():
    """Check if backend is running"""
    try:
        response = requests.get("http://127.0.0.1:8010/health", timeout=5)
        if response.status_code == 200:
            print("✓ Backend is running")
            print(f"  Version: {response.json().get('version')}")
            return True
        else:
            print(f"✗ Backend returned status code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"✗ Backend is not running: {str(e)}")
        print("\nPlease start the backend first:")
        print("  cd backend")
        print("  python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("CORS Configuration Test")
    print("=" * 60 + "\n")

    # Check if backend is running
    if not check_backend_health():
        exit(1)

    print()

    # Test CORS
    test_cors_from_different_ports()

    # Test registration and login
    test_registration_and_login()

    print("\n✓ All tests completed!")
    print("\nNext steps:")
    print("1. Restart your Flutter Web app")
    print("2. Try registering with: username='flutter_user', password='Test123!@#'")
    print("3. Check the browser console for any CORS errors")

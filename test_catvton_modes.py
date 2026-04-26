"""
Test CatVTON via realistic and professional modes.
Sends real API requests to the backend.
"""
import asyncio
import base64
import json as _json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))

import httpx
from PIL import Image


BACKEND_URL = "http://127.0.0.1:8010"
PERSON_IMG = Path(__file__).parent / "backend" / "preview_1.jpg"
GARMENT_IMG = Path(__file__).parent / "backend" / "preview_2.jpg"


def load_image(path: Path) -> bytes:
    img = Image.open(path).convert("RGB")
    import io
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


async def get_auth_headers(client: httpx.AsyncClient) -> dict:
    """Register a test user and return auth headers."""
    username = f"test_{uuid.uuid4().hex[:8]}"
    email = f"{username}@test.com"
    password = "testpass123"

    try:
        await client.post(
            f"{BACKEND_URL}/api/v1/auth/register",
            json={"username": username, "email": email, "password": password},
            timeout=15.0,
        )
    except Exception:
        pass

    login_resp = await client.post(
        f"{BACKEND_URL}/api/v1/auth/login",
        json={"username": username, "password": password},
        timeout=15.0,
    )
    if login_resp.status_code == 200:
        resp_json = login_resp.json()
        # Token may be at top level or nested under "data"
        token = resp_json.get("access_token") or resp_json.get("data", {}).get("access_token")
        if token:
            return {"Authorization": f"Bearer {token}"}

    raise RuntimeError(f"Could not authenticate: {login_resp.status_code} - {login_resp.text[:200]}")


async def test_mode(client: httpx.AsyncClient, headers: dict, mode: str, label: str) -> dict:
    print(f"\n{'=' * 60}")
    print(f"TEST: {label} (mode={mode})")
    print("=" * 60)

    person_bytes = load_image(PERSON_IMG)
    garment_bytes = load_image(GARMENT_IMG)

    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }
    data = {
        "garment_category": "上装",
        "mode": mode,
    }

    t0 = time.time()
    try:
        resp = await client.post(
            f"{BACKEND_URL}/api/v2/tryon/garment",
            files=files,
            data=data,
            headers=headers,
            timeout=900.0,
        )
        elapsed = time.time() - t0
        print(f"Status: {resp.status_code}, Time: {elapsed:.1f}s")

        if resp.status_code == 200:
            result = resp.json()
            print(f"  Raw response keys: {list(result.keys())}")
            print(f"  Full response: {_json.dumps(result, ensure_ascii=False, indent=2)[:500]}")
            print(f"  Success: {result.get('status')}")
            print(f"  Message: {result.get('message', '')}")
            print(f"  Pipeline: {result.get('pipeline', '?')}")
            engine = result.get("metadata", {}).get("engine", "unknown")
            print(f"  Engine: {engine}")
            result_url = result.get("result_image_url")
            if result_url:
                print(f"  Result URL: {result_url}")
            print(f"  QC scores: {result.get('qc_scores', {})}")
            print(f"  Postprocess: {result.get('metadata', {}).get('postprocess_applied', False)}")
            return {"success": True, "elapsed": elapsed, "engine": engine, "result": result}
        else:
            print(f"  Error (raw): {resp.text[:800]}")
            try:
                err_data = resp.json()
                print(f"  Error parsed keys: {list(err_data.keys())}")
                print(f"  Error details: {_json.dumps(err_data, ensure_ascii=False)[:800]}")
            except Exception:
                pass
            return {"success": False, "elapsed": elapsed, "error": resp.text[:200]}
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  Exception after {elapsed:.1f}s: {e}")
        return {"success": False, "elapsed": elapsed, "error": str(e)}


async def main():
    print(f"Backend: {BACKEND_URL}")
    print(f"Person image: {PERSON_IMG} ({Path(PERSON_IMG).exists()})")
    print(f"Garment image: {GARMENT_IMG} ({Path(GARMENT_IMG).exists()})")

    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{BACKEND_URL}/health", timeout=15.0)
            print(f"Backend health: {r.status_code}")
        except Exception as e:
            print(f"Backend NOT reachable: {e}")
            return

        headers = await get_auth_headers(client)
        print(f"Auth: OK (user registered and logged in)")

        r1 = await test_mode(client, headers, "realistic", "Realistic Mode (CatVTON direct)")
        print("-" * 60)
        r2 = await test_mode(client, headers, "professional", "Professional Mode (CatVTON + postprocess)")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Realistic mode:   {'OK' if r1.get('success') else 'FAIL'} ({r1.get('elapsed', 0):.1f}s, engine={r1.get('engine', '?')})")
    print(f"Professional mode: {'OK' if r2.get('success') else 'FAIL'} ({r2.get('elapsed', 0):.1f}s, engine={r2.get('engine', '?')})")


if __name__ == "__main__":
    asyncio.run(main())

"""
Contract-style tests: auth gates + stable JSON shapes for critical routes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.api_json import unwrap_json


@pytest.mark.parametrize(
    "method,path,kwargs",
    [
        (
            "GET",
            "/api/v1/smart-outfit/weather",
            {"params": {"latitude": 31.23, "longitude": 121.47}},
        ),
        (
            "POST",
            "/api/v1/smart-outfit/generate",
            {
                "json": {
                    "image_url": "/uploads/u/x.jpg",
                    "location": "上海",
                    "city": "",
                    "address": {},
                    "weather": "晴",
                    "temperature": 20.0,
                    "mood": "",
                    "count": 1,
                    "regeneration_index": 0,
                }
            },
        ),
        ("POST", "/api/v1/wardrobe/simple/garments/repair-image-urls", {"json": {}}),
    ],
)
def test_key_routes_require_auth(client, method, path, kwargs):
    """Unauthenticated requests must not succeed (401/403)."""
    r = client.request(method, path, **kwargs)
    assert r.status_code in (401, 403), f"{method} {path} -> {r.status_code} {r.text}"


@patch("app.api.smart_outfit.fetch_weather_lat_lon", new_callable=AsyncMock)
def test_smart_outfit_weather_authenticated_shape(mock_fetch, client, auth_headers):
    mock_fetch.return_value = {
        "city": "上海市",
        "addr_city": "上海市",
        "province": "上海",
        "district": "浦东新区",
        "street": "",
        "full_address": "上海市浦东新区",
        "display_address": "上海市浦东新区",
        "latitude": 31.23,
        "longitude": 121.47,
        "temperature": 19.5,
        "weather": "晴",
        "weather_code": 0,
        "geocode_source": "test",
        "geocode_error": "",
    }
    r = client.get(
        "/api/v1/smart-outfit/weather",
        params={"latitude": 31.23, "longitude": 121.47},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = unwrap_json(r)
    assert isinstance(data, dict)
    assert "weather" in data and "temperature" in data
    assert "address" in data and isinstance(data["address"], dict)


def test_wardrobe_repair_authenticated_shape(client, auth_headers):
    r = client.post(
        "/api/v1/wardrobe/simple/garments/repair-image-urls",
        json={},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = unwrap_json(r)
    assert data.get("message") == "ok"
    for key in ("scanned", "changed", "skipped"):
        assert key in data
        assert isinstance(data[key], int)
    assert "changes" in data and isinstance(data["changes"], list)


def test_smart_outfit_generate_authenticated_shape(client, auth_headers):
    fake_payload = {
        "outfits": [
            {
                "description": "契约测试占位",
                "items": [],
                "preview_image_url": "",
            }
        ],
        "city": "上海",
        "weather": "晴",
        "temperature": 20.0,
        "mood": "",
        "weather_fallback": False,
        "message": "ok",
    }
    with patch("app.api.smart_outfit.generate_smart_outfits", new_callable=AsyncMock) as m:
        m.return_value = fake_payload
        r = client.post(
            "/api/v1/smart-outfit/generate",
            headers=auth_headers,
            json={
                "image_url": "/uploads/00000000-0000-0000-0000-000000000001/ref.jpg",
                "location": "上海",
                "city": "",
                "address": {},
                "weather": "晴",
                "temperature": 20.0,
                "mood": "",
                "count": 1,
                "regeneration_index": 0,
            },
        )
    assert r.status_code == 200, r.text
    data = unwrap_json(r)
    assert isinstance(data.get("outfits"), list)
    assert len(data["outfits"]) >= 1
    assert "weather" in data
    assert "temperature" in data
    assert "address" in data

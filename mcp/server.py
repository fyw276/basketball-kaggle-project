#!/usr/bin/env python3
"""Smart Outfit MCP server.

This server uses FastMCP and bridges tool calls to existing backend APIs.

Environment variables:
- OUTFIT_API_BASE_URL (default: http://127.0.0.1:8010/api/v1)
- OUTFIT_API_TOKEN (required for authenticated tools)
"""

from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency 'mcp'. Install with: pip install mcp httpx"
    ) from exc

DEFAULT_BASE_URL = "http://127.0.0.1:8010/api/v1"
mcp = FastMCP("smart-outfit-mcp")


def _base_url() -> str:
    return os.getenv("OUTFIT_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _token() -> str:
    token = os.getenv("OUTFIT_API_TOKEN", "").strip()
    if not token:
        raise ValueError("OUTFIT_API_TOKEN is required")
    return token


def _headers(with_auth: bool = True) -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if with_auth:
        headers["Authorization"] = f"Bearer {_token()}"
    return headers


def _unwrap_envelope(payload: Any) -> Any:
    """Align with FastAPI envelope: success -> inner data."""
    if isinstance(payload, dict) and payload.get("success") is True and "data" in payload:
        return payload["data"]
    return payload


def _handle(resp: httpx.Response) -> Any:
    try:
        payload = resp.json()
    except Exception:
        payload = {"status_code": resp.status_code, "text": resp.text}

    if resp.status_code >= 400:
        detail = None
        if isinstance(payload, dict):
            detail = payload.get("detail")
            err = payload.get("error")
            if isinstance(err, dict) and err.get("message"):
                detail = detail or err.get("message")
        raise ValueError(f"HTTP {resp.status_code}: {detail or payload}")
    return _unwrap_envelope(payload)


def _file_part(path: str) -> tuple[str, Any, str]:
    p = Path(path)
    if not p.exists():
        raise ValueError(f"File not found: {path}")
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return (p.name, p.open("rb"), mime)


@mcp.tool()
def health() -> Dict[str, Any]:
    """Check backend health endpoint."""
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(_base_url().replace("/api/v1", "") + "/health")
    return _handle(resp)


@mcp.tool()
def login(identifier: str, password: str) -> Dict[str, Any]:
    """Login with username/email/phone and return token payload."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{_base_url()}/auth/login",
            json={"username": identifier, "password": password},
            headers=_headers(with_auth=False),
        )
    return _handle(resp)


@mcp.tool()
def list_wardrobe(page: int = 1, page_size: int = 20, category: Optional[str] = None) -> Dict[str, Any]:
    """List wardrobe garments for current token user."""
    params: Dict[str, Any] = {"page": page, "page_size": page_size}
    if category:
        params["category"] = category

    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"{_base_url()}/wardrobe/garments",
            headers=_headers(with_auth=True),
            params=params,
        )
    return _handle(resp)


@mcp.tool()
def analyze_similarity(image_path: str) -> Dict[str, Any]:
    """Analyze similarity using one image path."""
    fd = None
    try:
        name, fd, mime = _file_part(image_path)
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{_base_url()}/analysis/similarity",
                headers=_headers(with_auth=True),
                files={"file": (name, fd, mime)},
            )
        return _handle(resp)
    finally:
        if fd:
            fd.close()


@mcp.tool()
def recommend_outfits(
    image_paths: List[str],
    num_outfits: int = 3,
    scene: Optional[str] = None,
) -> Dict[str, Any]:
    """Recommend outfits with one or multiple images."""
    if not image_paths:
        raise ValueError("image_paths must not be empty")

    files = []
    opened = []
    try:
        for p in image_paths:
            name, fd, mime = _file_part(p)
            opened.append(fd)
            files.append(("files", (name, fd, mime)))

        endpoint = f"{_base_url()}/analysis/outfits?num_outfits={num_outfits}"
        if scene:
            endpoint += f"&scene={scene}"

        with httpx.Client(timeout=180.0) as client:
            resp = client.post(endpoint, headers=_headers(with_auth=True), files=files)
        return _handle(resp)
    finally:
        for fd in opened:
            fd.close()


@mcp.tool()
def analyze_suitability(image_path: str) -> Dict[str, Any]:
    """Analyze suitability score using one image path."""
    fd = None
    try:
        name, fd, mime = _file_part(image_path)
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{_base_url()}/analysis/suitability",
                headers=_headers(with_auth=True),
                files={"file": (name, fd, mime)},
            )
        return _handle(resp)
    finally:
        if fd:
            fd.close()


@mcp.tool()
def get_weather_by_city(city: str) -> Any:
    """Fetch weather context by city name (requires login)."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"{_base_url()}/smart-outfit/weather-by-city",
            headers=_headers(with_auth=True),
            params={"name": city},
        )
    return _handle(resp)


@mcp.tool()
def upload_smart_outfit_reference(image_path: str) -> Any:
    """Upload a reference garment image; returns image_url for generate_smart_outfit."""
    fd = None
    try:
        name, fd, mime = _file_part(image_path)
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{_base_url()}/smart-outfit/upload-reference",
                headers=_headers(with_auth=True),
                files={"file": (name, fd, mime)},
            )
        return _handle(resp)
    finally:
        if fd:
            fd.close()


@mcp.tool()
def generate_smart_outfit(
    image_url: str,
    city: str = "",
    location: str = "",
    weather: str = "晴",
    temperature: float = 20.0,
    mood: str = "",
    count: int = 3,
    regeneration_index: int = 0,
    address_json: Optional[str] = None,
    gender_expression: Optional[float] = None,
) -> Any:
    """
    Generate smart outfits from a reference image URL plus place/weather/mood.
    Use upload_smart_outfit_reference first to obtain image_url.
    """
    body: Dict[str, Any] = {
        "image_url": image_url,
        "location": location or "",
        "city": city or "",
        "address": {},
        "weather": weather or "晴",
        "temperature": float(temperature),
        "mood": mood or "",
        "count": min(max(int(count), 1), 5),
        "regeneration_index": max(int(regeneration_index), 0),
    }
    if address_json:
        try:
            parsed = json.loads(address_json)
            if isinstance(parsed, dict):
                body["address"] = parsed
        except json.JSONDecodeError as exc:
            raise ValueError(f"address_json must be valid JSON object: {exc}") from exc
    if gender_expression is not None:
        body["gender_expression"] = float(gender_expression)

    with httpx.Client(timeout=180.0) as client:
        resp = client.post(
            f"{_base_url()}/smart-outfit/generate",
            headers={**_headers(with_auth=True), "Content-Type": "application/json"},
            json=body,
        )
    return _handle(resp)


@mcp.tool()
def list_mood_types() -> Any:
    """List available mood types (no authentication required)."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{_base_url()}/mood/moods", headers={"Accept": "application/json"})
    return _handle(resp)


@mcp.tool()
def recommend_by_mood(mood: str = "", include_wardrobe: bool = False) -> Any:
    """Mood-based style/color advice; optional wardrobe garment matches."""
    body = {"mood": mood or "", "include_wardrobe": bool(include_wardrobe)}
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{_base_url()}/mood/recommend",
            headers={**_headers(with_auth=True), "Content-Type": "application/json"},
            json=body,
        )
    return _handle(resp)


@mcp.tool()
def virtual_try_on(
    garment_image_path: str,
    person_image_path: str,
    prompt: str = "",
    model_gender: str = "neutral",
) -> Any:
    """Virtual try-on: garment product photo + person photo. GPU recommended; may fallback."""
    if model_gender not in ("male", "female", "neutral"):
        raise ValueError("model_gender must be male, female, or neutral")

    g_name, g_fd, g_mime = _file_part(garment_image_path)
    p_name, p_fd, p_mime = _file_part(person_image_path)
    try:
        with httpx.Client(timeout=300.0) as client:
            resp = client.post(
                f"{_base_url()}/tryon/garment",
                headers=_headers(with_auth=True),
                data={"prompt": prompt or "", "model_gender": model_gender},
                files={
                    "garment_file": (g_name, g_fd, g_mime),
                    "person_file": (p_name, p_fd, p_mime),
                },
            )
        return _handle(resp)
    finally:
        g_fd.close()
        p_fd.close()


@mcp.tool()
def list_outfit_collections(
    page: int = 1,
    page_size: int = 20,
    scene: Optional[str] = None,
) -> Any:
    """List user's saved outfit collections."""
    params: Dict[str, Any] = {"page": page, "page_size": page_size}
    if scene:
        params["scene"] = scene
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"{_base_url()}/outfits/collections",
            headers=_headers(with_auth=True),
            params=params,
        )
    return _handle(resp)


@mcp.tool()
def submit_feedback(
    event_type: str,
    source: str = "analysis_outfit",
    garment_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    scene: Optional[str] = None,
) -> Any:
    """Record like / dislike / adopt / view for analytics and reranking."""
    body: Dict[str, Any] = {
        "event_type": event_type,
        "source": source,
        "garment_id": garment_id,
        "collection_id": collection_id,
        "scene": scene,
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{_base_url()}/feedback/events",
            headers={**_headers(with_auth=True), "Content-Type": "application/json"},
            json=body,
        )
    return _handle(resp)


@mcp.tool()
def get_analytics_summary(scope: str = "user") -> Any:
    """Flywheel metrics: feedback counts, collection_rate_proxy, positive_feedback_rate."""
    sc = scope if scope in ("user", "global") else "user"
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"{_base_url()}/analytics/summary",
            headers=_headers(with_auth=True),
            params={"scope": sc},
        )
    return _handle(resp)


@mcp.tool()
def route_agent_intent(query: str) -> Any:
    """Rule-based intent -> suggested MCP tool names (no auth)."""
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            f"{_base_url()}/agent/intent",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={"query": query},
        )
    return _handle(resp)


@mcp.tool()
def add_memory_snippet(title: str, content: str) -> Any:
    """Store a user memory line for keyword RAG search."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{_base_url()}/memory/snippets",
            headers={**_headers(with_auth=True), "Content-Type": "application/json"},
            json={"title": title or "", "content": content},
        )
    return _handle(resp)


@mcp.tool()
def search_memory_snippets(query: str, top_k: int = 5) -> Any:
    """Keyword overlap search over memory snippets."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"{_base_url()}/memory/snippets/search",
            headers=_headers(with_auth=True),
            params={"q": query, "top_k": top_k},
        )
    return _handle(resp)


if __name__ == "__main__":
    mcp.run()

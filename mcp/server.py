#!/usr/bin/env python3
"""Smart Outfit MCP server.

This server uses FastMCP and bridges tool calls to existing backend APIs.

Environment variables:
- OUTFIT_API_BASE_URL (default: http://127.0.0.1:8010/api/v1)
- OUTFIT_API_TOKEN (required for authenticated tools)
"""

from __future__ import annotations

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


def _handle(resp: httpx.Response) -> Any:
    try:
        payload = resp.json()
    except Exception:
        payload = {"status_code": resp.status_code, "text": resp.text}

    if resp.status_code >= 400:
        detail = payload.get("detail") if isinstance(payload, dict) else str(payload)
        raise ValueError(f"HTTP {resp.status_code}: {detail or payload}")
    return payload


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


if __name__ == "__main__":
    mcp.run()

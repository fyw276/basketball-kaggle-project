"""Simple in-process sliding-window rate limit (per client IP)."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class SlidingWindowRateLimitMiddleware(BaseHTTPMiddleware):
    """Reject with 429 when an IP exceeds ``limit`` requests per ``window_seconds``."""

    def __init__(self, app, *, limit: int, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.limit = max(1, limit)
        self.window = max(1, window_seconds)
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def _allow(self, ip: str) -> bool:
        now = time.monotonic()
        q = self._hits[ip]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS":
            return await call_next(request)
        if path in _RATE_LIMIT_SKIP_PATHS or path.startswith(_SKIP_PREFIXES):
            return await call_next(request)

        ip = _client_ip(request)
        if not self._allow(ip):
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "data": None,
                    "error": {
                        "type": "RateLimitExceeded",
                        "message": f"Too many requests (limit {self.limit} per {self.window}s)",
                        "status_code": 429,
                    },
                    "message": "Too many requests",
                },
            )
        return await call_next(request)


_RATE_LIMIT_SKIP_PATHS = frozenset(
    {
        "/",
        "/health",
        "/health/ready",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/redoc-alt",
        "/test-html",
    }
)
_SKIP_PREFIXES = ("/docs/", "/redoc/", "/static/", "/uploads/")

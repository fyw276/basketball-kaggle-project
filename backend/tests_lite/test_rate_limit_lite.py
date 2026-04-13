"""Sliding-window rate limit middleware (in-process)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.rate_limit import SlidingWindowRateLimitMiddleware


def test_rate_limit_allows_health_without_counting():
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "healthy"}

    @app.get("/api/v1/x")
    def x():
        return {"ok": True}

    app.add_middleware(SlidingWindowRateLimitMiddleware, limit=2, window_seconds=60)
    c = TestClient(app)
    for _ in range(5):
        r = c.get("/health")
        assert r.status_code == 200
    assert c.get("/api/v1/x").status_code == 200
    assert c.get("/api/v1/x").status_code == 200
    assert c.get("/api/v1/x").status_code == 429


def test_rate_limit_blocks_excess_requests():
    app = FastAPI()

    @app.get("/api/v1/x")
    def x():
        return {"ok": True}

    app.add_middleware(SlidingWindowRateLimitMiddleware, limit=2, window_seconds=60)
    c = TestClient(app)
    assert c.get("/api/v1/x").status_code == 200
    assert c.get("/api/v1/x").status_code == 200
    r = c.get("/api/v1/x")
    assert r.status_code == 429

"""Tests for hybrid memory search: embedding client, hybrid scoring, API integration."""

import math
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.memory_snippet import MemorySnippet
from app.services.embedding_client import EmbeddingClient, _l2_normalize
from app.services.memory_search import _cosine_similarity, _keyword_score, _tokenize, hybrid_search
from tests.api_json import unwrap_json

_USER_1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


# ── Unit tests: L2 normalization ──────────────────────────────────────────────


class TestL2Normalize:
    def test_normalizes_vector(self):
        vec = [3.0, 4.0]
        result = _l2_normalize(vec)
        norm = math.sqrt(sum(x * x for x in result))
        assert abs(norm - 1.0) < 1e-6

    def test_zero_vector_returns_as_is(self):
        vec = [0.0, 0.0, 0.0]
        result = _l2_normalize(vec)
        assert result == [0.0, 0.0, 0.0]

    def test_unit_vector_unchanged(self):
        vec = [1.0, 0.0, 0.0]
        result = _l2_normalize(vec)
        assert abs(result[0] - 1.0) < 1e-6
        assert abs(result[1]) < 1e-6


# ── Unit tests: cosine similarity ─────────────────────────────────────────────


class TestCosineSimilarity:
    def test_identical_vectors(self):
        vec = [0.5, 0.5, 0.5, 0.5]
        assert abs(_cosine_similarity(vec, vec) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(_cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_empty_vectors(self):
        assert _cosine_similarity([], []) == 0.0

    def test_mismatched_lengths(self):
        assert _cosine_similarity([1.0], [1.0, 2.0]) == 0.0


# ── Unit tests: keyword score ─────────────────────────────────────────────────


class TestKeywordScore:
    def test_exact_match(self):
        tokens = set(_tokenize("天气 怎么样"))
        score = _keyword_score(tokens, "天气 怎么样")
        assert score > 0.5

    def test_partial_match(self):
        tokens = set(_tokenize("今天 天气"))
        score = _keyword_score(tokens, "天气 很好")
        assert 0 < score < 1

    def test_no_match(self):
        tokens = set(_tokenize("穿搭 推荐"))
        score = _keyword_score(tokens, "天气 预报")
        assert score == 0.0


# ── Unit tests: EmbeddingClient ───────────────────────────────────────────────


class TestEmbeddingClient:
    @pytest.mark.asyncio
    async def test_embed_success(self):
        client = EmbeddingClient(
            api_base="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
            dim=4,
        )
        mock_response = {
            "data": [{"index": 0, "embedding": [3.0, 4.0, 0.0, 0.0]}],
        }
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = AsyncMock(
                status_code=200,
                json=lambda: mock_response,
                raise_for_status=lambda: None,
            )
            result = await client.embed("hello")
            assert result is not None
            norm = math.sqrt(sum(x * x for x in result))
            assert abs(norm - 1.0) < 1e-6

    @pytest.mark.asyncio
    async def test_embed_failure_returns_none(self):
        client = EmbeddingClient(
            api_base="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("network error")
            result = await client.embed("hello")
            assert result is None

    @pytest.mark.asyncio
    async def test_embed_batch(self):
        client = EmbeddingClient(
            api_base="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
            dim=2,
        )
        mock_response = {
            "data": [
                {"index": 0, "embedding": [1.0, 0.0]},
                {"index": 1, "embedding": [0.0, 1.0]},
            ],
        }
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = AsyncMock(
                status_code=200,
                json=lambda: mock_response,
                raise_for_status=lambda: None,
            )
            results = await client.embed_batch(["a", "b"])
            assert results is not None
            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_embed_batch_empty(self):
        client = EmbeddingClient(
            api_base="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
        )
        results = await client.embed_batch([])
        assert results == []


# ── Unit tests: hybrid_search ─────────────────────────────────────────────────


class TestHybridSearch:
    def _make_session_with_snippets(self, snippets_data):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        factory = sessionmaker(bind=engine)
        db = factory()
        for sd in snippets_data:
            row = MemorySnippet(
                user_id=sd["user_id"],
                title=sd.get("title"),
                content=sd["content"],
                embedding_json=sd.get("embedding"),
            )
            db.add(row)
        db.commit()
        return db

    def test_keyword_only_search(self):
        db = self._make_session_with_snippets(
            [
                {"user_id": _USER_1, "content": "我 喜欢 穿 白色 T恤"},
                {"user_id": _USER_1, "content": "今天 天气 很好"},
            ]
        )
        hits = hybrid_search("白色 T恤", db, _USER_1, top_k=5)
        assert len(hits) >= 1
        assert hits[0]["score"] > 0
        db.close()

    def test_hybrid_search_with_embeddings(self):
        db = self._make_session_with_snippets(
            [
                {
                    "user_id": _USER_1,
                    "content": "我喜欢简约风格",
                    "embedding": [1.0, 0.0, 0.0],
                },
                {
                    "user_id": _USER_1,
                    "content": "今天适合运动风",
                    "embedding": [0.0, 1.0, 0.0],
                },
            ]
        )
        # Query embedding similar to first snippet
        hits = hybrid_search(
            "简约风格穿搭",
            db,
            _USER_1,
            top_k=2,
            query_embedding=[0.9, 0.1, 0.0],
        )
        assert len(hits) >= 1
        # First result should be the one with similar embedding
        assert "简约" in hits[0]["content"]
        db.close()

    def test_degrades_without_embeddings(self):
        db = self._make_session_with_snippets(
            [
                {"user_id": _USER_1, "content": "我 喜欢 白色 T恤", "embedding": None},
            ]
        )
        hits = hybrid_search("白色 T恤", db, _USER_1, top_k=5, query_embedding=[0.1, 0.2])
        assert len(hits) >= 1
        assert hits[0]["match_type"] == "keyword"
        db.close()

    def test_empty_db(self):
        db = self._make_session_with_snippets([])
        hits = hybrid_search("test", db, _USER_1, top_k=5)
        assert hits == []
        db.close()

    def test_user_isolation(self):
        db = self._make_session_with_snippets(
            [
                {"user_id": _USER_1, "content": "user1 memory"},
                {"user_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "content": "user2 memory"},
            ]
        )
        hits = hybrid_search("memory", db, _USER_1, top_k=5)
        assert all("user1" in h["content"] for h in hits)
        db.close()


# ── Integration tests: API endpoints ──────────────────────────────────────────


class TestMemoryAPI:
    def test_create_snippet_with_embedding(self, client, auth_headers):
        """POST /api/v1/memory/snippets creates snippet (embedding depends on client config)."""
        resp = client.post(
            "/api/v1/memory/snippets",
            json={"title": "风格偏好", "content": "我喜欢简约风格，不喜欢太花哨的颜色"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = unwrap_json(resp)
        assert "snippet_id" in data

    def test_search_returns_hits(self, client, auth_headers):
        client.post(
            "/api/v1/memory/snippets",
            json={"content": "我 喜欢 穿 白色 T恤 和 牛仔裤"},
            headers=auth_headers,
        )
        resp = client.get(
            "/api/v1/memory/snippets/search",
            params={"q": "白色 T恤"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = unwrap_json(resp)
        assert len(data["hits"]) >= 1
        assert "score" in data["hits"][0]

    def test_search_empty(self, client, auth_headers):
        resp = client.get(
            "/api/v1/memory/snippets/search",
            params={"q": "不存在的内容"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = unwrap_json(resp)
        assert data["hits"] == []

    def test_delete_snippet(self, client, auth_headers):
        create_resp = client.post(
            "/api/v1/memory/snippets",
            json={"content": "to be deleted"},
            headers=auth_headers,
        )
        snippet_id = unwrap_json(create_resp)["snippet_id"]
        resp = client.delete(
            f"/api/v1/memory/snippets/{snippet_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

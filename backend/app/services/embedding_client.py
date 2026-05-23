"""Async OpenAI-compatible embedding client.

Calls the /embeddings endpoint to generate text embeddings.
Results are L2-normalized so cosine similarity = dot product.
"""

import logging
import math
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

# Module-level singleton, initialized at startup
_instance: Optional["EmbeddingClient"] = None


def get_embedding_client() -> Optional["EmbeddingClient"]:
    return _instance


def init_embedding_client(client: "EmbeddingClient") -> None:
    global _instance
    _instance = client


class EmbeddingClient:
    """Async OpenAI-compatible embedding client."""

    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str,
        dim: int = 1024,
        timeout_seconds: float = 10.0,
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dim = dim
        self.timeout_seconds = timeout_seconds

    async def embed(self, text: str) -> Optional[List[float]]:
        """Generate L2-normalized embedding for a single text.

        Returns None on failure (graceful degradation).
        """
        results = await self.embed_batch([text])
        return results[0] if results else None

    async def embed_batch(self, texts: List[str]) -> Optional[List[List[float]]]:
        """Generate L2-normalized embeddings for multiple texts.

        Returns None on failure (graceful degradation).
        """
        if not texts:
            return []

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": texts,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.api_base}/embeddings",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

            # OpenAI-compatible response: data[].embedding
            embeddings = []
            for item in sorted(data.get("data", []), key=lambda x: x.get("index", 0)):
                vec = item.get("embedding", [])
                vec = _l2_normalize(vec)
                embeddings.append(vec)

            if len(embeddings) != len(texts):
                logger.warning(
                    "Embedding count mismatch: expected %d, got %d",
                    len(texts),
                    len(embeddings),
                )
                return None

            logger.debug("Embedding batch: %d texts, dim=%d", len(texts), len(embeddings[0]))
            return embeddings

        except Exception as e:
            logger.warning("Embedding API failed: %s", e)
            return None


def _l2_normalize(vec: List[float]) -> List[float]:
    """L2-normalize a vector so its unit length = 1."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm < 1e-12:
        return vec
    return [x / norm for x in vec]

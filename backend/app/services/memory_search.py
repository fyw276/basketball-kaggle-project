"""Hybrid memory search: keyword Jaccard + embedding cosine similarity.

Combines keyword overlap (fallback) with embedding-based semantic search.
When embeddings are unavailable, degrades gracefully to keyword-only.
"""

import re
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.memory_snippet import MemorySnippet


def _tokenize(text: str) -> List[str]:
    """Split text into lowercase tokens (>= 2 chars), handling CJK punctuation."""
    return [x for x in re.split(r"[\s　,.;，。；]+", text.lower()) if len(x) >= 2]


def _keyword_score(query_tokens: set, snippet_text: str) -> float:
    """Jaccard similarity between query tokens and snippet tokens."""
    snippet_tokens = set(_tokenize(snippet_text))
    inter = len(query_tokens & snippet_tokens)
    union = len(query_tokens | snippet_tokens) or 1
    return inter / union


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors (assumed L2-normalized → dot product)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def hybrid_search(
    query: str,
    db: Session,
    user_id,
    *,
    top_k: int = 5,
    keyword_weight: float = 0.3,
    embedding_weight: float = 0.7,
    query_embedding: Optional[List[float]] = None,
) -> List[dict]:
    """Hybrid search: keyword Jaccard + embedding cosine similarity.

    Args:
        query: Search query text.
        db: Database session.
        user_id: User UUID (str or UUID object).
        top_k: Number of results to return.
        keyword_weight: Weight for keyword score (0-1).
        embedding_weight: Weight for embedding score (0-1).
        query_embedding: Pre-computed query embedding (avoids re-computing).

    Returns:
        List of dicts with snippet_id, title, content, score, match_type.
    """
    rows = (
        db.query(MemorySnippet)
        .filter(MemorySnippet.user_id == user_id)
        .order_by(MemorySnippet.created_at.desc())
        .limit(500)
        .all()
    )
    if not rows:
        return []

    query_tokens = set(_tokenize(query))
    has_embedding_weights = query_embedding is not None and embedding_weight > 0

    # Normalize weights
    if has_embedding_weights:
        total_w = keyword_weight + embedding_weight
        kw = keyword_weight / total_w
        ew = embedding_weight / total_w
    else:
        kw = 1.0
        ew = 0.0

    scored: List[Tuple[float, str, MemorySnippet]] = []
    for r in rows:
        blob = f"{r.title or ''} {r.content}"
        k_score = _keyword_score(query_tokens, blob) if query_tokens else 0.0

        e_score = 0.0
        if has_embedding_weights and r.embedding_json:
            e_score = max(0.0, _cosine_similarity(query_embedding, r.embedding_json))

        final = kw * k_score + ew * e_score
        if final > 0:
            match_type = (
                "hybrid"
                if (k_score > 0 and e_score > 0)
                else ("keyword" if e_score == 0 else "embedding")
            )
            scored.append((final, match_type, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    hits = []
    for score, match_type, r in scored[:top_k]:
        hits.append(
            {
                "snippet_id": str(r.snippet_id),
                "title": r.title,
                "content": r.content[:2000],
                "score": round(score, 4),
                "match_type": match_type,
            }
        )
    return hits


async def preload_memories(
    query: str,
    db: Session,
    user_id,
    top_k: int = 3,
) -> str:
    """Preload relevant memory snippets for agent system prompt injection.

    Returns a formatted string block to append to the system prompt,
    or empty string if no relevant memories found.
    """
    from app.services.embedding_client import get_embedding_client

    client = get_embedding_client()
    query_embedding = None
    if client:
        query_embedding = await client.embed(query)

    hits = hybrid_search(
        query,
        db,
        user_id,
        top_k=top_k,
        keyword_weight=0.3,
        embedding_weight=0.7,
        query_embedding=query_embedding,
    )

    if not hits:
        return ""

    lines = ["以下是与当前问题相关的用户记忆/偏好，请在回答时参考："]
    for i, h in enumerate(hits, 1):
        title_part = f"（{h['title']}）" if h.get("title") else ""
        lines.append(f"{i}. {title_part}{h['content'][:500]}")
    return "\n".join(lines)

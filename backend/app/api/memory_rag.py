"""Memory snippets: hybrid keyword + embedding search.

Search combines keyword Jaccard (fallback) with embedding cosine similarity.
Embeddings are generated on snippet creation and cached in embedding_json.
"""

import re
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.api_response import success_response
from app.db.session import get_db
from app.models.memory_snippet import MemorySnippet
from app.models.user import User
from app.services.memory_search import hybrid_search

router = APIRouter(prefix="/memory", tags=["Memory"])


class SnippetCreate(BaseModel):
    title: str = Field("", max_length=200)
    content: str = Field(..., min_length=1, max_length=8000)


def _tokenize(text: str) -> List[str]:
    return [x for x in re.split(r"[\s　,.;，。；]+", text.lower()) if len(x) >= 2]


@router.post("/snippets")
async def create_snippet(
    body: SnippetCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = MemorySnippet(
        user_id=current_user.user_id,
        title=body.title or None,
        content=body.content,
    )

    # Generate embedding if client is available
    from app.services.embedding_client import get_embedding_client

    client = get_embedding_client()
    if client:
        embedding = await client.embed(body.content)
        if embedding:
            row.embedding_json = embedding

    db.add(row)
    db.commit()
    db.refresh(row)
    return success_response(
        {
            "snippet_id": str(row.snippet_id),
            "title": row.title,
            "created_at": row.created_at.isoformat(),
        },
        message="ok",
    )


@router.get("/snippets/search")
async def search_snippets(
    q: str = Query(..., min_length=1, max_length=500),
    top_k: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Hybrid search: keyword Jaccard + embedding cosine similarity."""
    from app.services.embedding_client import get_embedding_client

    client = get_embedding_client()
    query_embedding = None
    if client:
        query_embedding = await client.embed(q)

    hits = hybrid_search(
        q,
        db,
        current_user.user_id,
        top_k=top_k,
        keyword_weight=0.3,
        embedding_weight=0.7,
        query_embedding=query_embedding,
    )
    return success_response({"query": q, "hits": hits}, message="ok")


@router.delete("/snippets/{snippet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_snippet(
    snippet_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        uid = UUID(snippet_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid snippet_id") from exc
    row = (
        db.query(MemorySnippet)
        .filter(MemorySnippet.snippet_id == uid, MemorySnippet.user_id == current_user.user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

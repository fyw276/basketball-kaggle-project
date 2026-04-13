"""Lightweight memory snippets: keyword RAG; embedding_json reserved for vectors."""

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

router = APIRouter(prefix="/memory", tags=["Memory"])


class SnippetCreate(BaseModel):
    title: str = Field("", max_length=200)
    content: str = Field(..., min_length=1, max_length=8000)


def _tokenize(text: str) -> List[str]:
    return [x for x in re.split(r"[\s\u3000,.;，。；]+", text.lower()) if len(x) >= 2]


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
    """简单关键词重叠打分（Jaccard 近似）；后续可换 embedding + pgvector。"""
    rows = (
        db.query(MemorySnippet)
        .filter(MemorySnippet.user_id == current_user.user_id)
        .order_by(MemorySnippet.created_at.desc())
        .limit(500)
        .all()
    )
    q_tokens = set(_tokenize(q))
    if not q_tokens:
        return success_response({"query": q, "hits": []}, message="ok")

    scored: List[tuple] = []
    for r in rows:
        blob = f"{r.title or ''} {r.content}"
        tset = set(_tokenize(blob))
        inter = len(q_tokens & tset)
        union = len(q_tokens | tset) or 1
        score = inter / union
        if score > 0:
            scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    hits = []
    for score, r in scored[:top_k]:
        hits.append(
            {
                "snippet_id": str(r.snippet_id),
                "title": r.title,
                "content": r.content[:2000],
                "score": round(score, 4),
            }
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

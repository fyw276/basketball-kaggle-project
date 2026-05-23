"""Memory tools: search_memory, add_memory (hybrid keyword + embedding search)."""

from typing import Any, Dict
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent.tools.registry import register_tool


@register_tool(
    name="search_memory",
    description="搜索用户的穿搭记忆/笔记（混合检索：关键词 + 语义向量）。",
    parameters_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "top_k": {"type": "integer", "description": "返回数量，最大20", "default": 5},
        },
        "required": ["query"],
    },
    mcp_name="search_memory_snippets",
    category="memory",
)
async def search_memory(*, db: Session, user_id: str, **kw) -> Dict[str, Any]:
    from app.services.embedding_client import get_embedding_client
    from app.services.memory_search import hybrid_search

    query = kw.get("query", "")
    top_k = min(20, max(1, int(kw.get("top_k", 5))))

    client = get_embedding_client()
    query_embedding = None
    if client:
        query_embedding = await client.embed(query)

    hits = hybrid_search(
        query,
        db,
        UUID(user_id),
        top_k=top_k,
        keyword_weight=0.3,
        embedding_weight=0.7,
        query_embedding=query_embedding,
    )
    return {"query": query, "hits": hits}


@register_tool(
    name="add_memory",
    description="保存一条穿搭记忆/笔记。",
    parameters_schema={
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "记忆内容"},
            "title": {"type": "string", "description": "标题（可选）"},
        },
        "required": ["content"],
    },
    mcp_name="add_memory_snippet",
    category="memory",
)
async def add_memory(*, db: Session, user_id: str, **kw) -> Dict[str, Any]:
    from app.models.memory_snippet import MemorySnippet
    from app.services.embedding_client import get_embedding_client

    content = kw.get("content", "")
    title = kw.get("title", "")
    if not content:
        return {"error": "content is required"}

    uid = UUID(user_id)
    row = MemorySnippet(user_id=uid, title=title or None, content=content)

    # Generate embedding if client is available
    client = get_embedding_client()
    if client:
        embedding = await client.embed(content)
        if embedding:
            row.embedding_json = embedding

    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "snippet_id": str(row.snippet_id),
        "title": row.title or "",
        "created_at": row.created_at.isoformat(),
    }

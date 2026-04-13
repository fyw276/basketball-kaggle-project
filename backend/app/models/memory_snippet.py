"""Optional text memory for lightweight RAG (keyword retrieval; embedding_json reserved)."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.garment import UUID, JSONBCompat


class MemorySnippet(Base):
    """用户可写短记忆；检索为关键词重叠，embedding_json 预留向量扩展。"""

    __tablename__ = "memory_snippets"

    snippet_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(200), nullable=True)
    content = Column(Text, nullable=False)
    embedding_json = Column(JSONBCompat, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", backref="memory_snippets")

    def __repr__(self):
        return f"<MemorySnippet(id={self.snippet_id}, user={self.user_id})>"

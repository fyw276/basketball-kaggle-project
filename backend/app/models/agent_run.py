"""Agent run persistence model for debugging failed agent decisions."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.db.base import Base
from app.models.garment import UUID, JSONBCompat


class AgentRun(Base):
    """Persisted record of a single agent chat run for post-mortem analysis."""

    __tablename__ = "agent_runs"

    run_id = Column(String(12), primary_key=True)
    user_id = Column(
        UUID(),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message = Column(Text, nullable=False)
    outcome = Column(String(16), nullable=False, index=True)  # success | failure | timeout
    total_rounds = Column(Integer, nullable=False, default=0)
    total_tool_calls = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    latency_ms = Column(Integer, nullable=False, default=0)
    failure_reason = Column(String(64), nullable=True)
    tool_calls_log = Column(
        JSONBCompat, nullable=True
    )  # [{tool_name, arguments, result_preview, latency_ms, outcome}]
    skill_id = Column(String(36), nullable=True)  # matched skill UUID as string
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

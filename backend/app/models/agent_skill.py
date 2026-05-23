"""Agent skill models for reusable tool-call workflows."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.garment import UUID, JSONBCompat


class AgentSkill(Base):
    """A reusable workflow captured from an agent run's tool-call sequence."""

    __tablename__ = "agent_skills"

    skill_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    keywords = Column(JSONBCompat, nullable=False, default=list)
    enabled = Column(Boolean, default=True, nullable=False)
    system_prompt_addon = Column(Text, nullable=False)
    tool_names = Column(JSONBCompat, nullable=False, default=list)
    active_version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", backref="agent_skills")
    versions = relationship(
        "AgentSkillVersion", back_populates="skill", cascade="all, delete-orphan"
    )


class AgentSkillVersion(Base):
    """A versioned snapshot of a skill's prompt addon and tool configuration."""

    __tablename__ = "agent_skill_versions"

    version_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    skill_id = Column(
        UUID(),
        ForeignKey("agent_skills.skill_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False, default=1)
    system_prompt_addon = Column(Text, nullable=False)
    tool_names = Column(JSONBCompat, nullable=False, default=list)
    capture_run_id = Column(String(32), nullable=True)
    capture_tool_calls = Column(JSONBCompat, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    skill = relationship("AgentSkill", back_populates="versions")

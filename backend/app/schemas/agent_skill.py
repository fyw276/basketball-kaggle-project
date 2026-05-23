"""Pydantic schemas for agent skill API."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)
    keywords: List[str] = Field(..., min_length=1, max_length=20)
    system_prompt_addon: str = Field(..., min_length=1, max_length=8000)
    tool_names: List[str] = Field(default_factory=list, max_length=20)


class SkillCapture(BaseModel):
    run_id: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)
    keywords: List[str] = Field(..., min_length=1, max_length=20)
    tool_calls: List[Dict[str, Any]] = Field(..., min_length=1)


class SkillResponse(BaseModel):
    skill_id: UUID
    name: str
    description: Optional[str]
    keywords: List[str]
    enabled: bool
    system_prompt_addon: str
    tool_names: List[str]
    active_version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SkillVersionResponse(BaseModel):
    version_id: UUID
    version: int
    system_prompt_addon: str
    tool_names: List[str]
    capture_run_id: Optional[str]
    capture_tool_calls: Optional[List[Dict[str, Any]]]
    created_at: datetime

    class Config:
        from_attributes = True


class SkillExecutePreviewResponse(BaseModel):
    skill_id: UUID
    skill_name: str
    version: int
    system_prompt_addon: str
    tool_names: List[str]
    matched_keywords: List[str]

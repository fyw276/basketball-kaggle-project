"""Agent skills API — CRUD, capture, and execute-preview."""

import json
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models.agent_skill import AgentSkill, AgentSkillVersion
from app.models.user import User
from app.schemas.agent_skill import (
    SkillCapture,
    SkillCreate,
    SkillExecutePreviewResponse,
    SkillResponse,
)

router = APIRouter(prefix="/agent/skills", tags=["Agent Skills"])


@router.get("", response_model=List[SkillResponse])
async def list_skills(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all skills for the current user."""
    skills = (
        db.query(AgentSkill)
        .filter(AgentSkill.user_id == current_user.user_id)
        .order_by(AgentSkill.created_at.desc())
        .all()
    )
    return skills


@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(
    body: SkillCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually create a new skill."""
    skill = AgentSkill(
        user_id=current_user.user_id,
        name=body.name,
        description=body.description,
        keywords=body.keywords,
        system_prompt_addon=body.system_prompt_addon,
        tool_names=body.tool_names,
        active_version=1,
    )
    db.add(skill)
    db.flush()

    version = AgentSkillVersion(
        skill_id=skill.skill_id,
        version=1,
        system_prompt_addon=body.system_prompt_addon,
        tool_names=body.tool_names,
    )
    db.add(version)
    db.commit()
    db.refresh(skill)
    return skill


@router.post("/capture", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def capture_skill(
    body: SkillCapture,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Capture a skill from a completed agent run's tool call sequence."""
    tool_names = list({tc["tool_name"] for tc in body.tool_calls if "tool_name" in tc})
    if not tool_names:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tool_calls must contain at least one entry with tool_name",
        )

    addon_lines = ["用户之前成功完成了以下工具调用序列，请参考并复用："]
    for i, tc in enumerate(body.tool_calls, 1):
        name = tc.get("tool_name", "unknown")
        args = tc.get("arguments", {})
        addon_lines.append(f"{i}. {name}({json.dumps(args, ensure_ascii=False)})")
    addon_lines.append("\n请使用相同的工具组合来完成类似任务。")
    system_prompt_addon = "\n".join(addon_lines)

    skill = AgentSkill(
        user_id=current_user.user_id,
        name=body.name,
        description=body.description,
        keywords=body.keywords,
        system_prompt_addon=system_prompt_addon,
        tool_names=tool_names,
        active_version=1,
    )
    db.add(skill)
    db.flush()

    version = AgentSkillVersion(
        skill_id=skill.skill_id,
        version=1,
        system_prompt_addon=system_prompt_addon,
        tool_names=tool_names,
        capture_run_id=body.run_id,
        capture_tool_calls=body.tool_calls,
    )
    db.add(version)
    db.commit()
    db.refresh(skill)
    return skill


@router.post("/{skill_id}/execute-preview", response_model=SkillExecutePreviewResponse)
async def execute_preview(
    skill_id: UUID,
    message: str = Query(..., min_length=1, max_length=2000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dry-run: show what would be injected for a given message against a skill."""
    skill = (
        db.query(AgentSkill)
        .filter(
            AgentSkill.skill_id == skill_id,
            AgentSkill.user_id == current_user.user_id,
        )
        .first()
    )
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    msg_lower = message.lower()
    matched_keywords = [kw for kw in (skill.keywords or []) if kw.lower() in msg_lower]

    return SkillExecutePreviewResponse(
        skill_id=skill.skill_id,
        skill_name=skill.name,
        version=skill.active_version,
        system_prompt_addon=skill.system_prompt_addon,
        tool_names=skill.tool_names,
        matched_keywords=matched_keywords,
    )

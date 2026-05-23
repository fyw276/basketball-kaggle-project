"""Skill matching service — keyword-based lookup before agent runs."""

from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.agent_skill import AgentSkill


def match_skill_for_message(
    user_message: str,
    db: Session,
    user_id: str,
) -> Tuple[Optional[AgentSkill], List[str]]:
    """Match user message against enabled skills by keyword substring overlap.

    Returns (matched_skill, matched_keywords) or (None, []).
    """
    skills = (
        db.query(AgentSkill)
        .filter(AgentSkill.user_id == user_id, AgentSkill.enabled == True)  # noqa: E712
        .all()
    )

    msg_lower = user_message.lower()
    best_skill = None
    best_matched: List[str] = []

    for skill in skills:
        matched = [kw for kw in (skill.keywords or []) if kw.lower() in msg_lower]
        if len(matched) > len(best_matched):
            best_matched = matched
            best_skill = skill

    return best_skill, best_matched

"""Single source of truth for all agent tools.

Every tool registers here via @register_tool.  All consumers — LLM schema,
MCP bridge, frontend cards, tests — derive from this module.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_RESULT_CHARS = 4000


# ── Data model ──────────────────────────────────────────────────────────────


@dataclass
class ToolSpec:
    """Canonical tool definition.  One tool → one ToolSpec."""

    name: str
    description: str
    parameters_schema: Dict[str, Any]  # JSON Schema
    fn: Callable[..., Any]  # async callable(*, db, user_id, **kw) -> dict
    mcp_name: Optional[str] = None  # MCP function name (None = same as name)
    category: str = "general"  # frontend grouping tag
    visible_in_ui: bool = True  # show in frontend tool cards


# ── Global registry ─────────────────────────────────────────────────────────

_registry: Dict[str, ToolSpec] = {}


def register_tool(
    name: str,
    description: str,
    parameters_schema: Dict[str, Any],
    *,
    mcp_name: Optional[str] = None,
    category: str = "general",
    visible_in_ui: bool = True,
) -> Callable:
    """Decorator that registers a tool function into the global registry."""

    def decorator(fn: Callable) -> Callable:
        if name in _registry:
            logger.warning("Tool %s already registered, overwriting", name)
        _registry[name] = ToolSpec(
            name=name,
            description=description,
            parameters_schema=parameters_schema,
            fn=fn,
            mcp_name=mcp_name,
            category=category,
            visible_in_ui=visible_in_ui,
        )
        return fn

    return decorator


def get_tool(name: str) -> Optional[ToolSpec]:
    return _registry.get(name)


def all_tools() -> List[ToolSpec]:
    return list(_registry.values())


# ── Derived views ───────────────────────────────────────────────────────────


def get_openai_tools() -> List[Dict[str, Any]]:
    """OpenAI-compatible tools list for LLM chat/completions."""
    return [
        {
            "type": "function",
            "function": {
                "name": s.name,
                "description": s.description,
                "parameters": s.parameters_schema,
            },
        }
        for s in _registry.values()
    ]


def get_mcp_mapping() -> Dict[str, str]:
    """Registry name → MCP function name for tools that have an MCP alias."""
    return {s.name: s.mcp_name or s.name for s in _registry.values() if s.mcp_name is not None}


def get_frontend_cards() -> List[Dict[str, Any]]:
    """Metadata for frontend tool cards."""
    return [
        {
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "parameters": s.parameters_schema.get("properties", {}),
        }
        for s in _registry.values()
        if s.visible_in_ui
    ]


def assert_consistency() -> None:
    """Validate registry integrity.  Raises AssertionError on problems."""
    names = list(_registry.keys())
    assert len(names) == len(set(names)), f"Duplicate tool names: {names}"

    for spec in _registry.values():
        assert spec.name, "Tool has empty name"
        assert spec.description, f"Tool {spec.name} has empty description"
        assert (
            spec.parameters_schema.get("type") == "object"
        ), f"Tool {spec.name} parameters_schema.type must be 'object'"
        assert (
            "properties" in spec.parameters_schema
        ), f"Tool {spec.name} parameters_schema missing 'properties'"
        assert callable(spec.fn), f"Tool {spec.name} fn is not callable"

    # MCP mapping values should be unique
    mcp = get_mcp_mapping()
    mcp_vals = list(mcp.values())
    assert len(mcp_vals) == len(set(mcp_vals)), f"Duplicate MCP names: {mcp_vals}"


# ── Agent loop execution helper ────────────────────────────────────────────


async def execute_tool(name: str, arguments: Dict[str, Any], *, db: Any, user_id: str) -> str:
    """Execute a registered tool by name.  Returns JSON string."""
    spec = _registry.get(name)
    if not spec:
        return json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
    try:
        result = await spec.fn(db=db, user_id=user_id, **arguments)
        text = json.dumps(result, ensure_ascii=False, default=str)
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + "...(truncated)"
        return text
    except Exception as e:
        logger.warning("Tool %s failed: %s", name, e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)

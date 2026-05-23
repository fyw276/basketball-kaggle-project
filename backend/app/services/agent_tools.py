"""Deprecated: use app.agent.tools instead.

This module re-exports from the canonical registry for backward compatibility.
"""

from app.agent.tools import (  # noqa: F401
    ToolSpec,
    all_tools,
    assert_consistency,
    execute_tool,
    get_frontend_cards,
    get_mcp_mapping,
    get_openai_tools,
    get_tool,
    register_tool,
)

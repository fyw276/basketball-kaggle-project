"""Agent tools package — single source of truth.

Importing this package triggers registration of all tools.
"""

# Import tool modules to trigger @register_tool decorators.
from app.agent.tools import (  # noqa: F401
    collections,
    memory,
    mood,
    outfits,
    tryon,
    wardrobe,
    weather,
)
from app.agent.tools.registry import (  # noqa: F401
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

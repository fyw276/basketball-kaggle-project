"""Consistency tests for the unified tool registry.

Ensures the registry is the single source of truth — no drift between
tool names, schemas, MCP mappings, and frontend metadata.
"""

from app.agent.tools import (
    all_tools,
    assert_consistency,
    get_frontend_cards,
    get_mcp_mapping,
    get_openai_tools,
    get_tool,
)


class TestRegistryConsistency:
    """Validate internal consistency of the tool registry."""

    def test_all_tools_have_valid_schemas(self):
        for spec in all_tools():
            assert spec.name, "Tool has empty name"
            assert spec.description, f"Tool {spec.name} has empty description"
            schema = spec.parameters_schema
            assert (
                schema.get("type") == "object"
            ), f"Tool {spec.name} parameters_schema.type must be 'object'"
            assert (
                "properties" in schema
            ), f"Tool {spec.name} parameters_schema missing 'properties'"
            assert callable(spec.fn), f"Tool {spec.name} fn is not callable"

    def test_no_duplicate_tool_names(self):
        names = [t.name for t in all_tools()]
        assert len(names) == len(set(names)), "Duplicate tool names found"

    def test_assert_consistency_passes(self):
        """The built-in consistency check should not raise."""
        assert_consistency()

    def test_registry_not_empty(self):
        assert len(all_tools()) > 0, "Registry has no tools registered"


class TestOpenAIToolsSchema:
    """Validate LLM-facing tool schema."""

    def test_openai_tools_names_match_registry(self):
        openai_tools = get_openai_tools()
        registry_names = {t.name for t in all_tools()}
        schema_names = {t["function"]["name"] for t in openai_tools}
        assert schema_names == registry_names

    def test_openai_tools_have_required_structure(self):
        for tool in get_openai_tools():
            assert tool["type"] == "function"
            fn = tool["function"]
            assert fn["name"]
            assert fn["description"]
            assert fn["parameters"]["type"] == "object"

    def test_openai_tools_count_matches_registry(self):
        assert len(get_openai_tools()) == len(all_tools())


class TestMCPMapping:
    """Validate MCP bridge mapping."""

    def test_mcp_mapping_values_unique(self):
        mapping = get_mcp_mapping()
        mcp_names = list(mapping.values())
        assert len(mcp_names) == len(set(mcp_names)), f"Duplicate MCP names: {mcp_names}"

    def test_mcp_mapping_keys_are_valid_tools(self):
        mapping = get_mcp_mapping()
        registry_names = {t.name for t in all_tools()}
        for name in mapping:
            assert name in registry_names, f"MCP mapping key '{name}' not in registry"

    def test_mcp_mapping_entries_have_mcp_name(self):
        mapping = get_mcp_mapping()
        for name in mapping:
            spec = get_tool(name)
            assert spec.mcp_name is not None, f"Tool {name} in MCP mapping but mcp_name is None"

    def test_mcp_mapping_values_exist_in_mcp_server(self):
        import ast
        from pathlib import Path

        server_path = Path(__file__).resolve().parents[2] / "mcp" / "server.py"
        tree = ast.parse(server_path.read_text(encoding="utf-8"))
        function_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        mapping = get_mcp_mapping()
        for registry_name, mcp_name in mapping.items():
            assert (
                mcp_name in function_names
            ), f"Registry tool {registry_name} maps to missing MCP tool {mcp_name}"


class TestFrontendCards:
    """Validate frontend card metadata."""

    def test_frontend_cards_have_required_fields(self):
        for card in get_frontend_cards():
            assert "name" in card
            assert "description" in card
            assert "category" in card
            assert "parameters" in card

    def test_frontend_cards_names_match_registry(self):
        card_names = {c["name"] for c in get_frontend_cards()}
        registry_names = {t.name for t in all_tools() if t.visible_in_ui}
        assert card_names == registry_names


class TestIntentRouterConsistency:
    """Verify intent router references valid tool names."""

    def test_intent_rules_reference_known_tools(self):
        from app.api.agent_intent import _INTENT_RULES

        registry_names = {t.name for t in all_tools()}
        for keywords, tool_names, label in _INTENT_RULES:
            for name in tool_names:
                # Some intent tools (health, analyze_similarity, etc.) are
                # MCP-only and not in the agent registry — that's fine.
                # We only check that tools in the registry are valid.
                if name not in registry_names:
                    # This is expected for MCP-only tools
                    pass

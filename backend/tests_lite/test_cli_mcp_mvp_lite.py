"""Lite tests for CLI and MCP MVP modules."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_cli_resolve_base_url_priority():
    repo_root = Path(__file__).resolve().parents[2]
    cli_mod = _load_module("outfit_cli_test_mod", repo_root / "cli" / "outfit_cli.py")

    config = {"base_url": "http://cfg.local/api/v1"}
    assert cli_mod.resolve_base_url(None, config) == "http://cfg.local/api/v1"
    assert cli_mod.resolve_base_url("http://arg.local/api/v1/", config) == "http://arg.local/api/v1"


def test_cli_handle_response_error_detail():
    repo_root = Path(__file__).resolve().parents[2]
    cli_mod = _load_module("outfit_cli_test_mod_resp", repo_root / "cli" / "outfit_cli.py")

    req = httpx.Request("POST", "http://127.0.0.1:8010/api/v1/auth/login")
    resp = httpx.Response(401, request=req, json={"detail": "Incorrect username or password"})

    with pytest.raises(cli_mod.CLIError) as exc:
        cli_mod.handle_response(resp)

    assert "HTTP 401" in str(exc.value)
    assert "Incorrect username or password" in str(exc.value)


def test_cli_load_config_invalid_json(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    cli_mod = _load_module("outfit_cli_test_mod_cfg", repo_root / "cli" / "outfit_cli.py")

    bad_cfg = tmp_path / "config.json"
    bad_cfg.write_text("{invalid", encoding="utf-8")

    old_path = cli_mod.CONFIG_PATH
    cli_mod.CONFIG_PATH = bad_cfg
    try:
        with pytest.raises(cli_mod.CLIError):
            cli_mod.load_config()
    finally:
        cli_mod.CONFIG_PATH = old_path


def test_mcp_token_required(monkeypatch: pytest.MonkeyPatch):
    repo_root = Path(__file__).resolve().parents[2]

    fake_fastmcp_mod = ModuleType("mcp.server.fastmcp")

    class _FakeFastMCP:
        def __init__(self, _: str):
            pass

        def tool(self):
            def deco(fn):
                return fn

            return deco

        def run(self):
            return None

    fake_fastmcp_mod.FastMCP = _FakeFastMCP
    sys.modules["mcp"] = ModuleType("mcp")
    sys.modules["mcp.server"] = ModuleType("mcp.server")
    sys.modules["mcp.server.fastmcp"] = fake_fastmcp_mod

    mcp_mod = _load_module("mcp_server_test_mod", repo_root / "mcp" / "server.py")

    monkeypatch.delenv("OUTFIT_API_TOKEN", raising=False)
    with pytest.raises(ValueError):
        mcp_mod._token()


def test_mcp_handle_http_error_payload(monkeypatch: pytest.MonkeyPatch):
    repo_root = Path(__file__).resolve().parents[2]

    fake_fastmcp_mod = ModuleType("mcp.server.fastmcp")

    class _FakeFastMCP:
        def __init__(self, _: str):
            pass

        def tool(self):
            def deco(fn):
                return fn

            return deco

        def run(self):
            return None

    fake_fastmcp_mod.FastMCP = _FakeFastMCP
    sys.modules["mcp"] = ModuleType("mcp")
    sys.modules["mcp.server"] = ModuleType("mcp.server")
    sys.modules["mcp.server.fastmcp"] = fake_fastmcp_mod

    mcp_mod = _load_module("mcp_server_test_mod_resp", repo_root / "mcp" / "server.py")

    req = httpx.Request("GET", "http://127.0.0.1:8010/health")
    resp = httpx.Response(500, request=req, json={"detail": "backend failed"})
    with pytest.raises(ValueError) as exc:
        mcp_mod._handle(resp)

    assert "HTTP 500" in str(exc.value)
    assert "backend failed" in str(exc.value)

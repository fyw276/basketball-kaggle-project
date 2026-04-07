"""
API routes
"""

from __future__ import annotations

from importlib import import_module

_ROUTER_MAP = {
    "analysis_router": "app.api.analysis",
    "auth_router": "app.api.auth",
    "outfit_collections_router": "app.api.outfit_collections",
    "profile_router": "app.api.profile",
    "recognition_router": "app.api.recognition",
    "users_router": "app.api.users",
    "wardrobe_router": "app.api.wardrobe",
}

__all__ = [
    "auth_router",
    "users_router",
    "profile_router",
    "wardrobe_router",
    "recognition_router",
    "analysis_router",
    "outfit_collections_router",
]


def __getattr__(name: str):
    module_name = _ROUTER_MAP.get(name)
    if module_name is None:
        raise AttributeError(f"module 'app.api' has no attribute '{name}'")
    module = import_module(module_name)
    value = getattr(module, "router")
    globals()[name] = value
    return value

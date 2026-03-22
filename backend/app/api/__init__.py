"""
API routes
"""

from app.api.auth import router as auth_router
from app.api.profile import router as profile_router
from app.api.users import router as users_router

__all__ = ["auth_router", "users_router", "profile_router"]

"""
API routes
"""

from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.profile import router as profile_router
from app.api.recognition import router as recognition_router
from app.api.users import router as users_router
from app.api.wardrobe import router as wardrobe_router

__all__ = [
    "auth_router",
    "users_router",
    "profile_router",
    "wardrobe_router",
    "recognition_router",
    "analysis_router",
]

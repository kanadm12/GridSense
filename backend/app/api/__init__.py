"""API routes."""

from app.api.auth import router as auth_router
from app.api.automation import router as automation_router
from app.api.billing import router as billing_router
from app.api.chat import router as chat_router
from app.api.insights import router as insights_router
from app.api.meters import router as meters_router
from app.api.notifications import router as notifications_router
from app.api.password_reset import router as password_reset_router
from app.api.recommendations import router as recommendations_router
from app.api.tariffs import router as tariffs_router
from app.api.upload import router as upload_router
from app.api.usage import router as usage_router

__all__ = [
    "auth_router",
    "automation_router",
    "billing_router",
    "chat_router",
    "insights_router",
    "meters_router",
    "notifications_router",
    "password_reset_router",
    "recommendations_router",
    "tariffs_router",
    "upload_router",
    "usage_router",
]

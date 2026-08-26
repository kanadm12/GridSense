"""GridSense API - Grid-Aware Energy Copilot for Victorian Households."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.rate_limit import limiter

from app.api import (
    auth_router,
    automation_router,
    billing_router,
    chat_router,
    insights_router,
    meters_router,
    notifications_router,
    password_reset_router,
    recommendations_router,
    tariffs_router,
    upload_router,
    usage_router,
)
from app.api.health import router as health_router
from app.api.errors import (
    http_exception_handler,
    validation_exception_handler,
    general_exception_handler,
)
from app.config import get_settings
from app.logging_config import setup_logging, get_logger
from app.middleware import LoggingMiddleware

settings = get_settings()

# Setup structured logging
setup_logging(debug=settings.debug)
logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown events."""
    logger.info("Application starting", extra={"event": "startup", "debug": settings.debug})
    yield
    logger.info("Application shutting down", extra={"event": "shutdown"})


app = FastAPI(
    title=settings.app_name,
    description="""GridSense is a grid-aware energy copilot that helps Victorian households
    optimize their electricity usage, reduce costs, and support grid stability.

    ## Features

    - **NEM12 Upload**: Parse and import smart meter data from your energy retailer
    - **Usage Analytics**: Visualize consumption patterns by day, hour, and week
    - **Recommendations**: Get personalized advice to shift load and reduce costs

    ## Getting Started

    1. Register an account using `/api/v1/auth/register`
    2. Login to get an access token via `/api/v1/auth/login`
    3. Upload your NEM12 file using `/api/v1/upload`
    4. View your usage data and recommendations
    """,
    version="0.1.0",
    lifespan=lifespan,
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add custom error handlers
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Add logging middleware
app.add_middleware(LoggingMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Include routers
app.include_router(health_router)  # No prefix - /health/live, /health/ready
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(password_reset_router, prefix=settings.api_v1_prefix)
app.include_router(meters_router, prefix=settings.api_v1_prefix)
app.include_router(upload_router, prefix=settings.api_v1_prefix)
app.include_router(usage_router, prefix=settings.api_v1_prefix)
app.include_router(recommendations_router, prefix=settings.api_v1_prefix)
app.include_router(tariffs_router, prefix=settings.api_v1_prefix)
app.include_router(billing_router, prefix=settings.api_v1_prefix)
app.include_router(notifications_router, prefix=settings.api_v1_prefix)
app.include_router(automation_router, prefix=settings.api_v1_prefix)
app.include_router(chat_router, prefix=settings.api_v1_prefix)
app.include_router(insights_router, prefix=settings.api_v1_prefix)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint returning API info."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health/live",
    }

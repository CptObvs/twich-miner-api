"""
Twitch Miner Backend API
========================
FastAPI application for managing multiple Twitch Channel Points Miner instances.

Features:
- Multi-user support with JWT authentication
- Instance management (start/stop/configure)
- Real-time log streaming via SSE
- OAuth2 Password Flow for authentication
"""

import sys
import io
from contextlib import asynccontextmanager

# Enable UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.models.database import init_db
from app.routers import auth, admin, instances
from app.services.miner_manager import miner_manager
from app.services.log_cleanup import log_cleanup


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    await init_db()
    # Reset all instance flags to false (no processes tracked after restart)
    await miner_manager.reset_all_on_startup()
    # Clean up old logs and start periodic cleanup task
    log_cleanup.rotate_large_logs()
    log_cleanup.cleanup_old_logs()
    log_cleanup.start_cleanup_task()
    yield
    # Shutdown
    await miner_manager.shutdown_all()


app = FastAPI(
    title="Twitch Miner Backend",
    description="Manage Twitch Channel Points Miner instances via REST API + SSE log streaming",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=settings.DOCS_URL if settings.ENABLE_SWAGGER else None,
    redoc_url=settings.REDOC_URL if settings.ENABLE_SWAGGER else None,
    openapi_url="/openapi.json" if settings.ENABLE_SWAGGER else None,  # Disable OpenAPI schema
    swagger_ui_parameters={
        "persistAuthorization": True,
        "syntaxHighlight.theme": "monokai",  # Dark theme
        "displayRequestDuration": True,
        "filter": True,
        "tryItOutEnabled": True,
    },
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(instances.router)


@app.get("/", tags=["health"])
async def root():
    """Root endpoint."""
    return {
        "status": "ok",
        "service": "Twitch Miner Backend",
        "version": "1.0.0",
        "docs": settings.DOCS_URL if settings.ENABLE_SWAGGER else "disabled",
    }


@app.get("/health", tags=["health"])
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}

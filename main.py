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

import logging
import sys
import io
from contextlib import asynccontextmanager

# Enable UTF-8 encoding for Windows console (skip during test runs)
if sys.platform == "win32" and "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from alembic import command
from alembic.config import Config

from app.core.config import settings
from app.routers import auth, admin, codes, instances
from app.services.miner_manager import miner_manager
from app.services.log_cleanup import log_cleanup

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    """Run Alembic migrations to bring the database up to date."""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    logger.info("Database migrations applied successfully")



@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    run_migrations()
    await miner_manager.reset_all_on_startup()
    log_cleanup.rotate_large_logs()
    log_cleanup.cleanup_old_logs()
    log_cleanup.start_cleanup_task()

    # Signal-Handler für sauberes Beenden (Linux/Unix)
    def force_kill_all(*_):
        for proc in list(miner_manager._processes.values()):
            try:
                if hasattr(proc, 'pid'):
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
        os._exit(1)

    if sys.platform != "win32":
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, force_kill_all)
            except NotImplementedError:
                pass

    # Starte Hintergrund-Task zur Überprüfung auf verwaiste Prozesse
    async def orphan_process_cleanup():
        while True:
            await asyncio.sleep(300)  # alle 5 Minuten
            await miner_manager.cleanup_orphan_processes()

    cleanup_task = asyncio.create_task(orphan_process_cleanup())

    try:
        yield
    finally:
        cleanup_task.cancel()
        await miner_manager.shutdown_all()



app = FastAPI(
    title="Twitch Miner Backend",
    description="Manage Twitch Channel Points Miner instances via REST API + SSE log streaming",
    version="1.0.0",
    root_path="/api",  # Behind reverse proxy at /api
    docs_url=settings.DOCS_URL if settings.ENABLE_SWAGGER else None,
    redoc_url=settings.REDOC_URL if settings.ENABLE_SWAGGER else None,
    openapi_url="/openapi.json" if settings.ENABLE_SWAGGER else None,
    swagger_ui_parameters={
        "persistAuthorization": True,
        "syntaxHighlight.theme": "monokai",  # Dark theme
        "displayRequestDuration": True,
        "filter": True,
        "tryItOutEnabled": True,
    },
)

# Startup/Shutdown-Events statt lifespan
@app.on_event("startup")
async def on_startup():
    run_migrations()
    await miner_manager.reset_all_on_startup()
    log_cleanup.rotate_large_logs()
    log_cleanup.cleanup_old_logs()
    log_cleanup.start_cleanup_task()
    # orphan_process_cleanup nur im Hauptprozess (kein Fork/Worker)
    import os
    if os.getpid() == os.getppid():
        app.state.cleanup_task = asyncio.create_task(orphan_process_cleanup())

@app.on_event("shutdown")
async def on_shutdown():
    cleanup_task = getattr(app.state, "cleanup_task", None)
    if cleanup_task:
        cleanup_task.cancel()
    await miner_manager.shutdown_all()

# orphan_process_cleanup als eigenständige Funktion
async def orphan_process_cleanup():
    while True:
        await asyncio.sleep(300)
        await miner_manager.cleanup_orphan_processes()

# Trust headers from reverse proxy
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"], 
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers (served under /api by reverse proxy)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(codes.router)
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

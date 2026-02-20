"""
Twitch Miner Backend API
========================
FastAPI application for managing multiple TwitchDropsMiner Docker instances.
"""

import asyncio
import gc
import io
import logging
import sys
import time
from collections import defaultdict
from time import perf_counter
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError, jwt

from app.core.config import settings
from app.routers import admin, auth, codes, instances, proxy
from app.services.miner_manager import miner_manager
from app.routers.proxy import close_http_client

logger = logging.getLogger("uvicorn.error")
request_logger = logging.getLogger("uvicorn.error")


# ------------------------------------------------------------------
# IP Blocker
# ------------------------------------------------------------------

# Whitelist of valid path prefixes — anything else is treated as suspicious
_ALLOWED_PREFIXES = (
    "/",           # exact root (health)
    "/health",
    "/auth/",
    "/admin/",
    "/codes/",
    "/instances/",
    "/openapi.json",
    "/docs",
    "/redoc",
)


def _is_allowed_path(path: str) -> bool:
    if path == "/":
        return True
    return any(path.startswith(p) for p in _ALLOWED_PREFIXES)


class IPBlocker:
    """Blocks IPs that repeatedly request paths outside the known API whitelist."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._blocked: dict[str, float] = {}  # IP -> unblock timestamp (monotonic)

    def is_blocked(self, ip: str) -> bool:
        unblock_at = self._blocked.get(ip)
        if unblock_at is None:
            return False
        if time.monotonic() < unblock_at:
            return True
        del self._blocked[ip]
        return False

    def record(self, ip: str, path: str) -> None:
        now = time.monotonic()
        window = settings.IP_BLOCKER_WINDOW_SECONDS
        max_hits = settings.IP_BLOCKER_MAX_404S

        self._hits[ip].append(now)

        # Trim entries outside the sliding window
        self._hits[ip] = [t for t in self._hits[ip] if now - t < window]

        if len(self._hits[ip]) >= max_hits:
            self._blocked[ip] = now + settings.IP_BLOCKER_BLOCK_DURATION_SECONDS
            self._hits.pop(ip, None)
            logger.warning("IP-Blocker: %s geblockt (letzter Pfad: %s)", ip, path)


ip_blocker = IPBlocker()


if sys.platform == "win32" and "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


def run_migrations() -> None:
    """Run Alembic migrations to bring the database up to date."""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    logger.info("Database migrations applied successfully")


async def orphan_container_cleanup() -> None:
    while True:
        await asyncio.sleep(300)
        await miner_manager.cleanup_orphan_containers()


async def memory_gc_cleanup() -> None:
    while True:
        await asyncio.sleep(settings.MEMORY_GC_INTERVAL_SECONDS)
        collected = gc.collect(settings.MEMORY_GC_GENERATION)
        logger.debug(f"Periodic GC run complete, collected objects: {collected}")


def start_background_tasks(app: FastAPI) -> None:
    app.state.cleanup_task = asyncio.create_task(orphan_container_cleanup())
    app.state.memory_gc_task = (
        asyncio.create_task(memory_gc_cleanup()) if settings.MEMORY_GC_ENABLED else None
    )


async def stop_background_tasks(app: FastAPI) -> None:
    tasks = []
    for attr in ("cleanup_task", "memory_gc_task"):
        task = getattr(app.state, attr, None)
        if task:
            task.cancel()
            tasks.append(task)

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def run_startup(app: FastAPI) -> None:
    logger.info("Starte API ...")
    if settings.RUN_MIGRATIONS_ON_STARTUP:
        run_migrations()
    else:
        logger.info("Überspringe Migrationen beim Startup (RUN_MIGRATIONS_ON_STARTUP=false)")
    await miner_manager.reconcile_all_on_startup()
    start_background_tasks(app)
    logger.info("API startup abgeschlossen")


async def run_shutdown(app: FastAPI) -> None:
    logger.info("Stopping API ...")
    await stop_background_tasks(app)
    await miner_manager.shutdown_all()
    await close_http_client()
    logger.info("API stopped cleanly")


def _extract_request_identity(request: Request) -> tuple[str | None, str | None]:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, None

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None, None

    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload.get("sub"), payload.get("username")
    except JWTError:
        return None, None


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_startup(app)
    try:
        yield
    finally:
        await run_shutdown(app)


app = FastAPI(
    title="Twitch Miner Backend",
    description="Manage TwitchDropsMiner Docker instances via REST API",
    version="2.0.0",
    root_path="/api",
    docs_url=settings.DOCS_URL if settings.ENABLE_SWAGGER else None,
    redoc_url=settings.REDOC_URL if settings.ENABLE_SWAGGER else None,
    openapi_url="/openapi.json" if settings.ENABLE_SWAGGER else None,
    swagger_ui_parameters={
        "persistAuthorization": True,
        "syntaxHighlight.theme": "monokai",
        "displayRequestDuration": True,
        "filter": True,
        "tryItOutEnabled": True,
    },
    lifespan=lifespan,
)


app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "-"
    path = request.url.path

    if settings.IP_BLOCKER_ENABLED:
        # Block IPs that have been flagged
        if ip_blocker.is_blocked(client_ip):
            logger.warning("IP-Blocker: Anfrage von geblockter IP %s auf %s abgewiesen", client_ip, path)
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})

        # Path not in whitelist → record hit immediately, skip processing
        if not _is_allowed_path(path):
            ip_blocker.record(client_ip, path)
            return JSONResponse(status_code=404, content={"detail": "Not Found"})

    if not settings.API_REQUEST_LOGGING_ENABLED:
        return await call_next(request)

    start = perf_counter()
    user_id, username = _extract_request_identity(request)
    actor = username or user_id or "anonymous"
    method = request.method

    try:
        response = await call_next(request)
        duration_ms = (perf_counter() - start) * 1000
        request_logger.info(
            "API %s %s abgeschlossen: Status %s in %.2f ms (Nutzer: %s, IP: %s)",
            method,
            path,
            response.status_code,
            duration_ms,
            actor,
            client_ip,
        )
        return response
    except Exception:
        duration_ms = (perf_counter() - start) * 1000
        request_logger.exception(
            "API %s %s fehlgeschlagen: Status 500 nach %.2f ms (Nutzer: %s, IP: %s)",
            method,
            path,
            duration_ms,
            actor,
            client_ip,
        )
        raise

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(codes.router)
app.include_router(instances.router)
app.include_router(proxy.router)


@app.get("/", tags=["health"])
async def root():
    return {
        "status": "ok",
        "service": "Twitch Miner Backend",
        "version": "2.0.0",
        "docs": settings.DOCS_URL if settings.ENABLE_SWAGGER else "disabled",
    }


@app.get("/health", tags=["health"])
async def health():
    return {"status": "healthy"}

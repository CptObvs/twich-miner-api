import json
import shutil
import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.database import User, MinerInstance, get_db
from app.models.enums import InstanceState
from app.models.schemas import InstanceCreate, InstanceResponse, InstanceStatus, StreamersUpdate
from app.services.auth import get_current_user
from app.services.miner_manager import miner_manager
from app.services.log_streamer import tail_log

router = APIRouter(prefix="/instances", tags=["instances"])


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def _get_user_instance(
    instance_id: str,
    current_user: User,
    db: AsyncSession,
) -> MinerInstance:
    if current_user.is_admin():
        result = await db.execute(
            select(MinerInstance).where(MinerInstance.id == instance_id)
        )
    else:
        result = await db.execute(
            select(MinerInstance).where(
                MinerInstance.id == instance_id,
                MinerInstance.user_id == current_user.id,
            )
        )
    instance = result.scalar_one_or_none()
    if not instance:
        raise HTTPException(404, "Instance not found")
    return instance


def _read_config(instance_id: str) -> dict:
    config_file = settings.INSTANCES_DIR / instance_id / "config.json"
    if not config_file.exists():
        raise HTTPException(400, "Instance config not found. Recreate the instance.")
    return json.loads(config_file.read_text())


def _write_config(instance_id: str, config: dict):
    config_dir = settings.INSTANCES_DIR / instance_id
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(json.dumps(config))


def _instance_to_response(instance: MinerInstance) -> InstanceResponse:
    """Build response with streamers from config.json. Uses DB status field."""
    streamers = []
    try:
        config = _read_config(instance.id)
        streamers = config.get("streamers", [])
    except Exception:
        pass
    return InstanceResponse(
        id=instance.id,
        user_id=instance.user_id,
        twitch_username=instance.twitch_username,
        status=instance.status,
        pid=instance.pid,
        streamers=streamers,
        created_at=instance.created_at,
        last_started_at=instance.last_started_at,
        last_stopped_at=instance.last_stopped_at,
    )


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------

@router.post("/", response_model=InstanceResponse, status_code=201)
async def create_instance(
    data: InstanceCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new miner instance (does NOT start it yet)."""
    # Check instance limit for non-admin users
    if not current_user.is_admin():
        result = await db.execute(
            select(MinerInstance).where(MinerInstance.user_id == current_user.id)
        )
        existing_instances = result.scalars().all()
        if len(existing_instances) >= settings.MAX_INSTANCES_PER_USER:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum {settings.MAX_INSTANCES_PER_USER} instances allowed for user role"
            )
    
    instance = MinerInstance(user_id=current_user.id, twitch_username=data.twitch_username)
    db.add(instance)
    await db.commit()
    await db.refresh(instance)

    _write_config(instance.id, {
        "twitch_username": data.twitch_username,
        "streamers": data.streamers,
    })

    return _instance_to_response(instance)


@router.get("/", response_model=list[InstanceResponse])
async def list_instances(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    List miner instances.

    - **Admin users**: See all instances from all users
    - **Regular users**: See only their own instances
    """
    if current_user.is_admin():
        # Admin sees all instances
        result = await db.execute(select(MinerInstance))
    else:
        # Regular user sees only their instances
        result = await db.execute(
            select(MinerInstance).where(MinerInstance.user_id == current_user.id)
        )
    return [_instance_to_response(inst) for inst in result.scalars().all()]


@router.get("/{instance_id}", response_model=InstanceResponse)
async def get_instance(
    instance_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get a single instance with its current config."""
    instance = await _get_user_instance(instance_id, current_user, db)
    return _instance_to_response(instance)


@router.delete("/{instance_id}", status_code=204)
async def delete_instance(
    instance_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a miner instance. Stops it first if it is still running."""
    instance = await _get_user_instance(instance_id, current_user, db)

    # Stop the process if it is running
    if miner_manager.is_process_tracked(instance_id):
        await miner_manager.stop(instance_id)

    # Remove instance directory (config, logs, cookies, run.py, …)
    instance_dir = settings.INSTANCES_DIR / instance_id
    if instance_dir.exists():
        shutil.rmtree(instance_dir, ignore_errors=True)

    # Remove from database
    await db.delete(instance)
    await db.commit()


# ------------------------------------------------------------------
# Update streamers
# ------------------------------------------------------------------

@router.put("/{instance_id}/streamers", response_model=InstanceResponse)
async def update_streamers(
    instance_id: str,
    data: StreamersUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update the streamer list for an instance.
    If the instance is running, you need to stop and restart it
    for changes to take effect.
    """
    instance = await _get_user_instance(instance_id, current_user, db)

    config = _read_config(instance_id)
    config["streamers"] = data.streamers
    _write_config(instance_id, config)

    return _instance_to_response(instance)


# ------------------------------------------------------------------
# Start / Stop
# ------------------------------------------------------------------

@router.post("/{instance_id}/start", response_model=InstanceStatus)
async def start_instance(
    instance_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Start a miner instance."""

    # Maximal 2 laufende Instanzen pro User (außer Admin)
    instance = await _get_user_instance(instance_id, current_user, db)
    if not current_user.is_admin():
        result = await db.execute(
            select(MinerInstance).where(
                MinerInstance.user_id == current_user.id,
                MinerInstance.status == InstanceState.RUNNING
            )
        )
        running_instances = result.scalars().all()
        # Zähle alle laufenden Instanzen außer die aktuelle (falls Restart)
        running_count = len([i for i in running_instances if i.id != instance_id])
        if running_count >= 2:
            raise HTTPException(
                400,
                "Maximal 2 laufende Instanzen pro Nutzer erlaubt. Stoppe zuerst eine andere Instanz."
            )

    if miner_manager.is_process_tracked(instance_id):
        raise HTTPException(409, "Instance is already running")

    config = _read_config(instance_id)

    if not config.get("streamers"):
        raise HTTPException(
            400,
            "No streamers configured. Add streamers first via PUT /instances/{id}/streamers",
        )

    try:
        pid = await miner_manager.start(
            instance_id=instance_id,
            twitch_username=config["twitch_username"],
            streamers=config["streamers"],
        )
    except RuntimeError as e:
        raise HTTPException(409, str(e))

    # Give the miner a short moment to flush initial activation lines to output.log
    await asyncio.sleep(1)

    # Nach dem Start: Logdatei nach Twitch-Activation durchsuchen
    from app.services.activation_log_parser import extract_twitch_activation
    log_path = settings.INSTANCES_DIR / instance_id / "logs" / "output.log"
    activation = extract_twitch_activation(log_path, lines=10)

    return InstanceStatus(
        id=instance_id,
        status=InstanceState.RUNNING,
        pid=pid,
        activation_url=activation.get("activation_url"),
        activation_code=activation.get("activation_code"),
    )


@router.post("/{instance_id}/stop", response_model=InstanceStatus)
async def stop_instance(
    instance_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Stop a running miner instance.

    The request blocks until the miner process has fully exited.
    While shutting down, the instance status is STOPPING (visible to
    other requests, e.g. from a second browser tab).
    The response is returned only once the instance is fully STOPPED.

    This endpoint is idempotent - calling it on an already stopped
    instance will return 200 with STOPPED status.
    """
    instance = await _get_user_instance(instance_id, current_user, db)

    stopped = await miner_manager.stop(instance_id)
    if not stopped:
        # Instance was not running - ensure DB is in sync
        if instance.status != InstanceState.STOPPED:
            instance.status = InstanceState.STOPPED
            instance.pid = None
            await db.commit()

    return InstanceStatus(id=instance_id, status=InstanceState.STOPPED, pid=None)


@router.get("/{instance_id}/status", response_model=InstanceStatus)
async def instance_status(
    instance_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Check if a miner instance is running."""
    instance = await _get_user_instance(instance_id, current_user, db)

    # Check if DB says RUNNING but process is not actually tracked
    if instance.status == InstanceState.RUNNING and not miner_manager.is_process_tracked(instance_id):
        # Process died/crashed - update DB to reflect reality
        instance.status = InstanceState.STOPPED
        instance.pid = None
        await db.commit()
        await db.refresh(instance)

    return InstanceStatus(
        id=instance_id,
        status=instance.status,
        pid=instance.pid,
    )


# ------------------------------------------------------------------
# SSE: Live log streaming
# ------------------------------------------------------------------

from fastapi import Query

@router.get("/{instance_id}/logs")
async def stream_logs(
    instance_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    history_lines: int | None = Query(
        None,
        ge=1,
        description="Wie viele Logzeilen initial laden? Leer = komplette Datei",
    ),
):
    """
    SSE endpoint – streams miner logs in real-time.

    curl:  curl -N -H "Authorization: Bearer <token>" http://localhost:8000/api/instances/{id}/logs
    JS:    fetch(url, {headers: {"Authorization": "Bearer ..."}})
           then read response.body as stream
    """
    await _get_user_instance(instance_id, current_user, db)

    async def event_generator():
        async for line in tail_log(instance_id, history_lines=history_lines):
            yield f"data: {line.rstrip()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

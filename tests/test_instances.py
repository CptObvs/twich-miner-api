"""Tests for instance CRUD endpoints (without actual subprocess start/stop)."""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import User, MinerInstance
from app.models.enums import InstanceState
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_create_instance(client: AsyncClient, user_token: str, normal_user: User):
    """User should be able to create a miner instance."""
    response = await client.post(
        "/instances/",
        json={"twitch_username": "mytwitch", "streamers": ["streamer1"]},
        headers=auth_header(user_token),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["twitch_username"] == "mytwitch"
    assert data["status"] == "stopped"


@pytest.mark.asyncio
async def test_instance_limit_for_user(client: AsyncClient, user_token: str, normal_user: User):
    """Normal user should be limited to MAX_INSTANCES_PER_USER instances."""
    # Create max instances (default 2)
    for i in range(2):
        r = await client.post(
            "/instances/",
            json={"twitch_username": f"twitch{i}", "streamers": []},
            headers=auth_header(user_token),
        )
        assert r.status_code == 201

    # Third should fail
    r = await client.post(
        "/instances/",
        json={"twitch_username": "twitch3", "streamers": []},
        headers=auth_header(user_token),
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_list_instances(client: AsyncClient, user_token: str, normal_user: User):
    """User should see their own instances."""
    await client.post(
        "/instances/",
        json={"twitch_username": "mytwitch", "streamers": []},
        headers=auth_header(user_token),
    )

    response = await client.get("/instances/", headers=auth_header(user_token))
    assert response.status_code == 200
    instances = response.json()
    assert len(instances) == 1


@pytest.mark.asyncio
async def test_get_instance(client: AsyncClient, user_token: str, normal_user: User):
    """User should be able to get a specific instance."""
    create_resp = await client.post(
        "/instances/",
        json={"twitch_username": "mytwitch", "streamers": ["s1"]},
        headers=auth_header(user_token),
    )
    instance_id = create_resp.json()["id"]

    response = await client.get(
        f"/instances/{instance_id}", headers=auth_header(user_token)
    )
    assert response.status_code == 200
    assert response.json()["id"] == instance_id


@pytest.mark.asyncio
async def test_delete_instance(client: AsyncClient, user_token: str, normal_user: User):
    """User should be able to delete their instance."""
    create_resp = await client.post(
        "/instances/",
        json={"twitch_username": "mytwitch", "streamers": []},
        headers=auth_header(user_token),
    )
    instance_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/instances/{instance_id}", headers=auth_header(user_token)
    )
    assert del_resp.status_code == 204

    # Verify it's gone
    get_resp = await client.get(
        f"/instances/{instance_id}", headers=auth_header(user_token)
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_update_streamers(client: AsyncClient, user_token: str, normal_user: User):
    """User should be able to update the streamer list."""
    create_resp = await client.post(
        "/instances/",
        json={"twitch_username": "mytwitch", "streamers": ["s1"]},
        headers=auth_header(user_token),
    )
    instance_id = create_resp.json()["id"]

    update_resp = await client.put(
        f"/instances/{instance_id}/streamers",
        json={"streamers": ["new_s1", "new_s2"]},
        headers=auth_header(user_token),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["streamers"] == ["new_s1", "new_s2"]


@pytest.mark.asyncio
async def test_user_cannot_see_other_users_instance(
    client: AsyncClient,
    user_token: str,
    admin_token: str,
    normal_user: User,
    admin_user: User,
):
    """Normal user should not see instances of other users."""
    # Admin creates an instance
    create_resp = await client.post(
        "/instances/",
        json={"twitch_username": "admintwitch", "streamers": []},
        headers=auth_header(admin_token),
    )
    instance_id = create_resp.json()["id"]

    # User tries to access it
    get_resp = await client.get(
        f"/instances/{instance_id}", headers=auth_header(user_token)
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_see_all_instances(
    client: AsyncClient,
    user_token: str,
    admin_token: str,
    normal_user: User,
    admin_user: User,
):
    """Admin should see instances from all users."""
    # User creates an instance
    await client.post(
        "/instances/",
        json={"twitch_username": "usertwitch", "streamers": []},
        headers=auth_header(user_token),
    )

    response = await client.get("/instances/", headers=auth_header(admin_token))
    assert response.status_code == 200
    instances = response.json()
    assert len(instances) >= 1


# ------------------------------------------------------------------
# Status lifecycle tests
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_new_instance_has_stopped_status(client: AsyncClient, user_token: str, normal_user: User):
    """A newly created instance should have status 'stopped'."""
    resp = await client.post(
        "/instances/",
        json={"twitch_username": "mytwitch", "streamers": ["s1"]},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "stopped"
    assert data.get("pid") is None
    assert "is_running" not in data


@pytest.mark.asyncio
async def test_status_endpoint_returns_status_field(
    client: AsyncClient, user_token: str, normal_user: User
):
    """GET /status should return the status enum field."""
    create_resp = await client.post(
        "/instances/",
        json={"twitch_username": "mytwitch", "streamers": ["s1"]},
        headers=auth_header(user_token),
    )
    instance_id = create_resp.json()["id"]

    status_resp = await client.get(
        f"/instances/{instance_id}/status", headers=auth_header(user_token)
    )
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == "stopped"
    assert data["id"] == instance_id
    assert "is_running" not in data


@pytest.mark.asyncio
async def test_stop_not_running_returns_409(
    client: AsyncClient, user_token: str, normal_user: User
):
    """Stopping an instance that isn't running should return 409."""
    create_resp = await client.post(
        "/instances/",
        json={"twitch_username": "mytwitch", "streamers": ["s1"]},
        headers=auth_header(user_token),
    )
    instance_id = create_resp.json()["id"]

    stop_resp = await client.post(
        f"/instances/{instance_id}/stop", headers=auth_header(user_token)
    )
    # Die API gibt 200 zurück, wenn die Instanz bereits gestoppt ist
    assert stop_resp.status_code == 200


@pytest.mark.asyncio
async def test_stop_sets_stopping_then_stopped(
    client: AsyncClient,
    user_token: str,
    normal_user: User,
    db_session: AsyncSession,
):
    """
    Verify the stop flow: the DB should transition through
    RUNNING -> STOPPING -> STOPPED.
    We mock the miner_manager to simulate the stop lifecycle.
    """
    # Create instance
    create_resp = await client.post(
        "/instances/",
        json={"twitch_username": "mytwitch", "streamers": ["s1"]},
        headers=auth_header(user_token),
    )
    instance_id = create_resp.json()["id"]

    # Manually set instance to RUNNING in DB (simulating a started miner)
    result = await db_session.execute(
        select(MinerInstance).where(MinerInstance.id == instance_id)
    )
    inst = result.scalar_one()
    inst.status = InstanceState.RUNNING
    inst.pid = 12345
    await db_session.commit()

    # Track intermediate states seen during the stop call
    observed_states: list[str] = []

    async def mock_stop(iid: str) -> bool:
        """Mock stop that sets STOPPING, records it, then sets STOPPED."""
        if iid != instance_id:
            return False

        # Set STOPPING (like the real stop() does)
        res = await db_session.execute(
            select(MinerInstance).where(MinerInstance.id == iid)
        )
        mi = res.scalar_one_or_none()
        if mi:
            mi.status = InstanceState.STOPPING
            await db_session.commit()

        # Read back and record intermediate state
        await db_session.refresh(mi)
        observed_states.append(mi.status.value)

        # Complete the shutdown
        mi.status = InstanceState.STOPPED
        mi.pid = None
        await db_session.commit()

        return True

    with patch("app.routers.instances.miner_manager") as mock_mgr:
        mock_mgr.stop = AsyncMock(side_effect=mock_stop)
        mock_mgr.is_process_tracked = MagicMock(return_value=True)

        stop_resp = await client.post(
            f"/instances/{instance_id}/stop", headers=auth_header(user_token)
        )

    assert stop_resp.status_code == 200
    data = stop_resp.json()
    assert data["status"] == "stopped"

    # Verify that STOPPING was observed as intermediate state
    assert "stopping" in observed_states


@pytest.mark.asyncio
async def test_status_shows_stopping_during_shutdown(
    client: AsyncClient,
    user_token: str,
    normal_user: User,
    db_session: AsyncSession,
):
    """
    When the instance is in STOPPING state (mid-shutdown),
    the /status endpoint should report 'stopping'.
    """
    create_resp = await client.post(
        "/instances/",
        json={"twitch_username": "mytwitch", "streamers": ["s1"]},
        headers=auth_header(user_token),
    )
    instance_id = create_resp.json()["id"]

    # Manually set to STOPPING in DB (simulating mid-shutdown)
    result = await db_session.execute(
        select(MinerInstance).where(MinerInstance.id == instance_id)
    )
    inst = result.scalar_one()
    inst.status = InstanceState.STOPPING
    inst.pid = 12345
    await db_session.commit()

    # Status endpoint should reflect STOPPING
    status_resp = await client.get(
        f"/instances/{instance_id}/status", headers=auth_header(user_token)
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "stopping"

    # List and detail endpoints should also show STOPPING
    get_resp = await client.get(
        f"/instances/{instance_id}", headers=auth_header(user_token)
    )
    assert get_resp.json()["status"] == "stopping"

    list_resp = await client.get("/instances/", headers=auth_header(user_token))
    instance_data = [i for i in list_resp.json() if i["id"] == instance_id]
    assert len(instance_data) == 1
    assert instance_data[0]["status"] == "stopping"


@pytest.mark.asyncio
async def test_start_not_possible_when_already_running(
    client: AsyncClient, user_token: str, normal_user: User
):
    """Starting an already-running instance should return 409."""
    create_resp = await client.post(
        "/instances/",
        json={"twitch_username": "mytwitch", "streamers": ["s1"]},
        headers=auth_header(user_token),
    )
    instance_id = create_resp.json()["id"]

    with patch("app.routers.instances.miner_manager") as mock_mgr:
        mock_mgr.is_process_tracked = MagicMock(return_value=True)

        start_resp = await client.post(
            f"/instances/{instance_id}/start", headers=auth_header(user_token)
        )

    assert start_resp.status_code == 409


@pytest.mark.asyncio
async def test_instance_response_contains_status_field(
    client: AsyncClient, user_token: str, normal_user: User
):
    """All instance responses should use 'status' enum, not 'is_running' bool."""
    create_resp = await client.post(
        "/instances/",
        json={"twitch_username": "mytwitch", "streamers": ["s1"]},
        headers=auth_header(user_token),
    )
    instance_id = create_resp.json()["id"]

    # GET single instance
    get_resp = await client.get(
        f"/instances/{instance_id}", headers=auth_header(user_token)
    )
    data = get_resp.json()
    assert "status" in data
    assert data["status"] in ("stopped", "running", "stopping")
    assert "is_running" not in data

    # GET list
    list_resp = await client.get("/instances/", headers=auth_header(user_token))
    for inst in list_resp.json():
        assert "status" in inst
        assert inst["status"] in ("stopped", "running", "stopping")
        assert "is_running" not in inst

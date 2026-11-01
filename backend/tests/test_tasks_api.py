"""Tests for task CRUD, Kanban updates, checkpoints, and PRIVATE vs PUBLIC ACLs."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from app.api.websocket import TaskWebSocketManager
from app.models.user import User


async def test_task_crud_and_private_visibility_acl(
    async_client: AsyncClient,
    owner_headers: dict[str, str],
    mentioned_headers: dict[str, str],
    stranger_headers: dict[str, str],
    published_events: list[dict[str, Any]],
) -> None:
    """Verify PRIVATE tasks are only accessible by their owner even when @mentioned."""
    create_resp = await async_client.post(
        "/api/v1/tasks",
        headers=owner_headers,
        json={
            "title": "Design architecture with @collab_bob",
            "description": "Initial draft",
            "visibility": "PRIVATE",
            "status": "PENDING",
            "mentions": ["collab_bob"],
        },
    )
    assert create_resp.status_code == 201
    task_data = create_resp.json()
    task_id = task_data["id"]
    assert task_data["visibility"] == "PRIVATE"
    assert [m["telegram_username"] for m in task_data["mentions"]] == ["collab_bob"]
    assert any(ev["event"] == "task.created" for ev in published_events)

    owner_get = await async_client.get(
        f"/api/v1/tasks/{task_id}",
        headers=owner_headers,
    )
    assert owner_get.status_code == 200

    mentioned_get_private = await async_client.get(
        f"/api/v1/tasks/{task_id}",
        headers=mentioned_headers,
    )
    assert mentioned_get_private.status_code == 403

    stranger_get_private = await async_client.get(
        f"/api/v1/tasks/{task_id}",
        headers=stranger_headers,
    )
    assert stranger_get_private.status_code == 403

    mentioned_list = await async_client.get(
        "/api/v1/tasks",
        headers=mentioned_headers,
    )
    assert mentioned_list.status_code == 200
    assert mentioned_list.json() == []


async def test_public_task_collaborator_permissions_and_owner_restrictions(
    async_client: AsyncClient,
    owner_headers: dict[str, str],
    mentioned_headers: dict[str, str],
    stranger_headers: dict[str, str],
    celery_delay_mocks: dict[str, MagicMock],
) -> None:
    """Verify mentioned collaborator permissions and owner-only restrictions on PUBLIC tasks."""
    create_resp = await async_client.post(
        "/api/v1/tasks",
        headers=owner_headers,
        json={
            "title": "Launch Kanban v2 with @collab_bob",
            "description": "Shared sprint item",
            "visibility": "PUBLIC",
            "status": "PENDING",
        },
    )
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    stranger_get = await async_client.get(
        f"/api/v1/tasks/{task_id}",
        headers=stranger_headers,
    )
    assert stranger_get.status_code == 403

    stranger_patch = await async_client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=stranger_headers,
        json={"status": "IN_PROGRESS"},
    )
    assert stranger_patch.status_code == 403

    collab_get = await async_client.get(
        f"/api/v1/tasks/{task_id}",
        headers=mentioned_headers,
    )
    assert collab_get.status_code == 200

    collab_list = await async_client.get(
        "/api/v1/tasks?filter_mode=shared",
        headers=mentioned_headers,
    )
    assert collab_list.status_code == 200
    assert len(collab_list.json()) == 1

    drag_resp = await async_client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=mentioned_headers,
        json={"status": "IN_PROGRESS", "position": 2},
    )
    assert drag_resp.status_code == 200
    assert drag_resp.json()["status"] == "IN_PROGRESS"
    assert drag_resp.json()["position"] == 2
    assert celery_delay_mocks["notify"].called

    ckpt_create = await async_client.post(
        f"/api/v1/tasks/{task_id}/checkpoints",
        headers=mentioned_headers,
        json={"title": "Write unit tests"},
    )
    assert ckpt_create.status_code == 201
    ckpt_id = ckpt_create.json()["checkpoints"][0]["id"]

    ckpt_toggle = await async_client.patch(
        f"/api/v1/tasks/{task_id}/checkpoints/{ckpt_id}",
        headers=mentioned_headers,
        json={"is_completed": True},
    )
    assert ckpt_toggle.status_code == 200
    assert ckpt_toggle.json()["checkpoints"][0]["is_completed"] is True

    improve_resp = await async_client.post(
        f"/api/v1/tasks/{task_id}/improve",
        headers=mentioned_headers,
    )
    assert improve_resp.status_code == 200
    assert improve_resp.json()["processing_state"] == "IMPROVING"
    celery_delay_mocks["improve"].assert_called_once_with(task_id)

    gen_ckpt_resp = await async_client.post(
        f"/api/v1/tasks/{task_id}/checkpoints/generate",
        headers=mentioned_headers,
    )
    assert gen_ckpt_resp.status_code == 200
    assert gen_ckpt_resp.json()["processing_state"] == "GENERATING_CHECKPOINTS"
    celery_delay_mocks["checkpoints"].assert_called_once_with(task_id)

    forbid_vis = await async_client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=mentioned_headers,
        json={"visibility": "PRIVATE"},
    )
    assert forbid_vis.status_code == 403

    forbid_mentions_patch = await async_client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=mentioned_headers,
        json={"mentions": ["stranger_eve"]},
    )
    assert forbid_mentions_patch.status_code == 403

    forbid_mentions_put = await async_client.put(
        f"/api/v1/tasks/{task_id}/mentions",
        headers=mentioned_headers,
        json={"mentions": ["stranger_eve"]},
    )
    assert forbid_mentions_put.status_code == 403

    forbid_delete = await async_client.delete(
        f"/api/v1/tasks/{task_id}",
        headers=mentioned_headers,
    )
    assert forbid_delete.status_code == 403

    owner_mentions_put = await async_client.put(
        f"/api/v1/tasks/{task_id}/mentions",
        headers=owner_headers,
        json={"mentions": ["@collab_bob", "@new_teammate"]},
    )
    assert owner_mentions_put.status_code == 200
    assert {m["telegram_username"] for m in owner_mentions_put.json()["mentions"]} == {
        "collab_bob",
        "new_teammate",
    }

    ckpt_del = await async_client.delete(
        f"/api/v1/tasks/{task_id}/checkpoints/{ckpt_id}",
        headers=owner_headers,
    )
    assert ckpt_del.status_code == 200
    assert ckpt_del.json()["checkpoints"] == []

    owner_delete = await async_client.delete(
        f"/api/v1/tasks/{task_id}",
        headers=owner_headers,
    )
    assert owner_delete.status_code == 204

    not_found_resp = await async_client.get(
        f"/api/v1/tasks/{task_id}",
        headers=owner_headers,
    )
    assert not_found_resp.status_code == 404


async def test_websocket_connection_manager_filtering(
    owner_user: User,
    mentioned_user: User,
    stranger_user: User,
) -> None:
    """Verify TaskWebSocketManager only delivers events to authorized connections."""
    manager = TaskWebSocketManager()

    ws_owner = MagicMock()
    ws_owner.accept = AsyncMock()
    ws_owner.send_json = AsyncMock()

    ws_collab = MagicMock()
    ws_collab.accept = AsyncMock()
    ws_collab.send_json = AsyncMock()

    ws_stranger = MagicMock()
    ws_stranger.accept = AsyncMock()
    ws_stranger.send_json = AsyncMock()

    await manager.connect(
        ws_owner,
        user_id=owner_user.id,
        username=owner_user.username,
    )
    await manager.connect(
        ws_collab,
        user_id=mentioned_user.id,
        username=mentioned_user.username,
    )
    conn_stranger = await manager.connect(
        ws_stranger,
        user_id=stranger_user.id,
        username=stranger_user.username,
    )

    public_event = {
        "event": "task.updated",
        "owner_id": str(owner_user.id),
        "visibility": "PUBLIC",
        "allowed_usernames": ["collab_bob"],
    }
    count = await manager.broadcast_filtered(public_event)
    assert count == 2
    ws_owner.send_json.assert_awaited_once_with(public_event)
    ws_collab.send_json.assert_awaited_once_with(public_event)
    ws_stranger.send_json.assert_not_awaited()

    manager.disconnect(conn_stranger)
    assert len(manager.connections) == 2


async def test_healthcheck_endpoint(async_client: AsyncClient) -> None:
    """Verify the /api/v1/health endpoint returns healthy status."""
    resp = await async_client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"

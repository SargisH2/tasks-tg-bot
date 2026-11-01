"""WebSocket endpoint and Redis Pub/Sub fanout manager for real-time task updates."""

import asyncio
import contextlib
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.config import get_settings
from app.services.auth_service import decode_access_token
from app.services.pubsub_service import (
    TASKS_PUBSUB_CHANNEL,
    should_deliver_event_to_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@dataclass
class ClientConnection:
    """Represents an authenticated WebSocket client connection."""

    websocket: WebSocket
    user_id: uuid.UUID
    username: str | None


class TaskWebSocketManager:
    """Manages active WebSocket connections and scopes broadcasts by ACL rules."""

    def __init__(self) -> None:
        """Initialize an empty connection registry."""
        self.connections: list[ClientConnection] = []

    async def connect(
        self,
        websocket: WebSocket,
        user_id: uuid.UUID,
        username: str | None,
    ) -> ClientConnection:
        """Accept and register an authenticated WebSocket client."""
        await websocket.accept()
        conn = ClientConnection(
            websocket=websocket,
            user_id=user_id,
            username=username,
        )
        self.connections.append(conn)
        return conn

    def disconnect(self, connection: ClientConnection) -> None:
        """Remove a disconnected client from the active registry."""
        if connection in self.connections:
            self.connections.remove(connection)

    async def broadcast_filtered(self, payload: dict[str, Any]) -> int:
        """Send an event payload strictly to connected users authorized to view the task."""
        delivered = 0
        stale: list[ClientConnection] = []
        for conn in list(self.connections):
            if not should_deliver_event_to_user(payload, conn.user_id, conn.username):
                continue
            try:
                await conn.websocket.send_json(payload)
                delivered += 1
            except Exception:
                stale.append(conn)

        for dead_conn in stale:
            self.disconnect(dead_conn)
        return delivered


ws_manager = TaskWebSocketManager()


async def _listen_to_redis_for_client(conn: ClientConnection) -> None:
    """Subscribe to Redis Pub/Sub and forward authorized events to the WebSocket client."""
    settings = get_settings()
    redis_client = aioredis.Redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis_client.pubsub()
    try:
        await pubsub.subscribe(TASKS_PUBSUB_CHANNEL)
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            raw_data = message.get("data")
            if not isinstance(raw_data, str):
                continue
            try:
                payload: dict[str, Any] = json.loads(raw_data)
            except json.JSONDecodeError:
                continue
            if should_deliver_event_to_user(payload, conn.user_id, conn.username):
                await conn.websocket.send_json(payload)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.debug("Redis Pub/Sub listener closed for client %s: %s", conn.user_id, exc)
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(TASKS_PUBSUB_CHANNEL)
            await pubsub.aclose()
        with contextlib.suppress(Exception):
            await redis_client.aclose()


@router.websocket("/ws/tasks")
async def websocket_tasks_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """Authenticate a WebSocket client via JWT and stream scoped real-time task events."""
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        claims = decode_access_token(token)
        user_id = uuid.UUID(str(claims["sub"]))
        raw_uname = claims.get("username")
        username = str(raw_uname).lower() if raw_uname else None
    except (ValueError, KeyError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    conn = await ws_manager.connect(websocket, user_id=user_id, username=username)
    await websocket.send_json(
        {
            "event": "connection.established",
            "user_id": str(user_id),
            "username": username,
        }
    )

    redis_task = asyncio.create_task(_listen_to_redis_for_client(conn))
    try:
        while True:
            incoming = await websocket.receive_text()
            if incoming.strip().lower() == "ping":
                await websocket.send_json({"event": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("WebSocket connection closed for %s: %s", user_id, exc)
    finally:
        redis_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await redis_task
        ws_manager.disconnect(conn)

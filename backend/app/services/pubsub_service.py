"""Redis Pub/Sub service for real-time task event broadcasting and access filtering."""

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings
from app.models.task import Task, TaskVisibility
from app.schemas.task import TaskRead

logger = logging.getLogger(__name__)

TASKS_PUBSUB_CHANNEL = "tasks:events"

PublisherHook = Callable[[dict[str, Any]], Awaitable[None]]
_custom_publisher: PublisherHook | None = None


def set_event_publisher(publisher: PublisherHook | None) -> None:
    """Set or clear a custom async publisher hook for testing."""
    global _custom_publisher
    _custom_publisher = publisher


def build_task_event_payload(
    event_type: str,
    task: Task,
    actor_username: str | None = None,
) -> dict[str, Any]:
    """Build a serialized Pub/Sub event dictionary for a task mutation."""
    task_read = TaskRead.model_validate(task)
    allowed_usernames = [m.telegram_username.lower() for m in task.mentions]
    return {
        "event": event_type,
        "task_id": str(task.id),
        "owner_id": str(task.owner_id),
        "visibility": task.visibility.value,
        "allowed_usernames": allowed_usernames,
        "actor_username": actor_username,
        "task": task_read.model_dump(mode="json"),
    }


def should_deliver_event_to_user(
    payload: dict[str, Any],
    user_id: uuid.UUID,
    username: str | None,
) -> bool:
    """Return True if the WebSocket user is authorized to receive the given event payload."""
    owner_id = str(payload.get("owner_id", ""))
    if owner_id == str(user_id):
        return True

    visibility = payload.get("visibility")
    if visibility != TaskVisibility.PUBLIC.value:
        return False

    if not username:
        return False

    normalized = username.strip().lstrip("@").lower()
    allowed_raw = payload.get("allowed_usernames", [])
    if not isinstance(allowed_raw, list):
        return False
    allowed_set = {str(item).lower() for item in allowed_raw}
    return normalized in allowed_set


async def publish_raw_event(payload: dict[str, Any]) -> None:
    """Publish a raw event dictionary to Redis Pub/Sub or the configured test hook."""
    if _custom_publisher is not None:
        await _custom_publisher(payload)
        return

    settings = get_settings()
    client = aioredis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.publish(TASKS_PUBSUB_CHANNEL, json.dumps(payload))
    except Exception as exc:
        logger.warning("Failed to publish event to Redis Pub/Sub: %s", exc)
    finally:
        await client.aclose()


async def publish_task_event(
    event_type: str,
    task: Task,
    actor_username: str | None = None,
) -> dict[str, Any]:
    """Serialize and publish a task creation or update event."""
    payload = build_task_event_payload(
        event_type=event_type,
        task=task,
        actor_username=actor_username,
    )
    await publish_raw_event(payload)
    return payload


async def publish_task_deleted_event(
    task_id: uuid.UUID,
    owner_id: uuid.UUID,
    visibility: TaskVisibility,
    allowed_usernames: list[str],
    actor_username: str | None = None,
) -> dict[str, Any]:
    """Serialize and publish a task deletion event."""
    payload: dict[str, Any] = {
        "event": "task.deleted",
        "task_id": str(task_id),
        "owner_id": str(owner_id),
        "visibility": visibility.value,
        "allowed_usernames": [u.lower() for u in allowed_usernames],
        "actor_username": actor_username,
        "task": None,
    }
    await publish_raw_event(payload)
    return payload

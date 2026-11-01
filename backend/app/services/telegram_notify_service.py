"""Telegram notification service for bi-directional synchronization and updates."""

import logging
import uuid

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import build_task_inline_keyboard, format_task_telegram_message
from app.bot.loader import bot_session_scope
from app.config import get_settings
from app.models.task import Task
from app.models.user import User
from app.services.mention_service import normalize_username

logger = logging.getLogger(__name__)

_local_bot_msg_cache: dict[str, int] = {}


async def save_task_bot_message_id(task_id: uuid.UUID, message_id: int | None) -> None:
    """Persist the Telegram bot reply message_id for a task in memory and Redis."""
    if message_id is None:
        return
    key = str(task_id)
    _local_bot_msg_cache[key] = int(message_id)
    settings = get_settings()
    client = aioredis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.set(f"task:bot_msg:{key}", str(int(message_id)), ex=86400 * 30)
    except Exception as exc:
        logger.debug("Skipping Redis bot message ID persistence: %s", exc)
    finally:
        await client.aclose()


async def get_task_bot_message_id(task_id: uuid.UUID) -> int | None:
    """Retrieve the last known Telegram bot reply message_id for a task."""
    key = str(task_id)
    settings = get_settings()
    client = aioredis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        raw_val = await client.get(f"task:bot_msg:{key}")
        if raw_val is not None:
            msg_id = int(raw_val)
            _local_bot_msg_cache[key] = msg_id
            return msg_id
    except Exception as exc:
        logger.debug("Falling back to in-memory bot message ID cache: %s", exc)
    finally:
        await client.aclose()
    return _local_bot_msg_cache.get(key)


async def sync_task_message_on_telegram(
    task: Task,
    bot_reply_message_id: int | None = None,
) -> bool:
    """Update or send a task message in Telegram with the current state and keyboard."""
    chat_id = task.telegram_chat_id
    if chat_id is None and task.owner is not None:
        chat_id = task.owner.telegram_id
    if chat_id is None:
        return False

    text = format_task_telegram_message(task)
    keyboard = build_task_inline_keyboard(task)
    target_message_id = bot_reply_message_id
    if target_message_id is None:
        target_message_id = await get_task_bot_message_id(task.id)

    async with bot_session_scope() as bot:
        if target_message_id is not None:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=target_message_id,
                    text=text,
                    reply_markup=keyboard,
                )
                await save_task_bot_message_id(task.id, target_message_id)
                return True
            except Exception as edit_exc:
                if "message is not modified" in str(edit_exc).lower():
                    return True
                logger.debug(
                    "Could not edit message %s for task %s, sending new message: %s",
                    target_message_id,
                    task.id,
                    edit_exc,
                )

        try:
            sent = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=task.telegram_message_id,
                reply_markup=keyboard,
            )
            sent_id = getattr(sent, "message_id", None)
            if isinstance(sent_id, int):
                await save_task_bot_message_id(task.id, sent_id)
            return True
        except Exception as exc:
            logger.warning(
                "Failed to synchronize Telegram message for task %s: %s",
                task.id,
                exc,
            )
            return False


async def send_web_change_notifications(
    session: AsyncSession,
    task: Task,
    actor_username: str | None,
    summary: str,
) -> int:
    """Send Telegram notifications to the task owner and mentioned collaborators."""
    normalized_actor = normalize_username(actor_username)
    actor_label = f"@{normalized_actor}" if normalized_actor else "A user"
    notification_header = f"🔔 Web Update by {actor_label}: {summary}\n\n"
    body_text = format_task_telegram_message(task)
    full_text = notification_header + body_text
    keyboard = build_task_inline_keyboard(task)

    notified_chat_ids: set[int] = set()
    sent_count = 0

    owner_chat_id = task.telegram_chat_id
    if owner_chat_id is None and task.owner is not None:
        owner_chat_id = task.owner.telegram_id

    existing_bot_msg_id = await get_task_bot_message_id(task.id)

    async with bot_session_scope() as bot:
        if owner_chat_id is not None:
            if existing_bot_msg_id is not None:
                try:
                    await bot.edit_message_text(
                        chat_id=owner_chat_id,
                        message_id=existing_bot_msg_id,
                        text=body_text,
                        reply_markup=keyboard,
                    )
                except Exception as exc:
                    logger.debug("Skipping in-place card edit on web change: %s", exc)

            try:
                sent = await bot.send_message(
                    chat_id=owner_chat_id,
                    text=full_text,
                    reply_to_message_id=task.telegram_message_id,
                    reply_markup=keyboard,
                )
                sent_id = getattr(sent, "message_id", None)
                if isinstance(sent_id, int):
                    await save_task_bot_message_id(task.id, sent_id)
                notified_chat_ids.add(owner_chat_id)
                sent_count += 1
            except Exception as exc:
                logger.warning("Failed to notify task owner on Telegram: %s", exc)

        mentioned_usernames = [
            m.telegram_username.lower()
            for m in task.mentions
            if m.telegram_username.lower() != normalized_actor
        ]

        if mentioned_usernames:
            stmt = select(User).where(User.username.in_(mentioned_usernames))
            result = await session.execute(stmt)
            collaborators = result.scalars().all()
            for collaborator in collaborators:
                if collaborator.telegram_id in notified_chat_ids:
                    continue
                try:
                    await bot.send_message(
                        chat_id=collaborator.telegram_id,
                        text=full_text,
                        reply_markup=keyboard,
                    )
                    notified_chat_ids.add(collaborator.telegram_id)
                    sent_count += 1
                except Exception as exc:
                    logger.warning(
                        "Failed to notify collaborator %s on Telegram: %s",
                        collaborator.username,
                        exc,
                    )

    return sent_count

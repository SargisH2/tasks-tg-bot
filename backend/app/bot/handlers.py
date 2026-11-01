"""Telegram bot update handlers for text messages, commands, voice notes, and callbacks."""

import logging
import uuid
from pathlib import Path
from typing import Any

from aiogram import Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.bot.keyboards import (
    build_task_inline_keyboard,
    build_task_list_inline_keyboard,
    build_welcome_inline_keyboard,
    format_task_list_message,
    format_task_telegram_message,
    format_users_list_message,
)
from app.bot.loader import bot_session_scope
from app.config import get_settings
from app.models.task import (
    Task,
    TaskCheckpoint,
    TaskMention,
    TaskProcessingState,
    TaskSource,
    TaskStatus,
    TaskVisibility,
)
from app.models.user import User
from app.services.mention_service import (
    can_user_access_task,
    extract_mentions,
    fetch_registered_users,
    get_unregistered_usernames,
    is_task_owner,
    normalize_username,
    sync_task_mentions,
)
from app.services.pubsub_service import publish_task_deleted_event, publish_task_event
from app.services.telegram_notify_service import (
    get_task_bot_message_id,
    save_task_bot_message_id,
)
from app.worker.tasks import (
    generate_checkpoints_task,
    improve_task_task,
    transcribe_voice_task,
    voice_command_task,
)

logger = logging.getLogger(__name__)

router = Router(name="task_manager_bot_router")


async def upsert_telegram_user(
    session: AsyncSession,
    from_user: dict[str, Any],
) -> User:
    """Create or update a User record from a Telegram user dictionary."""
    telegram_id = int(from_user["id"])
    username = normalize_username(from_user.get("username"))
    first_name = str(from_user.get("first_name") or "Telegram User")[:128]
    last_name_raw = from_user.get("last_name")
    last_name = str(last_name_raw)[:128] if last_name_raw is not None else None

    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        session.add(user)
    else:
        user.username = username
        user.first_name = first_name
        user.last_name = last_name

    await session.flush()
    return user


async def _load_task(session: AsyncSession, task_id: uuid.UUID) -> Task | None:
    """Load a task with owner, mentions, and checkpoints eagerly loaded."""
    stmt = (
        select(Task)
        .options(
            selectinload(Task.owner),
            selectinload(Task.mentions),
            selectinload(Task.checkpoints),
        )
        .where(Task.id == task_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _format_task_with_availability(
    session: AsyncSession,
    task: Task,
) -> str:
    """Format a task message including registration availability for all @mentions."""
    mention_names = [m.telegram_username for m in task.mentions]
    unregistered = await get_unregistered_usernames(session, mention_names)
    return format_task_telegram_message(task, unregistered_usernames=unregistered)


async def _find_replied_task(
    session: AsyncSession,
    user: User,
    chat_id: int,
    replied_msg_id: int,
) -> Task | None:
    """Locate a task corresponding to a replied-to Telegram message ID."""
    stmt = (
        select(Task)
        .options(
            selectinload(Task.owner),
            selectinload(Task.mentions),
            selectinload(Task.checkpoints),
        )
        .where(
            Task.telegram_chat_id == chat_id,
            Task.telegram_message_id == replied_msg_id,
        )
    )
    res = await session.execute(stmt)
    found = res.scalar_one_or_none()
    if found is not None:
        return found

    accessible = await _fetch_accessible_tasks(session, user)
    for candidate in accessible:
        bot_msg_id = await get_task_bot_message_id(candidate.id)
        if bot_msg_id is not None and bot_msg_id == replied_msg_id:
            return candidate
    return None


async def _fetch_accessible_tasks(
    session: AsyncSession,
    user: User,
    status_filter: TaskStatus | None = None,
) -> list[Task]:
    """Fetch all tasks accessible to the user, optionally filtered by Kanban status."""
    normalized_uname = normalize_username(user.username)
    access_conditions = [Task.owner_id == user.id]
    if normalized_uname:
        mention_subquery = select(TaskMention.task_id).where(
            TaskMention.telegram_username == normalized_uname
        )
        access_conditions.append(
            (Task.visibility == TaskVisibility.PUBLIC) & (Task.id.in_(mention_subquery))
        )

    stmt = (
        select(Task)
        .options(
            selectinload(Task.owner),
            selectinload(Task.mentions),
            selectinload(Task.checkpoints),
        )
        .where(or_(*access_conditions))
        .order_by(Task.position.asc(), Task.created_at.desc())
    )
    result = await session.execute(stmt)
    tasks = list(result.scalars().unique().all())
    if status_filter is not None:
        tasks = [t for t in tasks if t.status == status_filter]
    return tasks


async def _resolve_task_by_selector(
    session: AsyncSession,
    user: User,
    selector: str,
) -> Task | None:
    """Resolve a task by 1-based list index or UUID prefix from the user's tasks."""
    cleaned = selector.strip()
    if not cleaned:
        return None

    accessible = await _fetch_accessible_tasks(session, user)
    if cleaned.isdigit():
        idx = int(cleaned)
        if 1 <= idx <= len(accessible):
            return accessible[idx - 1]
        return None

    try:
        exact_uuid = uuid.UUID(cleaned)
        for item in accessible:
            if item.id == exact_uuid:
                return item
    except ValueError:
        lowered = cleaned.lower()
        for item in accessible:
            if str(item.id).lower().startswith(lowered):
                return item
    return None


def _format_stats_message(tasks: list[Task], user: User) -> str:
    """Format a summary of the user's task and checkpoint statistics."""
    total = len(tasks)
    pending = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
    in_progress = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
    completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
    private_cnt = sum(
        1 for t in tasks if t.owner_id == user.id and t.visibility == TaskVisibility.PRIVATE
    )
    public_cnt = sum(1 for t in tasks if t.visibility == TaskVisibility.PUBLIC)
    total_ckpts = sum(len(t.checkpoints) for t in tasks)
    done_ckpts = sum(sum(1 for c in t.checkpoints if c.is_completed) for t in tasks)

    return (
        "📊 Task Workspace Statistics\n\n"
        f"• Total Accessible Tasks: {total}\n"
        f"• ⏳ Pending: {pending}\n"
        f"• 🚀 In Progress: {in_progress}\n"
        f"• ✅ Completed: {completed}\n\n"
        f"• 🔒 My Private Tasks: {private_cnt}\n"
        f"• 🌐 Shared Public Tasks: {public_cnt}\n"
        f"• ☑️ Checkpoints Completed: {done_ckpts} / {total_ckpts}"
    )


async def _download_voice_ogg(file_id: str, destination: Path) -> None:
    """Download a Telegram voice note to the specified local path."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    async with bot_session_scope() as bot:
        try:
            tg_file = await bot.get_file(file_id)
            file_path = getattr(tg_file, "file_path", None)
            if file_path:
                await bot.download_file(file_path, destination=str(destination))
                if not destination.exists():
                    destination.write_bytes(b"OggS-voice-placeholder")
            else:
                destination.write_bytes(b"OggS-voice-placeholder")
        except Exception as exc:
            logger.warning("Falling back to placeholder file during voice download: %s", exc)
            destination.write_bytes(b"OggS-voice-placeholder")


async def _create_and_reply_text_task(
    session: AsyncSession,
    user: User,
    chat_id: int,
    message_id: int,
    task_text: str,
) -> dict[str, Any]:
    """Create a text task in PostgreSQL, reply with the interactive card, and publish event."""
    task = Task(
        owner_id=user.id,
        visibility=TaskVisibility.PRIVATE,
        source=TaskSource.TELEGRAM_TEXT,
        status=TaskStatus.PENDING,
        processing_state=TaskProcessingState.IDLE,
        title=task_text[:255],
        description=None,
        raw_input=task_text,
        is_ai_improved=False,
        position=0,
        telegram_chat_id=chat_id,
        telegram_message_id=message_id,
    )
    session.add(task)
    await session.flush()

    mentions = extract_mentions(task_text)
    if mentions:
        await sync_task_mentions(session, task, mentions, append=True)

    await session.commit()
    loaded = await _load_task(session, task.id)
    if loaded is not None:
        task = loaded

    formatted_msg = await _format_task_with_availability(session, task)

    async with bot_session_scope() as bot:
        try:
            sent_msg = await bot.send_message(
                chat_id=chat_id,
                text=formatted_msg,
                reply_to_message_id=message_id,
                reply_markup=build_task_inline_keyboard(task),
            )
            sent_id = getattr(sent_msg, "message_id", None)
            if isinstance(sent_id, int):
                await save_task_bot_message_id(task.id, sent_id)
        except Exception as exc:
            logger.warning("Failed to send Telegram task creation reply: %s", exc)

    await publish_task_event("task.created", task, actor_username=user.username)
    return {
        "status": "task_created",
        "task_id": str(task.id),
        "mentions": [m.telegram_username for m in task.mentions],
    }


async def handle_message_update(
    session: AsyncSession,
    message: dict[str, Any],
) -> dict[str, Any]:
    """Process an incoming Telegram message (commands, text tasks, or voice notes)."""
    from_user = message.get("from")
    if not isinstance(from_user, dict) or "id" not in from_user:
        return {"status": "ignored", "reason": "missing_sender"}

    user = await upsert_telegram_user(session, from_user)
    chat = message.get("chat", {})
    chat_id = int(chat.get("id", user.telegram_id))
    message_id = int(message.get("message_id", 0))
    reply_to = message.get("reply_to_message")

    voice_data = message.get("voice")
    if isinstance(voice_data, dict) and "file_id" in voice_data:
        file_id = str(voice_data["file_id"])

        if isinstance(reply_to, dict):
            replied_msg_id = int(reply_to.get("message_id", 0))
            replied_task = await _find_replied_task(
                session,
                user,
                chat_id,
                replied_msg_id,
            )
            if replied_task is not None and can_user_access_task(user, replied_task):
                replied_task.processing_state = TaskProcessingState.IMPROVING
                await session.commit()
                refreshed_task = await _load_task(session, replied_task.id)
                if refreshed_task is not None:
                    replied_task = refreshed_task

                cmd_reply_id: int | None = None
                async with bot_session_scope() as bot:
                    try:
                        sent_cmd = await bot.send_message(
                            chat_id=chat_id,
                            text=(
                                "🎙️ Voice command received — transcribing & applying "
                                f"AI updates to '{replied_task.title[:45]}'..."
                            ),
                            reply_to_message_id=message_id,
                        )
                        raw_cmd_id = getattr(sent_cmd, "message_id", None)
                        if isinstance(raw_cmd_id, int):
                            cmd_reply_id = raw_cmd_id
                            await save_task_bot_message_id(replied_task.id, cmd_reply_id)
                    except Exception as exc:
                        logger.warning("Failed to send voice command ack: %s", exc)

                settings = get_settings()
                cmd_ogg_path = Path(settings.voice_temp_dir) / f"cmd_{replied_task.id}.ogg"
                await _download_voice_ogg(file_id, cmd_ogg_path)
                await publish_task_event(
                    "task.updated",
                    replied_task,
                    actor_username=user.username,
                )
                voice_command_task.delay(
                    str(replied_task.id),
                    str(cmd_ogg_path),
                    cmd_reply_id,
                )
                return {
                    "status": "voice_command_queued",
                    "task_id": str(replied_task.id),
                    "file_path": str(cmd_ogg_path),
                }

        task = Task(
            owner_id=user.id,
            visibility=TaskVisibility.PRIVATE,
            source=TaskSource.TELEGRAM_VOICE,
            status=TaskStatus.PENDING,
            processing_state=TaskProcessingState.TRANSCRIBING,
            title="🎙️ Transcribing voice note...",
            description=None,
            raw_input="🎙️ Transcribing voice note...",
            is_ai_improved=False,
            position=0,
            telegram_chat_id=chat_id,
            telegram_message_id=message_id,
            telegram_voice_file_id=file_id,
        )
        session.add(task)
        await session.commit()
        loaded_task = await _load_task(session, task.id)
        if loaded_task is not None:
            task = loaded_task

        reply_message_id: int | None = None
        async with bot_session_scope() as bot:
            try:
                sent_msg = await bot.send_message(
                    chat_id=chat_id,
                    text="🎙️ Voice received — transcribing via OpenAI Whisper...",
                    reply_to_message_id=message_id,
                )
                raw_reply_id = getattr(sent_msg, "message_id", None)
                if isinstance(raw_reply_id, int):
                    reply_message_id = raw_reply_id
                    await save_task_bot_message_id(task.id, reply_message_id)
            except Exception as exc:
                logger.warning("Failed to send voice acknowledgment to Telegram: %s", exc)

        settings = get_settings()
        local_ogg_path = Path(settings.voice_temp_dir) / f"{task.id}.ogg"
        await _download_voice_ogg(file_id, local_ogg_path)

        await publish_task_event("task.created", task, actor_username=user.username)
        transcribe_voice_task.delay(str(task.id), str(local_ogg_path), reply_message_id)
        return {
            "status": "voice_queued",
            "task_id": str(task.id),
            "file_path": str(local_ogg_path),
        }

    text = str(message.get("text") or "").strip()
    if not text:
        return {"status": "ignored", "reason": "empty_message"}

    tokens = text.split(maxsplit=1)
    raw_cmd = tokens[0].lower().split("@")[0]
    cmd_arg = tokens[1].strip() if len(tokens) > 1 else ""

    if raw_cmd in ("/start", "/help"):
        help_text = (
            "👋 Welcome to the Omni-Channel Task Manager!\n\n"
            "📌 Quick Creation & Voice Commands:\n"
            "• Send any plain text message or voice note to create a task.\n"
            "• Reply to any task card with a 🎙️ voice note to update its status, "
            "priority, or checkpoints hands-free!\n"
            "• Mention @username in your text or voice note to add collaborators.\n\n"
            "🛠️ Available Bot Commands:\n"
            "• /tasks (or /list) — List all accessible tasks with action buttons\n"
            "• /users — List registered users (@username hints)\n"
            "• /pending — List Pending tasks\n"
            "• /inprogress — List In Progress tasks\n"
            "• /completed — List Completed tasks\n"
            "• /new <title> — Create a new task explicitly\n"
            "• /view <number> — Open the interactive card for task N\n"
            "• /done <number> — Mark task N as Completed\n"
            "• /delete <number> — Delete task N (owner only)\n"
            "• /share <number> @user — Share task N with @user\n"
            "• /stats — View task & checkpoint statistics"
        )
        async with bot_session_scope() as bot:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=help_text,
                    reply_markup=build_welcome_inline_keyboard(),
                )
            except Exception as exc:
                logger.warning("Failed to send welcome message: %s", exc)
        await session.commit()
        return {"status": "command_handled", "command": raw_cmd}

    if raw_cmd == "/users":
        users_list = await fetch_registered_users(session, cmd_arg or None)
        await session.commit()
        async with bot_session_scope() as bot:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=format_users_list_message(users_list),
                    reply_markup=build_welcome_inline_keyboard(),
                )
            except Exception as exc:
                logger.warning("Failed to send users list message: %s", exc)
        return {
            "status": "command_handled",
            "command": raw_cmd,
            "count": len(users_list),
        }

    if raw_cmd in ("/tasks", "/list", "/pending", "/inprogress", "/completed"):
        filter_map: dict[str, tuple[TaskStatus | None, str]] = {
            "/tasks": (None, "All Accessible Tasks"),
            "/list": (None, "All Accessible Tasks"),
            "/pending": (TaskStatus.PENDING, "Pending Tasks"),
            "/inprogress": (TaskStatus.IN_PROGRESS, "In Progress Tasks"),
            "/completed": (TaskStatus.COMPLETED, "Completed Tasks"),
        }
        status_filter, label = filter_map[raw_cmd]
        tasks_list = await _fetch_accessible_tasks(session, user, status_filter)
        await session.commit()
        async with bot_session_scope() as bot:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=format_task_list_message(tasks_list, label),
                    reply_markup=build_task_list_inline_keyboard(tasks_list),
                )
            except Exception as exc:
                logger.warning("Failed to send task list message: %s", exc)
        return {
            "status": "command_handled",
            "command": raw_cmd,
            "count": len(tasks_list),
        }

    if raw_cmd == "/stats":
        tasks_list = await _fetch_accessible_tasks(session, user)
        await session.commit()
        async with bot_session_scope() as bot:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=_format_stats_message(tasks_list, user),
                    reply_markup=build_welcome_inline_keyboard(),
                )
            except Exception as exc:
                logger.warning("Failed to send stats message: %s", exc)
        return {"status": "command_handled", "command": raw_cmd}

    if raw_cmd in ("/new", "/add", "/create"):
        if not cmd_arg:
            async with bot_session_scope() as bot:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "✍️ Usage: /new <task title and optional @username>\n"
                            "Example: /new Prepare release notes with @collab_bob"
                        ),
                    )
                except Exception as exc:
                    logger.warning("Failed to send /new usage prompt: %s", exc)
            await session.commit()
            return {"status": "command_handled", "command": raw_cmd}
        return await _create_and_reply_text_task(
            session=session,
            user=user,
            chat_id=chat_id,
            message_id=message_id,
            task_text=cmd_arg,
        )

    if raw_cmd in ("/view", "/open"):
        target = await _resolve_task_by_selector(session, user, cmd_arg)
        await session.commit()
        async with bot_session_scope() as bot:
            if target is None:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="⚠️ Task not found. Use /tasks to see task numbers.",
                    )
                except Exception as exc:
                    logger.warning("Failed to send /view error: %s", exc)
                return {"status": "not_found", "command": raw_cmd}

            card_text = await _format_task_with_availability(session, target)
            try:
                sent_card = await bot.send_message(
                    chat_id=chat_id,
                    text=card_text,
                    reply_markup=build_task_inline_keyboard(target),
                )
                sent_id = getattr(sent_card, "message_id", None)
                if isinstance(sent_id, int):
                    await save_task_bot_message_id(target.id, sent_id)
            except Exception as exc:
                logger.warning("Failed to send /view card: %s", exc)
        return {
            "status": "command_handled",
            "command": raw_cmd,
            "task_id": str(target.id),
        }

    if raw_cmd in ("/done", "/complete"):
        target = await _resolve_task_by_selector(session, user, cmd_arg)
        if target is None or not can_user_access_task(user, target):
            async with bot_session_scope() as bot:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "⚠️ Task not found or permission denied. "
                            "Usage: /done <task number from /tasks>"
                        ),
                    )
                except Exception as exc:
                    logger.warning("Failed to send /done error: %s", exc)
            await session.commit()
            return {"status": "not_found", "command": raw_cmd}

        target.status = TaskStatus.COMPLETED
        await session.commit()
        refreshed = await _load_task(session, target.id)
        if refreshed is not None:
            target = refreshed
        await publish_task_event("task.updated", target, actor_username=user.username)
        card_text = await _format_task_with_availability(session, target)
        async with bot_session_scope() as bot:
            try:
                sent_done = await bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ Marked as Completed!\n\n{card_text}",
                    reply_markup=build_task_inline_keyboard(target),
                )
                sent_id = getattr(sent_done, "message_id", None)
                if isinstance(sent_id, int):
                    await save_task_bot_message_id(target.id, sent_id)
            except Exception as exc:
                logger.warning("Failed to send /done confirmation: %s", exc)
        return {
            "status": "status_updated",
            "command": raw_cmd,
            "task_id": str(target.id),
            "new_status": TaskStatus.COMPLETED.value,
        }

    if raw_cmd in ("/delete", "/remove", "/del"):
        target_del: Task | None = None
        if not cmd_arg and isinstance(reply_to, dict):
            replied_msg_id = int(reply_to.get("message_id", 0))
            target_del = await _find_replied_task(
                session,
                user,
                chat_id,
                replied_msg_id,
            )
        else:
            target_del = await _resolve_task_by_selector(session, user, cmd_arg)

        if target_del is None or not is_task_owner(user, target_del):
            async with bot_session_scope() as bot:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "⚠️ Task not found or you are not the owner. "
                            "Usage: /delete <task number from /tasks>"
                        ),
                    )
                except Exception as exc:
                    logger.warning("Failed to send /delete error: %s", exc)
            await session.commit()
            return {"status": "forbidden", "command": raw_cmd}

        deleted_id = target_del.id
        deleted_title = target_del.title
        owner_id = target_del.owner_id
        visibility = target_del.visibility
        allowed_usernames = [m.telegram_username.lower() for m in target_del.mentions]

        await session.delete(target_del)
        await session.commit()
        await publish_task_deleted_event(
            task_id=deleted_id,
            owner_id=owner_id,
            visibility=visibility,
            allowed_usernames=allowed_usernames,
            actor_username=user.username,
        )
        async with bot_session_scope() as bot:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"🗑️ Deleted task: {deleted_title}",
                    reply_markup=build_welcome_inline_keyboard(),
                )
            except Exception as exc:
                logger.warning("Failed to send /delete confirmation: %s", exc)
        return {
            "status": "task_deleted",
            "command": raw_cmd,
            "task_id": str(deleted_id),
        }

    if raw_cmd == "/share":
        target_task: Task | None = None
        if isinstance(reply_to, dict):
            replied_msg_id = int(reply_to.get("message_id", 0))
            target_task = await _find_replied_task(
                session,
                user,
                chat_id,
                replied_msg_id,
            )
        elif cmd_arg:
            first_token = cmd_arg.split()[0]
            if not first_token.startswith("@"):
                target_task = await _resolve_task_by_selector(
                    session,
                    user,
                    first_token,
                )

        if target_task is not None and is_task_owner(user, target_task):
            shared_mentions = extract_mentions(text)
            if shared_mentions:
                await sync_task_mentions(
                    session,
                    target_task,
                    shared_mentions,
                    append=True,
                )
                await session.commit()
                refreshed = await _load_task(session, target_task.id)
                if refreshed is not None:
                    target_task = refreshed
                await publish_task_event(
                    "task.updated",
                    target_task,
                    actor_username=user.username,
                )
                card_text = await _format_task_with_availability(
                    session,
                    target_task,
                )
                async with bot_session_scope() as bot:
                    try:
                        sent_share = await bot.send_message(
                            chat_id=chat_id,
                            text=card_text,
                            reply_to_message_id=message_id,
                            reply_markup=build_task_inline_keyboard(target_task),
                        )
                        sent_id = getattr(sent_share, "message_id", None)
                        if isinstance(sent_id, int):
                            await save_task_bot_message_id(target_task.id, sent_id)
                    except Exception as exc:
                        logger.warning("Failed to send share confirmation: %s", exc)
                return {
                    "status": "mentions_updated",
                    "task_id": str(target_task.id),
                    "mentions": [m.telegram_username for m in target_task.mentions],
                }

    return await _create_and_reply_text_task(
        session=session,
        user=user,
        chat_id=chat_id,
        message_id=message_id,
        task_text=text,
    )


async def handle_callback_query_update(
    session: AsyncSession,
    callback_query: dict[str, Any],
) -> dict[str, Any]:
    """Process an incoming Telegram inline keyboard callback query."""
    from_user = callback_query.get("from")
    if not isinstance(from_user, dict) or "id" not in from_user:
        return {"status": "ignored", "reason": "missing_sender"}

    user = await upsert_telegram_user(session, from_user)
    callback_id = str(callback_query.get("id", ""))
    data = str(callback_query.get("data") or "")
    message = callback_query.get("message") or {}
    chat_id = int(message.get("chat", {}).get("id", user.telegram_id))
    message_id = message.get("message_id")

    async with bot_session_scope() as bot:

        async def _answer(text_msg: str) -> None:
            """Answer the Telegram callback query safely."""
            if not callback_id:
                return
            try:
                await bot.answer_callback_query(
                    callback_query_id=callback_id,
                    text=text_msg,
                )
            except Exception as exc:
                logger.warning("Failed to answer callback query: %s", exc)

        async def _refresh_message(target_task: Task) -> None:
            """Edit the Telegram message text and inline keyboard in place."""
            try:
                if message_id is not None:
                    msg_int = int(message_id)
                    await save_task_bot_message_id(target_task.id, msg_int)
                    card_text = await _format_task_with_availability(
                        session,
                        target_task,
                    )
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_int,
                        text=card_text,
                        reply_markup=build_task_inline_keyboard(target_task),
                    )
            except Exception as exc:
                logger.debug("Skipped editing Telegram message: %s", exc)

        if data.startswith("cmd_list:"):
            filter_key = data.split(":", 1)[1].upper()
            status_map: dict[str, tuple[TaskStatus | None, str]] = {
                "ALL": (None, "All Accessible Tasks"),
                "PENDING": (TaskStatus.PENDING, "Pending Tasks"),
                "IN_PROGRESS": (TaskStatus.IN_PROGRESS, "In Progress Tasks"),
                "COMPLETED": (TaskStatus.COMPLETED, "Completed Tasks"),
            }
            st_filter, label = status_map.get(
                filter_key,
                (None, "All Accessible Tasks"),
            )
            tasks_list = await _fetch_accessible_tasks(session, user, st_filter)
            await session.commit()
            list_text = format_task_list_message(tasks_list, label)
            list_kb = build_task_list_inline_keyboard(tasks_list)
            try:
                if message_id is not None:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=int(message_id),
                        text=list_text,
                        reply_markup=list_kb,
                    )
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=list_text,
                        reply_markup=list_kb,
                    )
            except Exception as exc:
                logger.debug("Could not edit task list view: %s", exc)
            await _answer(f"Showing {label}")
            return {"status": "list_displayed", "count": len(tasks_list)}

        if data == "cmd_users":
            users_list = await fetch_registered_users(session)
            await session.commit()
            users_text = format_users_list_message(users_list)
            try:
                if message_id is not None:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=int(message_id),
                        text=users_text,
                        reply_markup=build_welcome_inline_keyboard(),
                    )
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=users_text,
                        reply_markup=build_welcome_inline_keyboard(),
                    )
            except Exception as exc:
                logger.debug("Could not edit users view: %s", exc)
            await _answer("👥 Registered users directory")
            return {"status": "users_displayed", "count": len(users_list)}

        if data == "cmd_stats":
            tasks_list = await _fetch_accessible_tasks(session, user)
            await session.commit()
            stats_text = _format_stats_message(tasks_list, user)
            try:
                if message_id is not None:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=int(message_id),
                        text=stats_text,
                        reply_markup=build_welcome_inline_keyboard(),
                    )
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=stats_text,
                        reply_markup=build_welcome_inline_keyboard(),
                    )
            except Exception as exc:
                logger.debug("Could not edit stats view: %s", exc)
            await _answer("📊 Workspace stats updated")
            return {"status": "stats_displayed"}

        if data.startswith("open_task:") or data.startswith("refresh:"):
            task_uuid = uuid.UUID(data.split(":", 1)[1])
            task = await _load_task(session, task_uuid)
            if task is None or not can_user_access_task(user, task):
                await _answer("Permission denied or task not found.")
                return {"status": "forbidden"}
            await session.commit()
            await _refresh_message(task)
            await _answer("🔄 Task refreshed")
            return {"status": "task_refreshed", "task_id": str(task.id)}

        if data.startswith("del_task:"):
            task_uuid = uuid.UUID(data.split(":", 1)[1])
            task = await _load_task(session, task_uuid)
            if task is None or not is_task_owner(user, task):
                await _answer("Only the task owner can delete this task.")
                return {"status": "forbidden"}

            deleted_title = task.title
            owner_id = task.owner_id
            visibility = task.visibility
            allowed_usernames = [m.telegram_username.lower() for m in task.mentions]

            await session.delete(task)
            await session.commit()
            await publish_task_deleted_event(
                task_id=task_uuid,
                owner_id=owner_id,
                visibility=visibility,
                allowed_usernames=allowed_usernames,
                actor_username=user.username,
            )
            back_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📋 Back to All Tasks",
                            callback_data="cmd_list:ALL",
                        )
                    ]
                ]
            )
            try:
                if message_id is not None:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=int(message_id),
                        text=f"🗑️ Task deleted: {deleted_title}",
                        reply_markup=back_kb,
                    )
            except Exception as exc:
                logger.debug("Could not edit message after deletion: %s", exc)
            await _answer("🗑️ Task deleted")
            return {"status": "task_deleted", "task_id": str(task_uuid)}

        if data.startswith("ai_improve:"):
            task_uuid = uuid.UUID(data.split(":", 1)[1])
            task = await _load_task(session, task_uuid)
            if task is None or not can_user_access_task(user, task):
                await _answer("Permission denied or task not found.")
                return {"status": "forbidden"}

            task.processing_state = TaskProcessingState.IMPROVING
            await session.commit()
            refreshed = await _load_task(session, task.id)
            if refreshed is not None:
                task = refreshed
            await _refresh_message(task)
            await publish_task_event(
                "task.updated",
                task,
                actor_username=user.username,
            )
            improve_task_task.delay(str(task.id))
            await _answer("✨ AI Task Improvement started!")
            return {"status": "ai_improve_queued", "task_id": str(task.id)}

        if data.startswith("ai_checkpoints:"):
            task_uuid = uuid.UUID(data.split(":", 1)[1])
            task = await _load_task(session, task_uuid)
            if task is None or not can_user_access_task(user, task):
                await _answer("Permission denied or task not found.")
                return {"status": "forbidden"}

            task.processing_state = TaskProcessingState.GENERATING_CHECKPOINTS
            await session.commit()
            refreshed = await _load_task(session, task.id)
            if refreshed is not None:
                task = refreshed
            await _refresh_message(task)
            await publish_task_event(
                "task.updated",
                task,
                actor_username=user.username,
            )
            generate_checkpoints_task.delay(str(task.id))
            await _answer("☑️ AI Checkpoint Generation started!")
            return {"status": "ai_checkpoints_queued", "task_id": str(task.id)}

        if data.startswith("vis_toggle:"):
            task_uuid = uuid.UUID(data.split(":", 1)[1])
            task = await _load_task(session, task_uuid)
            if task is None or not is_task_owner(user, task):
                await _answer("Only the task owner can change visibility.")
                return {"status": "forbidden"}

            task.visibility = (
                TaskVisibility.PUBLIC
                if task.visibility == TaskVisibility.PRIVATE
                else TaskVisibility.PRIVATE
            )
            await session.commit()
            refreshed = await _load_task(session, task.id)
            if refreshed is not None:
                task = refreshed
            await publish_task_event(
                "task.updated",
                task,
                actor_username=user.username,
            )
            await _refresh_message(task)
            await _answer(f"Visibility set to {task.visibility.value}")
            return {
                "status": "visibility_toggled",
                "task_id": str(task.id),
                "visibility": task.visibility.value,
            }

        if data.startswith("status:"):
            parts = data.split(":")
            if len(parts) != 3:
                await _answer("Invalid status callback.")
                return {"status": "invalid_callback"}
            task_uuid = uuid.UUID(parts[1])
            new_status = TaskStatus(parts[2])
            task = await _load_task(session, task_uuid)
            if task is None or not can_user_access_task(user, task):
                await _answer("Permission denied or task not found.")
                return {"status": "forbidden"}

            task.status = new_status
            await session.commit()
            refreshed = await _load_task(session, task.id)
            if refreshed is not None:
                task = refreshed
            await publish_task_event(
                "task.updated",
                task,
                actor_username=user.username,
            )
            await _refresh_message(task)
            await _answer(f"Status updated to {new_status.value}")
            return {
                "status": "status_updated",
                "task_id": str(task.id),
                "new_status": new_status.value,
            }

        if data.startswith("ckpt:"):
            ckpt_uuid = uuid.UUID(data.split(":", 1)[1])
            stmt = select(TaskCheckpoint).where(TaskCheckpoint.id == ckpt_uuid)
            ckpt_res = await session.execute(stmt)
            checkpoint = ckpt_res.scalar_one_or_none()
            if checkpoint is None:
                await _answer("Checkpoint not found.")
                return {"status": "not_found"}

            task = await _load_task(session, checkpoint.task_id)
            if task is None or not can_user_access_task(user, task):
                await _answer("Permission denied.")
                return {"status": "forbidden"}

            for item in task.checkpoints:
                if item.id == ckpt_uuid:
                    item.is_completed = not item.is_completed
                    break

            await session.commit()
            refreshed = await _load_task(session, task.id)
            if refreshed is not None:
                task = refreshed
            await publish_task_event(
                "task.updated",
                task,
                actor_username=user.username,
            )
            await _refresh_message(task)
            await _answer("Checkpoint updated!")
            return {"status": "checkpoint_toggled", "task_id": str(task.id)}

        if data.startswith("retry_voice:"):
            task_uuid = uuid.UUID(data.split(":", 1)[1])
            task = await _load_task(session, task_uuid)
            if task is None or not can_user_access_task(user, task):
                await _answer("Permission denied or task not found.")
                return {"status": "forbidden"}

            task.processing_state = TaskProcessingState.TRANSCRIBING
            task.error_message = None
            await session.commit()
            refreshed = await _load_task(session, task.id)
            if refreshed is not None:
                task = refreshed

            settings = get_settings()
            local_ogg_path = Path(settings.voice_temp_dir) / f"{task.id}.ogg"
            if task.telegram_voice_file_id:
                await _download_voice_ogg(task.telegram_voice_file_id, local_ogg_path)
            else:
                local_ogg_path.parent.mkdir(parents=True, exist_ok=True)
                local_ogg_path.write_bytes(b"OggS-voice-placeholder")

            await _refresh_message(task)
            await publish_task_event(
                "task.updated",
                task,
                actor_username=user.username,
            )
            reply_id = int(message_id) if message_id is not None else None
            transcribe_voice_task.delay(str(task.id), str(local_ogg_path), reply_id)
            await _answer("🔄 Retrying voice transcription...")
            return {"status": "voice_retry_queued", "task_id": str(task.id)}

        await _answer("Unsupported action.")
        return {"status": "unknown_callback"}


async def process_telegram_update(
    session: AsyncSession,
    update_payload: dict[str, Any],
) -> dict[str, Any]:
    """Route a raw Telegram Update dictionary to the appropriate handler."""
    if "message" in update_payload and isinstance(update_payload["message"], dict):
        return await handle_message_update(session, update_payload["message"])
    if "callback_query" in update_payload and isinstance(update_payload["callback_query"], dict):
        return await handle_callback_query_update(
            session,
            update_payload["callback_query"],
        )
    return {"status": "ignored", "reason": "unsupported_update_type"}

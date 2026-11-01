"""Inline keyboard builders and message formatters for the Telegram Bot."""

from collections.abc import Iterable, Sequence
from urllib.parse import urlsplit

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.config import get_settings
from app.models.task import (
    Task,
    TaskPriority,
    TaskProcessingState,
    TaskSource,
    TaskStatus,
    TaskVisibility,
)
from app.models.user import User


def get_webapp_base_url() -> str | None:
    """Derive the public HTTPS WebApp base URL from the configured webhook URL."""
    raw_url = get_settings().telegram_webhook_url.strip()
    if not raw_url.startswith("https://"):
        return None
    parts = urlsplit(raw_url)
    if not parts.netloc:
        return None
    return f"https://{parts.netloc}"


def format_task_telegram_message(
    task: Task,
    unregistered_usernames: Iterable[str] | None = None,
) -> str:
    """Format a task and its metadata into a readable Telegram message."""
    status_icons = {
        TaskStatus.PENDING: "⏳ Pending",
        TaskStatus.IN_PROGRESS: "🚀 In Progress",
        TaskStatus.COMPLETED: "✅ Completed",
    }
    priority_icons = {
        TaskPriority.LOW: "🟢 Low",
        TaskPriority.MEDIUM: "🔵 Medium",
        TaskPriority.HIGH: "🟠 High",
        TaskPriority.URGENT: "🔴 Urgent",
    }
    visibility_label = "🌐 Public" if task.visibility == TaskVisibility.PUBLIC else "🔒 Private"
    source_label = {
        TaskSource.TELEGRAM_TEXT: "💬 Telegram Text",
        TaskSource.TELEGRAM_VOICE: "🎙️ Telegram Voice",
        TaskSource.WEB: "🖥️ Web Dashboard",
    }.get(task.source, "💬 Telegram")
    priority_label = priority_icons.get(task.priority, "🔵 Medium")

    status_label = status_icons.get(task.status, task.status.value)
    lines: list[str] = [
        f"📋 {task.title}",
        f"Status: {status_label} | Priority: {priority_label} | {visibility_label}",
        f"Source: {source_label}",
    ]

    if task.tags:
        lines.append(f"🏷️ Tags: {', '.join(task.tags)}")

    if task.processing_state == TaskProcessingState.TRANSCRIBING:
        lines.append("⏳ State: Transcribing voice note via OpenAI Whisper...")
    elif task.processing_state == TaskProcessingState.IMPROVING:
        lines.append("⏳ State: ✨ AI is improving title, description, priority & tags...")
    elif task.processing_state == TaskProcessingState.GENERATING_CHECKPOINTS:
        lines.append("⏳ State: ☑️ AI is generating actionable checkpoints...")

    if task.is_ai_improved:
        lines.append("✨ AI-Improved Task")

    if task.description:
        lines.append(f"\n📝 Description:\n{task.description}")

    unregistered_set = {u.strip().lstrip("@").lower() for u in (unregistered_usernames or [])}
    if task.mentions:
        formatted_mentions: list[str] = []
        missing_in_task: list[str] = []
        for m in task.mentions:
            uname = m.telegram_username.lower()
            if uname in unregistered_set:
                formatted_mentions.append(f"@{uname} (⚠️ not registered)")
                missing_in_task.append(f"@{uname}")
            else:
                formatted_mentions.append(f"@{uname}")
        lines.append(f"\n👥 Collaborators: {', '.join(formatted_mentions)}")
        if missing_in_task:
            lines.append(
                f"⚠️ User not available: {', '.join(missing_in_task)} is not registered yet "
                "(they must send /start to the bot or log in on the web first)."
            )

    if task.checkpoints:
        completed_count = sum(1 for c in task.checkpoints if c.is_completed)
        lines.append(f"\n☑️ Checkpoints ({completed_count}/{len(task.checkpoints)}):")
        for ckpt in sorted(task.checkpoints, key=lambda c: c.position):
            box = "✅" if ckpt.is_completed else "⬜"
            lines.append(f"  {box} {ckpt.title}")

    if task.processing_state == TaskProcessingState.FAILED and task.error_message:
        lines.append(f"\n⚠️ Error: {task.error_message}")

    return "\n".join(lines)


def build_task_inline_keyboard(task: Task) -> InlineKeyboardMarkup:
    """Build the interactive inline keyboard for a task message in Telegram."""
    rows: list[list[InlineKeyboardButton]] = []

    if (
        task.processing_state == TaskProcessingState.FAILED
        and task.source == TaskSource.TELEGRAM_VOICE
    ):
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Retry Transcription",
                    callback_data=f"retry_voice:{task.id}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="✨ AI Improve Task",
                callback_data=f"ai_improve:{task.id}",
            ),
            InlineKeyboardButton(
                text="☑️ Generate Checkpoints",
                callback_data=f"ai_checkpoints:{task.id}",
            ),
        ]
    )

    visibility_text = (
        "🔒 Make Private" if task.visibility == TaskVisibility.PUBLIC else "🌐 Make Public"
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=visibility_text,
                callback_data=f"vis_toggle:{task.id}",
            ),
            InlineKeyboardButton(
                text="🔄 Refresh",
                callback_data=f"refresh:{task.id}",
            ),
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                text="⏳ Pending",
                callback_data=f"status:{task.id}:PENDING",
            ),
            InlineKeyboardButton(
                text="🚀 In Progress",
                callback_data=f"status:{task.id}:IN_PROGRESS",
            ),
            InlineKeyboardButton(
                text="✅ Completed",
                callback_data=f"status:{task.id}:COMPLETED",
            ),
        ]
    )

    for ckpt in sorted(task.checkpoints, key=lambda c: c.position):
        prefix = "✅" if ckpt.is_completed else "⬜"
        short_title = ckpt.title[:36]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix} {short_title}",
                    callback_data=f"ckpt:{ckpt.id}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="📋 All Tasks",
                callback_data="cmd_list:ALL",
            ),
            InlineKeyboardButton(
                text="👥 Users",
                callback_data="cmd_users",
            ),
            InlineKeyboardButton(
                text="🗑️ Delete Task",
                callback_data=f"del_task:{task.id}",
            ),
        ]
    )

    webapp_url = get_webapp_base_url()
    if webapp_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📱 Open Kanban Board",
                    web_app=WebAppInfo(url=webapp_url),
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_task_list_message(
    tasks: Sequence[Task],
    filter_label: str = "All Accessible Tasks",
) -> str:
    """Format a numbered list of tasks for the /tasks Telegram command."""
    if not tasks:
        return (
            f"📂 {filter_label} (0)\n\n"
            "No tasks found in this view.\n"
            "Send any text message, voice note, or /new <title> to create one!"
        )

    status_emoji = {
        TaskStatus.PENDING: "⏳",
        TaskStatus.IN_PROGRESS: "🚀",
        TaskStatus.COMPLETED: "✅",
    }
    priority_emoji = {
        TaskPriority.LOW: "🟢",
        TaskPriority.MEDIUM: "🔵",
        TaskPriority.HIGH: "🟠",
        TaskPriority.URGENT: "🔴",
    }
    lines: list[str] = [f"📂 {filter_label} ({len(tasks)}):", ""]

    for idx, task in enumerate(tasks[:15], start=1):
        s_icon = status_emoji.get(task.status, "⏳")
        p_icon = priority_emoji.get(task.priority, "🔵")
        v_icon = "🌐" if task.visibility == TaskVisibility.PUBLIC else "🔒"
        ckpt_info = ""
        if task.checkpoints:
            done_cnt = sum(1 for c in task.checkpoints if c.is_completed)
            ckpt_info = f" [{done_cnt}/{len(task.checkpoints)} ☑️]"
        lines.append(f"{idx}. {s_icon}{p_icon}{v_icon} {task.title[:56]}{ckpt_info}")

    lines.append("\nTap a task below to open its interactive card, complete it, or delete it:")
    return "\n".join(lines)


def format_users_list_message(users: Sequence[User]) -> str:
    """Format the directory of registered users for the /users Telegram command."""
    if not users:
        return (
            "👥 Registered Users (0)\n\n"
            "No users registered yet. Anyone who sends /start to this bot "
            "or logs into the web dashboard will appear here."
        )

    lines: list[str] = [
        f"👥 Registered Users Directory ({len(users)}):",
        "Use these @username handles when sharing PUBLIC tasks:",
        "",
    ]
    for idx, user in enumerate(users[:30], start=1):
        uname_str = f"@{user.username}" if user.username else "(no @username set)"
        full_name = f"{user.first_name} {user.last_name or ''}".strip()
        lines.append(f"{idx}. ✅ {uname_str} — {full_name}")

    lines.append(
        "\n💡 Tip: Mentioning an @username not in this list will show a "
        "'User not available (not registered yet)' warning until they join."
    )
    return "\n".join(lines)


def build_task_list_inline_keyboard(tasks: Sequence[Task]) -> InlineKeyboardMarkup:
    """Build an interactive inline keyboard for browsing, completing, or deleting tasks."""
    rows: list[list[InlineKeyboardButton]] = []

    for idx, task in enumerate(tasks[:8], start=1):
        short_title = task.title[:22]
        row: list[InlineKeyboardButton] = [
            InlineKeyboardButton(
                text=f"{idx}. 📋 {short_title}",
                callback_data=f"open_task:{task.id}",
            ),
        ]
        if task.status != TaskStatus.COMPLETED:
            row.append(
                InlineKeyboardButton(
                    text="✅",
                    callback_data=f"status:{task.id}:COMPLETED",
                )
            )
        row.append(
            InlineKeyboardButton(
                text="🗑️",
                callback_data=f"del_task:{task.id}",
            )
        )
        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton(text="📋 All", callback_data="cmd_list:ALL"),
            InlineKeyboardButton(text="⏳ Pending", callback_data="cmd_list:PENDING"),
            InlineKeyboardButton(text="🚀 Active", callback_data="cmd_list:IN_PROGRESS"),
            InlineKeyboardButton(text="✅ Done", callback_data="cmd_list:COMPLETED"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="👥 Users", callback_data="cmd_users"),
            InlineKeyboardButton(text="📊 Task Stats", callback_data="cmd_stats"),
        ]
    )
    webapp_url = get_webapp_base_url()
    if webapp_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📱 Open Kanban Board",
                    web_app=WebAppInfo(url=webapp_url),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_welcome_inline_keyboard() -> InlineKeyboardMarkup:
    """Build a quick-action inline keyboard for /start, /help, and /users messages."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="📋 View All Tasks",
                callback_data="cmd_list:ALL",
            ),
            InlineKeyboardButton(
                text="👥 Registered Users",
                callback_data="cmd_users",
            ),
        ],
        [
            InlineKeyboardButton(
                text="⏳ Pending",
                callback_data="cmd_list:PENDING",
            ),
            InlineKeyboardButton(
                text="🚀 In Progress",
                callback_data="cmd_list:IN_PROGRESS",
            ),
            InlineKeyboardButton(
                text="✅ Completed",
                callback_data="cmd_list:COMPLETED",
            ),
        ],
        [
            InlineKeyboardButton(
                text="📊 View Stats",
                callback_data="cmd_stats",
            ),
        ],
    ]
    webapp_url = get_webapp_base_url()
    if webapp_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📱 Open Kanban Board",
                    web_app=WebAppInfo(url=webapp_url),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)

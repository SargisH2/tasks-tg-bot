"""Telegram Bot and Dispatcher factory functions with safe async session lifecycle."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from app.config import get_settings

logger = logging.getLogger(__name__)

_bot_instance: Bot | None = None
_dispatcher_instance: Dispatcher | None = None

BOT_COMMANDS: list[BotCommand] = [
    BotCommand(command="tasks", description="📋 List all accessible tasks"),
    BotCommand(command="users", description="👥 List registered users (@username hints)"),
    BotCommand(command="new", description="➕ Create a task: /new <title>"),
    BotCommand(command="pending", description="⏳ List Pending tasks"),
    BotCommand(command="inprogress", description="🚀 List In Progress tasks"),
    BotCommand(command="completed", description="✅ List Completed tasks"),
    BotCommand(command="view", description="🔍 Open task card: /view <number>"),
    BotCommand(command="done", description="✅ Complete task: /done <number>"),
    BotCommand(command="delete", description="🗑️ Delete task: /delete <number>"),
    BotCommand(command="share", description="🌐 Share task: /share <number> @user"),
    BotCommand(command="stats", description="📊 View workspace statistics"),
    BotCommand(command="help", description="ℹ️ Show all bot commands"),
]


def get_bot() -> Bot:
    """Return a configured aiogram Bot instance."""
    global _bot_instance
    if _bot_instance is None:
        settings = get_settings()
        _bot_instance = Bot(token=settings.telegram_bot_token.strip())
    return _bot_instance


def set_bot(bot: Bot | None) -> None:
    """Override the singleton Bot instance for testing."""
    global _bot_instance
    _bot_instance = bot


@asynccontextmanager
async def bot_session_scope() -> AsyncGenerator[Bot, None]:
    """Yield the test Bot override if set, or a fresh Bot whose session closes cleanly."""
    if _bot_instance is not None:
        yield _bot_instance
        return

    settings = get_settings()
    scoped_bot = Bot(token=settings.telegram_bot_token.strip())
    try:
        yield scoped_bot
    finally:
        await scoped_bot.session.close()


def get_dispatcher() -> Dispatcher:
    """Return the singleton aiogram Dispatcher instance."""
    global _dispatcher_instance
    if _dispatcher_instance is None:
        _dispatcher_instance = Dispatcher()
    return _dispatcher_instance


async def register_telegram_webhook() -> bool:
    """Register the configured webhook URL and command menu with Telegram."""
    settings = get_settings()
    webhook_url = settings.telegram_webhook_url.strip()
    if not webhook_url:
        return False

    async with bot_session_scope() as bot:
        try:
            await bot.set_webhook(
                url=webhook_url,
                secret_token=settings.telegram_webhook_secret,
                drop_pending_updates=False,
            )
            await bot.set_my_commands(commands=BOT_COMMANDS)
            logger.info("Registered Telegram webhook at %s", webhook_url)
            return True
        except Exception as exc:
            logger.warning("Failed to register Telegram webhook: %s", exc)
            return False


async def register_telegram_webhook_with_retry(
    max_attempts: int = 10,
    retry_delay_seconds: float = 15.0,
) -> bool:
    """Retry Telegram webhook registration in the background without blocking startup."""
    settings = get_settings()
    if not settings.telegram_webhook_url.strip():
        return False

    for attempt in range(1, max_attempts + 1):
        if await register_telegram_webhook():
            return True
        if attempt < max_attempts:
            logger.info(
                "Retrying Telegram webhook registration (attempt %d/%d) in %.1fs",
                attempt,
                max_attempts,
                retry_delay_seconds,
            )
            await asyncio.sleep(retry_delay_seconds)
    logger.error(
        "Exhausted %d attempts to register Telegram webhook",
        max_attempts,
    )
    return False

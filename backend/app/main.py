"""FastAPI application entry point, lifespan management, and router registration."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, tasks, telegram_webhook, websocket
from app.bot.loader import (
    BOT_COMMANDS,
    register_telegram_webhook,
    register_telegram_webhook_with_retry,
)
from app.config import get_settings

__all__ = [
    "BOT_COMMANDS",
    "app",
    "create_application",
    "lifespan",
    "register_telegram_webhook",
    "register_telegram_webhook_with_retry",
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle tasks."""
    _ = app
    settings = get_settings()
    Path(settings.voice_temp_dir).mkdir(parents=True, exist_ok=True)
    webhook_task = asyncio.create_task(register_telegram_webhook_with_retry())
    try:
        yield
    finally:
        if not webhook_task.done():
            webhook_task.cancel()
            with suppress(asyncio.CancelledError):
                await webhook_task


def create_application() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Telegram-Bot-Api-Secret-Token",
        ],
    )

    application.include_router(auth.router, prefix="/api/v1")
    application.include_router(auth.users_router, prefix="/api/v1")
    application.include_router(tasks.router, prefix="/api/v1")
    application.include_router(telegram_webhook.router, prefix="/api/v1")
    application.include_router(websocket.router)

    @application.get("/api/v1/health", tags=["health"])
    async def healthcheck() -> dict[str, str]:
        """Return health status of the FastAPI service."""
        return {"status": "healthy", "service": settings.app_name}

    return application


app = create_application()

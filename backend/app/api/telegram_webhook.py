"""FastAPI webhook endpoint for receiving updates from the Telegram Bot API."""

import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import process_telegram_update
from app.bot.loader import register_telegram_webhook
from app.config import get_settings
from app.database import get_db

router = APIRouter(prefix="/telegram", tags=["telegram"])


def _verify_webhook_secret(secret_header: str | None) -> None:
    """Validate the X-Telegram-Bot-Api-Secret-Token header using constant-time comparison."""
    settings = get_settings()
    if secret_header is None or not hmac.compare_digest(
        secret_header,
        settings.telegram_webhook_secret,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-Telegram-Bot-Api-Secret-Token header",
        )


@router.post("/webhook")
async def telegram_webhook(
    payload: dict[str, Any],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Verify the Telegram secret token and dispatch the incoming update payload."""
    _verify_webhook_secret(x_telegram_bot_api_secret_token)
    result = await process_telegram_update(db, payload)
    return {"ok": True, **result}


@router.post("/register-webhook")
async def trigger_telegram_webhook_registration(
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Verify the secret header and manually trigger Telegram webhook registration."""
    _verify_webhook_secret(x_telegram_bot_api_secret_token)
    settings = get_settings()
    registered = await register_telegram_webhook()
    return {
        "ok": registered,
        "webhook_url": settings.telegram_webhook_url,
    }

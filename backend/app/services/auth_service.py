"""Authentication service for Telegram Login Widget, WebApp initData, and JWT tokens."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl

import jwt
from jwt import PyJWTError

from app.config import get_settings
from app.schemas.auth import TelegramAuthPayload


def compute_telegram_hash(data: dict[str, Any], bot_token: str) -> str:
    """Compute the expected HMAC-SHA256 signature for Telegram Login Widget data."""
    clean_token = bot_token.strip()
    filtered_items = [
        f"{key}={value}"
        for key, value in sorted(data.items())
        if key != "hash" and value is not None
    ]
    data_check_string = "\n".join(filtered_items)
    secret_key = hashlib.sha256(clean_token.encode("utf-8")).digest()
    return hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_telegram_auth(
    payload: TelegramAuthPayload,
    bot_token: str | None = None,
    max_age_seconds: int | None = None,
) -> bool:
    """Verify the authenticity and freshness of a Telegram Login Widget payload."""
    settings = get_settings()
    effective_token = (bot_token if bot_token is not None else settings.telegram_bot_token).strip()
    effective_max_age = (
        max_age_seconds if max_age_seconds is not None else settings.auth_max_age_seconds
    )

    now = int(time.time())
    if now - payload.auth_date > effective_max_age:
        return False
    future_tolerance = max(300, effective_max_age) if effective_max_age > 86400 else 300
    if payload.auth_date > now + future_tolerance:
        return False

    raw_data = payload.model_dump(exclude={"hash"}, exclude_none=True)
    expected_hash = compute_telegram_hash(raw_data, effective_token)
    return hmac.compare_digest(expected_hash.lower(), payload.hash.lower())


def compute_telegram_webapp_hash(
    pairs: list[tuple[str, str]],
    bot_token: str,
) -> str:
    """Compute the expected HMAC-SHA256 signature for Telegram WebApp initData."""
    clean_token = bot_token.strip()
    filtered_items = [
        f"{key}={value}" for key, value in sorted(pairs, key=lambda item: item[0]) if key != "hash"
    ]
    data_check_string = "\n".join(filtered_items)
    secret_key = hmac.new(
        b"WebAppData",
        clean_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_telegram_webapp_init_data(
    init_data: str,
    bot_token: str | None = None,
    max_age_seconds: int | None = None,
) -> dict[str, Any] | None:
    """Verify Telegram Mini App initData and return the decoded user dictionary if valid."""
    settings = get_settings()
    effective_token = (bot_token if bot_token is not None else settings.telegram_bot_token).strip()
    effective_max_age = (
        max_age_seconds if max_age_seconds is not None else settings.auth_max_age_seconds
    )

    pairs = parse_qsl(init_data.strip(), keep_blank_values=True)
    params = dict(pairs)
    received_hash = params.get("hash")
    raw_user = params.get("user")
    raw_auth_date = params.get("auth_date")
    if not received_hash or not raw_user or not raw_auth_date:
        return None

    try:
        auth_date = int(raw_auth_date)
    except ValueError:
        return None

    now = int(time.time())
    if now - auth_date > effective_max_age:
        return None
    future_tolerance = max(300, effective_max_age) if effective_max_age > 86400 else 300
    if auth_date > now + future_tolerance:
        return None

    expected_hash = compute_telegram_webapp_hash(pairs, effective_token)
    if not hmac.compare_digest(expected_hash.lower(), received_hash.lower()):
        return None

    try:
        user_data = json.loads(raw_user)
    except json.JSONDecodeError:
        return None

    if not isinstance(user_data, dict) or "id" not in user_data:
        return None
    return user_data


def create_access_token(
    user_id: uuid.UUID,
    telegram_id: int,
    username: str | None = None,
    expires_minutes: int | None = None,
) -> str:
    """Issue a signed JWT access token for an authenticated user."""
    settings = get_settings()
    lifetime = expires_minutes if expires_minutes is not None else settings.jwt_expire_minutes
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=lifetime)

    claims: dict[str, Any] = {
        "sub": str(user_id),
        "telegram_id": telegram_id,
        "username": username.lower() if username else None,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    encoded: str = jwt.encode(
        claims,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return encoded


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a signed JWT access token."""
    settings = get_settings()
    try:
        decoded: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except PyJWTError as exc:
        raise ValueError("Invalid or expired authentication token") from exc

    if "sub" not in decoded:
        raise ValueError("Token missing subject claim")
    return decoded

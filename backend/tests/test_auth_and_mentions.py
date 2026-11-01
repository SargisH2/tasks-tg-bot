"""Tests for Telegram Login Widget HMAC verification, JWT auth, and @username mentions."""

import time
import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.models.task import TaskVisibility
from app.models.user import User
from app.schemas.auth import TelegramAuthPayload
from app.services.auth_service import (
    compute_telegram_hash,
    create_access_token,
    decode_access_token,
    verify_telegram_auth,
)
from app.services.mention_service import (
    extract_mentions,
    is_valid_telegram_username,
    normalize_mention_list,
    normalize_username,
)
from app.services.pubsub_service import should_deliver_event_to_user


def test_telegram_hmac_hash_generation_and_verification() -> None:
    """Verify valid Telegram Login Widget data passes HMAC-SHA256 verification."""
    settings = get_settings()
    now = int(time.time())
    raw_data: dict[str, Any] = {
        "id": 555666,
        "first_name": "Satoshi",
        "last_name": "Nakamoto",
        "username": "Satoshi_Dev",
        "auth_date": now,
    }
    valid_hash = compute_telegram_hash(raw_data, settings.telegram_bot_token)
    payload = TelegramAuthPayload(**raw_data, hash=valid_hash)

    assert verify_telegram_auth(payload, settings.telegram_bot_token) is True


def test_telegram_auth_rejects_expired_or_tampered_payload() -> None:
    """Verify expired auth_date or tampered signature is rejected."""
    settings = get_settings()
    expired_time = int(time.time()) - 100000
    raw_data: dict[str, Any] = {
        "id": 555666,
        "first_name": "Satoshi",
        "auth_date": expired_time,
    }
    expired_hash = compute_telegram_hash(raw_data, settings.telegram_bot_token)
    expired_payload = TelegramAuthPayload(**raw_data, hash=expired_hash)
    assert (
        verify_telegram_auth(
            expired_payload,
            settings.telegram_bot_token,
            max_age_seconds=86400,
        )
        is False
    )

    future_data: dict[str, Any] = {
        "id": 555666,
        "first_name": "Satoshi",
        "auth_date": int(time.time()) + 3600,
    }
    future_hash = compute_telegram_hash(future_data, settings.telegram_bot_token)
    future_payload = TelegramAuthPayload(**future_data, hash=future_hash)
    assert (
        verify_telegram_auth(
            future_payload,
            settings.telegram_bot_token,
            max_age_seconds=86400,
        )
        is False
    )

    tampered_payload = TelegramAuthPayload(
        id=555666,
        first_name="Hacker",
        auth_date=int(time.time()),
        hash=expired_hash,
    )
    assert verify_telegram_auth(tampered_payload, settings.telegram_bot_token) is False


def test_jwt_create_and_decode_roundtrip() -> None:
    """Verify JWT access token creation, decoding, and expiration validation."""
    uid = uuid.uuid4()
    token = create_access_token(user_id=uid, telegram_id=777888, username="Alice_Test")
    decoded = decode_access_token(token)
    assert decoded["sub"] == str(uid)
    assert decoded["telegram_id"] == 777888
    assert decoded["username"] == "alice_test"

    with pytest.raises(ValueError, match="Invalid or expired"):
        decode_access_token("invalid.jwt.token")

    expired_token = create_access_token(
        user_id=uid,
        telegram_id=777888,
        username="Alice_Test",
        expires_minutes=-10,
    )
    with pytest.raises(ValueError, match="Invalid or expired"):
        decode_access_token(expired_token)


def test_mention_extraction_and_normalization() -> None:
    """Verify @username regex extraction, normalization, and validation rules."""
    text = (
        "Deploy backend with @Alice_Dev and @Bob_12345! "
        "Ignore @ab (too short) and email test@example_domain.com "
        "and duplicate @ALICE_DEV."
    )
    mentions = extract_mentions(text)
    assert mentions == ["alice_dev", "bob_12345"]
    assert extract_mentions(None) == []
    assert extract_mentions("") == []

    assert normalize_username("  @Charlie_99 ") == "charlie_99"
    assert normalize_username("   ") is None
    assert normalize_username(None) is None

    assert is_valid_telegram_username("valid_user_1") is True
    assert is_valid_telegram_username("abc") is False
    assert is_valid_telegram_username("invalid-dash") is False

    normalized = normalize_mention_list(["@User_One", "user_one", "bad", "@Second_User_22"])
    assert normalized == ["user_one", "second_user_22"]


def test_pubsub_event_scoping() -> None:
    """Verify WebSocket event scoping for PRIVATE and PUBLIC tasks."""
    owner_id = uuid.uuid4()
    collab_id = uuid.uuid4()
    stranger_id = uuid.uuid4()

    private_payload = {
        "event": "task.updated",
        "owner_id": str(owner_id),
        "visibility": TaskVisibility.PRIVATE.value,
        "allowed_usernames": ["collab_bob"],
    }
    assert should_deliver_event_to_user(private_payload, owner_id, "owner_alice") is True
    assert should_deliver_event_to_user(private_payload, collab_id, "collab_bob") is False
    assert should_deliver_event_to_user(private_payload, stranger_id, "stranger_eve") is False

    public_payload = {
        "event": "task.updated",
        "owner_id": str(owner_id),
        "visibility": TaskVisibility.PUBLIC.value,
        "allowed_usernames": ["collab_bob"],
    }
    assert should_deliver_event_to_user(public_payload, owner_id, "owner_alice") is True
    assert should_deliver_event_to_user(public_payload, collab_id, "collab_bob") is True
    assert should_deliver_event_to_user(public_payload, stranger_id, "stranger_eve") is False
    assert should_deliver_event_to_user(public_payload, collab_id, None) is False


async def test_auth_endpoints(
    async_client: AsyncClient,
    owner_user: User,
    owner_headers: dict[str, str],
) -> None:
    """Verify /auth/telegram, /auth/dev, and /auth/me endpoints."""
    settings = get_settings()
    now = int(time.time())
    tg_data = {
        "id": 999111,
        "first_name": "Diana",
        "last_name": "Prince",
        "username": "Wonder_Diana",
        "auth_date": now,
    }
    tg_hash = compute_telegram_hash(tg_data, settings.telegram_bot_token)

    resp = await async_client.post(
        "/api/v1/auth/telegram",
        json={**tg_data, "hash": tg_hash},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["username"] == "wonder_diana"
    assert "access_token" in body

    bad_resp = await async_client.post(
        "/api/v1/auth/telegram",
        json={**tg_data, "hash": "0" * 64},
    )
    assert bad_resp.status_code == 401

    dev_resp = await async_client.post(
        "/api/v1/auth/dev",
        json={
            "telegram_id": 888222,
            "username": "Dev_Tester",
            "first_name": "Dev",
            "last_name": "User",
        },
    )
    assert dev_resp.status_code == 200
    assert dev_resp.json()["user"]["username"] == "dev_tester"

    me_resp = await async_client.get("/api/v1/auth/me", headers=owner_headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["id"] == str(owner_user.id)

    users_resp = await async_client.get(
        "/api/v1/users?q=owner",
        headers=owner_headers,
    )
    assert users_resp.status_code == 200
    assert any(u["username"] == "owner_alice" for u in users_resp.json())

    unauth_resp = await async_client.get("/api/v1/auth/me")
    assert unauth_resp.status_code == 401

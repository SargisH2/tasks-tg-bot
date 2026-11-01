"""Tests for the Telegram Webhook endpoint, text/voice ingestion, and inline callbacks."""

import uuid
from typing import Any
from unittest.mock import MagicMock

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.bot.loader import register_telegram_webhook_with_retry
from app.config import get_settings
from app.models.task import (
    Task,
    TaskCheckpoint,
    TaskProcessingState,
    TaskSource,
    TaskStatus,
    TaskVisibility,
)


def _webhook_headers() -> dict[str, str]:
    """Return valid Telegram webhook secret token headers."""
    settings = get_settings()
    return {"X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret}


async def test_webhook_rejects_missing_or_invalid_secret_token(
    async_client: AsyncClient,
) -> None:
    """Verify webhook requests without a valid secret token return 401."""
    resp_missing = await async_client.post(
        "/api/v1/telegram/webhook",
        json={"update_id": 1},
    )
    assert resp_missing.status_code == 401

    resp_wrong = await async_client.post(
        "/api/v1/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        json={"update_id": 1},
    )
    assert resp_wrong.status_code == 401


async def test_telegram_text_message_creates_task_with_mentions_and_keyboard(
    async_client: AsyncClient,
    db_session: AsyncSession,
    mock_telegram_bot: MagicMock,
    published_events: list[dict[str, Any]],
) -> None:
    """Verify text message creates a PRIVATE task, saves message_id, and extracts @mentions."""
    update_payload = {
        "update_id": 1001,
        "message": {
            "message_id": 4242,
            "from": {
                "id": 700100,
                "first_name": "TelegramAlice",
                "username": "Tg_Alice",
            },
            "chat": {"id": 700100, "type": "private"},
            "text": "Review payment gateway PR with @collab_bob and @qa_charlie",
        },
    }

    resp = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json=update_payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "task_created"
    assert set(data["mentions"]) == {"collab_bob", "qa_charlie"}

    task_uuid = uuid.UUID(data["task_id"])
    stmt = select(Task).options(selectinload(Task.mentions)).where(Task.id == task_uuid)
    res = await db_session.execute(stmt)
    task = res.scalar_one()

    assert task.source == TaskSource.TELEGRAM_TEXT
    assert task.visibility == TaskVisibility.PRIVATE
    assert task.status == TaskStatus.PENDING
    assert task.processing_state == TaskProcessingState.IDLE
    assert task.telegram_message_id == 4242
    assert task.telegram_chat_id == 700100
    assert {m.telegram_username for m in task.mentions} == {"collab_bob", "qa_charlie"}

    mock_telegram_bot.send_message.assert_awaited()
    call_kwargs = mock_telegram_bot.send_message.await_args.kwargs
    assert call_kwargs["reply_to_message_id"] == 4242
    keyboard = call_kwargs["reply_markup"]
    button_texts = [btn.text for row in keyboard.inline_keyboard for btn in row]
    assert "✨ AI Improve Task" in button_texts
    assert "☑️ Generate Checkpoints" in button_texts
    assert "🌐 Make Public" in button_texts
    assert any(ev["event"] == "task.created" for ev in published_events)

    share_payload = {
        "update_id": 1002,
        "message": {
            "message_id": 4243,
            "from": {
                "id": 700100,
                "first_name": "TelegramAlice",
                "username": "Tg_Alice",
            },
            "chat": {"id": 700100, "type": "private"},
            "reply_to_message": {"message_id": 4242},
            "text": "/share @devops_dave",
        },
    }
    share_resp = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json=share_payload,
    )
    assert share_resp.status_code == 200
    assert share_resp.json()["status"] == "mentions_updated"
    assert "devops_dave" in share_resp.json()["mentions"]


async def test_telegram_voice_message_queues_whisper_transcription(
    async_client: AsyncClient,
    db_session: AsyncSession,
    celery_delay_mocks: dict[str, MagicMock],
) -> None:
    """Verify voice message creates a TRANSCRIBING task and queues transcribe_voice_task."""
    voice_update = {
        "update_id": 2001,
        "message": {
            "message_id": 5151,
            "from": {
                "id": 700200,
                "first_name": "VoiceUser",
                "username": "voice_creator",
            },
            "chat": {"id": 700200, "type": "private"},
            "voice": {
                "file_id": "AwACAgIAAxkBAAIBZ2VoiceFileId123",
                "duration": 8,
            },
        },
    }

    resp = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json=voice_update,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "voice_queued"

    task_uuid = uuid.UUID(body["task_id"])
    stmt = select(Task).where(Task.id == task_uuid)
    res = await db_session.execute(stmt)
    task = res.scalar_one()

    assert task.source == TaskSource.TELEGRAM_VOICE
    assert task.processing_state == TaskProcessingState.TRANSCRIBING
    assert task.telegram_message_id == 5151
    assert task.telegram_voice_file_id == "AwACAgIAAxkBAAIBZ2VoiceFileId123"
    celery_delay_mocks["transcribe"].assert_called_once()


async def test_telegram_inline_callbacks_and_commands(
    async_client: AsyncClient,
    db_session: AsyncSession,
    celery_delay_mocks: dict[str, MagicMock],
) -> None:
    """Verify inline keyboard callbacks for AI triggers, visibility, status, and checkpoints."""
    start_resp = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3000,
            "message": {
                "message_id": 10,
                "from": {"id": 800100, "first_name": "CallbackOwner", "username": "cb_owner"},
                "chat": {"id": 800100, "type": "private"},
                "text": "/start",
            },
        },
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "command_handled"

    create_resp = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3001,
            "message": {
                "message_id": 6001,
                "from": {"id": 800100, "first_name": "CallbackOwner", "username": "cb_owner"},
                "chat": {"id": 800100, "type": "private"},
                "text": "Implement OAuth callback flow @cb_collab",
            },
        },
    )
    task_id = create_resp.json()["task_id"]
    task_uuid = uuid.UUID(task_id)

    ckpt = TaskCheckpoint(
        task_id=task_uuid,
        title="Verify state parameter",
        is_completed=False,
        position=0,
    )
    db_session.add(ckpt)
    await db_session.commit()
    await db_session.refresh(ckpt)

    improve_cb = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3002,
            "callback_query": {
                "id": "cb_1",
                "from": {"id": 800100, "first_name": "CallbackOwner", "username": "cb_owner"},
                "message": {"message_id": 6002, "chat": {"id": 800100}},
                "data": f"ai_improve:{task_id}",
            },
        },
    )
    assert improve_cb.json()["status"] == "ai_improve_queued"
    celery_delay_mocks["improve"].assert_called_once_with(task_id)

    ckpts_cb = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3003,
            "callback_query": {
                "id": "cb_2",
                "from": {"id": 800100, "first_name": "CallbackOwner", "username": "cb_owner"},
                "message": {"message_id": 6002, "chat": {"id": 800100}},
                "data": f"ai_checkpoints:{task_id}",
            },
        },
    )
    assert ckpts_cb.json()["status"] == "ai_checkpoints_queued"
    celery_delay_mocks["checkpoints"].assert_called_once_with(task_id)

    vis_cb = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3004,
            "callback_query": {
                "id": "cb_3",
                "from": {"id": 800100, "first_name": "CallbackOwner", "username": "cb_owner"},
                "message": {"message_id": 6002, "chat": {"id": 800100}},
                "data": f"vis_toggle:{task_id}",
            },
        },
    )
    assert vis_cb.json()["status"] == "visibility_toggled"
    assert vis_cb.json()["visibility"] == "PUBLIC"

    non_owner_vis = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3005,
            "callback_query": {
                "id": "cb_4",
                "from": {"id": 800999, "first_name": "Collab", "username": "cb_collab"},
                "message": {"message_id": 6002, "chat": {"id": 800100}},
                "data": f"vis_toggle:{task_id}",
            },
        },
    )
    assert non_owner_vis.json()["status"] == "forbidden"

    status_cb = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3006,
            "callback_query": {
                "id": "cb_5",
                "from": {"id": 800999, "first_name": "Collab", "username": "cb_collab"},
                "message": {"message_id": 6002, "chat": {"id": 800100}},
                "data": f"status:{task_id}:IN_PROGRESS",
            },
        },
    )
    assert status_cb.json()["status"] == "status_updated"
    assert status_cb.json()["new_status"] == "IN_PROGRESS"

    ckpt_toggle_cb = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3007,
            "callback_query": {
                "id": "cb_6",
                "from": {"id": 800999, "first_name": "Collab", "username": "cb_collab"},
                "message": {"message_id": 6002, "chat": {"id": 800100}},
                "data": f"ckpt:{ckpt.id}",
            },
        },
    )
    assert ckpt_toggle_cb.json()["status"] == "checkpoint_toggled"

    retry_cb = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3008,
            "callback_query": {
                "id": "cb_7",
                "from": {"id": 800100, "first_name": "CallbackOwner", "username": "cb_owner"},
                "message": {"message_id": 6002, "chat": {"id": 800100}},
                "data": f"retry_voice:{task_id}",
            },
        },
    )
    assert retry_cb.json()["status"] == "voice_retry_queued"

    tasks_cmd = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3009,
            "message": {
                "message_id": 6010,
                "from": {"id": 800100, "first_name": "CallbackOwner", "username": "cb_owner"},
                "chat": {"id": 800100, "type": "private"},
                "text": "/tasks",
            },
        },
    )
    assert tasks_cmd.json()["status"] == "command_handled"
    assert tasks_cmd.json()["count"] >= 1

    new_cmd = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3010,
            "message": {
                "message_id": 6011,
                "from": {"id": 800100, "first_name": "CallbackOwner", "username": "cb_owner"},
                "chat": {"id": 800100, "type": "private"},
                "text": "/new Ship CLI release @cb_collab",
            },
        },
    )
    assert new_cmd.json()["status"] == "task_created"
    second_task_id = new_cmd.json()["task_id"]

    view_cmd = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3011,
            "message": {
                "message_id": 6012,
                "from": {"id": 800100, "first_name": "CallbackOwner", "username": "cb_owner"},
                "chat": {"id": 800100, "type": "private"},
                "text": "/view 1",
            },
        },
    )
    assert view_cmd.json()["status"] == "command_handled"

    done_cmd = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3012,
            "message": {
                "message_id": 6013,
                "from": {"id": 800100, "first_name": "CallbackOwner", "username": "cb_owner"},
                "chat": {"id": 800100, "type": "private"},
                "text": "/done 1",
            },
        },
    )
    assert done_cmd.json()["status"] == "status_updated"

    stats_cmd = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3013,
            "message": {
                "message_id": 6014,
                "from": {"id": 800100, "first_name": "CallbackOwner", "username": "cb_owner"},
                "chat": {"id": 800100, "type": "private"},
                "text": "/stats",
            },
        },
    )
    assert stats_cmd.json()["status"] == "command_handled"

    users_cmd = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 30131,
            "message": {
                "message_id": 60141,
                "from": {"id": 800100, "first_name": "CallbackOwner", "username": "cb_owner"},
                "chat": {"id": 800100, "type": "private"},
                "text": "/users",
            },
        },
    )
    assert users_cmd.json()["status"] == "command_handled"

    voice_cmd_reply = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 30132,
            "message": {
                "message_id": 60142,
                "from": {"id": 800100, "first_name": "CallbackOwner", "username": "cb_owner"},
                "chat": {"id": 800100, "type": "private"},
                "reply_to_message": {"message_id": 6001},
                "voice": {
                    "file_id": "AwACAgIAAxkBAAIBZ2VoiceCmdFileId999",
                    "duration": 5,
                },
            },
        },
    )
    assert voice_cmd_reply.json()["status"] == "voice_command_queued"
    celery_delay_mocks["voice_cmd"].assert_called_once()

    list_cb = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3014,
            "callback_query": {
                "id": "cb_8",
                "from": {"id": 800100, "first_name": "CallbackOwner", "username": "cb_owner"},
                "message": {"message_id": 6002, "chat": {"id": 800100}},
                "data": "cmd_list:ALL",
            },
        },
    )
    assert list_cb.json()["status"] == "list_displayed"

    del_cb = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3015,
            "callback_query": {
                "id": "cb_9",
                "from": {"id": 800100, "first_name": "CallbackOwner", "username": "cb_owner"},
                "message": {"message_id": 6002, "chat": {"id": 800100}},
                "data": f"del_task:{second_task_id}",
            },
        },
    )
    assert del_cb.json()["status"] == "task_deleted"

    del_cmd = await async_client.post(
        "/api/v1/telegram/webhook",
        headers=_webhook_headers(),
        json={
            "update_id": 3016,
            "message": {
                "message_id": 6015,
                "from": {"id": 800100, "first_name": "CallbackOwner", "username": "cb_owner"},
                "chat": {"id": 800100, "type": "private"},
                "text": "/delete 1",
            },
        },
    )
    assert del_cmd.json()["status"] == "task_deleted"


async def test_manual_and_retry_webhook_registration(
    async_client: AsyncClient,
    mock_telegram_bot: MagicMock,
) -> None:
    """Verify POST /api/v1/telegram/register-webhook and background retry logic."""
    unauth_resp = await async_client.post("/api/v1/telegram/register-webhook")
    assert unauth_resp.status_code == 401

    settings = get_settings()
    original_url = settings.telegram_webhook_url
    try:
        settings.telegram_webhook_url = "https://tasks-bot.space/api/v1/telegram/webhook"
        reg_resp = await async_client.post(
            "/api/v1/telegram/register-webhook",
            headers=_webhook_headers(),
        )
        assert reg_resp.status_code == 200
        assert reg_resp.json()["ok"] is True
        assert reg_resp.json()["webhook_url"] == "https://tasks-bot.space/api/v1/telegram/webhook"

        retry_ok = await register_telegram_webhook_with_retry(
            max_attempts=2,
            retry_delay_seconds=0.01,
        )
        assert retry_ok is True

        mock_telegram_bot.set_webhook.side_effect = RuntimeError("TLS not ready yet")
        retry_fail = await register_telegram_webhook_with_retry(
            max_attempts=2,
            retry_delay_seconds=0.01,
        )
        assert retry_fail is False
    finally:
        mock_telegram_bot.set_webhook.side_effect = None
        settings.telegram_webhook_url = original_url

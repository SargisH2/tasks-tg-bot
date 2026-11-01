"""Unit tests for OpenAI Whisper/Structured Outputs services and Celery worker tasks."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.task import (
    Task,
    TaskMention,
    TaskPriority,
    TaskProcessingState,
    TaskSource,
    TaskStatus,
    TaskVisibility,
)
from app.models.user import User
from app.schemas.task import (
    GeneratedCheckpointsResult,
    ImprovedTaskResult,
    VoiceCommandResult,
)
from app.services.openai_service import (
    generate_task_checkpoints,
    improve_task_content,
    transcribe_audio_file,
)
from app.worker.tasks import (
    generate_checkpoints_task,
    improve_task_task,
    notify_telegram_on_web_change,
    run_generate_checkpoints,
    run_improve_task,
    run_notify_telegram_on_web_change,
    run_transcribe_voice,
    run_voice_command,
    transcribe_voice_task,
    voice_command_task,
)


async def test_openai_service_whisper_and_structured_outputs(tmp_path: Path) -> None:
    """Verify openai_service Whisper retry logic and Structured Outputs parsing."""
    audio_file = tmp_path / "sample.ogg"
    audio_file.write_bytes(b"OggS-fake-audio-bytes")

    mock_client = MagicMock()
    transcript_resp = MagicMock()
    transcript_resp.text = "Schedule deployment review with @collab_bob"
    mock_client.audio.transcriptions.create = AsyncMock(
        side_effect=[RuntimeError("Transient network glitch"), transcript_resp]
    )

    improved_parsed = ImprovedTaskResult(
        improved_title="Conduct Production Deployment Review",
        improved_description="Coordinate deployment checklist with @collab_bob.",
    )
    improve_choice = MagicMock()
    improve_choice.message.parsed = improved_parsed
    improve_completion = MagicMock(choices=[improve_choice])

    ckpts_parsed = GeneratedCheckpointsResult(
        checkpoints=[
            "Run database migrations",
            "Verify health check endpoints",
            "Monitor error rates",
        ]
    )
    ckpt_choice = MagicMock()
    ckpt_choice.message.parsed = ckpts_parsed
    ckpt_completion = MagicMock(choices=[ckpt_choice])

    mock_client.beta.chat.completions.parse = AsyncMock(
        side_effect=[improve_completion, ckpt_completion]
    )

    with patch("app.services.openai_service.get_openai_client", return_value=mock_client):
        transcript = await transcribe_audio_file(
            str(audio_file),
            max_retries=2,
            base_delay=0.001,
        )
        assert transcript == "Schedule deployment review with @collab_bob"

        improved = await improve_task_content(
            raw_input=transcript,
            current_title=transcript,
            current_description=None,
        )
        assert improved.improved_title == "Conduct Production Deployment Review"

        checkpoints = await generate_task_checkpoints(
            title=improved.improved_title,
            description=improved.improved_description,
            raw_input=transcript,
        )
        assert len(checkpoints.checkpoints) == 3

    with pytest.raises(FileNotFoundError):
        await transcribe_audio_file(str(tmp_path / "missing.ogg"))


async def test_worker_transcribe_voice_success_and_cleanup(
    db_session: AsyncSession,
    owner_user: User,
    published_events: list[dict[str, Any]],
    mock_telegram_bot: MagicMock,
    tmp_path: Path,
) -> None:
    """Verify transcribe_voice_task updates transcript, extracts mentions, and deletes .ogg."""
    _ = mock_telegram_bot
    voice_task = Task(
        owner_id=owner_user.id,
        visibility=TaskVisibility.PRIVATE,
        source=TaskSource.TELEGRAM_VOICE,
        status=TaskStatus.PENDING,
        processing_state=TaskProcessingState.TRANSCRIBING,
        title="🎙️ Transcribing voice note...",
        raw_input="🎙️ Transcribing voice note...",
        telegram_chat_id=owner_user.telegram_id,
        telegram_message_id=777,
        telegram_voice_file_id="voice_file_777",
    )
    db_session.add(voice_task)
    await db_session.commit()
    await db_session.refresh(voice_task)

    ogg_file = tmp_path / f"{voice_task.id}.ogg"
    ogg_file.write_bytes(b"OggS-test-voice")
    assert ogg_file.exists()

    with patch(
        "app.worker.tasks.transcribe_audio_file",
        new=AsyncMock(return_value="Prepare Q4 roadmap presentation with @collab_bob"),
    ):
        result = await run_transcribe_voice(
            task_id=str(voice_task.id),
            file_path=str(ogg_file),
            bot_reply_message_id=888,
        )

    assert result["status"] == "completed"
    assert not ogg_file.exists()

    stmt = (
        select(Task)
        .options(selectinload(Task.mentions))
        .where(Task.id == voice_task.id)
        .execution_options(populate_existing=True)
    )
    refreshed = (await db_session.execute(stmt)).scalar_one()
    assert refreshed.processing_state == TaskProcessingState.IDLE
    assert refreshed.raw_input == "Prepare Q4 roadmap presentation with @collab_bob"
    assert refreshed.telegram_message_id == 777
    assert refreshed.telegram_chat_id == owner_user.telegram_id
    assert [m.telegram_username for m in refreshed.mentions] == ["collab_bob"]
    assert any(ev["event"] == "task.updated" for ev in published_events)


async def test_worker_transcribe_voice_failure_renders_retry_button_and_cleans_up(
    db_session: AsyncSession,
    owner_user: User,
    mock_telegram_bot: MagicMock,
    tmp_path: Path,
) -> None:
    """Verify failed Whisper transcription sets FAILED state, cleans .ogg, and shows retry."""
    voice_task = Task(
        owner_id=owner_user.id,
        visibility=TaskVisibility.PRIVATE,
        source=TaskSource.TELEGRAM_VOICE,
        status=TaskStatus.PENDING,
        processing_state=TaskProcessingState.TRANSCRIBING,
        title="🎙️ Transcribing voice note...",
        raw_input="🎙️ Transcribing voice note...",
        telegram_chat_id=owner_user.telegram_id,
        telegram_message_id=778,
        telegram_voice_file_id="voice_file_778",
    )
    db_session.add(voice_task)
    await db_session.commit()
    await db_session.refresh(voice_task)

    ogg_file = tmp_path / f"{voice_task.id}.ogg"
    ogg_file.write_bytes(b"OggS-corrupted")

    with patch(
        "app.worker.tasks.transcribe_audio_file",
        new=AsyncMock(side_effect=RuntimeError("Whisper quota exceeded")),
    ):
        result = await run_transcribe_voice(
            task_id=str(voice_task.id),
            file_path=str(ogg_file),
            bot_reply_message_id=889,
        )

    assert result["status"] == "failed"
    assert not ogg_file.exists()

    stmt = select(Task).where(Task.id == voice_task.id).execution_options(populate_existing=True)
    refreshed = (await db_session.execute(stmt)).scalar_one()
    assert refreshed.processing_state == TaskProcessingState.FAILED
    assert refreshed.error_message is not None
    assert "Whisper quota exceeded" in refreshed.error_message

    mock_telegram_bot.edit_message_text.assert_awaited()
    edit_kwargs = mock_telegram_bot.edit_message_text.await_args.kwargs
    kb_buttons = [btn.text for row in edit_kwargs["reply_markup"].inline_keyboard for btn in row]
    assert "🔄 Retry Transcription" in kb_buttons


async def test_worker_improve_task_and_generate_checkpoints_and_notifications(
    db_session: AsyncSession,
    owner_user: User,
    mentioned_user: User,
    mock_telegram_bot: MagicMock,
) -> None:
    """Verify improve_task_task, generate_checkpoints_task, and notify_telegram_on_web_change."""
    _ = mentioned_user
    task = Task(
        owner_id=owner_user.id,
        visibility=TaskVisibility.PUBLIC,
        source=TaskSource.TELEGRAM_TEXT,
        status=TaskStatus.PENDING,
        processing_state=TaskProcessingState.IMPROVING,
        title="fix login bug @collab_bob",
        raw_input="fix login bug @collab_bob",
        telegram_chat_id=owner_user.telegram_id,
        telegram_message_id=901,
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskMention(task_id=task.id, telegram_username="collab_bob"))
    await db_session.commit()
    await db_session.refresh(task)

    mock_improved = ImprovedTaskResult(
        improved_title="Resolve Authentication Session Timeout Bug",
        improved_description="Investigate and fix JWT refresh issue with @collab_bob.",
        priority=TaskPriority.URGENT,
        tags=["auth", "security"],
    )
    with patch(
        "app.worker.tasks.improve_task_content",
        new=AsyncMock(return_value=mock_improved),
    ):
        imp_res = await run_improve_task(str(task.id))
    assert imp_res["status"] == "completed"
    assert imp_res["priority"] == "URGENT"
    assert "auth" in imp_res["tags"]

    mock_ckpts = GeneratedCheckpointsResult(
        checkpoints=[
            "Reproduce session timeout locally",
            "Update token expiration handler",
            "Add regression test coverage",
        ]
    )
    with patch(
        "app.worker.tasks.generate_task_checkpoints",
        new=AsyncMock(return_value=mock_ckpts),
    ):
        ckpt_res = await run_generate_checkpoints(str(task.id))
    assert ckpt_res["status"] == "completed"
    assert ckpt_res["checkpoints_count"] == 3

    mock_voice_cmd = VoiceCommandResult(
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.HIGH,
        completed_checkpoint_indices=[0],
        new_checkpoints=["Verify fix in staging"],
        tags=["verified"],
        summary="Moved to IN_PROGRESS and completed first checkpoint",
    )
    cmd_audio = Path("/tmp") / f"cmd_test_{task.id}.ogg"
    cmd_audio.write_bytes(b"OggS-voice-cmd")
    with (
        patch(
            "app.worker.tasks.transcribe_audio_file",
            new=AsyncMock(return_value="Move to in progress and mark first checkpoint done"),
        ),
        patch(
            "app.worker.tasks.interpret_voice_command",
            new=AsyncMock(return_value=mock_voice_cmd),
        ),
    ):
        vcmd_res = await run_voice_command(str(task.id), str(cmd_audio), 950)
    assert vcmd_res["status"] == "completed"
    assert not cmd_audio.exists()

    stmt = (
        select(Task)
        .options(selectinload(Task.checkpoints))
        .where(Task.id == task.id)
        .execution_options(populate_existing=True)
    )
    updated_task = (await db_session.execute(stmt)).scalar_one()
    assert updated_task.is_ai_improved is True
    assert updated_task.title == "Resolve Authentication Session Timeout Bug"
    assert updated_task.status == TaskStatus.IN_PROGRESS
    assert updated_task.priority == TaskPriority.HIGH
    assert "verified" in updated_task.tags
    assert len(updated_task.checkpoints) == 4
    assert updated_task.processing_state == TaskProcessingState.IDLE

    mock_telegram_bot.send_message.reset_mock()
    notify_res = await run_notify_telegram_on_web_change(
        task_id=str(task.id),
        actor_username="owner_alice",
        summary="status moved to IN_PROGRESS",
    )
    assert notify_res["status"] == "completed"
    assert notify_res["sent_count"] == 2

    with (
        patch(
            "app.worker.tasks.run_transcribe_voice",
            new=AsyncMock(return_value={"status": "completed"}),
        ),
        patch(
            "app.worker.tasks.run_improve_task",
            new=AsyncMock(return_value={"status": "completed"}),
        ),
        patch(
            "app.worker.tasks.run_generate_checkpoints",
            new=AsyncMock(return_value={"status": "completed"}),
        ),
        patch(
            "app.worker.tasks.run_voice_command",
            new=AsyncMock(return_value={"status": "completed"}),
        ),
        patch(
            "app.worker.tasks.run_notify_telegram_on_web_change",
            new=AsyncMock(return_value={"status": "completed"}),
        ),
    ):
        assert transcribe_voice_task(str(task.id), "/tmp/voice/x.ogg", 1)["status"] == "completed"
        assert improve_task_task(str(task.id))["status"] == "completed"
        assert generate_checkpoints_task(str(task.id))["status"] == "completed"
        assert voice_command_task(str(task.id), "/tmp/voice/c.ogg", 1)["status"] == "completed"
        assert (
            notify_telegram_on_web_change(str(task.id), "owner_alice", "edited")["status"]
            == "completed"
        )

"""Celery background tasks for voice transcription, AI workflows, and Telegram sync."""

import asyncio
import logging
import uuid
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_worker_session
from app.models.task import Task, TaskCheckpoint, TaskProcessingState
from app.services.mention_service import extract_mentions, sync_task_mentions
from app.services.openai_service import (
    generate_task_checkpoints,
    improve_task_content,
    interpret_voice_command,
    transcribe_audio_file,
)
from app.services.pubsub_service import publish_task_event
from app.services.telegram_notify_service import (
    send_web_change_notifications,
    sync_task_message_on_telegram,
)
from app.worker.celery_app import typed_task

logger = logging.getLogger(__name__)


def _execute_coroutine[T](coro: Coroutine[Any, Any, T]) -> T:
    """Execute an async coroutine safely from either sync or async contexts."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


async def _load_task_with_relations(session: Any, task_uuid: uuid.UUID) -> Task | None:
    """Load a Task by ID with owner, mentions, and checkpoints eagerly loaded."""
    stmt = (
        select(Task)
        .options(
            selectinload(Task.owner),
            selectinload(Task.mentions),
            selectinload(Task.checkpoints),
        )
        .where(Task.id == task_uuid)
    )
    result = await session.execute(stmt)
    task: Task | None = result.scalar_one_or_none()
    return task


async def run_transcribe_voice(
    task_id: str,
    file_path: str,
    bot_reply_message_id: int | None = None,
) -> dict[str, Any]:
    """Execute the async voice transcription workflow and update PostgreSQL and Telegram."""
    task_uuid = uuid.UUID(task_id)
    audio_path = Path(file_path)
    try:
        async with get_worker_session() as session:
            task = await _load_task_with_relations(session, task_uuid)
            if task is None:
                return {"status": "not_found", "task_id": task_id}

            try:
                transcript = await transcribe_audio_file(file_path)
                task.raw_input = transcript
                task.title = transcript[:255]
                task.processing_state = TaskProcessingState.IDLE
                task.error_message = None

                mentions = extract_mentions(transcript)
                if mentions:
                    await sync_task_mentions(session, task, mentions, append=True)

                await session.commit()
                await session.refresh(task)
                await publish_task_event("task.updated", task)
                await sync_task_message_on_telegram(task, bot_reply_message_id)
                return {
                    "status": "completed",
                    "task_id": task_id,
                    "transcript": transcript,
                }
            except Exception as exc:
                logger.warning("Voice transcription failed for task %s: %s", task_id, exc)
                task.processing_state = TaskProcessingState.FAILED
                task.error_message = str(exc)
                await session.commit()
                await session.refresh(task)
                await publish_task_event("task.updated", task)
                await sync_task_message_on_telegram(task, bot_reply_message_id)
                return {
                    "status": "failed",
                    "task_id": task_id,
                    "error": str(exc),
                }
    finally:
        try:
            audio_path.unlink(missing_ok=True)
        except OSError as cleanup_err:
            logger.warning("Failed to delete temporary audio file %s: %s", file_path, cleanup_err)


async def run_improve_task(task_id: str) -> dict[str, Any]:
    """Execute the async AI task improvement workflow without modifying checkpoints."""
    task_uuid = uuid.UUID(task_id)
    async with get_worker_session() as session:
        task = await _load_task_with_relations(session, task_uuid)
        if task is None:
            return {"status": "not_found", "task_id": task_id}

        try:
            improved = await improve_task_content(
                raw_input=task.raw_input,
                current_title=task.title,
                current_description=task.description,
            )
            task.title = improved.improved_title[:255]
            task.description = improved.improved_description
            task.priority = improved.priority
            if improved.tags:
                merged_tags = [*task.tags, *improved.tags]
                task.tags = merged_tags
            task.is_ai_improved = True
            task.processing_state = TaskProcessingState.IDLE
            task.error_message = None

            extracted = extract_mentions(
                f"{improved.improved_title} {improved.improved_description}"
            )
            if extracted:
                await sync_task_mentions(session, task, extracted, append=True)

            await session.commit()
            await session.refresh(task)
            await publish_task_event("task.updated", task)
            await sync_task_message_on_telegram(task)
            return {
                "status": "completed",
                "task_id": task_id,
                "improved_title": task.title,
                "priority": task.priority.value,
                "tags": task.tags,
            }
        except Exception as exc:
            logger.warning("AI task improvement failed for task %s: %s", task_id, exc)
            task.processing_state = TaskProcessingState.FAILED
            task.error_message = str(exc)
            await session.commit()
            await session.refresh(task)
            await publish_task_event("task.updated", task)
            await sync_task_message_on_telegram(task)
            return {
                "status": "failed",
                "task_id": task_id,
                "error": str(exc),
            }


async def run_generate_checkpoints(task_id: str) -> dict[str, Any]:
    """Execute the async AI checkpoint decomposition workflow without altering title."""
    task_uuid = uuid.UUID(task_id)
    async with get_worker_session() as session:
        task = await _load_task_with_relations(session, task_uuid)
        if task is None:
            return {"status": "not_found", "task_id": task_id}

        try:
            generated = await generate_task_checkpoints(
                title=task.title,
                description=task.description,
                raw_input=task.raw_input,
            )
            for existing_ckpt in list(task.checkpoints):
                task.checkpoints.remove(existing_ckpt)
                await session.delete(existing_ckpt)
            await session.flush()

            for index, ckpt_title in enumerate(generated.checkpoints):
                cleaned_title = ckpt_title.strip()[:255]
                if not cleaned_title:
                    continue
                new_ckpt = TaskCheckpoint(
                    task_id=task.id,
                    title=cleaned_title,
                    is_completed=False,
                    position=index,
                )
                task.checkpoints.append(new_ckpt)
                session.add(new_ckpt)

            task.processing_state = TaskProcessingState.IDLE
            task.error_message = None
            await session.commit()
            await session.refresh(task)
            await publish_task_event("task.updated", task)
            await sync_task_message_on_telegram(task)
            return {
                "status": "completed",
                "task_id": task_id,
                "checkpoints_count": len(task.checkpoints),
            }
        except Exception as exc:
            logger.warning("AI checkpoint generation failed for task %s: %s", task_id, exc)
            task.processing_state = TaskProcessingState.FAILED
            task.error_message = str(exc)
            await session.commit()
            await session.refresh(task)
            await publish_task_event("task.updated", task)
            await sync_task_message_on_telegram(task)
            return {
                "status": "failed",
                "task_id": task_id,
                "error": str(exc),
            }


async def run_voice_command(
    task_id: str,
    file_path: str,
    bot_reply_message_id: int | None = None,
) -> dict[str, Any]:
    """Transcribe a voice command reply and apply AI-interpreted updates to an existing task."""
    task_uuid = uuid.UUID(task_id)
    audio_path = Path(file_path)
    try:
        async with get_worker_session() as session:
            task = await _load_task_with_relations(session, task_uuid)
            if task is None:
                return {"status": "not_found", "task_id": task_id}

            try:
                transcript = await transcribe_audio_file(file_path)
                sorted_ckpts = sorted(task.checkpoints, key=lambda c: c.position)
                existing_titles = [c.title for c in sorted_ckpts]

                cmd_result = await interpret_voice_command(
                    voice_transcript=transcript,
                    task_title=task.title,
                    task_description=task.description,
                    task_status=task.status.value,
                    task_priority=task.priority.value,
                    existing_checkpoints=existing_titles,
                )

                if cmd_result.status is not None:
                    task.status = cmd_result.status
                if cmd_result.priority is not None:
                    task.priority = cmd_result.priority
                if cmd_result.visibility is not None:
                    task.visibility = cmd_result.visibility
                if cmd_result.updated_title and cmd_result.updated_title.strip():
                    task.title = cmd_result.updated_title.strip()[:255]
                if cmd_result.updated_description and cmd_result.updated_description.strip():
                    task.description = cmd_result.updated_description.strip()
                if cmd_result.tags:
                    task.tags = [*task.tags, *cmd_result.tags]

                for idx in cmd_result.completed_checkpoint_indices:
                    if 0 <= idx < len(sorted_ckpts):
                        sorted_ckpts[idx].is_completed = True

                base_pos = len(task.checkpoints)
                for offset, new_title in enumerate(cmd_result.new_checkpoints):
                    cleaned = new_title.strip()[:255]
                    if not cleaned:
                        continue
                    ckpt = TaskCheckpoint(
                        task_id=task.id,
                        title=cleaned,
                        is_completed=False,
                        position=base_pos + offset,
                    )
                    task.checkpoints.append(ckpt)
                    session.add(ckpt)

                mentions = extract_mentions(transcript)
                if mentions:
                    await sync_task_mentions(session, task, mentions, append=True)

                task.processing_state = TaskProcessingState.IDLE
                task.error_message = None
                await session.commit()
                await session.refresh(task)
                await publish_task_event("task.updated", task)
                await sync_task_message_on_telegram(task, bot_reply_message_id)
                return {
                    "status": "completed",
                    "task_id": task_id,
                    "transcript": transcript,
                    "summary": cmd_result.summary,
                }
            except Exception as exc:
                logger.warning("Voice command failed for task %s: %s", task_id, exc)
                task.processing_state = TaskProcessingState.FAILED
                task.error_message = str(exc)
                await session.commit()
                await session.refresh(task)
                await publish_task_event("task.updated", task)
                await sync_task_message_on_telegram(task, bot_reply_message_id)
                return {
                    "status": "failed",
                    "task_id": task_id,
                    "error": str(exc),
                }
    finally:
        try:
            audio_path.unlink(missing_ok=True)
        except OSError as cleanup_err:
            logger.warning("Failed to delete temporary audio file %s: %s", file_path, cleanup_err)


async def run_notify_telegram_on_web_change(
    task_id: str,
    actor_username: str | None,
    summary: str,
) -> dict[str, Any]:
    """Execute bi-directional Telegram notification delivery after a web dashboard edit."""
    task_uuid = uuid.UUID(task_id)
    async with get_worker_session() as session:
        task = await _load_task_with_relations(session, task_uuid)
        if task is None:
            return {"status": "not_found", "task_id": task_id, "sent_count": 0}

        sent_count = await send_web_change_notifications(
            session=session,
            task=task,
            actor_username=actor_username,
            summary=summary,
        )
        return {
            "status": "completed",
            "task_id": task_id,
            "sent_count": sent_count,
        }


@typed_task(name="transcribe_voice_task")
def transcribe_voice_task(
    task_id: str,
    file_path: str,
    bot_reply_message_id: int | None = None,
) -> dict[str, Any]:
    """Celery task wrapper for automatic voice-to-text transcription via OpenAI Whisper."""
    return _execute_coroutine(
        run_transcribe_voice(
            task_id=task_id,
            file_path=file_path,
            bot_reply_message_id=bot_reply_message_id,
        )
    )


@typed_task(name="improve_task_task")
def improve_task_task(task_id: str) -> dict[str, Any]:
    """Celery task wrapper for on-demand AI task title and description refinement."""
    return _execute_coroutine(run_improve_task(task_id=task_id))


@typed_task(name="generate_checkpoints_task")
def generate_checkpoints_task(task_id: str) -> dict[str, Any]:
    """Celery task wrapper for on-demand AI task checkpoint decomposition."""
    return _execute_coroutine(run_generate_checkpoints(task_id=task_id))


@typed_task(name="voice_command_task")
def voice_command_task(
    task_id: str,
    file_path: str,
    bot_reply_message_id: int | None = None,
) -> dict[str, Any]:
    """Celery task wrapper for hands-free voice command updates on an existing task."""
    return _execute_coroutine(
        run_voice_command(
            task_id=task_id,
            file_path=file_path,
            bot_reply_message_id=bot_reply_message_id,
        )
    )


@typed_task(name="notify_telegram_on_web_change")
def notify_telegram_on_web_change(
    task_id: str,
    actor_username: str | None,
    summary: str,
) -> dict[str, Any]:
    """Celery task wrapper for bi-directional Telegram notifications on web changes."""
    return _execute_coroutine(
        run_notify_telegram_on_web_change(
            task_id=task_id,
            actor_username=actor_username,
            summary=summary,
        )
    )

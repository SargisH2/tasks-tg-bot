"""OpenAI service for Whisper audio transcription and Structured Outputs AI workflows."""

import asyncio
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from app.config import get_settings
from app.schemas.task import (
    GeneratedCheckpointsResult,
    ImprovedTaskResult,
    VoiceCommandResult,
)


def get_openai_client() -> AsyncOpenAI:
    """Instantiate an AsyncOpenAI client using application settings."""
    settings = get_settings()
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def transcribe_audio_file(
    file_path: str,
    max_retries: int = 3,
    base_delay: float = 0.05,
) -> str:
    """Transcribe a voice audio file using OpenAI Whisper with exponential backoff."""
    settings = get_settings()
    client = get_openai_client()
    path_obj = Path(file_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Audio file not found at {file_path}")

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            with path_obj.open("rb") as audio_file:
                response: Any = await client.audio.transcriptions.create(
                    model=settings.openai_whisper_model,
                    file=audio_file,
                )
            text_value = getattr(response, "text", None)
            if isinstance(text_value, str) and text_value.strip():
                return text_value.strip()
            if isinstance(response, str) and response.strip():
                return response.strip()
            raise ValueError("Whisper API returned an empty transcript")
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                await asyncio.sleep(base_delay * (2 ** (attempt - 1)))

    raise RuntimeError(f"Whisper transcription failed after {max_retries} attempts: {last_error}")


async def improve_task_content(
    raw_input: str,
    current_title: str,
    current_description: str | None = None,
) -> ImprovedTaskResult:
    """Refine a task title, description, priority, and tags using OpenAI Structured Outputs."""
    settings = get_settings()
    client = get_openai_client()

    system_prompt = (
        "You are an expert technical project manager. "
        "Rewrite the provided task into a concise, actionable title (max 120 chars), "
        "a well-structured clear description, an appropriate priority "
        "(LOW, MEDIUM, HIGH, or URGENT), and 1 to 4 short lowercase topic tags. "
        "Preserve all @username mentions and technical context."
    )
    user_prompt = (
        f"Raw Input: {raw_input}\n"
        f"Current Title: {current_title}\n"
        f"Current Description: {current_description or 'None'}"
    )

    completion: Any = await client.beta.chat.completions.parse(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format=ImprovedTaskResult,
    )

    message = completion.choices[0].message
    parsed = getattr(message, "parsed", None)
    if isinstance(parsed, ImprovedTaskResult):
        return parsed
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return ImprovedTaskResult.model_validate_json(content)
    raise RuntimeError("OpenAI Structured Outputs did not return a valid ImprovedTaskResult")


async def generate_task_checkpoints(
    title: str,
    description: str | None,
    raw_input: str,
) -> GeneratedCheckpointsResult:
    """Decompose a task into 3 to 6 actionable checkpoints using OpenAI Structured Outputs."""
    settings = get_settings()
    client = get_openai_client()

    system_prompt = (
        "You are an expert technical lead. "
        "Break the provided task down into 3 to 6 concrete, sequential, "
        "actionable implementation checkpoints."
    )
    user_prompt = (
        f"Task Title: {title}\n"
        f"Task Description: {description or 'None'}\n"
        f"Original Input: {raw_input}"
    )

    completion: Any = await client.beta.chat.completions.parse(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format=GeneratedCheckpointsResult,
    )

    message = completion.choices[0].message
    parsed = getattr(message, "parsed", None)
    if isinstance(parsed, GeneratedCheckpointsResult):
        cleaned = [item.strip() for item in parsed.checkpoints if item.strip()]
        return GeneratedCheckpointsResult(checkpoints=cleaned[:6] or ["Complete task"])
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        validated = GeneratedCheckpointsResult.model_validate_json(content)
        cleaned = [item.strip() for item in validated.checkpoints if item.strip()]
        return GeneratedCheckpointsResult(checkpoints=cleaned[:6] or ["Complete task"])
    raise RuntimeError(
        "OpenAI Structured Outputs did not return a valid GeneratedCheckpointsResult"
    )


async def interpret_voice_command(
    voice_transcript: str,
    task_title: str,
    task_description: str | None,
    task_status: str,
    task_priority: str,
    existing_checkpoints: list[str],
) -> VoiceCommandResult:
    """Interpret a spoken voice command reply against an existing task."""
    settings = get_settings()
    client = get_openai_client()

    numbered_ckpts = "\n".join(f"{idx}: {title}" for idx, title in enumerate(existing_checkpoints))
    system_prompt = (
        "You are an AI voice assistant for a task manager. "
        "The user replied to an existing task with a spoken voice command. "
        "Determine which fields to update (status: PENDING, IN_PROGRESS, COMPLETED; "
        "priority: LOW, MEDIUM, HIGH, URGENT; visibility: PRIVATE, PUBLIC; "
        "updated_title; updated_description; 0-based indices of existing checkpoints "
        "to mark completed in completed_checkpoint_indices; any new_checkpoints to add; "
        "and a short summary of the changes applied)."
    )
    user_prompt = (
        f"Current Task Title: {task_title}\n"
        f"Current Description: {task_description or 'None'}\n"
        f"Current Status: {task_status}\n"
        f"Current Priority: {task_priority}\n"
        f"Existing Checkpoints (0-based index):\n{numbered_ckpts or 'None'}\n\n"
        f"Spoken Voice Command: {voice_transcript}"
    )

    completion: Any = await client.beta.chat.completions.parse(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format=VoiceCommandResult,
    )

    message = completion.choices[0].message
    parsed = getattr(message, "parsed", None)
    if isinstance(parsed, VoiceCommandResult):
        return parsed
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return VoiceCommandResult.model_validate_json(content)
    return VoiceCommandResult(summary=f"Processed voice command: {voice_transcript[:80]}")

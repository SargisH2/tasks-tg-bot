"""Pydantic schemas for tasks, mentions, checkpoints, and AI structured outputs."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import (
    TaskPriority,
    TaskProcessingState,
    TaskSource,
    TaskStatus,
    TaskVisibility,
)
from app.schemas.user import UserRead


class CheckpointCreate(BaseModel):
    """Payload to create a new task checkpoint."""

    title: str = Field(..., min_length=1, max_length=255)
    position: int | None = None


class CheckpointUpdate(BaseModel):
    """Payload to update an existing task checkpoint."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    is_completed: bool | None = None
    position: int | None = None


class CheckpointRead(BaseModel):
    """Serialized task checkpoint representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    title: str
    is_completed: bool
    position: int
    created_at: datetime


class TaskMentionRead(BaseModel):
    """Serialized task mention representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    telegram_username: str
    created_at: datetime


class TaskCreate(BaseModel):
    """Payload to create a new task from the web dashboard."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    visibility: TaskVisibility = TaskVisibility.PRIVATE
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    tags: list[str] = Field(default_factory=list)
    mentions: list[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    """Payload to update task properties, Kanban column status, priority, tags, or mentions."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    tags: list[str] | None = None
    position: int | None = None
    visibility: TaskVisibility | None = None
    mentions: list[str] | None = None


class TaskMentionsUpdate(BaseModel):
    """Payload to replace the mentioned Telegram usernames on a task."""

    mentions: list[str] = Field(default_factory=list)


class TaskRead(BaseModel):
    """Full serialized representation of a task with owner, mentions, checkpoints, and tags."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    owner: UserRead | None = None
    visibility: TaskVisibility
    source: TaskSource
    status: TaskStatus
    priority: TaskPriority = TaskPriority.MEDIUM
    tags: list[str] = Field(default_factory=list)
    processing_state: TaskProcessingState
    title: str
    description: str | None = None
    raw_input: str
    is_ai_improved: bool
    position: int
    telegram_chat_id: int | None = None
    telegram_message_id: int | None = None
    telegram_voice_file_id: int | str | None = None
    error_message: str | None = None
    mentions: list[TaskMentionRead] = Field(default_factory=list)
    checkpoints: list[CheckpointRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ImprovedTaskResult(BaseModel):
    """Structured output schema returned by OpenAI for AI task improvement."""

    improved_title: str = Field(..., min_length=1, max_length=255)
    improved_description: str = Field(..., min_length=1)
    priority: TaskPriority = TaskPriority.MEDIUM
    tags: list[str] = Field(default_factory=list)


class GeneratedCheckpointsResult(BaseModel):
    """Structured output schema returned by OpenAI for AI checkpoint generation."""

    checkpoints: list[str] = Field(..., min_length=1)


class VoiceCommandResult(BaseModel):
    """Structured output schema returned by OpenAI when interpreting a voice reply command."""

    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    visibility: TaskVisibility | None = None
    updated_title: str | None = None
    updated_description: str | None = None
    completed_checkpoint_indices: list[int] = Field(default_factory=list)
    new_checkpoints: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    summary: str = Field(default="Applied voice command updates")

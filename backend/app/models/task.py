"""SQLAlchemy ORM models for tasks, mentions, and checkpoints."""

from __future__ import annotations

import enum
import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


def _utc_now() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(UTC)


class TaskVisibility(enum.StrEnum):
    """Access visibility level for a task."""

    PRIVATE = "PRIVATE"
    PUBLIC = "PUBLIC"


class TaskSource(enum.StrEnum):
    """Origin channel from which a task was created."""

    TELEGRAM_TEXT = "TELEGRAM_TEXT"
    TELEGRAM_VOICE = "TELEGRAM_VOICE"
    WEB = "WEB"


class TaskStatus(enum.StrEnum):
    """Kanban workflow column status for a task."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class TaskPriority(enum.StrEnum):
    """Urgency priority level for a task."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class TaskProcessingState(enum.StrEnum):
    """Background AI processing state for a task."""

    IDLE = "IDLE"
    TRANSCRIBING = "TRANSCRIBING"
    IMPROVING = "IMPROVING"
    GENERATING_CHECKPOINTS = "GENERATING_CHECKPOINTS"
    FAILED = "FAILED"


class Task(Base):
    """Represents a user task with omni-channel metadata, priority, tags, and AI state."""

    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    visibility: Mapped[TaskVisibility] = mapped_column(
        Enum(TaskVisibility, name="task_visibility"),
        default=TaskVisibility.PRIVATE,
        index=True,
        nullable=False,
    )
    source: Mapped[TaskSource] = mapped_column(
        Enum(TaskSource, name="task_source"),
        nullable=False,
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"),
        default=TaskStatus.PENDING,
        index=True,
        nullable=False,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority, name="task_priority", native_enum=False, length=32),
        default=TaskPriority.MEDIUM,
        server_default="MEDIUM",
        nullable=False,
    )
    processing_state: Mapped[TaskProcessingState] = mapped_column(
        Enum(TaskProcessingState, name="task_processing_state"),
        default=TaskProcessingState.IDLE,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    raw_input: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    tags_json: Mapped[str] = mapped_column(
        "tags",
        Text,
        default="[]",
        server_default="[]",
        nullable=False,
    )
    is_ai_improved: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    position: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    telegram_chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        index=True,
        nullable=True,
    )
    telegram_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        index=True,
        nullable=True,
    )
    telegram_voice_file_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=_utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=_utc_now,
        default=_utc_now,
        nullable=False,
    )

    owner: Mapped[User] = relationship(
        "User",
        back_populates="tasks",
        lazy="selectin",
    )
    mentions: Mapped[list[TaskMention]] = relationship(
        "TaskMention",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TaskMention.created_at",
    )
    checkpoints: Mapped[list[TaskCheckpoint]] = relationship(
        "TaskCheckpoint",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TaskCheckpoint.position",
    )

    @property
    def tags(self) -> list[str]:
        """Deserialize and return the list of tags attached to the task."""
        if not self.tags_json:
            return []
        try:
            loaded = json.loads(self.tags_json)
            if isinstance(loaded, list):
                return [str(item).strip().lower() for item in loaded if str(item).strip()]
        except (ValueError, TypeError):
            pass
        return []

    @tags.setter
    def tags(self, value: list[str] | None) -> None:
        """Normalize and serialize a list of tag strings into tags_json."""
        if not value:
            self.tags_json = "[]"
            return
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in value:
            norm = str(raw).strip().lstrip("\u0023").lower()[:32]
            if norm and norm not in seen:
                seen.add(norm)
                cleaned.append(norm)
        self.tags_json = json.dumps(cleaned[:8])


class TaskMention(Base):
    """Represents a mentioned Telegram username granted access when a task is PUBLIC."""

    __tablename__ = "task_mentions"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "telegram_username",
            name="uq_task_mention_username",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    telegram_username: Mapped[str] = mapped_column(
        String(128),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=_utc_now,
        nullable=False,
    )

    task: Mapped[Task] = relationship(
        "Task",
        back_populates="mentions",
    )


class TaskCheckpoint(Base):
    """Represents an actionable step or sub-item belonging to a task."""

    __tablename__ = "task_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    is_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    position: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=_utc_now,
        nullable=False,
    )

    task: Mapped[Task] = relationship(
        "Task",
        back_populates="checkpoints",
    )

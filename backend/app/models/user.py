"""SQLAlchemy ORM model for Telegram-authenticated users."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.task import Task


def _utc_now() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(UTC)


class User(Base):
    """Represents an authenticated Telegram user in the system."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )
    username: Mapped[str | None] = mapped_column(
        String(128),
        index=True,
        nullable=True,
    )
    first_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    last_name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    photo_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=_utc_now,
        nullable=False,
    )

    tasks: Mapped[list[Task]] = relationship(
        "Task",
        back_populates="owner",
        cascade="all, delete-orphan",
    )

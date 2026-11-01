"""Pydantic schemas for user serialization."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserRead(BaseModel):
    """Schema representing a user returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    telegram_id: int
    username: str | None = None
    first_name: str
    last_name: str | None = None
    photo_url: str | None = None
    created_at: datetime

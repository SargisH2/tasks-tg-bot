"""Pydantic schemas for Telegram Login Widget, Telegram Mini App, and JWT authentication."""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserRead


class TelegramAuthPayload(BaseModel):
    """Payload received from the Telegram Login Widget callback."""

    model_config = ConfigDict(extra="allow")

    id: int
    first_name: str = Field(..., min_length=1, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)
    username: str | None = Field(default=None, max_length=128)
    photo_url: str | None = Field(default=None, max_length=512)
    auth_date: int
    hash: str


class TelegramWebAppAuthPayload(BaseModel):
    """Payload containing the raw signed initData string from Telegram WebApp."""

    init_data: str = Field(..., min_length=1)


class DevAuthPayload(BaseModel):
    """Development login payload for testing with arbitrary Telegram usernames."""

    telegram_id: int = 100001
    username: str = Field(..., min_length=5, max_length=32)
    first_name: str = Field(default="Developer", min_length=1, max_length=128)
    last_name: str | None = Field(default="User", max_length=128)


class TokenResponse(BaseModel):
    """JWT authentication response containing bearer token and user profile."""

    access_token: str
    token_type: str = "bearer"
    user: UserRead

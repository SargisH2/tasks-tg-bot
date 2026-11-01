"""Authentication and user directory REST API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    DevAuthPayload,
    TelegramAuthPayload,
    TelegramWebAppAuthPayload,
    TokenResponse,
)
from app.schemas.user import UserRead
from app.services.auth_service import (
    create_access_token,
    verify_telegram_auth,
    verify_telegram_webapp_init_data,
)
from app.services.mention_service import fetch_registered_users, normalize_username

router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


async def _upsert_telegram_user_and_issue_token(
    db: AsyncSession,
    telegram_id: int,
    first_name: str,
    last_name: str | None,
    username: str | None,
    photo_url: str | None,
) -> TokenResponse:
    """Create or update a User record from verified Telegram data and return a JWT response."""
    normalized_uname = normalize_username(username)
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=normalized_uname,
            first_name=first_name,
            last_name=last_name,
            photo_url=photo_url,
        )
        db.add(user)
    else:
        user.username = normalized_uname
        user.first_name = first_name
        user.last_name = last_name
        user.photo_url = photo_url

    await db.commit()
    await db.refresh(user)

    token = create_access_token(
        user_id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
    )
    return TokenResponse(
        access_token=token,
        user=UserRead.model_validate(user),
    )


@router.post("/telegram", response_model=TokenResponse)
async def login_with_telegram(
    payload: TelegramAuthPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Authenticate a user via Telegram Login Widget HMAC-SHA256 verification."""
    if not verify_telegram_auth(payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram authentication signature or expired auth_date",
        )

    return await _upsert_telegram_user_and_issue_token(
        db=db,
        telegram_id=payload.id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        username=payload.username,
        photo_url=payload.photo_url,
    )


@router.post("/telegram-webapp", response_model=TokenResponse)
async def login_with_telegram_webapp(
    payload: TelegramWebAppAuthPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Authenticate a user automatically via Telegram Mini App signed initData."""
    user_data = verify_telegram_webapp_init_data(payload.init_data)
    if user_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram WebApp initData signature or expired auth_date",
        )

    return await _upsert_telegram_user_and_issue_token(
        db=db,
        telegram_id=int(user_data["id"]),
        first_name=str(user_data.get("first_name") or "Telegram User"),
        last_name=str(user_data["last_name"]) if user_data.get("last_name") else None,
        username=str(user_data["username"]) if user_data.get("username") else None,
        photo_url=str(user_data["photo_url"]) if user_data.get("photo_url") else None,
    )


@router.post("/dev", response_model=TokenResponse)
async def dev_login(
    payload: DevAuthPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Authenticate a local development user when ALLOW_DEV_AUTH is enabled."""
    settings = get_settings()
    if not settings.allow_dev_auth:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Development authentication is disabled",
        )

    normalized_uname = normalize_username(payload.username)
    if not normalized_uname:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid Telegram username",
        )

    stmt = select(User).where(User.telegram_id == payload.telegram_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        stmt_by_name = select(User).where(User.username == normalized_uname)
        res_name = await db.execute(stmt_by_name)
        user = res_name.scalar_one_or_none()

    if user is None:
        user = User(
            telegram_id=payload.telegram_id,
            username=normalized_uname,
            first_name=payload.first_name,
            last_name=payload.last_name,
        )
        db.add(user)
    else:
        user.username = normalized_uname
        user.first_name = payload.first_name
        user.last_name = payload.last_name

    await db.commit()
    await db.refresh(user)

    token = create_access_token(
        user_id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
    )
    return TokenResponse(
        access_token=token,
        user=UserRead.model_validate(user),
    )


@router.get("/me", response_model=UserRead)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserRead:
    """Return the profile of the currently authenticated user."""
    return UserRead.model_validate(current_user)


@users_router.get("", response_model=list[UserRead])
@router.get("/users", response_model=list[UserRead])
async def list_registered_users(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str | None = Query(default=None),
) -> list[UserRead]:
    """Return all registered users in the system for directory and @username hints."""
    _ = current_user
    users = await fetch_registered_users(db, q)
    return [UserRead.model_validate(u) for u in users]

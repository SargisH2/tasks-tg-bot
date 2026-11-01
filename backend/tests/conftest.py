"""Pytest fixtures for isolated async SQLite database, HTTP client, users, and mocks."""

from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.bot.loader import set_bot
from app.database import Base, get_db, set_worker_session_factory
from app.main import app
from app.models.user import User
from app.services.auth_service import create_access_token
from app.services.pubsub_service import set_event_publisher
from app.worker import tasks as worker_tasks


@pytest.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create an isolated in-memory SQLite async engine with all schema tables."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def session_factory(
    db_engine: AsyncEngine,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Provide an async_sessionmaker bound to the test engine and wire worker sessions."""
    factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    set_worker_session_factory(factory)
    try:
        yield factory
    finally:
        set_worker_session_factory(None)


@pytest.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for test setup and assertions."""
    async with session_factory() as session:
        yield session


@pytest.fixture
def published_events() -> Generator[list[dict[str, Any]], None, None]:
    """Capture all Redis Pub/Sub events published during a test."""
    events: list[dict[str, Any]] = []

    async def _capture(payload: dict[str, Any]) -> None:
        """Append published event dictionary to the in-memory test list."""
        events.append(payload)

    set_event_publisher(_capture)
    try:
        yield events
    finally:
        set_event_publisher(None)


@pytest.fixture
def mock_telegram_bot() -> Generator[MagicMock, None, None]:
    """Provide a mocked aiogram Bot instance for Telegram API calls."""
    bot_mock = MagicMock()
    sent_message = MagicMock()
    sent_message.message_id = 999
    bot_mock.send_message = AsyncMock(return_value=sent_message)
    bot_mock.edit_message_text = AsyncMock(return_value=sent_message)
    bot_mock.answer_callback_query = AsyncMock(return_value=True)
    bot_mock.set_webhook = AsyncMock(return_value=True)
    bot_mock.set_my_commands = AsyncMock(return_value=True)
    file_obj = MagicMock()
    file_obj.file_path = "voice/file_123.ogg"
    bot_mock.get_file = AsyncMock(return_value=file_obj)
    bot_mock.download_file = AsyncMock(return_value=None)
    set_bot(bot_mock)
    try:
        yield bot_mock
    finally:
        set_bot(None)


@pytest.fixture
def celery_delay_mocks() -> Generator[dict[str, MagicMock], None, None]:
    """Mock Celery .delay() methods on all four background worker tasks."""
    with (
        patch.object(worker_tasks.transcribe_voice_task, "delay") as mock_transcribe,
        patch.object(worker_tasks.improve_task_task, "delay") as mock_improve,
        patch.object(worker_tasks.generate_checkpoints_task, "delay") as mock_checkpoints,
        patch.object(worker_tasks.voice_command_task, "delay") as mock_voice_cmd,
        patch.object(worker_tasks.notify_telegram_on_web_change, "delay") as mock_notify,
    ):
        yield {
            "transcribe": mock_transcribe,
            "improve": mock_improve,
            "checkpoints": mock_checkpoints,
            "voice_cmd": mock_voice_cmd,
            "notify": mock_notify,
        }


@pytest.fixture
async def async_client(
    session_factory: async_sessionmaker[AsyncSession],
    published_events: list[dict[str, Any]],
    mock_telegram_bot: MagicMock,
    celery_delay_mocks: dict[str, MagicMock],
) -> AsyncGenerator[AsyncClient, None]:
    """Provide an httpx.AsyncClient wired to the FastAPI app with test overrides."""
    _ = (published_events, mock_telegram_bot, celery_delay_mocks)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        """Yield a database session from the test session factory."""
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def owner_user(db_session: AsyncSession) -> User:
    """Create and return the primary task owner user."""
    user = User(
        telegram_id=100001,
        username="owner_alice",
        first_name="Alice",
        last_name="Owner",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def mentioned_user(db_session: AsyncSession) -> User:
    """Create and return the mentioned collaborator user."""
    user = User(
        telegram_id=200002,
        username="collab_bob",
        first_name="Bob",
        last_name="Collaborator",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def stranger_user(db_session: AsyncSession) -> User:
    """Create and return an unmentioned third-party user."""
    user = User(
        telegram_id=300003,
        username="stranger_eve",
        first_name="Eve",
        last_name="Stranger",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def owner_headers(owner_user: User) -> dict[str, str]:
    """Return HTTP Authorization headers for owner_user."""
    token = create_access_token(
        user_id=owner_user.id,
        telegram_id=owner_user.telegram_id,
        username=owner_user.username,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mentioned_headers(mentioned_user: User) -> dict[str, str]:
    """Return HTTP Authorization headers for mentioned_user."""
    token = create_access_token(
        user_id=mentioned_user.id,
        telegram_id=mentioned_user.telegram_id,
        username=mentioned_user.username,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def stranger_headers(stranger_user: User) -> dict[str, str]:
    """Return HTTP Authorization headers for stranger_user."""
    token = create_access_token(
        user_id=stranger_user.id,
        telegram_id=stranger_user.telegram_id,
        username=stranger_user.username,
    )
    return {"Authorization": f"Bearer {token}"}

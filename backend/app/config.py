"""Application configuration settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed environment configuration for the task management backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Omni-Channel Task Manager"
    environment: str = "development"
    domain_name: str = "tasks-bot.space"
    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/taskmanager"
    sync_database_url: str = "postgresql+psycopg2://postgres:postgres@postgres:5432/taskmanager"
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"
    jwt_secret_key: str = "super-secret-jwt-key-for-omni-channel-task-manager-2026"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080
    telegram_bot_token: str = "123456789:AAE_test_bot_token_placeholder"
    telegram_bot_username: str = "ai_task_mgr_bot"
    telegram_webhook_url: str = ""
    telegram_webhook_secret: str = "telegram-webhook-secret-token"
    openai_api_key: str = "sk-test-placeholder"
    openai_whisper_model: str = "whisper-1"
    openai_chat_model: str = "gpt-4o-mini"
    voice_temp_dir: str = "/tmp/voice"
    allow_dev_auth: bool = True
    auth_max_age_seconds: int = 86400
    cors_origins: list[str] = [
        "https://tasks-bot.space",
        "https://www.tasks-bot.space",
        "http://tasks-bot.space",
        "http://www.tasks-bot.space",
        "http://51.83.187.8",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:80",
        "http://localhost",
    ]


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of application settings."""
    return Settings()

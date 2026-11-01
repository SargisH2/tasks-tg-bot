"""Celery application configuration and typed task decorator registration."""

from collections.abc import Callable
from typing import Any, ParamSpec, Protocol, TypeVar, cast

from celery import Celery

from app.config import get_settings

P = ParamSpec("P")
R = TypeVar("R", covariant=True)


class CeleryTaskCallable(Protocol[P, R]):
    """Protocol describing a registered Celery task with synchronous and delay execution."""

    name: str

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Execute the task function directly."""

    def delay(self, *args: Any, **kwargs: Any) -> Any:
        """Dispatch the task asynchronously to the Celery broker."""

    def apply_async(self, *args: Any, **kwargs: Any) -> Any:
        """Dispatch the task with extended Celery options."""


settings = get_settings()

celery_app = Celery(
    "task_manager_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)


def typed_task(name: str) -> Callable[[Callable[P, R]], CeleryTaskCallable[P, R]]:
    """Create a strictly typed Celery task decorator."""
    raw_decorator: Any = celery_app.task(name=name)
    return cast(Callable[[Callable[P, R]], CeleryTaskCallable[P, R]], raw_decorator)

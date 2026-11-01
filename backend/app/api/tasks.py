"""REST API endpoints for tasks, Kanban drag-and-drop, checkpoints, and AI triggers."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.task import (
    Task,
    TaskCheckpoint,
    TaskMention,
    TaskProcessingState,
    TaskSource,
    TaskVisibility,
)
from app.models.user import User
from app.schemas.task import (
    CheckpointCreate,
    CheckpointUpdate,
    TaskCreate,
    TaskMentionsUpdate,
    TaskRead,
    TaskUpdate,
)
from app.services.mention_service import (
    can_user_access_task,
    extract_mentions,
    is_task_owner,
    normalize_username,
    sync_task_mentions,
)
from app.services.pubsub_service import publish_task_deleted_event, publish_task_event
from app.worker.tasks import (
    generate_checkpoints_task,
    improve_task_task,
    notify_telegram_on_web_change,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def _fetch_task_or_404(db: AsyncSession, task_id: uuid.UUID) -> Task:
    """Fetch a task with all relationships or raise 404 Not Found."""
    stmt = (
        select(Task)
        .options(
            selectinload(Task.owner),
            selectinload(Task.mentions),
            selectinload(Task.checkpoints),
        )
        .where(Task.id == task_id)
    )
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return task


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filter_mode: str = Query(default="all", pattern="^(all|private|shared)$"),
) -> list[TaskRead]:
    """List all tasks accessible to the current user (owned or PUBLIC mentioned)."""
    normalized_uname = normalize_username(current_user.username)

    access_conditions = [Task.owner_id == current_user.id]
    if normalized_uname:
        mention_subquery = select(TaskMention.task_id).where(
            TaskMention.telegram_username == normalized_uname
        )
        access_conditions.append(
            (Task.visibility == TaskVisibility.PUBLIC) & (Task.id.in_(mention_subquery))
        )

    stmt = (
        select(Task)
        .options(
            selectinload(Task.owner),
            selectinload(Task.mentions),
            selectinload(Task.checkpoints),
        )
        .where(or_(*access_conditions))
        .order_by(Task.position.asc(), Task.created_at.desc())
    )
    result = await db.execute(stmt)
    tasks = list(result.scalars().unique().all())

    if filter_mode == "private":
        tasks = [
            t
            for t in tasks
            if t.owner_id == current_user.id and t.visibility == TaskVisibility.PRIVATE
        ]
    elif filter_mode == "shared":
        tasks = [t for t in tasks if t.visibility == TaskVisibility.PUBLIC]

    return [TaskRead.model_validate(t) for t in tasks]


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskRead:
    """Create a new task from the web dashboard and broadcast its creation."""
    combined_raw = (
        f"{payload.title}\n{payload.description}" if payload.description else payload.title
    )
    task = Task(
        owner_id=current_user.id,
        visibility=payload.visibility,
        source=TaskSource.WEB,
        status=payload.status,
        priority=payload.priority,
        processing_state=TaskProcessingState.IDLE,
        title=payload.title,
        description=payload.description,
        raw_input=combined_raw,
        is_ai_improved=False,
        position=0,
        telegram_chat_id=current_user.telegram_id,
    )
    if payload.tags:
        task.tags = payload.tags
    db.add(task)
    await db.flush()

    extracted = extract_mentions(combined_raw)
    all_mentions = [*payload.mentions, *extracted]
    if all_mentions:
        await sync_task_mentions(db, task, all_mentions, append=False)

    await db.commit()
    refreshed = await _fetch_task_or_404(db, task.id)
    await publish_task_event(
        "task.created",
        refreshed,
        actor_username=current_user.username,
    )
    notify_telegram_on_web_change.delay(
        str(refreshed.id),
        current_user.username,
        "created new task on web dashboard",
    )
    return TaskRead.model_validate(refreshed)


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskRead:
    """Retrieve a single task if the current user has permission to access it."""
    task = await _fetch_task_or_404(db, task_id)
    if not can_user_access_task(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this task",
        )
    return TaskRead.model_validate(task)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskRead:
    """Update a task's status, position, content, visibility, or mentions."""
    task = await _fetch_task_or_404(db, task_id)
    if not can_user_access_task(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to edit this task",
        )

    if payload.visibility is not None or payload.mentions is not None:
        if not is_task_owner(current_user, task):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the task owner can modify visibility or mentions",
            )

    changes: list[str] = []
    if payload.title is not None and payload.title != task.title:
        task.title = payload.title
        changes.append(f"title updated to '{payload.title}'")
    if payload.description is not None and payload.description != task.description:
        task.description = payload.description
        changes.append("description updated")
    if payload.status is not None and payload.status != task.status:
        task.status = payload.status
        changes.append(f"status moved to {payload.status.value}")
    if payload.priority is not None and payload.priority != task.priority:
        task.priority = payload.priority
        changes.append(f"priority changed to {payload.priority.value}")
    if payload.tags is not None:
        task.tags = payload.tags
        changes.append("tags updated")
    if payload.position is not None and payload.position != task.position:
        task.position = payload.position
        changes.append(f"position updated to {payload.position}")
    if payload.visibility is not None and payload.visibility != task.visibility:
        task.visibility = payload.visibility
        changes.append(f"visibility changed to {payload.visibility.value}")
    if payload.mentions is not None:
        await sync_task_mentions(db, task, payload.mentions, append=False)
        changes.append("collaborator mentions updated")

    await db.commit()
    refreshed = await _fetch_task_or_404(db, task.id)
    await publish_task_event(
        "task.updated",
        refreshed,
        actor_username=current_user.username,
    )

    summary = ", ".join(changes) if changes else "task updated on web dashboard"
    notify_telegram_on_web_change.delay(
        str(refreshed.id),
        current_user.username,
        summary,
    )
    return TaskRead.model_validate(refreshed)


@router.put("/{task_id}/mentions", response_model=TaskRead)
async def update_task_mentions(
    task_id: uuid.UUID,
    payload: TaskMentionsUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskRead:
    """Replace the @username mention access list on a task (owner only)."""
    task = await _fetch_task_or_404(db, task_id)
    if not is_task_owner(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the task owner can modify mentions",
        )

    await sync_task_mentions(db, task, payload.mentions, append=False)
    await db.commit()
    refreshed = await _fetch_task_or_404(db, task.id)
    await publish_task_event(
        "task.updated",
        refreshed,
        actor_username=current_user.username,
    )
    notify_telegram_on_web_change.delay(
        str(refreshed.id),
        current_user.username,
        "collaborator @username mentions updated",
    )
    return TaskRead.model_validate(refreshed)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Delete a task permanently (owner only)."""
    task = await _fetch_task_or_404(db, task_id)
    if not is_task_owner(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the task owner can delete this task",
        )

    owner_id = task.owner_id
    visibility = task.visibility
    allowed_usernames = [m.telegram_username.lower() for m in task.mentions]

    await db.delete(task)
    await db.commit()

    await publish_task_deleted_event(
        task_id=task_id,
        owner_id=owner_id,
        visibility=visibility,
        allowed_usernames=allowed_usernames,
        actor_username=current_user.username,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{task_id}/improve", response_model=TaskRead)
async def trigger_ai_improve_task(
    task_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskRead:
    """Trigger the on-demand AI Task Improvement workflow via Celery."""
    task = await _fetch_task_or_404(db, task_id)
    if not can_user_access_task(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to improve this task",
        )

    task.processing_state = TaskProcessingState.IMPROVING
    task.error_message = None
    await db.commit()
    refreshed = await _fetch_task_or_404(db, task.id)
    await publish_task_event(
        "task.updated",
        refreshed,
        actor_username=current_user.username,
    )
    improve_task_task.delay(str(refreshed.id))
    return TaskRead.model_validate(refreshed)


@router.post("/{task_id}/checkpoints/generate", response_model=TaskRead)
async def trigger_ai_generate_checkpoints(
    task_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskRead:
    """Trigger the on-demand AI Checkpoints Generation workflow via Celery."""
    task = await _fetch_task_or_404(db, task_id)
    if not can_user_access_task(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to generate checkpoints for this task",
        )

    task.processing_state = TaskProcessingState.GENERATING_CHECKPOINTS
    task.error_message = None
    await db.commit()
    refreshed = await _fetch_task_or_404(db, task.id)
    await publish_task_event(
        "task.updated",
        refreshed,
        actor_username=current_user.username,
    )
    generate_checkpoints_task.delay(str(refreshed.id))
    return TaskRead.model_validate(refreshed)


@router.post(
    "/{task_id}/checkpoints",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_checkpoint(
    task_id: uuid.UUID,
    payload: CheckpointCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskRead:
    """Add a manual checkpoint item to an accessible task."""
    task = await _fetch_task_or_404(db, task_id)
    if not can_user_access_task(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to add checkpoints to this task",
        )

    next_pos = payload.position if payload.position is not None else len(task.checkpoints)
    checkpoint = TaskCheckpoint(
        task_id=task.id,
        title=payload.title,
        is_completed=False,
        position=next_pos,
    )
    task.checkpoints.append(checkpoint)
    db.add(checkpoint)
    await db.commit()

    refreshed = await _fetch_task_or_404(db, task.id)
    await publish_task_event(
        "task.updated",
        refreshed,
        actor_username=current_user.username,
    )
    notify_telegram_on_web_change.delay(
        str(refreshed.id),
        current_user.username,
        f"added checkpoint '{payload.title}'",
    )
    return TaskRead.model_validate(refreshed)


@router.patch(
    "/{task_id}/checkpoints/{checkpoint_id}",
    response_model=TaskRead,
)
async def update_checkpoint(
    task_id: uuid.UUID,
    checkpoint_id: uuid.UUID,
    payload: CheckpointUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskRead:
    """Toggle or edit a task checkpoint on an accessible task."""
    task = await _fetch_task_or_404(db, task_id)
    if not can_user_access_task(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify checkpoints on this task",
        )

    target_ckpt: TaskCheckpoint | None = None
    for ckpt in task.checkpoints:
        if ckpt.id == checkpoint_id:
            target_ckpt = ckpt
            break

    if target_ckpt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checkpoint not found",
        )

    if payload.title is not None:
        target_ckpt.title = payload.title
    if payload.is_completed is not None:
        target_ckpt.is_completed = payload.is_completed
    if payload.position is not None:
        target_ckpt.position = payload.position

    await db.commit()
    refreshed = await _fetch_task_or_404(db, task.id)
    await publish_task_event(
        "task.updated",
        refreshed,
        actor_username=current_user.username,
    )
    state_label = "completed" if target_ckpt.is_completed else "reopened"
    notify_telegram_on_web_change.delay(
        str(refreshed.id),
        current_user.username,
        f"checkpoint '{target_ckpt.title}' {state_label}",
    )
    return TaskRead.model_validate(refreshed)


@router.delete(
    "/{task_id}/checkpoints/{checkpoint_id}",
    response_model=TaskRead,
)
async def delete_checkpoint(
    task_id: uuid.UUID,
    checkpoint_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskRead:
    """Remove a checkpoint from an accessible task."""
    task = await _fetch_task_or_404(db, task_id)
    if not can_user_access_task(current_user, task):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete checkpoints on this task",
        )

    target_ckpt: TaskCheckpoint | None = None
    for ckpt in task.checkpoints:
        if ckpt.id == checkpoint_id:
            target_ckpt = ckpt
            break

    if target_ckpt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checkpoint not found",
        )

    removed_title = target_ckpt.title
    task.checkpoints.remove(target_ckpt)
    await db.delete(target_ckpt)
    await db.commit()

    refreshed = await _fetch_task_or_404(db, task.id)
    await publish_task_event(
        "task.updated",
        refreshed,
        actor_username=current_user.username,
    )
    notify_telegram_on_web_change.delay(
        str(refreshed.id),
        current_user.username,
        f"deleted checkpoint '{removed_title}'",
    )
    return TaskRead.model_validate(refreshed)

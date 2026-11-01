"""Service for extracting, normalizing, and enforcing Telegram @username mentions."""

import re
from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.models.task import Task, TaskMention, TaskVisibility
from app.models.user import User

MENTION_REGEX = re.compile(r"(?<![a-zA-Z0-9_])@([a-zA-Z0-9_]{5,32})(?![a-zA-Z0-9_])")
USERNAME_VALID_REGEX = re.compile(r"^[a-z0-9_]{5,32}$")


def normalize_username(raw_username: str | None) -> str | None:
    """Normalize a Telegram username to lowercase without a leading @ symbol."""
    if raw_username is None:
        return None
    cleaned = raw_username.strip().lstrip("@").lower()
    if not cleaned:
        return None
    return cleaned


def is_valid_telegram_username(username: str) -> bool:
    """Return True if the normalized username matches Telegram length and character rules."""
    return bool(USERNAME_VALID_REGEX.match(username))


def extract_mentions(text: str | None) -> list[str]:
    """Extract unique normalized @username mentions from free-form text."""
    if not text:
        return []
    seen: set[str] = set()
    extracted: list[str] = []
    for match in MENTION_REGEX.finditer(text):
        candidate = match.group(1).lower()
        if candidate not in seen:
            seen.add(candidate)
            extracted.append(candidate)
    return extracted


def normalize_mention_list(usernames: Iterable[str]) -> list[str]:
    """Normalize, validate, and deduplicate an iterable of Telegram usernames."""
    seen: set[str] = set()
    normalized_list: list[str] = []
    for item in usernames:
        norm = normalize_username(item)
        if norm and is_valid_telegram_username(norm) and norm not in seen:
            seen.add(norm)
            normalized_list.append(norm)
    return normalized_list


def is_task_owner(user: User, task: Task) -> bool:
    """Return True if the given user is the owner of the task."""
    return task.owner_id == user.id


def can_user_access_task(user: User, task: Task) -> bool:
    """Return True if the user is allowed to view and collaborate on the task."""
    if task.owner_id == user.id:
        return True
    if task.visibility != TaskVisibility.PUBLIC:
        return False
    user_norm = normalize_username(user.username)
    if not user_norm:
        return False
    mentioned_usernames = {m.telegram_username.lower() for m in task.mentions}
    return user_norm in mentioned_usernames


async def sync_task_mentions(
    session: AsyncSession,
    task: Task,
    usernames: Iterable[str],
    append: bool = False,
) -> list[TaskMention]:
    """Synchronize the task_mentions collection on a task with normalized usernames."""
    target_usernames = normalize_mention_list(usernames)
    stmt = (
        select(TaskMention)
        .where(TaskMention.task_id == task.id)
        .order_by(TaskMention.created_at.asc())
    )
    existing_rows = list((await session.execute(stmt)).scalars().all())
    existing_by_name = {m.telegram_username.lower(): m for m in existing_rows}

    if not append:
        target_set = set(target_usernames)
        for existing_name, mention_obj in list(existing_by_name.items()):
            if existing_name not in target_set:
                await session.delete(mention_obj)
                del existing_by_name[existing_name]

    for uname in target_usernames:
        if uname not in existing_by_name:
            new_mention = TaskMention(
                task_id=task.id,
                telegram_username=uname,
            )
            session.add(new_mention)
            existing_by_name[uname] = new_mention

    await session.flush()
    final_mentions = list(existing_by_name.values())
    set_committed_value(task, "mentions", final_mentions)
    return final_mentions


async def get_unregistered_usernames(
    session: AsyncSession,
    usernames: Iterable[str],
) -> list[str]:
    """Return mentioned usernames that do not have a registered User record yet."""
    normalized = normalize_mention_list(usernames)
    if not normalized:
        return []
    stmt = select(User.username).where(User.username.in_(normalized))
    result = await session.execute(stmt)
    registered_set = {str(uname).lower() for uname in result.scalars().all() if uname is not None}
    return [uname for uname in normalized if uname not in registered_set]


async def fetch_registered_users(
    session: AsyncSession,
    query_text: str | None = None,
) -> list[User]:
    """Fetch registered users ordered by username, optionally filtered by a search query."""
    stmt = select(User).order_by(User.username.asc(), User.first_name.asc())
    if query_text and query_text.strip():
        cleaned = query_text.strip().lstrip("@").lower()
        pattern = f"%{cleaned}%"
        stmt = stmt.where(
            or_(
                User.username.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
            )
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())

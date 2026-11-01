"""Initial schema for users, tasks, task_mentions, and task_checkpoints.

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-10-31 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

task_visibility_enum = sa.Enum("PRIVATE", "PUBLIC", name="task_visibility")
task_source_enum = sa.Enum("TELEGRAM_TEXT", "TELEGRAM_VOICE", "WEB", name="task_source")
task_status_enum = sa.Enum("PENDING", "IN_PROGRESS", "COMPLETED", name="task_status")
task_processing_state_enum = sa.Enum(
    "IDLE",
    "TRANSCRIBING",
    "IMPROVING",
    "GENERATING_CHECKPOINTS",
    "FAILED",
    name="task_processing_state",
)


def upgrade() -> None:
    """Create initial tables and indexes for the task management system."""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=False),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("photo_url", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=False)

    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "owner_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "visibility",
            task_visibility_enum,
            nullable=False,
            server_default="PRIVATE",
        ),
        sa.Column("source", task_source_enum, nullable=False),
        sa.Column(
            "status",
            task_status_enum,
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "processing_state",
            task_processing_state_enum,
            nullable=False,
            server_default="IDLE",
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("raw_input", sa.Text(), nullable=False),
        sa.Column(
            "is_ai_improved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_voice_file_id", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_tasks_owner_id", "tasks", ["owner_id"], unique=False)
    op.create_index("ix_tasks_visibility", "tasks", ["visibility"], unique=False)
    op.create_index("ix_tasks_status", "tasks", ["status"], unique=False)
    op.create_index("ix_tasks_telegram_chat_id", "tasks", ["telegram_chat_id"], unique=False)
    op.create_index(
        "ix_tasks_telegram_message_id",
        "tasks",
        ["telegram_message_id"],
        unique=False,
    )

    op.create_table(
        "task_mentions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "task_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_username", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "task_id",
            "telegram_username",
            name="uq_task_mention_username",
        ),
    )
    op.create_index("ix_task_mentions_task_id", "task_mentions", ["task_id"], unique=False)
    op.create_index(
        "ix_task_mentions_telegram_username",
        "task_mentions",
        ["telegram_username"],
        unique=False,
    )

    op.create_table(
        "task_checkpoints",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "task_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "is_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_task_checkpoints_task_id", "task_checkpoints", ["task_id"], unique=False)


def downgrade() -> None:
    """Drop all tables and enum types created in the initial migration."""
    op.drop_index("ix_task_checkpoints_task_id", table_name="task_checkpoints")
    op.drop_table("task_checkpoints")

    op.drop_index("ix_task_mentions_telegram_username", table_name="task_mentions")
    op.drop_index("ix_task_mentions_task_id", table_name="task_mentions")
    op.drop_table("task_mentions")

    op.drop_index("ix_tasks_telegram_message_id", table_name="tasks")
    op.drop_index("ix_tasks_telegram_chat_id", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_visibility", table_name="tasks")
    op.drop_index("ix_tasks_owner_id", table_name="tasks")
    op.drop_table("tasks")

    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    task_processing_state_enum.drop(bind, checkfirst=True)
    task_status_enum.drop(bind, checkfirst=True)
    task_source_enum.drop(bind, checkfirst=True)
    task_visibility_enum.drop(bind, checkfirst=True)

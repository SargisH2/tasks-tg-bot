"""Add priority and tags columns to tasks table.

Revision ID: 0002_add_priority_and_tags
Revises: 0001_initial_schema
Create Date: 2026-10-31 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_add_priority_and_tags"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add priority and tags columns to the tasks table if not already present."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("tasks")}

    if "priority" not in existing_columns:
        op.add_column(
            "tasks",
            sa.Column(
                "priority",
                sa.String(length=32),
                nullable=False,
                server_default="MEDIUM",
            ),
        )

    if "tags" not in existing_columns:
        op.add_column(
            "tasks",
            sa.Column(
                "tags",
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
        )


def downgrade() -> None:
    """Drop tags and priority columns from the tasks table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("tasks")}

    if "tags" in existing_columns:
        op.drop_column("tasks", "tags")

    if "priority" in existing_columns:
        op.drop_column("tasks", "priority")

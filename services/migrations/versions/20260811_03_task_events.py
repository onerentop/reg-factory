"""Persist append-only task events for local task replay.

Revision ID: 20260811_03
Revises: 20260811_02
Create Date: 2026-08-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260811_03"
down_revision: Union[str, Sequence[str], None] = "20260811_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "registration_jobs",
        sa.Column("last_event_seq", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "task_events",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "task_id",
            sa.String(64),
            sa.ForeignKey("registration_jobs.task_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("level", sa.String(10), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("task_id", "seq", name="uq_task_events_task_id_seq"),
    )
    op.create_index("ix_task_events_task_id", "task_events", ["task_id"])
    op.create_index("ix_task_events_task_id_seq", "task_events", ["task_id", "seq"])
    op.create_index("ix_task_events_created_at", "task_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_task_events_created_at", table_name="task_events")
    op.drop_index("ix_task_events_task_id_seq", table_name="task_events")
    op.drop_index("ix_task_events_task_id", table_name="task_events")
    op.drop_table("task_events")
    op.drop_column("registration_jobs", "last_event_seq")

"""Add durable registration job state.

Revision ID: 20260811_02
Revises: 20260811_01
Create Date: 2026-08-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260811_02"
down_revision: Union[str, Sequence[str], None] = "20260811_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "registration_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("task_id"),
    )
    op.create_index("ix_registration_jobs_task_id", "registration_jobs", ["task_id"])
    op.create_index("ix_registration_jobs_platform", "registration_jobs", ["platform"])
    op.create_index("ix_registration_jobs_status", "registration_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("registration_jobs")

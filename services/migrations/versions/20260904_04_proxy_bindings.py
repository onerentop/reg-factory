"""Track per-day proxy-to-window bindings.

Revision ID: 20260904_04
Revises: 20260811_03
Create Date: 2026-09-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260904_04"
down_revision: Union[str, Sequence[str], None] = "20260811_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "proxy_bindings",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "proxy_id",
            sa.Uuid(),
            sa.ForeignKey("proxy_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bound_date", sa.Date(), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=True),
        sa.Column("profile_id", sa.String(32), nullable=True),
        sa.Column("profile_name", sa.String(255), nullable=True),
        sa.Column("platform", sa.String(32), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="claimed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("proxy_id", "bound_date", name="uq_proxy_bindings_proxy_date"),
    )
    op.create_index("ix_proxy_bindings_proxy_id", "proxy_bindings", ["proxy_id"])
    op.create_index("ix_proxy_bindings_task_id", "proxy_bindings", ["task_id"])
    op.create_index("ix_proxy_bindings_proxy_date", "proxy_bindings", ["proxy_id", "bound_date"])


def downgrade() -> None:
    op.drop_index("ix_proxy_bindings_proxy_date", table_name="proxy_bindings")
    op.drop_index("ix_proxy_bindings_task_id", table_name="proxy_bindings")
    op.drop_index("ix_proxy_bindings_proxy_id", table_name="proxy_bindings")
    op.drop_table("proxy_bindings")

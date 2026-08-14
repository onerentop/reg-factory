"""Create the initial shared schema for the modular monolith.

Revision ID: 20260811_01
Revises:
Create Date: 2026-08-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260811_01"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UUID = sa.Uuid()
TIMESTAMP = sa.DateTime(timezone=True)
JSON = sa.JSON()


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    account_platform = sa.Enum("OUTLOOK", "GOOGLE", name="account_platform")
    account_status = sa.Enum("PENDING", "RUNNING", "SUCCESS", "FAILED", "LOCKED", name="account_status")
    step_status = sa.Enum("PENDING", "RUNNING", "SUCCESS", "FAILED", "SKIPPED", name="step_status")
    order_status = sa.Enum("PENDING", "RECEIVED", "COMPLETED", "CANCELLED", "TIMEOUT", name="order_status")

    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "api_keys",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("scopes", JSON, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_used_at", TIMESTAMP, nullable=True),
        sa.Column("call_count", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_api_keys_key", "api_keys", ["key"])

    op.create_table(
        "accounts",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password", sa.String(255), nullable=True),
        sa.Column("platform", account_platform, nullable=False),
        sa.Column("status", account_status, nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=False),
        sa.Column("total_steps", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cookies", JSON, nullable=True),
        sa.Column("tokens", JSON, nullable=True),
        sa.Column("proxy_used", sa.String(255), nullable=True),
        sa.Column("browser_provider", sa.String(50), nullable=True),
        sa.Column("metadata", JSON, nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_accounts_email", "accounts", ["email"])
    op.create_index("ix_accounts_platform", "accounts", ["platform"])

    op.create_table(
        "registration_steps",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("account_id", UUID, sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("status", step_status, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("metadata", JSON, nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_registration_steps_account_id", "registration_steps", ["account_id"])

    op.create_table(
        "sms_orders",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("service", sa.String(50), nullable=False),
        sa.Column("country", sa.String(10), nullable=False),
        sa.Column("phone_number", sa.String(30), nullable=True),
        sa.Column("order_id_external", sa.String(100), nullable=True),
        sa.Column("code", sa.String(20), nullable=True),
        sa.Column("status", order_status, nullable=False),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column("metadata", JSON, nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_sms_orders_provider", "sms_orders", ["provider"])

    op.create_table(
        "sms_platform_configs",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("provider_name", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("enabled", sa.String(5), nullable=False),
        sa.Column("priority", sa.Float(), nullable=False),
        sa.Column("config", JSON, nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("provider_name"),
    )
    op.create_index("ix_sms_platform_configs_provider_name", "sms_platform_configs", ["provider_name"])

    op.create_table(
        "config_entries",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("value", JSON, nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_config_entries_key", "config_entries", ["key"])

    op.create_table(
        "config_versions",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("config_key", sa.String(255), nullable=False),
        sa.Column("old_value", JSON, nullable=True),
        sa.Column("new_value", JSON, nullable=False),
        sa.Column("changed_by", sa.String(100), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_config_versions_config_key", "config_versions", ["config_key"])

    op.create_table(
        "audit_logs",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("operator", sa.String(100), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("target", sa.String(255), nullable=True),
        sa.Column("before_value", JSON, nullable=True),
        sa.Column("after_value", JSON, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_audit_logs_operator", "audit_logs", ["operator"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

    op.create_table(
        "alert_rules",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("threshold", sa.String(50), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("notify_channels", JSON, nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "alert_history",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("rule_name", sa.String(100), nullable=False),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "proxy_entries",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("type", sa.String(10), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("password", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("region", sa.String(20), nullable=True),
        *_timestamps(),
    )
    op.create_table(
        "logs",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("service", sa.String(50), nullable=False),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.String(36), nullable=True),
        sa.Column("account_id", sa.String(36), nullable=True),
        sa.Column("extra", JSON, nullable=True),
        sa.Column("created_at", TIMESTAMP, nullable=False),
    )
    op.create_index("ix_logs_service", "logs", ["service"])
    op.create_index("ix_logs_level", "logs", ["level"])
    op.create_index("ix_logs_trace_id", "logs", ["trace_id"])
    op.create_index("ix_logs_account_id", "logs", ["account_id"])
    op.create_index("ix_logs_created_at", "logs", ["created_at"])


def downgrade() -> None:
    for table in (
        "logs", "proxy_entries", "alert_history", "alert_rules", "audit_logs",
        "config_versions", "config_entries", "sms_platform_configs", "sms_orders",
        "registration_steps", "accounts", "api_keys", "users",
    ):
        op.drop_table(table)

    bind = op.get_bind()
    for enum in (
        sa.Enum(name="order_status"),
        sa.Enum(name="step_status"),
        sa.Enum(name="account_status"),
        sa.Enum(name="account_platform"),
    ):
        enum.drop(bind, checkfirst=True)

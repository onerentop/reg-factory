from sqlalchemy import Column, String, JSON, Boolean, Integer, DateTime
from datetime import datetime, timezone

from shared.base_model import BaseModel, TimestampMixin


class User(TimestampMixin, BaseModel):
    __tablename__ = "users"

    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="readonly")
    is_active = Column(Boolean, nullable=False, default=True)


class ApiKey(TimestampMixin, BaseModel):
    __tablename__ = "api_keys"

    key = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    owner_id = Column(String(36), nullable=False)
    scopes = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    call_count = Column(Integer, nullable=False, default=0)


class AuditLog(TimestampMixin, BaseModel):
    __tablename__ = "audit_logs"

    operator = Column(String(100), nullable=False, index=True)
    action = Column(String(50), nullable=False, index=True)
    target = Column(String(255), nullable=True)
    before_value = Column(JSON, nullable=True)
    after_value = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)


class AlertRule(TimestampMixin, BaseModel):
    __tablename__ = "alert_rules"

    name = Column(String(100), nullable=False)
    rule_type = Column(String(50), nullable=False)
    threshold = Column(String(50), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    notify_channels = Column(JSON, nullable=False, default=list)


class AlertHistory(TimestampMixin, BaseModel):
    __tablename__ = "alert_history"

    rule_name = Column(String(100), nullable=False)
    rule_type = Column(String(50), nullable=False)
    message = Column(String(500), nullable=False)
    resolved = Column(Boolean, nullable=False, default=False)

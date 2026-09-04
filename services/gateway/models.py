from sqlalchemy import (
    Column,
    String,
    JSON,
    Boolean,
    Integer,
    DateTime,
    Date,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
)
from datetime import datetime, timezone

from shared.base_model import BaseModel, TimestampMixin


class User(TimestampMixin, BaseModel):
    __tablename__ = "users"

    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="readonly")
    is_active = Column(Boolean, nullable=False, default=True)




class ProxyEntry(TimestampMixin, BaseModel):
    __tablename__ = "proxy_entries"

    type = Column(String(10), nullable=False, default="socks5")
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(100), nullable=True)
    password = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="unknown")
    region = Column(String(20), nullable=True)


class RegistrationJob(TimestampMixin, BaseModel):
    """本机任务的持久化投影，可审计其最终状态。"""
    __tablename__ = "registration_jobs"

    task_id = Column(String(64), unique=True, nullable=False, index=True)
    platform = Column(String(32), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="queued", index=True)
    result = Column(JSON, nullable=True)
    error_message = Column(String(1000), nullable=True)
    last_event_seq = Column(Integer, nullable=False, default=0, server_default="0")


class TaskEvent(BaseModel):
    """父 API 进程写入的任务事件审计流；seq 是断线回放游标。"""
    __tablename__ = "task_events"
    __table_args__ = (
        UniqueConstraint("task_id", "seq", name="uq_task_events_task_id_seq"),
        Index("ix_task_events_task_id_seq", "task_id", "seq"),
    )

    task_id = Column(
        String(64),
        ForeignKey("registration_jobs.task_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq = Column(Integer, nullable=False)
    event_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=True)
    level = Column(String(10), nullable=True)
    message = Column(Text, nullable=True)
    data = Column(JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class ProxyBinding(TimestampMixin, BaseModel):
    """代理与 ixBrowser 窗口的当天绑定。

    UNIQUE(proxy_id, bound_date) 在数据库层保证「当天一个 IP 只绑一个窗口」，
    不依赖应用层的先查后插。bound_date 用本地自然日，与 TimestampMixin 的 UTC 时间戳不同。
    """
    __tablename__ = "proxy_bindings"
    __table_args__ = (
        UniqueConstraint("proxy_id", "bound_date", name="uq_proxy_bindings_proxy_date"),
        Index("ix_proxy_bindings_proxy_date", "proxy_id", "bound_date"),
    )

    proxy_id = Column(
        ForeignKey("proxy_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bound_date = Column(Date, nullable=False)
    task_id = Column(String(64), nullable=True, index=True)
    profile_id = Column(String(32), nullable=True)
    profile_name = Column(String(255), nullable=True)
    platform = Column(String(32), nullable=True)
    status = Column(String(20), nullable=False, default="claimed")

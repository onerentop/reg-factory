from sqlalchemy import Column, String, Text, JSON, DateTime
from datetime import datetime, timezone

from shared.base_model import BaseModel


class LogEntry(BaseModel):
    __tablename__ = "logs"

    service = Column(String(50), nullable=False, index=True)
    level = Column(String(10), nullable=False, index=True)
    message = Column(Text, nullable=False)
    trace_id = Column(String(36), nullable=True, index=True)
    account_id = Column(String(36), nullable=True, index=True)
    extra = Column(JSON, nullable=True, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

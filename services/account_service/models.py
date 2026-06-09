from sqlalchemy import Column, String, Text, JSON, Integer, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import relationship
from enum import Enum

from shared.base_model import BaseModel, TimestampMixin


class AccountPlatform(Enum):
    OUTLOOK = "outlook"
    GOOGLE = "google"


class AccountStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    LOCKED = "locked"


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class Account(TimestampMixin, BaseModel):
    __tablename__ = "accounts"

    email = Column(String(255), nullable=False, index=True)
    password = Column(String(255), nullable=True)
    platform = Column(
        SAEnum(AccountPlatform, name="account_platform"),
        nullable=False, index=True,
    )
    status = Column(
        SAEnum(AccountStatus, name="account_status"),
        nullable=False, default=AccountStatus.PENDING,
    )
    current_step = Column(Integer, nullable=False, default=0)
    total_steps = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    cookies = Column(JSON, nullable=True)
    tokens = Column(JSON, nullable=True)
    proxy_used = Column(String(255), nullable=True)
    browser_provider = Column(String(50), nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True, default=dict)

    steps = relationship("RegistrationStep", back_populates="account", cascade="all, delete-orphan", order_by="RegistrationStep.step_number")


class RegistrationStep(TimestampMixin, BaseModel):
    __tablename__ = "registration_steps"

    account_id = Column(ForeignKey("accounts.id"), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    name = Column(String(100), nullable=False)
    status = Column(
        SAEnum(StepStatus, name="step_status"),
        nullable=False, default=StepStatus.PENDING,
    )
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True, default=dict)

    account = relationship("Account", back_populates="steps")

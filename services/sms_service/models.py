from sqlalchemy import Column, String, Float, JSON, Enum as SAEnum

from shared.base_model import BaseModel, TimestampMixin
from sms_service.providers.base import OrderStatus


class SmsOrder(TimestampMixin, BaseModel):
    __tablename__ = "sms_orders"

    provider = Column(String(50), nullable=False, index=True)
    service = Column(String(50), nullable=False)
    country = Column(String(10), nullable=False)
    phone_number = Column(String(30), nullable=True)
    order_id_external = Column(String(100), nullable=True)
    code = Column(String(20), nullable=True)
    status = Column(
        SAEnum(OrderStatus, name="order_status"),
        nullable=False,
        default=OrderStatus.PENDING,
    )
    cost = Column(Float, nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True, default=dict)


class SmsPlatformConfig(TimestampMixin, BaseModel):
    __tablename__ = "sms_platform_configs"

    provider_name = Column(String(50), unique=True, nullable=False, index=True)
    display_name = Column(String(100), nullable=False)
    enabled = Column(String(5), nullable=False, default="true")
    priority = Column(Float, nullable=False, default=0)
    config = Column(JSON, nullable=False, default=dict)

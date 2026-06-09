from sqlalchemy import Column, String, Text, JSON

from shared.base_model import BaseModel, TimestampMixin


class ConfigEntry(TimestampMixin, BaseModel):
    __tablename__ = "config_entries"

    key = Column(String(255), unique=True, nullable=False, index=True)
    value = Column(JSON, nullable=False, default=dict)
    category = Column(String(100), nullable=False, default="general")
    description = Column(Text, nullable=True)


class ConfigVersion(TimestampMixin, BaseModel):
    __tablename__ = "config_versions"

    config_key = Column(String(255), nullable=False, index=True)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=False)
    changed_by = Column(String(100), nullable=False, default="system")

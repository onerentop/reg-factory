import pytest
from sqlalchemy import Column, String
from shared.base_model import BaseModel, TimestampMixin


class SampleModel(TimestampMixin, BaseModel):
    __tablename__ = "sample"
    name = Column(String(100))


def test_base_model_has_id():
    cols = {c.name for c in SampleModel.__table__.columns}
    assert "id" in cols


def test_timestamp_mixin_has_timestamps():
    cols = {c.name for c in SampleModel.__table__.columns}
    assert "created_at" in cols
    assert "updated_at" in cols


def test_base_model_repr():
    assert "SampleModel" in repr(SampleModel.__name__)

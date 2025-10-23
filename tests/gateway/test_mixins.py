"""Tests for model mixins."""

import pytest
from datetime import datetime, UTC
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, Session
from services.gateway.app.db import Base
from services.gateway.app.models.mixins import SoftDeleteMixin


# Test model using SoftDeleteMixin
class TestModel(SoftDeleteMixin, Base):
    """Test model for mixin testing."""
    __tablename__ = "test_soft_delete_model"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


class TestSoftDeleteMixin:
    """Tests for SoftDeleteMixin functionality."""

    def test_is_deleted_when_deleted_at_is_none(self, db_session: Session):
        """Test that is_deleted returns False when deleted_at is None."""
        obj = TestModel(name="Test Object")
        db_session.add(obj)
        db_session.commit()

        assert obj.is_deleted is False
        assert obj.deleted_at is None

    def test_is_deleted_when_deleted_at_is_set(self, db_session: Session):
        """Test that is_deleted returns True when deleted_at is set."""
        obj = TestModel(name="Test Object")
        obj.deleted_at = datetime.now(UTC)
        db_session.add(obj)
        db_session.commit()

        assert obj.is_deleted is True
        assert obj.deleted_at is not None

    def test_soft_delete_sets_deleted_at(self, db_session: Session):
        """Test that soft_delete sets deleted_at timestamp."""
        obj = TestModel(name="Test Object")
        db_session.add(obj)
        db_session.commit()

        assert obj.deleted_at is None

        obj.soft_delete()

        assert obj.deleted_at is not None
        assert obj.is_deleted is True
        assert isinstance(obj.deleted_at, datetime)

    def test_soft_delete_idempotent(self, db_session: Session):
        """Test that soft_delete can be called multiple times safely."""
        obj = TestModel(name="Test Object")
        db_session.add(obj)
        db_session.commit()

        obj.soft_delete()
        first_deleted_at = obj.deleted_at

        # Call again
        obj.soft_delete()
        second_deleted_at = obj.deleted_at

        # Should not change the timestamp
        assert first_deleted_at == second_deleted_at

    def test_restore_clears_deleted_at(self, db_session: Session):
        """Test that restore clears the deleted_at timestamp."""
        obj = TestModel(name="Test Object")
        db_session.add(obj)
        db_session.commit()

        obj.soft_delete()
        assert obj.is_deleted is True

        obj.restore()

        assert obj.deleted_at is None
        assert obj.is_deleted is False

    def test_restore_on_non_deleted_object(self, db_session: Session):
        """Test that restore works on non-deleted objects."""
        obj = TestModel(name="Test Object")
        db_session.add(obj)
        db_session.commit()

        assert obj.is_deleted is False

        obj.restore()

        # Should still be not deleted
        assert obj.is_deleted is False
        assert obj.deleted_at is None

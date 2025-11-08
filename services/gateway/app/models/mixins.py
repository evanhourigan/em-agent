"""Model mixins for common patterns."""

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


class SoftDeleteMixin:
    """
    Mixin for soft-delete functionality.

    Adds a deleted_at timestamp column and helper methods for soft deleting records.
    Records with deleted_at != NULL are considered "soft deleted" and should be
    filtered out of normal queries.

    Usage:
        class MyModel(SoftDeleteMixin, Base):
            ...

        # Soft delete a record
        record.soft_delete()

        # Check if deleted
        if record.is_deleted:
            ...

        # Query non-deleted records
        active_records = session.query(MyModel).filter(MyModel.deleted_at == None).all()
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, index=True
    )

    @property
    def is_deleted(self) -> bool:
        """Check if this record is soft-deleted."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Mark this record as deleted."""
        if not self.is_deleted:
            self.deleted_at = datetime.now(UTC)

    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.deleted_at = None


class TimestampMixin:
    """
    Mixin for automatic timestamp management.

    Adds created_at and updated_at columns that are automatically maintained.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

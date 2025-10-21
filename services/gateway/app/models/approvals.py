from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        # Index for filtering pending approvals (most common query)
        Index("ix_approvals_status", "status"),
        # Index for subject lookups
        Index("ix_approvals_subject", "subject"),
        # Index for time-based queries
        Index("ix_approvals_created_at", "created_at"),
        # Composite index for status+created_at (find oldest pending)
        Index("ix_approvals_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

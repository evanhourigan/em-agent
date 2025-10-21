from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from .mixins import SoftDeleteMixin


class Objective(SoftDeleteMixin, Base):
    """
    Objective model with soft-delete support.

    OKRs are historical data that should be preserved for reporting and analysis.
    Use soft deletes to archive old objectives while maintaining historical records.
    """

    __tablename__ = "objectives"
    __table_args__ = (
        # Index for filtering active objectives
        Index("ix_objectives_status", "status"),
        # Index for filtering by owner (my objectives)
        Index("ix_objectives_owner", "owner"),
        # Index for filtering by period (quarterly OKRs)
        Index("ix_objectives_period", "period"),
        # Index for time-based queries
        Index("ix_objectives_created_at", "created_at"),
        # Composite index for period+status (active OKRs for Q4)
        Index("ix_objectives_period_status", "period", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    period: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # e.g., 2025Q4
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    # deleted_at column provided by SoftDeleteMixin

    key_results: Mapped[list[KeyResult]] = relationship(
        "KeyResult", back_populates="objective", cascade="all, delete-orphan"
    )


class KeyResult(Base):
    __tablename__ = "key_results"
    __table_args__ = (
        # Index for filtering by status
        Index("ix_key_results_status", "status"),
        # Composite index for objective+status (tracking KRs for objective)
        Index("ix_key_results_objective_status", "objective_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    objective_id: Mapped[int] = mapped_column(ForeignKey("objectives.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    target: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    current: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # e.g., % or count
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="tracking")

    objective: Mapped[Objective] = relationship("Objective", back_populates="key_results")



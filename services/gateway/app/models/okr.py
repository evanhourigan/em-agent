from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Objective(Base):
    __tablename__ = "objectives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    period: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # e.g., 2025Q4
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    key_results: Mapped[list[KeyResult]] = relationship(
        "KeyResult", back_populates="objective", cascade="all, delete-orphan"
    )


class KeyResult(Base):
    __tablename__ = "key_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    objective_id: Mapped[int] = mapped_column(ForeignKey("objectives.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    target: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    current: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # e.g., % or count
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="tracking")

    objective: Mapped[Objective] = relationship("Objective", back_populates="key_results")



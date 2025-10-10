from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class OnboardingPlan(Base):
    __tablename__ = "onboarding_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    tasks: Mapped[list[OnboardingTask]] = relationship(
        "OnboardingTask", back_populates="plan", cascade="all, delete-orphan"
    )


class OnboardingTask(Base):
    __tablename__ = "onboarding_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("onboarding_plans.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="todo")  # todo|done
    assignee: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped[OnboardingPlan] = relationship("OnboardingPlan", back_populates="tasks")



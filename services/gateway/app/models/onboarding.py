from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class OnboardingPlan(Base):
    __tablename__ = "onboarding_plans"
    __table_args__ = (
        # Index for filtering active plans
        Index("ix_onboarding_plans_status", "status"),
        # Index for time-based queries
        Index("ix_onboarding_plans_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    tasks: Mapped[list[OnboardingTask]] = relationship(
        "OnboardingTask", back_populates="plan", cascade="all, delete-orphan"
    )


class OnboardingTask(Base):
    __tablename__ = "onboarding_tasks"
    __table_args__ = (
        # Index for filtering todo/done tasks
        Index("ix_onboarding_tasks_status", "status"),
        # Index for assignee lookups (find my tasks)
        Index("ix_onboarding_tasks_assignee", "assignee"),
        # Index for due date queries (find overdue tasks)
        Index("ix_onboarding_tasks_due_date", "due_date"),
        # Composite index for plan+status (find incomplete tasks for plan)
        Index("ix_onboarding_tasks_plan_status", "plan_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("onboarding_plans.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="todo"
    )  # todo|done
    assignee: Mapped[str | None] = mapped_column(String(128), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    plan: Mapped[OnboardingPlan] = relationship(
        "OnboardingPlan", back_populates="tasks"
    )

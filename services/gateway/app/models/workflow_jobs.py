from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class WorkflowJob(Base):
    __tablename__ = "workflow_jobs"
    __table_args__ = (
        # Index for finding queued/running jobs (workflow runner polls this)
        Index("ix_workflow_jobs_status", "status"),
        # Index for filtering by rule kind
        Index("ix_workflow_jobs_rule_kind", "rule_kind"),
        # Index for subject lookups
        Index("ix_workflow_jobs_subject", "subject"),
        # Index for time-based queries
        Index("ix_workflow_jobs_created_at", "created_at"),
        # Composite index for status+created_at (find oldest queued jobs)
        Index("ix_workflow_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    rule_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

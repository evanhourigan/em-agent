from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ActionLog(Base):
    __tablename__ = "action_log"
    __table_args__ = (
        # Index for filtering by rule name
        Index("ix_action_log_rule_name", "rule_name"),
        # Index for subject lookups
        Index("ix_action_log_subject", "subject"),
        # Index for action type filtering
        Index("ix_action_log_action", "action"),
        # Index for time-based queries (audit logs)
        Index("ix_action_log_created_at", "created_at"),
        # Composite index for rule+time queries
        Index("ix_action_log_rule_created", "rule_name", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_name: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)  # nudge|escalate|block
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


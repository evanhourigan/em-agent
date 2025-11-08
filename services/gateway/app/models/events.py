from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class EventRaw(Base):
    __tablename__ = "events_raw"
    __table_args__ = (
        # Unique index on delivery_id for idempotency
        Index("uix_events_delivery_id", "delivery_id", unique=True),
        # Index for filtering by source
        Index("ix_events_source", "source"),
        # Index for filtering by event_type
        Index("ix_events_event_type", "event_type"),
        # Index for time-based queries (most recent events)
        Index("ix_events_received_at", "received_at"),
        # Composite index for source+time queries
        Index("ix_events_source_received", "source", "received_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # github|jira|slack
    event_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivery_id: Mapped[str] = mapped_column(
        String(128), nullable=False
    )  # idempotency key
    signature: Mapped[str | None] = mapped_column(String(256), nullable=True)
    headers: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

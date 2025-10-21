from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        # Index for filtering open incidents (most common query)
        Index("ix_incidents_status", "status"),
        # Index for filtering by severity
        Index("ix_incidents_severity", "severity"),
        # Index for time-based queries
        Index("ix_incidents_created_at", "created_at"),
        # Composite index for status+severity (find critical open incidents)
        Index("ix_incidents_status_severity", "status", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    severity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    timeline: Mapped[list[IncidentTimeline]] = relationship(
        "IncidentTimeline", back_populates="incident", cascade="all, delete-orphan"
    )


class IncidentTimeline(Base):
    __tablename__ = "incident_timeline"
    __table_args__ = (
        # Index for chronological ordering within an incident
        Index("ix_incident_timeline_ts", "ts"),
        # Composite index for incident+time (fetch timeline for incident)
        Index("ix_incident_timeline_incident_ts", "incident_id", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="note")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    incident: Mapped[Incident] = relationship("Incident", back_populates="timeline")



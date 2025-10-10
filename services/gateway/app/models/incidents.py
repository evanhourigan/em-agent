from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    severity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    timeline: Mapped[list[IncidentTimeline]] = relationship(
        "IncidentTimeline", back_populates="incident", cascade="all, delete-orphan"
    )


class IncidentTimeline(Base):
    __tablename__ = "incident_timeline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="note")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    incident: Mapped[Incident] = relationship("Incident", back_populates="timeline")



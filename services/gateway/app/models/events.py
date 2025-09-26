from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class EventRaw(Base):
    __tablename__ = "events_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # github|jira|slack
    event_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    delivery_id: Mapped[str] = mapped_column(String(128), nullable=False)  # idempotency key
    signature: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    headers: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

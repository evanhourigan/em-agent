from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Identity(Base):
    __tablename__ = "identities"
    __table_args__ = (
        # Composite unique constraint: one external identity per type+id
        UniqueConstraint("external_type", "external_id", name="uix_identities_external"),
        # Index for user_id lookups (find all identities for a user)
        Index("ix_identities_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_type: Mapped[str] = mapped_column(String(32), nullable=False)  # github|slack
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    meta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

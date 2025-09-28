from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005_events_raw_unique_fix"
down_revision = "0004_identities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_events_raw_source_delivery", table_name="events_raw")
    op.create_index(
        "ix_events_raw_source_delivery_event",
        "events_raw",
        ["source", "delivery_id", "event_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_events_raw_source_delivery_event", table_name="events_raw")
    op.create_index(
        "ix_events_raw_source_delivery", "events_raw", ["source", "delivery_id"], unique=True
    )

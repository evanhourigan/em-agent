from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_events_raw"
down_revision = "0002_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events_raw",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=True),
        sa.Column("delivery_id", sa.String(length=128), nullable=False),
        sa.Column("signature", sa.String(length=256), nullable=True),
        sa.Column("headers", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_events_raw_source_delivery", "events_raw", ["source", "delivery_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_events_raw_source_delivery", table_name="events_raw")
    op.drop_table("events_raw")

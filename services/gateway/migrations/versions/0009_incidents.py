from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0009_incidents'
down_revision = '0008_approvals'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'incidents',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        'incident_timeline',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('incident_id', sa.Integer, sa.ForeignKey('incidents.id'), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('text', sa.Text, nullable=False),
        sa.Column('author', sa.String(length=128), nullable=True),
    )
    op.create_index('idx_incident_timeline_incident', 'incident_timeline', ['incident_id'])


def downgrade() -> None:
    op.drop_index('idx_incident_timeline_incident', table_name='incident_timeline')
    op.drop_table('incident_timeline')
    op.drop_table('incidents')



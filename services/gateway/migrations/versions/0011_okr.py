from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0011_okr'
down_revision = '0010_onboarding'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'objectives',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('owner', sa.String(length=128), nullable=True),
        sa.Column('period', sa.String(length=32), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'key_results',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('objective_id', sa.Integer, sa.ForeignKey('objectives.id'), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('target', sa.Numeric(12,2), nullable=True),
        sa.Column('current', sa.Numeric(12,2), nullable=True),
        sa.Column('unit', sa.String(length=32), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
    )
    op.create_index('idx_key_results_objective', 'key_results', ['objective_id'])


def downgrade() -> None:
    op.drop_index('idx_key_results_objective', table_name='key_results')
    op.drop_table('key_results')
    op.drop_table('objectives')



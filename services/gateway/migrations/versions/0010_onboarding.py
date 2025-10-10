from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0010_onboarding'
down_revision = '0009_incidents'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'onboarding_plans',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'onboarding_tasks',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('plan_id', sa.Integer, sa.ForeignKey('onboarding_plans.id'), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('assignee', sa.String(length=128), nullable=True),
        sa.Column('due_date', sa.Date, nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_onboarding_tasks_plan', 'onboarding_tasks', ['plan_id'])


def downgrade() -> None:
    op.drop_index('idx_onboarding_tasks_plan', table_name='onboarding_tasks')
    op.drop_table('onboarding_tasks')
    op.drop_table('onboarding_plans')



"""add_database_indexes_for_performance

Revision ID: 0012
Revises: 0011
Create Date: 2025-10-21

This migration adds comprehensive indexes to all database tables to improve query performance.
See DATABASE_INDEXES.md for detailed documentation on each index and its purpose.

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '0012'
down_revision = '0011_okr'
branch_labels = None
depends_on = None


def upgrade():
    """Add database indexes for performance."""

    # Identity indexes
    op.execute('CREATE UNIQUE INDEX CONCURRENTLY uix_identities_external ON identities (external_type, external_id)')
    op.execute('CREATE INDEX CONCURRENTLY ix_identities_user_id ON identities (user_id)')

    # EventRaw indexes
    op.execute('CREATE UNIQUE INDEX CONCURRENTLY uix_events_delivery_id ON events_raw (delivery_id)')
    op.execute('CREATE INDEX CONCURRENTLY ix_events_source ON events_raw (source)')
    op.execute('CREATE INDEX CONCURRENTLY ix_events_event_type ON events_raw (event_type)')
    op.execute('CREATE INDEX CONCURRENTLY ix_events_received_at ON events_raw (received_at)')
    op.execute('CREATE INDEX CONCURRENTLY ix_events_source_received ON events_raw (source, received_at)')

    # Approval indexes
    op.execute('CREATE INDEX CONCURRENTLY ix_approvals_status ON approvals (status)')
    op.execute('CREATE INDEX CONCURRENTLY ix_approvals_subject ON approvals (subject)')
    op.execute('CREATE INDEX CONCURRENTLY ix_approvals_created_at ON approvals (created_at)')
    op.execute('CREATE INDEX CONCURRENTLY ix_approvals_status_created ON approvals (status, created_at)')

    # WorkflowJob indexes
    op.execute('CREATE INDEX CONCURRENTLY ix_workflow_jobs_status ON workflow_jobs (status)')
    op.execute('CREATE INDEX CONCURRENTLY ix_workflow_jobs_rule_kind ON workflow_jobs (rule_kind)')
    op.execute('CREATE INDEX CONCURRENTLY ix_workflow_jobs_subject ON workflow_jobs (subject)')
    op.execute('CREATE INDEX CONCURRENTLY ix_workflow_jobs_created_at ON workflow_jobs (created_at)')
    op.execute('CREATE INDEX CONCURRENTLY ix_workflow_jobs_status_created ON workflow_jobs (status, created_at)')

    # ActionLog indexes
    op.execute('CREATE INDEX CONCURRENTLY ix_action_log_rule_name ON action_log (rule_name)')
    op.execute('CREATE INDEX CONCURRENTLY ix_action_log_subject ON action_log (subject)')
    op.execute('CREATE INDEX CONCURRENTLY ix_action_log_action ON action_log (action)')
    op.execute('CREATE INDEX CONCURRENTLY ix_action_log_created_at ON action_log (created_at)')
    op.execute('CREATE INDEX CONCURRENTLY ix_action_log_rule_created ON action_log (rule_name, created_at)')

    # Incident indexes
    op.execute('CREATE INDEX CONCURRENTLY ix_incidents_status ON incidents (status)')
    op.execute('CREATE INDEX CONCURRENTLY ix_incidents_severity ON incidents (severity)')
    op.execute('CREATE INDEX CONCURRENTLY ix_incidents_created_at ON incidents (created_at)')
    op.execute('CREATE INDEX CONCURRENTLY ix_incidents_status_severity ON incidents (status, severity)')

    # IncidentTimeline indexes
    op.execute('CREATE INDEX CONCURRENTLY ix_incident_timeline_ts ON incident_timeline (ts)')
    op.execute('CREATE INDEX CONCURRENTLY ix_incident_timeline_incident_ts ON incident_timeline (incident_id, ts)')

    # OnboardingPlan indexes
    op.execute('CREATE INDEX CONCURRENTLY ix_onboarding_plans_status ON onboarding_plans (status)')
    op.execute('CREATE INDEX CONCURRENTLY ix_onboarding_plans_created_at ON onboarding_plans (created_at)')

    # OnboardingTask indexes
    op.execute('CREATE INDEX CONCURRENTLY ix_onboarding_tasks_status ON onboarding_tasks (status)')
    op.execute('CREATE INDEX CONCURRENTLY ix_onboarding_tasks_assignee ON onboarding_tasks (assignee)')
    op.execute('CREATE INDEX CONCURRENTLY ix_onboarding_tasks_due_date ON onboarding_tasks (due_date)')
    op.execute('CREATE INDEX CONCURRENTLY ix_onboarding_tasks_plan_status ON onboarding_tasks (plan_id, status)')

    # Objective indexes
    op.execute('CREATE INDEX CONCURRENTLY ix_objectives_status ON objectives (status)')
    op.execute('CREATE INDEX CONCURRENTLY ix_objectives_owner ON objectives (owner)')
    op.execute('CREATE INDEX CONCURRENTLY ix_objectives_period ON objectives (period)')
    op.execute('CREATE INDEX CONCURRENTLY ix_objectives_created_at ON objectives (created_at)')
    op.execute('CREATE INDEX CONCURRENTLY ix_objectives_period_status ON objectives (period, status)')

    # KeyResult indexes
    op.execute('CREATE INDEX CONCURRENTLY ix_key_results_status ON key_results (status)')
    op.execute('CREATE INDEX CONCURRENTLY ix_key_results_objective_status ON key_results (objective_id, status)')


def downgrade():
    """Remove database indexes."""

    # Identity indexes
    op.drop_index('ix_identities_user_id', table_name='identities')
    op.drop_index('uix_identities_external', table_name='identities')

    # EventRaw indexes
    op.drop_index('ix_events_source_received', table_name='events_raw')
    op.drop_index('ix_events_received_at', table_name='events_raw')
    op.drop_index('ix_events_event_type', table_name='events_raw')
    op.drop_index('ix_events_source', table_name='events_raw')
    op.drop_index('uix_events_delivery_id', table_name='events_raw')

    # Approval indexes
    op.drop_index('ix_approvals_status_created', table_name='approvals')
    op.drop_index('ix_approvals_created_at', table_name='approvals')
    op.drop_index('ix_approvals_subject', table_name='approvals')
    op.drop_index('ix_approvals_status', table_name='approvals')

    # WorkflowJob indexes
    op.drop_index('ix_workflow_jobs_status_created', table_name='workflow_jobs')
    op.drop_index('ix_workflow_jobs_created_at', table_name='workflow_jobs')
    op.drop_index('ix_workflow_jobs_subject', table_name='workflow_jobs')
    op.drop_index('ix_workflow_jobs_rule_kind', table_name='workflow_jobs')
    op.drop_index('ix_workflow_jobs_status', table_name='workflow_jobs')

    # ActionLog indexes
    op.drop_index('ix_action_log_rule_created', table_name='action_log')
    op.drop_index('ix_action_log_created_at', table_name='action_log')
    op.drop_index('ix_action_log_action', table_name='action_log')
    op.drop_index('ix_action_log_subject', table_name='action_log')
    op.drop_index('ix_action_log_rule_name', table_name='action_log')

    # Incident indexes
    op.drop_index('ix_incidents_status_severity', table_name='incidents')
    op.drop_index('ix_incidents_created_at', table_name='incidents')
    op.drop_index('ix_incidents_severity', table_name='incidents')
    op.drop_index('ix_incidents_status', table_name='incidents')

    # IncidentTimeline indexes
    op.drop_index('ix_incident_timeline_incident_ts', table_name='incident_timeline')
    op.drop_index('ix_incident_timeline_ts', table_name='incident_timeline')

    # OnboardingPlan indexes
    op.drop_index('ix_onboarding_plans_created_at', table_name='onboarding_plans')
    op.drop_index('ix_onboarding_plans_status', table_name='onboarding_plans')

    # OnboardingTask indexes
    op.drop_index('ix_onboarding_tasks_plan_status', table_name='onboarding_tasks')
    op.drop_index('ix_onboarding_tasks_due_date', table_name='onboarding_tasks')
    op.drop_index('ix_onboarding_tasks_assignee', table_name='onboarding_tasks')
    op.drop_index('ix_onboarding_tasks_status', table_name='onboarding_tasks')

    # Objective indexes
    op.drop_index('ix_objectives_period_status', table_name='objectives')
    op.drop_index('ix_objectives_created_at', table_name='objectives')
    op.drop_index('ix_objectives_period', table_name='objectives')
    op.drop_index('ix_objectives_owner', table_name='objectives')
    op.drop_index('ix_objectives_status', table_name='objectives')

    # KeyResult indexes
    op.drop_index('ix_key_results_objective_status', table_name='key_results')
    op.drop_index('ix_key_results_status', table_name='key_results')

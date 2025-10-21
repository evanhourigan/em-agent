# Database Indexes Documentation

## Overview

This document describes the database indexing strategy for the EM Agent Gateway. Indexes are strategically placed on frequently queried columns to improve read performance and support common query patterns.

## Index Summary

Total indexes added across all models: **40 indexes**

| Model | Indexes | Purpose |
|-------|---------|---------|
| Identity | 2 | External identity lookups, user identity aggregation |
| EventRaw | 5 | Event filtering, idempotency, time-based queries |
| Approval | 4 | Pending approval queries, subject lookups |
| WorkflowJob | 5 | Job queue polling, status filtering |
| ActionLog | 5 | Audit queries, rule-based filtering |
| Incident | 4 | Open incident filtering, severity queries |
| IncidentTimeline | 2 | Timeline chronological ordering |
| OnboardingPlan | 2 | Active plan filtering |
| OnboardingTask | 4 | Task assignment, due date queries |
| Objective | 5 | OKR period filtering, owner queries |
| KeyResult | 2 | Key result tracking |

## Detailed Index Descriptions

### Identity Model

```python
__table_args__ = (
    UniqueConstraint("external_type", "external_id", name="uix_identities_external"),
    Index("ix_identities_user_id", "user_id"),
)
```

**Purpose:**
- **Unique constraint (external_type, external_id)**: Ensures one identity per external source (e.g., one GitHub user, one Slack user). Prevents duplicate identity records.
- **user_id index**: Enables fast lookups to find all external identities for a given user (e.g., "Show me all the linked accounts for user 123").

**Query patterns:**
```sql
-- Find identity by external source (uses unique constraint index)
SELECT * FROM identities WHERE external_type = 'github' AND external_id = 'user123';

-- Find all identities for a user (uses user_id index)
SELECT * FROM identities WHERE user_id = 42;
```

### EventRaw Model

```python
__table_args__ = (
    Index("uix_events_delivery_id", "delivery_id", unique=True),
    Index("ix_events_source", "source"),
    Index("ix_events_event_type", "event_type"),
    Index("ix_events_received_at", "received_at"),
    Index("ix_events_source_received", "source", "received_at"),
)
```

**Purpose:**
- **delivery_id unique index**: Idempotency - prevents duplicate event processing
- **source index**: Filter events by source (GitHub, Slack, Jira)
- **event_type index**: Filter by specific event types
- **received_at index**: Time-based queries (recent events)
- **source+received_at composite**: Optimizes "recent GitHub events" queries

**Query patterns:**
```sql
-- Check for duplicate delivery (uses delivery_id unique index)
SELECT * FROM events_raw WHERE delivery_id = 'abc123';

-- Get recent GitHub events (uses composite index)
SELECT * FROM events_raw
WHERE source = 'github'
ORDER BY received_at DESC
LIMIT 100;

-- Get all pull request events (uses event_type index)
SELECT * FROM events_raw WHERE event_type = 'pull_request';
```

### Approval Model

```python
__table_args__ = (
    Index("ix_approvals_status", "status"),
    Index("ix_approvals_subject", "subject"),
    Index("ix_approvals_created_at", "created_at"),
    Index("ix_approvals_status_created", "status", "created_at"),
)
```

**Purpose:**
- **status index**: Find pending/approved/rejected approvals
- **subject index**: Lookup approvals for a specific resource
- **created_at index**: Time-based queries
- **status+created_at composite**: Find oldest pending approvals (prioritization)

**Query patterns:**
```sql
-- Get all pending approvals, oldest first (uses composite index)
SELECT * FROM approvals
WHERE status = 'pending'
ORDER BY created_at ASC;

-- Find approvals for a subject (uses subject index)
SELECT * FROM approvals WHERE subject = 'deploy:prod-service';
```

### WorkflowJob Model

```python
__table_args__ = (
    Index("ix_workflow_jobs_status", "status"),
    Index("ix_workflow_jobs_rule_kind", "rule_kind"),
    Index("ix_workflow_jobs_subject", "subject"),
    Index("ix_workflow_jobs_created_at", "created_at"),
    Index("ix_workflow_jobs_status_created", "status", "created_at"),
)
```

**Purpose:**
- **status index**: Critical for workflow runner polling (find queued jobs)
- **rule_kind index**: Filter jobs by workflow type
- **subject index**: Track jobs for specific resources
- **created_at index**: Job age tracking
- **status+created_at composite**: Optimizes queue polling (oldest queued jobs first)

**Query patterns:**
```sql
-- Workflow runner polling for next job (uses composite index)
SELECT * FROM workflow_jobs
WHERE status = 'queued'
ORDER BY created_at ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- Find all jobs for a subject (uses subject index)
SELECT * FROM workflow_jobs WHERE subject = 'service:api';
```

### ActionLog Model

```python
__table_args__ = (
    Index("ix_action_log_rule_name", "rule_name"),
    Index("ix_action_log_subject", "subject"),
    Index("ix_action_log_action", "action"),
    Index("ix_action_log_created_at", "created_at"),
    Index("ix_action_log_rule_created", "rule_name", "created_at"),
)
```

**Purpose:**
- **rule_name index**: Filter logs by specific rule
- **subject index**: Audit trail for a resource
- **action index**: Filter by action type (nudge, escalate, block)
- **created_at index**: Time-based audit queries
- **rule_name+created_at composite**: Rule activity over time

**Query patterns:**
```sql
-- Audit log for a subject (uses subject index)
SELECT * FROM action_log
WHERE subject = 'pr:123'
ORDER BY created_at DESC;

-- Recent activity for a rule (uses composite index)
SELECT * FROM action_log
WHERE rule_name = 'code_review_timeout'
  AND created_at > NOW() - INTERVAL '7 days';
```

### Incident Model

```python
__table_args__ = (
    Index("ix_incidents_status", "status"),
    Index("ix_incidents_severity", "severity"),
    Index("ix_incidents_created_at", "created_at"),
    Index("ix_incidents_status_severity", "status", "severity"),
)
```

**Purpose:**
- **status index**: Find open/closed incidents
- **severity index**: Filter by severity level
- **created_at index**: Recent incidents
- **status+severity composite**: Critical open incidents

**Query patterns:**
```sql
-- Active critical incidents (uses composite index)
SELECT * FROM incidents
WHERE status = 'open'
  AND severity = 'critical'
ORDER BY created_at DESC;

-- Recent closed incidents (uses status + created_at)
SELECT * FROM incidents
WHERE status = 'closed'
  AND created_at > NOW() - INTERVAL '30 days';
```

### IncidentTimeline Model

```python
__table_args__ = (
    Index("ix_incident_timeline_ts", "ts"),
    Index("ix_incident_timeline_incident_ts", "incident_id", "ts"),
)
```

**Purpose:**
- **ts index**: Chronological ordering
- **incident_id+ts composite**: Fetch timeline for an incident in order (most common query)

**Query patterns:**
```sql
-- Get incident timeline (uses composite index)
SELECT * FROM incident_timeline
WHERE incident_id = 42
ORDER BY ts ASC;
```

### OnboardingPlan Model

```python
__table_args__ = (
    Index("ix_onboarding_plans_status", "status"),
    Index("ix_onboarding_plans_created_at", "created_at"),
)
```

**Purpose:**
- **status index**: Find active/completed plans
- **created_at index**: Recent plans

### OnboardingTask Model

```python
__table_args__ = (
    Index("ix_onboarding_tasks_status", "status"),
    Index("ix_onboarding_tasks_assignee", "assignee"),
    Index("ix_onboarding_tasks_due_date", "due_date"),
    Index("ix_onboarding_tasks_plan_status", "plan_id", "status"),
)
```

**Purpose:**
- **status index**: Find todo/done tasks
- **assignee index**: "My tasks" queries
- **due_date index**: Find overdue tasks
- **plan_id+status composite**: Incomplete tasks for a plan

**Query patterns:**
```sql
-- My outstanding tasks (uses assignee index)
SELECT * FROM onboarding_tasks
WHERE assignee = 'john@example.com'
  AND status = 'todo'
ORDER BY due_date ASC;

-- Overdue tasks (uses due_date index)
SELECT * FROM onboarding_tasks
WHERE due_date < CURRENT_DATE
  AND status = 'todo';
```

### Objective Model

```python
__table_args__ = (
    Index("ix_objectives_status", "status"),
    Index("ix_objectives_owner", "owner"),
    Index("ix_objectives_period", "period"),
    Index("ix_objectives_created_at", "created_at"),
    Index("ix_objectives_period_status", "period", "status"),
)
```

**Purpose:**
- **status index**: Active vs archived objectives
- **owner index**: "My OKRs" queries
- **period index**: Quarterly OKR filtering
- **created_at index**: Recent objectives
- **period+status composite**: Active OKRs for Q4 2025

**Query patterns:**
```sql
-- Active OKRs for current quarter (uses composite index)
SELECT * FROM objectives
WHERE period = '2025Q4'
  AND status = 'active';

-- My active objectives (uses owner + status)
SELECT * FROM objectives
WHERE owner = 'engineering-team'
  AND status = 'active';
```

### KeyResult Model

```python
__table_args__ = (
    Index("ix_key_results_status", "status"),
    Index("ix_key_results_objective_status", "objective_id", "status"),
)
```

**Purpose:**
- **status index**: Filter by tracking status
- **objective_id+status composite**: Tracking key results for an objective

**Query patterns:**
```sql
-- Get tracking KRs for an objective (uses composite index)
SELECT * FROM key_results
WHERE objective_id = 42
  AND status = 'tracking';
```

## Index Design Principles

### 1. Status Columns

Almost all models with a `status` column have an index on it because status is frequently used in WHERE clauses:
- `WHERE status = 'pending'`
- `WHERE status = 'open'`
- `WHERE status = 'queued'`

### 2. Foreign Keys

All foreign key columns already have indexes (automatically created or explicitly defined):
- `incident_id` in IncidentTimeline
- `plan_id` in OnboardingTask
- `objective_id` in KeyResult

### 3. Timestamp Columns

Timestamp columns used for ordering or filtering have indexes:
- `created_at` - Most common for "recent items" queries
- `received_at` - For event processing
- `ts` - For timelines
- `due_date` - For deadline queries

### 4. Composite Indexes

Composite indexes optimize common multi-column queries:
- `(status, created_at)` - "Oldest pending items"
- `(source, received_at)` - "Recent events from GitHub"
- `(period, status)` - "Active OKRs for Q4"
- `(incident_id, ts)` - "Timeline for incident"

**Left-prefix rule:** Composite index `(a, b, c)` can be used for queries on:
- `(a)`
- `(a, b)`
- `(a, b, c)`

But NOT for `(b)`, `(c)`, or `(b, c)` alone.

### 5. Unique Indexes

Unique indexes serve dual purposes:
1. Enforce data integrity
2. Provide fast lookups

Examples:
- `delivery_id` - Idempotency (no duplicate events)
- `(external_type, external_id)` - No duplicate identities

## Performance Impact

### Benefits

1. **Faster SELECT queries**: Indexes dramatically speed up WHERE, ORDER BY, and JOIN operations
2. **Reduced full table scans**: Database can use index lookups instead of scanning entire tables
3. **Improved worker efficiency**: Background workers (workflow runner, evaluator) poll queues faster
4. **Better user experience**: Faster API responses for list/filter endpoints

### Trade-offs

1. **Slower writes**: Each INSERT/UPDATE/DELETE must update indexes
   - **Impact**: Minimal - our workload is read-heavy
   - **Mitigation**: Only index frequently queried columns

2. **Storage overhead**: Indexes consume disk space
   - **Impact**: ~15-30% more storage (acceptable for PostgreSQL)
   - **Benefit**: Worth it for query performance gains

3. **Memory usage**: Active indexes cached in RAM
   - **Impact**: Minimal with selective indexing
   - **Benefit**: Frequently used indexes stay hot in cache

## Monitoring Index Usage

### Check Index Usage (PostgreSQL)

```sql
-- Find unused indexes
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans
FROM pg_stat_user_indexes
WHERE idx_scan = 0
  AND indexrelname NOT LIKE 'pg_toast%'
ORDER BY schemaname, tablename;

-- Find most used indexes
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan as scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC
LIMIT 20;

-- Check table sizes including indexes
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
    pg_size_pretty(pg_indexes_size(schemaname||'.'||tablename)) AS indexes_size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Query Execution Plans

```sql
-- Explain a query to see if indexes are used
EXPLAIN ANALYZE
SELECT * FROM approvals
WHERE status = 'pending'
ORDER BY created_at ASC
LIMIT 10;

-- Look for "Index Scan" or "Index Only Scan" (good)
-- Avoid "Seq Scan" on large tables (bad)
```

## Best Practices

### ✅ Do

1. **Index foreign keys**: Always index columns used in JOINs
2. **Index status columns**: Status is almost always filtered
3. **Use composite indexes**: For multi-column WHERE clauses
4. **Index sort columns**: Columns used in ORDER BY
5. **Monitor usage**: Drop unused indexes periodically

### ❌ Don't

1. **Over-index**: Don't index every column (slows writes)
2. **Duplicate indexes**: Don't create redundant indexes
3. **Index low-cardinality columns alone**: Boolean columns don't benefit much from single-column indexes
4. **Ignore query patterns**: Profile actual queries before adding indexes
5. **Index large text columns**: Full-text search requires different strategy

## Migration Strategy

When indexes are added to models:

1. **Development**: SQLAlchemy creates indexes automatically with `Base.metadata.create_all()`
2. **Production**: Use Alembic migrations to add indexes with `CREATE INDEX CONCURRENTLY` (PostgreSQL)

**Example Alembic migration:**

```python
def upgrade():
    # Use CONCURRENTLY to avoid locking table
    op.execute('CREATE INDEX CONCURRENTLY ix_approvals_status ON approvals (status)')
    op.execute('CREATE INDEX CONCURRENTLY ix_approvals_status_created ON approvals (status, created_at)')

def downgrade():
    op.drop_index('ix_approvals_status', table_name='approvals')
    op.drop_index('ix_approvals_status_created', table_name='approvals')
```

**Why CONCURRENTLY?**
- Allows reads/writes to continue during index creation
- Critical for production databases with active traffic
- Takes longer but doesn't lock the table

## Troubleshooting

### Slow queries despite indexes

**Possible causes:**
1. Index not covering the query (check EXPLAIN ANALYZE)
2. Poor query structure (e.g., OR conditions can prevent index usage)
3. Statistics out of date (run ANALYZE)
4. Index bloat (rebuild with REINDEX)

**Solutions:**
```sql
-- Update table statistics
ANALYZE approvals;

-- Rebuild bloated index
REINDEX INDEX CONCURRENTLY ix_approvals_status;

-- Check if index is being used
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM approvals WHERE status = 'pending';
```

### Too many indexes

**Symptoms:**
- Slow INSERT/UPDATE/DELETE operations
- High disk usage
- Maintenance overhead

**Solutions:**
1. Review index usage statistics
2. Drop unused indexes
3. Consolidate redundant indexes
4. Consider partial indexes for specific use cases

## Future Optimizations

### Partial Indexes

For columns with skewed distributions:

```python
# Example: Only index pending approvals (most common filter)
Index("ix_approvals_pending", "created_at", postgresql_where=text("status = 'pending'"))
```

### Covering Indexes

Include frequently selected columns:

```python
# Include subject in index to avoid table lookup
Index("ix_approvals_status_covering", "status", "created_at", postgresql_include=["subject"])
```

### GIN/GiST Indexes

For advanced queries:

```python
# Full-text search on text columns
Index("ix_incidents_title_fts", "title", postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"})
```

## References

- [PostgreSQL Index Documentation](https://www.postgresql.org/docs/current/indexes.html)
- [SQLAlchemy Index Documentation](https://docs.sqlalchemy.org/en/20/core/constraints.html#indexes)
- [Use The Index, Luke](https://use-the-index-luke.com/) - Comprehensive indexing guide
- [PostgreSQL Index Advisor](https://github.com/ankane/dexter) - Tool for identifying missing indexes

# Soft Deletes Documentation

## Overview

Soft deletes is a pattern where records are marked as deleted instead of being physically removed from the database. This allows preserving historical data, enabling audit trails, and supporting "undo" functionality.

## Implementation

### SoftDeleteMixin

The `SoftDeleteMixin` class in `app/models/mixins.py` provides soft delete functionality:

```python
from app.models.mixins import SoftDeleteMixin

class MyModel(SoftDeleteMixin, Base):
    __tablename__ = "my_table"
    # ... other columns
    # deleted_at column automatically provided by mixin
```

**Provided Fields:**
- `deleted_at`: Optional timestamp marking when the record was soft-deleted
- Index on `deleted_at` for efficient querying

**Provided Methods:**
- `soft_delete()`: Mark record as deleted
- `restore()`: Restore a soft-deleted record
- `is_deleted` (property): Check if record is soft-deleted

## Models with Soft Deletes

### Project

**Rationale:** Projects may be archived/deactivated but their historical data should be preserved for reporting and auditing.

**Usage:**
```python
from app.models.projects import Project

# Soft delete a project
project = session.query(Project).filter_by(key="my-project").first()
project.soft_delete()
session.commit()

# Query active (non-deleted) projects only
active_projects = session.query(Project).filter(Project.deleted_at == None).all()

# Restore a soft-deleted project
project.restore()
session.commit()
```

### Objective (OKR)

**Rationale:** OKRs are historical records that should be preserved for trend analysis and performance reviews.

**Usage:**
```python
from app.models.okr import Objective

# Archive old objectives
old_objective = session.query(Objective).filter_by(period="2023Q4").first()
old_objective.soft_delete()
session.commit()

# Query only active objectives
active_objectives = session.query(Objective).filter(
    Objective.deleted_at == None,
    Objective.status == "active"
).all()
```

## Query Patterns

### Basic Queries

```python
# Get all non-deleted records
active = session.query(Model).filter(Model.deleted_at == None).all()

# Get only deleted records
deleted = session.query(Model).filter(Model.deleted_at != None).all()

# Get all records (including deleted)
all_records = session.query(Model).all()
```

### With Additional Filters

```python
# Active projects by key
project = session.query(Project).filter(
    Project.key == "my-project",
    Project.deleted_at == None
).first()

# Active OKRs for current quarter
objectives = session.query(Objective).filter(
    Objective.period == "2025Q4",
    Objective.status == "active",
    Objective.deleted_at == None
).all()
```

### Count Active vs Deleted

```python
# Count active records
active_count = session.query(Project).filter(Project.deleted_at == None).count()

# Count deleted records
deleted_count = session.query(Project).filter(Project.deleted_at != None).count()
```

### Ordering by Deletion Date

```python
# Recently deleted records
recently_deleted = session.query(Project).filter(
    Project.deleted_at != None
).order_by(Project.deleted_at.desc()).limit(10).all()
```

## API Endpoints

### List Endpoints

When implementing list endpoints, **always exclude soft-deleted records by default**:

```python
@router.get("/projects")
def list_projects(
    include_deleted: bool = False,  # Optional query param
    db: Session = Depends(get_session)
):
    query = db.query(Project)

    if not include_deleted:
        query = query.filter(Project.deleted_at == None)

    return query.all()
```

### Delete Endpoint

Implement soft delete instead of hard delete:

```python
@router.delete("/projects/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_session)
):
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.deleted_at == None  # Ensure not already deleted
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.soft_delete()
    db.commit()

    return {"message": "Project deleted successfully"}
```

### Restore Endpoint

Allow restoring soft-deleted records:

```python
@router.post("/projects/{project_id}/restore")
def restore_project(
    project_id: int,
    db: Session = Depends(get_session)
):
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.deleted_at != None  # Must be soft-deleted
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Deleted project not found")

    project.restore()
    db.commit()

    return {"message": "Project restored successfully"}
```

## Best Practices

### 1. Always Filter by deleted_at in Queries

❌ **Don't:**
```python
# This includes soft-deleted records!
projects = session.query(Project).all()
```

✅ **Do:**
```python
# Explicitly filter out soft-deleted records
projects = session.query(Project).filter(Project.deleted_at == None).all()
```

### 2. Use Query Helpers

Create helper methods to reduce repetition:

```python
class Project(SoftDeleteMixin, Base):
    # ... columns ...

    @classmethod
    def query_active(cls, session):
        """Query only non-deleted projects."""
        return session.query(cls).filter(cls.deleted_at == None)

# Usage
active_projects = Project.query_active(session).all()
```

### 3. Document Soft Delete Behavior

In API documentation, clearly indicate:
- Which endpoints return soft-deleted records
- Which endpoints perform soft vs hard deletes
- How to include/exclude deleted records

### 4. Consider Cascade Behavior

When soft-deleting a parent record, decide whether to soft-delete or orphan child records:

**Option 1: Soft-delete children too**
```python
def soft_delete(self):
    """Soft delete this objective and all its key results."""
    self.deleted_at = datetime.now(UTC)
    for kr in self.key_results:
        if hasattr(kr, 'soft_delete'):
            kr.soft_delete()
```

**Option 2: Leave children active (orphaned)**
```python
# Default behavior - children remain active
# Parent's deleted_at is set, children's deleted_at remains NULL
```

### 5. Periodic Cleanup (Optional)

For compliance or storage concerns, permanently delete old soft-deleted records:

```python
# Delete records soft-deleted more than 90 days ago
cutoff_date = datetime.now(UTC) - timedelta(days=90)
old_deleted = session.query(Project).filter(
    Project.deleted_at < cutoff_date
).delete()
session.commit()
```

**Warning:** This is a hard delete and cannot be undone!

## When to Use Soft Deletes

### ✅ Use Soft Deletes For:

1. **Historical Data**
   - Financial records
   - Audit logs
   - Performance history (OKRs, metrics)

2. **User-Created Content**
   - Projects
   - Documents
   - User profiles

3. **Recoverable Deletions**
   - Items in "trash" folders
   - Deactivated accounts
   - Archived resources

### ❌ Don't Use Soft Deletes For:

1. **Truly Immutable Logs**
   - Event logs (just keep them)
   - Action logs (never delete)

2. **Temporary/Ephemeral Data**
   - Sessions
   - Cache entries
   - Temporary files

3. **High-Volume Tables**
   - Time-series data (use time-based retention instead)
   - Logs with millions of rows (partition and drop old partitions)

## Testing

### Unit Tests

```python
def test_soft_delete():
    """Test soft delete functionality."""
    project = Project(key="test", name="Test Project")
    db.add(project)
    db.commit()

    # Verify not deleted
    assert not project.is_deleted
    assert project.deleted_at is None

    # Soft delete
    project.soft_delete()
    db.commit()

    # Verify deleted
    assert project.is_deleted
    assert project.deleted_at is not None

    # Verify excluded from active queries
    active = db.query(Project).filter(Project.deleted_at == None).all()
    assert project not in active


def test_restore():
    """Test restoring soft-deleted record."""
    project = Project(key="test", name="Test Project")
    db.add(project)
    db.commit()

    # Soft delete
    project.soft_delete()
    db.commit()
    assert project.is_deleted

    # Restore
    project.restore()
    db.commit()
    assert not project.is_deleted
    assert project.deleted_at is None
```

### Integration Tests

```python
def test_list_excludes_deleted(client):
    """Test that list endpoint excludes soft-deleted records."""
    # Create active project
    client.post("/v1/projects", json={"key": "active", "name": "Active"})

    # Create and delete project
    client.post("/v1/projects", json={"key": "deleted", "name": "Deleted"})
    project = client.get("/v1/projects").json()[1]
    client.delete(f"/v1/projects/{project['id']}")

    # List should only return active project
    response = client.get("/v1/projects")
    assert len(response.json()) == 1
    assert response.json()[0]["key"] == "active"
```

## Migration

### Adding Soft Deletes to Existing Tables

```python
"""add_soft_deletes_to_projects

Revision ID: 0013
Revises: 0012
Create Date: 2025-10-21

"""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'

def upgrade():
    # Add deleted_at column (nullable, indexed)
    op.add_column('projects', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.execute('CREATE INDEX CONCURRENTLY ix_projects_deleted_at ON projects (deleted_at)')

def downgrade():
    op.drop_index('ix_projects_deleted_at', table_name='projects')
    op.drop_column('projects', 'deleted_at')
```

## Performance Considerations

### Index on deleted_at

The `SoftDeleteMixin` automatically creates an index on `deleted_at` for efficient filtering:

```sql
-- Fast query (uses index)
SELECT * FROM projects WHERE deleted_at IS NULL;

-- Fast query (uses index)
SELECT * FROM projects WHERE deleted_at IS NOT NULL;
```

### Composite Indexes

For frequently used query patterns, create composite indexes:

```python
# In model __table_args__
Index("ix_projects_key_deleted", "key", "deleted_at"),
```

This optimizes queries like:
```python
# Fast lookup: key + deleted_at filter
project = session.query(Project).filter(
    Project.key == "my-project",
    Project.deleted_at == None
).first()
```

### Table Size Impact

Soft deletes increase table size over time:

**Before soft deletes:**
- 10,000 active records = 10,000 rows

**After soft deletes (1 year):**
- 10,000 active + 5,000 deleted = 15,000 rows (+50%)

**Mitigation:**
- Periodic cleanup (hard delete old soft-deleted records)
- Table partitioning by deleted_at
- Archive to separate "deleted_X" table

## Monitoring

### Query to Find Soft-Deleted Records

```sql
-- Count of soft-deleted vs active records
SELECT
    COUNT(*) FILTER (WHERE deleted_at IS NULL) as active,
    COUNT(*) FILTER (WHERE deleted_at IS NOT NULL) as deleted,
    COUNT(*) as total
FROM projects;

-- Soft-deleted records by age
SELECT
    DATE_TRUNC('month', deleted_at) as month,
    COUNT(*) as deleted_count
FROM projects
WHERE deleted_at IS NOT NULL
GROUP BY month
ORDER BY month DESC;
```

### Alert on High Deletion Rate

```python
# Monitor deletion rate
recent_deletions = session.query(Project).filter(
    Project.deleted_at > datetime.now(UTC) - timedelta(hours=24)
).count()

if recent_deletions > 100:
    alert("High deletion rate: {} projects deleted in last 24h".format(recent_deletions))
```

## Troubleshooting

### Records Not Appearing in Queries

**Symptom:** Record exists in database but doesn't appear in query results.

**Cause:** Record is soft-deleted but query doesn't include deleted records.

**Solution:**
```python
# Check if record is soft-deleted
project = session.query(Project).filter(Project.key == "my-project").first()
if project and project.is_deleted:
    print(f"Project was soft-deleted at {project.deleted_at}")
```

### Unique Constraint Violations After Soft Delete

**Symptom:** Cannot create new record with same unique key as soft-deleted record.

**Cause:** Unique constraints apply to all rows, including soft-deleted ones.

**Solutions:**

**Option 1:** Use composite unique constraint (recommended)
```python
class Project(Base):
    __table_args__ = (
        # Unique constraint only for non-deleted records
        UniqueConstraint('key', 'deleted_at', name='uq_project_key_active'),
    )
```

**Option 2:** Modify key on soft delete
```python
def soft_delete(self):
    # Append timestamp to make key unique
    self.key = f"{self.key}_deleted_{int(datetime.now(UTC).timestamp())}"
    self.deleted_at = datetime.now(UTC)
```

## References

- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Soft Delete Pattern](https://www.martinfowler.com/eaaCatalog/softDelete.html)
- [Database Refactoring](https://databaserefactoring.com/)

# Alembic Database Migrations Guide

## Overview

The EM Agent Gateway uses [Alembic](https://alembic.sqlalchemy.org/) for database schema migrations. Alembic provides version control for your database schema, allowing you to track changes, upgrade/downgrade schemas, and maintain consistency across environments.

## Directory Structure

```
services/gateway/
├── alembic.ini                    # Alembic configuration
├── migrations/
│   ├── env.py                     # Migration environment configuration
│   └── versions/                  # Migration scripts
│       ├── 0001_initial.py
│       ├── 0002_projects.py
│       ├── ...
│       └── 0012_add_database_indexes.py
```

## Configuration

### alembic.ini

The main configuration file. Key settings:

```ini
[alembic]
script_location = migrations        # Location of migration scripts
sqlalchemy.url = postgresql+psycopg://postgres:postgres@localhost:5432/postgres
```

**Note:** The `sqlalchemy.url` in `alembic.ini` is overridden by the `DATABASE_URL` environment variable in `env.py`.

### migrations/env.py

The migration environment script. This file:
- Loads all SQLAlchemy models for auto-detection
- Reads `DATABASE_URL` from environment
- Configures online and offline migration modes
- Sets `target_metadata` for auto-generation

## Common Operations

### 1. Check Current Database Version

```bash
cd services/gateway
alembic current
```

**Output example:**
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
0012 (head)
```

### 2. View Migration History

```bash
alembic history
```

**Output example:**
```
0012 -> head, add_database_indexes_for_performance
0011 -> 0012, okr
0010 -> 0011, onboarding
...
```

### 3. Upgrade Database to Latest

```bash
# Upgrade to latest (head)
alembic upgrade head

# Upgrade to specific revision
alembic upgrade 0012

# Upgrade by relative steps
alembic upgrade +2  # Upgrade 2 versions forward
```

**Example output:**
```
INFO  [alembic.runtime.migration] Running upgrade 0011 -> 0012, add_database_indexes_for_performance
```

### 4. Downgrade Database

```bash
# Downgrade to specific revision
alembic downgrade 0010

# Downgrade by relative steps
alembic downgrade -1  # Downgrade 1 version back

# Downgrade to base (empty database)
alembic downgrade base
```

**⚠️ Warning:** Downgrading can result in data loss. Always backup before downgrading.

### 5. Create New Migration

#### Auto-generate from model changes

```bash
# Alembic will detect changes between models and database
alembic revision --autogenerate -m "add_user_roles"
```

**Alembic detects:**
- New tables
- Removed tables
- New columns
- Removed columns
- Changed column types
- New indexes
- New constraints

**Alembic does NOT detect:**
- Table or column renames (use `op.rename_table` or `op.alter_column` manually)
- Changes to default values
- Changes to server defaults

#### Manually create empty migration

```bash
alembic revision -m "custom_data_migration"
```

This creates an empty migration template that you fill in manually.

### 6. View SQL Without Executing

```bash
# Generate SQL for upgrade
alembic upgrade head --sql

# Generate SQL for downgrade
alembic downgrade -1 --sql
```

Useful for:
- Reviewing changes before applying
- Applying migrations manually
- Generating deployment scripts

## Writing Migrations

### Migration Template

```python
"""description

Revision ID: 0013
Revises: 0012
Create Date: 2025-10-21

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None

def upgrade():
    """Apply changes to database."""
    pass

def downgrade():
    """Revert changes to database."""
    pass
```

### Common Operations

#### Create Table

```python
def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

def downgrade():
    op.drop_table('users')
```

#### Add Column

```python
def upgrade():
    op.add_column('users', sa.Column('role', sa.String(32), nullable=True))

def downgrade():
    op.drop_column('users', 'role')
```

#### Create Index

```python
def upgrade():
    # Use CONCURRENTLY to avoid table locks (PostgreSQL only)
    op.execute('CREATE INDEX CONCURRENTLY ix_users_email ON users (email)')

def downgrade():
    op.drop_index('ix_users_email', table_name='users')
```

**Why CONCURRENTLY?**
- Allows reads and writes to continue during index creation
- Critical for production databases
- Takes longer but doesn't block traffic
- PostgreSQL-specific (omit for other databases)

#### Add Foreign Key

```python
def upgrade():
    op.create_foreign_key(
        'fk_posts_user_id',
        'posts',     # source table
        'users',     # reference table
        ['user_id'], # source columns
        ['id']       # reference columns
    )

def downgrade():
    op.drop_constraint('fk_posts_user_id', 'posts', type_='foreignkey')
```

#### Rename Column

```python
def upgrade():
    op.alter_column('users', 'name', new_column_name='full_name')

def downgrade():
    op.alter_column('users', 'full_name', new_column_name='name')
```

#### Change Column Type

```python
def upgrade():
    op.alter_column('users', 'role',
                    existing_type=sa.String(32),
                    type_=sa.String(64),
                    existing_nullable=True)

def downgrade():
    op.alter_column('users', 'role',
                    existing_type=sa.String(64),
                    type_=sa.String(32),
                    existing_nullable=True)
```

#### Data Migration

```python
def upgrade():
    # Get database connection
    conn = op.get_bind()

    # Execute raw SQL
    conn.execute(sa.text("""
        UPDATE users
        SET role = 'user'
        WHERE role IS NULL
    """))

def downgrade():
    # Usually not reversible
    pass
```

### Best Practices

#### 1. Always Test Migrations

```bash
# Test upgrade
alembic upgrade head

# Test downgrade
alembic downgrade -1

# Test re-upgrade
alembic upgrade head
```

#### 2. Use Transactions

Alembic automatically wraps migrations in transactions (PostgreSQL):

```python
# This is automatic:
# BEGIN;
# ... your migration ...
# COMMIT;
```

If something fails, changes are rolled back.

#### 3. Make Migrations Reversible

Always implement both `upgrade()` and `downgrade()`:

```python
def upgrade():
    op.add_column('users', sa.Column('verified', sa.Boolean(), default=False))

def downgrade():
    op.drop_column('users', 'verified')
```

#### 4. One Logical Change Per Migration

❌ **Don't:**
```python
def upgrade():
    op.create_table('users', ...)
    op.create_table('posts', ...)
    op.add_column('projects', ...)  # Unrelated change
```

✅ **Do:**
```python
# Migration 1: Create users table
# Migration 2: Create posts table
# Migration 3: Add column to projects
```

#### 5. Document Complex Migrations

```python
"""Add user roles and permissions

Revision ID: 0013
Revises: 0012
Create Date: 2025-10-21

This migration:
1. Adds 'role' column to users table
2. Creates 'permissions' table
3. Backfills existing users with 'user' role
4. Creates indexes for performance

Related: Issue #123
"""
```

#### 6. Review Auto-generated Migrations

**Always review** migrations created with `--autogenerate`:

```python
# Alembic might generate unnecessary changes
# Review and remove false positives before committing
```

Common false positives:
- Server default changes
- Unrelated type changes
- Metadata changes

## Production Deployment

### Pre-deployment Checklist

- [ ] Migration tested on development database
- [ ] Migration tested on staging database
- [ ] Backup of production database created
- [ ] Downgrade path tested
- [ ] Team notified of maintenance window (if needed)
- [ ] Monitoring set up for migration progress

### Deployment Process

```bash
# 1. Backup database
pg_dump -h localhost -U postgres postgres > backup_$(date +%Y%m%d_%H%M%S).sql

# 2. Check current version
alembic current

# 3. Review migration SQL
alembic upgrade head --sql > migration.sql
less migration.sql

# 4. Apply migration
alembic upgrade head

# 5. Verify migration
alembic current
# Should show: 0012 (head)

# 6. Verify application works
curl http://localhost:8000/v1/health
```

### Zero-Downtime Migrations

For large tables or high-traffic production systems:

#### Phase 1: Add (Backward Compatible)

```python
# Migration: Add new column (nullable)
def upgrade():
    op.add_column('users', sa.Column('new_email', sa.String(255), nullable=True))
```

**Deploy:** Application ignores new column, continues using old column.

#### Phase 2: Backfill

```python
# Migration: Copy data from old to new column
def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE users SET new_email = email WHERE new_email IS NULL"))
```

**Deploy:** Application writes to both columns, reads from old column.

#### Phase 3: Switch

```python
# Migration: Make new column non-nullable, add index
def upgrade():
    op.alter_column('users', 'new_email', nullable=False)
    op.execute('CREATE UNIQUE INDEX CONCURRENTLY ix_users_new_email ON users (new_email)')
```

**Deploy:** Application switches to read from new column.

#### Phase 4: Cleanup

```python
# Migration: Drop old column
def upgrade():
    op.drop_column('users', 'email')
    op.alter_column('users', 'new_email', new_column_name='email')
```

**Deploy:** Old column removed.

## Troubleshooting

### Migration Fails Mid-way

**Symptom:** Migration partially applied, database in inconsistent state.

**Solution:**
```bash
# Check current version (may show partial state)
alembic current

# If transaction rolled back (PostgreSQL):
# Database is consistent, retry migration
alembic upgrade head

# If transaction committed partially (rare):
# Manually fix database to match expected state
# Then stamp version
alembic stamp 0012
```

### "Can't locate revision" Error

**Symptom:**
```
sqlalchemy.exc.CommandError: Can't locate revision identified by 'abc123'
```

**Cause:** Migration file missing or revision ID mismatch.

**Solution:**
```bash
# Check migration history
alembic history

# Verify all migration files exist
ls migrations/versions/

# Re-clone repository if files missing
```

### Conflicting Migrations

**Symptom:**
```
Multiple head revisions are present
```

**Cause:** Two developers created migrations from the same parent.

**Solution:**
```bash
# Merge heads
alembic merge -m "merge_branches" [rev1] [rev2]
```

### Auto-generate Detects No Changes

**Symptom:** `alembic revision --autogenerate` creates empty migration despite model changes.

**Possible causes:**
1. Models not imported in `env.py`
2. Database already has the changes
3. `target_metadata` not set in `env.py`

**Solution:**
```python
# In migrations/env.py
from app.db import Base
from app.models.users import User  # Import all models

target_metadata = Base.metadata  # Set this!
```

## Environment Variables

```bash
# Database URL (overrides alembic.ini)
export DATABASE_URL="postgresql+psycopg://user:pass@host:5432/dbname"

# Run migrations
alembic upgrade head
```

## Integration with Application

### Check Database Version on Startup

```python
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext

def check_migration_status():
    """Verify database is at latest migration."""
    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)

    with engine.begin() as conn:
        context = MigrationContext.configure(conn)
        current = context.get_current_revision()
        head = script.get_current_head()

        if current != head:
            raise RuntimeError(
                f"Database migration mismatch! "
                f"Current: {current}, Expected: {head}. "
                f"Run 'alembic upgrade head' before starting."
            )
```

### Auto-upgrade on Startup (Development Only)

```python
# DO NOT use in production - migrations should be controlled
from alembic import command
from alembic.config import Config

def auto_upgrade():
    """Auto-upgrade database (dev only!)."""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
```

## References

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Alembic Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Alembic Cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html)
- [PostgreSQL CREATE INDEX CONCURRENTLY](https://www.postgresql.org/docs/current/sql-createindex.html#SQL-CREATEINDEX-CONCURRENTLY)
- [Zero-Downtime Migrations](https://www.braintreepayments.com/blog/safe-operations-for-high-volume-postgresql/)

## Quick Reference

```bash
# View current version
alembic current

# View history
alembic history

# Upgrade to latest
alembic upgrade head

# Downgrade one version
alembic downgrade -1

# Create new migration (auto)
alembic revision --autogenerate -m "description"

# Create new migration (manual)
alembic revision -m "description"

# Show SQL without executing
alembic upgrade head --sql

# Stamp database with specific version (careful!)
alembic stamp 0012
```

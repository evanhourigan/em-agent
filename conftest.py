"""
Root conftest.py for pytest configuration and shared fixtures.
"""
import os
import pytest
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# Set test environment BEFORE importing any app code
os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["TESTING"] = "true"

# Disable background workers that interfere with SQLite tests
os.environ["WORKFLOW_RUNNER_ENABLED"] = "false"
os.environ["SIGNAL_EVALUATOR_ENABLED"] = "false"
os.environ["RETENTION_ENABLED"] = "false"

# Set JWT secret for auth tests (32+ chars required)
os.environ["JWT_SECRET_KEY"] = "test_secret_key_for_testing_purposes_only_do_not_use_in_production"


@pytest.fixture(scope="session")
def test_db_engine():
    """
    Create a test database engine using SQLite in-memory.
    Session-scoped so it's created once for all tests.
    """
    from services.gateway.app.db import Base
    # Import all models so they're registered with Base.metadata
    from services.gateway.app.models.projects import Project
    from services.gateway.app.models.identities import Identity
    from services.gateway.app.models.events import EventRaw
    from services.gateway.app.models.approvals import Approval
    from services.gateway.app.models.workflow_jobs import WorkflowJob
    from services.gateway.app.models.action_log import ActionLog
    from services.gateway.app.models.incidents import Incident, IncidentTimeline
    from services.gateway.app.models.onboarding import OnboardingPlan, OnboardingTask
    from services.gateway.app.models.okr import Objective, KeyResult

    # Use in-memory SQLite for tests (fast and isolated)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # Required for SQLite in-memory
        echo=False,
    )

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Cleanup
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(test_db_engine) -> Generator[Session, None, None]:
    """
    Create a new database session for a test.
    Function-scoped so each test gets a fresh session with rollback.
    """
    connection = test_db_engine.connect()
    transaction = connection.begin()

    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()

    # Begin a nested transaction (using SAVEPOINT)
    nested = connection.begin_nested()

    # If the application code calls session.commit(), it will only commit
    # the nested transaction (SAVEPOINT), not the outer transaction
    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        if transaction.nested and not transaction._parent.nested:
            session.expire_all()
            session.begin_nested()

    yield session

    # Rollback everything (test changes are discarded)
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(test_db_engine, db_session: Session) -> Generator[TestClient, None, None]:
    """
    Create a FastAPI test client with database overrides.
    """
    # Must import here to ensure test environment is set
    import services.gateway.app.db as db_module
    from services.gateway.app.main import app
    from services.gateway.app.api.deps import get_db_session

    # Override the global engine and sessionmaker
    original_engine = db_module._engine
    original_sessionmaker = db_module._SessionLocal

    db_module._engine = test_db_engine
    db_module._SessionLocal = sessionmaker(bind=test_db_engine, expire_on_commit=False)

    # Override the database session dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # Don't close, managed by db_session fixture

    app.dependency_overrides[get_db_session] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    # Restore original state
    app.dependency_overrides.clear()
    db_module._engine = original_engine
    db_module._SessionLocal = original_sessionmaker


@pytest.fixture
def sample_approval_data():
    """Sample data for approval tests."""
    return {
        "subject": "deploy:test-service",
        "action": "deploy",
        "reason": "Testing deployment approval flow",
        "payload": {
            "service": "test-service",
            "version": "1.0.0",
            "environment": "staging"
        }
    }


@pytest.fixture
def sample_workflow_data():
    """Sample data for workflow tests."""
    return {
        "rule_kind": "test_rule",
        "subject": "test:123",
        "action": "test_action",
        "payload": {"key": "value"}
    }


@pytest.fixture(autouse=True)
def reset_environment():
    """Reset environment variables after each test."""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_slack_client(mocker):
    """Mock SlackClient for tests that don't need real Slack integration."""
    mock = mocker.patch("services.gateway.app.services.slack_client.SlackClient")
    mock.return_value.post_text.return_value = {"ok": True, "message": {"ts": "1234567890.123456"}}
    return mock


@pytest.fixture
def mock_temporal_client(mocker):
    """Mock Temporal client for tests that don't need real Temporal."""
    mock = mocker.patch("temporalio.client.Client")
    return mock

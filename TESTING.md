# Testing Guide

## Quick Start

### Install Dependencies

```bash
# Install main dependencies
pip install -r services/gateway/requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt
```

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov

# Run specific test file
pytest tests/gateway/test_approvals.py

# Run specific test class
pytest tests/gateway/test_approvals.py::TestProposeApproval

# Run specific test
pytest tests/gateway/test_approvals.py::TestProposeApproval::test_propose_approval_success

# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run tests in parallel (faster)
pytest -n auto
```

### Code Quality Checks

```bash
# Run linter
ruff check services/gateway/app

# Auto-fix linting issues
ruff check --fix services/gateway/app

# Format code
black services/gateway/app

# Type checking
mypy services/gateway/app --ignore-missing-imports
```

### Pre-commit Hooks

Install pre-commit hooks to automatically check code before commits:

```bash
# Install hooks
pre-commit install

# Run hooks manually
pre-commit run --all-files
```

## Test Organization

Tests are organized by service and type:

```
tests/
├── gateway/           # Gateway service tests
│   ├── test_approvals.py
│   ├── test_workflows.py
│   └── ...
├── rag/              # RAG service tests
├── connectors/       # Connector tests
└── conftest.py       # Shared fixtures
```

## Test Markers

- `@pytest.mark.unit` - Fast, isolated unit tests
- `@pytest.mark.integration` - Tests requiring external dependencies
- `@pytest.mark.e2e` - End-to-end tests
- `@pytest.mark.slow` - Slow running tests (> 1 second)

## Writing Tests

### Unit Test Example

```python
import pytest
from fastapi.testclient import TestClient

@pytest.mark.unit
def test_list_approvals_empty(client: TestClient, db_session):
    """Test listing approvals when database is empty."""
    response = client.get("/v1/approvals")

    assert response.status_code == 200
    assert response.json() == []
```

### Integration Test Example

```python
import pytest
from unittest.mock import patch

@pytest.mark.integration
def test_slack_notification(client: TestClient, db_session):
    """Test Slack notification integration."""
    with patch("services.gateway.app.services.slack_client.SlackClient") as mock:
        mock.return_value.post_blocks.return_value = {"ok": True}

        response = client.post("/v1/approvals/1/notify")
        assert response.status_code == 200
```

## Fixtures

Common fixtures available in `conftest.py`:

- `db_session` - Database session with automatic rollback
- `client` - FastAPI TestClient with database override
- `sample_approval_data` - Sample approval payload
- `mock_slack_client` - Mocked Slack client
- `mock_temporal_client` - Mocked Temporal client

## Coverage Goals

- **Overall**: 70%+ coverage required to pass CI
- **Critical paths**: 85%+ coverage for approvals, workflows, core APIs
- **Target**: 85%+ coverage for production readiness

## CI/CD

Tests run automatically on:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop`

CI includes:
- Linting (ruff)
- Formatting check (black)
- Type checking (mypy)
- Unit tests with coverage
- Integration tests

## Troubleshooting

### Tests fail with database errors

Ensure PostgreSQL is running or use SQLite (default in tests):

```bash
# Tests use in-memory SQLite by default
pytest
```

### Import errors

Ensure you're in the project root and dependencies are installed:

```bash
pip install -r requirements-dev.txt
```

### Slow tests

Run tests in parallel:

```bash
pytest -n auto
```

Or skip slow tests:

```bash
pytest -m "not slow"
```

## Next Steps

1. Run `pytest` to verify all tests pass
2. Install pre-commit hooks: `pre-commit install`
3. Check coverage: `pytest --cov --cov-report=html` and open `htmlcov/index.html`
4. Write tests for new features before implementing them (TDD)

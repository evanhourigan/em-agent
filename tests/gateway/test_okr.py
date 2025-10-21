"""
Tests for OKR router.

Basic validation tests to ensure refactored endpoints work correctly.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from services.gateway.app.models.okr import Objective, KeyResult


class TestCreateObjective:
    """Test objective creation endpoint."""

    def test_create_objective_success(self, client: TestClient, db_session: Session):
        """Test creating an objective successfully."""
        # Clean database
        db_session.query(KeyResult).delete()
        db_session.query(Objective).delete()
        db_session.commit()

        payload = {
            "title": "Improve API performance by 50%",
            "owner": "Platform Team",
            "period": "Q1 2025"
        }

        response = client.post("/v1/okr/objectives", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Improve API performance by 50%"
        assert "id" in data

        # Verify objective was created
        objectives = db_session.query(Objective).all()
        assert len(objectives) == 1
        assert objectives[0].owner == "Platform Team"
        assert objectives[0].period == "Q1 2025"

    def test_create_objective_minimal(self, client: TestClient, db_session: Session):
        """Test creating objective with minimal data."""
        # Clean database
        db_session.query(KeyResult).delete()
        db_session.query(Objective).delete()
        db_session.commit()

        payload = {
            "title": "Increase user engagement"
        }

        response = client.post("/v1/okr/objectives", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Increase user engagement"

    def test_create_objective_empty_title(self, client: TestClient, db_session: Session):
        """Test that empty title returns validation error."""
        payload = {
            "title": "   "  # Whitespace only
        }

        response = client.post("/v1/okr/objectives", json=payload)

        # Pydantic validation returns 422
        assert response.status_code == 422

    def test_create_objective_missing_title(self, client: TestClient, db_session: Session):
        """Test that missing title returns validation error."""
        payload = {
            "owner": "Team A"
        }

        response = client.post("/v1/okr/objectives", json=payload)

        # Pydantic validation returns 422
        assert response.status_code == 422


class TestAddKeyResult:
    """Test adding key results to objectives."""

    def test_add_key_result_success(self, client: TestClient, db_session: Session):
        """Test adding a key result to an objective."""
        # Clean database
        db_session.query(KeyResult).delete()
        db_session.query(Objective).delete()
        db_session.commit()

        # Create objective
        objective = Objective(title="Test objective", owner="Team A", period="Q1 2025")
        db_session.add(objective)
        db_session.commit()
        db_session.refresh(objective)

        payload = {
            "title": "Reduce API response time to <200ms",
            "target": 200,
            "unit": "ms"
        }

        response = client.post(f"/v1/okr/objectives/{objective.id}/krs", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "id" in data

        # Verify key result was created
        krs = db_session.query(KeyResult).filter_by(objective_id=objective.id).all()
        assert len(krs) == 1
        assert krs[0].title == "Reduce API response time to <200ms"
        assert krs[0].target == 200
        assert krs[0].unit == "ms"

    def test_add_key_result_minimal(self, client: TestClient, db_session: Session):
        """Test adding key result with minimal data."""
        # Clean database
        db_session.query(KeyResult).delete()
        db_session.query(Objective).delete()
        db_session.commit()

        objective = Objective(title="Test objective")
        db_session.add(objective)
        db_session.commit()
        db_session.refresh(objective)

        payload = {
            "title": "Launch new feature"
        }

        response = client.post(f"/v1/okr/objectives/{objective.id}/krs", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "id" in data

    def test_add_key_result_objective_not_found(self, client: TestClient, db_session: Session):
        """Test adding key result to non-existent objective returns 404."""
        payload = {
            "title": "Test KR"
        }

        response = client.post("/v1/okr/objectives/99999/krs", json=payload)

        assert response.status_code == 404

    def test_add_key_result_empty_title(self, client: TestClient, db_session: Session):
        """Test that empty title returns validation error."""
        # Clean database
        db_session.query(KeyResult).delete()
        db_session.query(Objective).delete()
        db_session.commit()

        objective = Objective(title="Test objective")
        db_session.add(objective)
        db_session.commit()
        db_session.refresh(objective)

        payload = {
            "title": "   "  # Whitespace only
        }

        response = client.post(f"/v1/okr/objectives/{objective.id}/krs", json=payload)

        # Pydantic validation returns 422
        assert response.status_code == 422


class TestUpdateProgress:
    """Test key result progress update endpoint."""

    def test_update_progress_success(self, client: TestClient, db_session: Session):
        """Test updating key result progress."""
        # Clean database
        db_session.query(KeyResult).delete()
        db_session.query(Objective).delete()
        db_session.commit()

        # Create objective and key result
        objective = Objective(title="Test objective")
        db_session.add(objective)
        db_session.commit()
        db_session.refresh(objective)

        kr = KeyResult(
            objective_id=objective.id,
            title="Test KR",
            target=100,
            current=0
        )
        db_session.add(kr)
        db_session.commit()
        db_session.refresh(kr)

        payload = {
            "current": 75
        }

        response = client.post(f"/v1/okr/krs/{kr.id}/progress", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

        # Verify progress was updated
        db_session.refresh(kr)
        assert kr.current == 75

    def test_update_progress_kr_not_found(self, client: TestClient, db_session: Session):
        """Test updating progress on non-existent key result returns 404."""
        payload = {
            "current": 50
        }

        response = client.post("/v1/okr/krs/99999/progress", json=payload)

        assert response.status_code == 404

    def test_update_progress_missing_current(self, client: TestClient, db_session: Session):
        """Test that missing current value returns validation error."""
        # Clean database
        db_session.query(KeyResult).delete()
        db_session.query(Objective).delete()
        db_session.commit()

        objective = Objective(title="Test objective")
        db_session.add(objective)
        db_session.commit()

        kr = KeyResult(objective_id=objective.id, title="Test KR")
        db_session.add(kr)
        db_session.commit()
        db_session.refresh(kr)

        payload = {}

        response = client.post(f"/v1/okr/krs/{kr.id}/progress", json=payload)

        # Pydantic validation returns 422
        assert response.status_code == 422


class TestListObjectives:
    """Test objectives listing endpoint."""

    def test_list_objectives_empty(self, client: TestClient, db_session: Session):
        """Test listing objectives when none exist."""
        # Clean database
        db_session.query(KeyResult).delete()
        db_session.query(Objective).delete()
        db_session.commit()

        response = client.get("/v1/okr/objectives")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_objectives_returns_objectives(self, client: TestClient, db_session: Session):
        """Test listing objectives returns all objectives."""
        # Clean database
        db_session.query(KeyResult).delete()
        db_session.query(Objective).delete()
        db_session.commit()

        # Create test objectives
        obj1 = Objective(title="Objective 1", owner="Team A", period="Q1 2025")
        obj2 = Objective(title="Objective 2", owner="Team B", period="Q2 2025")
        db_session.add_all([obj1, obj2])
        db_session.commit()

        response = client.get("/v1/okr/objectives")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all("id" in obj for obj in data)
        assert all("title" in obj for obj in data)
        assert all("owner" in obj for obj in data)
        assert all("period" in obj for obj in data)

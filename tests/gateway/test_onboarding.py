"""Tests for onboarding endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


class TestCreatePlan:
    """Tests for POST /v1/onboarding/plans endpoint."""

    def test_create_plan_with_title(self, client: TestClient, db_session: Session):
        """Test creating an onboarding plan with custom title."""
        from services.gateway.app.models.onboarding import OnboardingPlan

        # Clean database
        db_session.query(OnboardingPlan).delete()
        db_session.commit()

        payload = {"title": "Engineering Onboarding"}

        response = client.post("/v1/onboarding/plans", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Engineering Onboarding"
        assert data["status"] == "active"
        assert "id" in data

        # Verify in database
        plan = db_session.query(OnboardingPlan).filter_by(id=data["id"]).first()
        assert plan is not None
        assert plan.title == "Engineering Onboarding"
        assert plan.status == "active"

    def test_create_plan_without_title(self, client: TestClient, db_session: Session):
        """Test creating plan without title uses default."""
        from services.gateway.app.models.onboarding import OnboardingPlan

        db_session.query(OnboardingPlan).delete()
        db_session.commit()

        payload = {}

        response = client.post("/v1/onboarding/plans", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Hire Plan"  # Default title

    def test_create_plan_with_empty_title(self, client: TestClient):
        """Test creating plan with empty title uses default."""
        payload = {"title": ""}

        response = client.post("/v1/onboarding/plans", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Hire Plan"

    def test_create_plan_with_whitespace_title(self, client: TestClient):
        """Test creating plan with whitespace-only title uses default."""
        payload = {"title": "   "}

        response = client.post("/v1/onboarding/plans", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Hire Plan"

    def test_create_plan_trims_whitespace(self, client: TestClient):
        """Test that title whitespace is trimmed."""
        payload = {"title": "  Sales Onboarding  "}

        response = client.post("/v1/onboarding/plans", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Sales Onboarding"


class TestAddTask:
    """Tests for POST /v1/onboarding/plans/{id}/tasks endpoint."""

    def test_add_task_minimal(self, client: TestClient, db_session: Session):
        """Test adding task with only required fields."""
        from services.gateway.app.models.onboarding import OnboardingPlan, OnboardingTask

        # Clean and create plan
        db_session.query(OnboardingTask).delete()
        db_session.query(OnboardingPlan).delete()
        plan = OnboardingPlan(title="Test Plan")
        db_session.add(plan)
        db_session.commit()

        payload = {"title": "Complete training"}

        response = client.post(f"/v1/onboarding/plans/{plan.id}/tasks", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data

        # Verify in database
        task = db_session.query(OnboardingTask).filter_by(id=data["id"]).first()
        assert task is not None
        assert task.title == "Complete training"
        assert task.plan_id == plan.id
        assert task.status == "todo"
        assert task.assignee is None
        assert task.due_date is None

    def test_add_task_with_all_fields(self, client: TestClient, db_session: Session):
        """Test adding task with all optional fields."""
        from services.gateway.app.models.onboarding import OnboardingPlan, OnboardingTask

        # Clean and create plan
        db_session.query(OnboardingTask).delete()
        db_session.query(OnboardingPlan).delete()
        plan = OnboardingPlan(title="Test Plan")
        db_session.add(plan)
        db_session.commit()

        payload = {
            "title": "Setup laptop",
            "assignee": "john@example.com",
            "due_date": "2025-01-15"
        }

        response = client.post(f"/v1/onboarding/plans/{plan.id}/tasks", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data

        # Verify in database
        task = db_session.query(OnboardingTask).filter_by(id=data["id"]).first()
        assert task is not None
        assert task.title == "Setup laptop"
        assert task.assignee == "john@example.com"
        assert task.due_date is not None
        # Compare as string since it's a date object
        assert str(task.due_date) == "2025-01-15"

    def test_add_task_missing_title(self, client: TestClient, db_session: Session):
        """Test that missing title returns 400."""
        from services.gateway.app.models.onboarding import OnboardingPlan

        db_session.query(OnboardingPlan).delete()
        plan = OnboardingPlan(title="Test Plan")
        db_session.add(plan)
        db_session.commit()

        payload = {}  # No title

        response = client.post(f"/v1/onboarding/plans/{plan.id}/tasks", json=payload)
        assert response.status_code == 400
        assert "title required" in response.json()["detail"]

    def test_add_task_empty_title(self, client: TestClient, db_session: Session):
        """Test that empty title returns 400."""
        from services.gateway.app.models.onboarding import OnboardingPlan

        db_session.query(OnboardingPlan).delete()
        plan = OnboardingPlan(title="Test Plan")
        db_session.add(plan)
        db_session.commit()

        payload = {"title": ""}

        response = client.post(f"/v1/onboarding/plans/{plan.id}/tasks", json=payload)
        assert response.status_code == 400

    def test_add_task_whitespace_title(self, client: TestClient, db_session: Session):
        """Test that whitespace-only title returns 400."""
        from services.gateway.app.models.onboarding import OnboardingPlan

        db_session.query(OnboardingPlan).delete()
        plan = OnboardingPlan(title="Test Plan")
        db_session.add(plan)
        db_session.commit()

        payload = {"title": "   "}

        response = client.post(f"/v1/onboarding/plans/{plan.id}/tasks", json=payload)
        assert response.status_code == 400

    def test_add_task_plan_not_found(self, client: TestClient, db_session: Session):
        """Test adding task to non-existent plan returns 404."""
        from services.gateway.app.models.onboarding import OnboardingPlan

        db_session.query(OnboardingPlan).delete()
        db_session.commit()

        payload = {"title": "Test task"}

        response = client.post("/v1/onboarding/plans/99999/tasks", json=payload)
        assert response.status_code == 404
        assert "plan not found" in response.json()["detail"]

    def test_add_task_invalid_due_date(self, client: TestClient, db_session: Session):
        """Test that invalid due_date is silently ignored."""
        from services.gateway.app.models.onboarding import OnboardingPlan, OnboardingTask

        db_session.query(OnboardingTask).delete()
        db_session.query(OnboardingPlan).delete()
        plan = OnboardingPlan(title="Test Plan")
        db_session.add(plan)
        db_session.commit()

        payload = {
            "title": "Test task",
            "due_date": "invalid-date"
        }

        response = client.post(f"/v1/onboarding/plans/{plan.id}/tasks", json=payload)
        assert response.status_code == 200
        data = response.json()

        # Verify due_date is None (invalid date ignored)
        task = db_session.query(OnboardingTask).filter_by(id=data["id"]).first()
        assert task.due_date is None


class TestMarkDone:
    """Tests for POST /v1/onboarding/tasks/{id}/done endpoint."""

    def test_mark_done_success(self, client: TestClient, db_session: Session):
        """Test marking a task as done."""
        from services.gateway.app.models.onboarding import OnboardingPlan, OnboardingTask

        # Clean and create plan with task
        db_session.query(OnboardingTask).delete()
        db_session.query(OnboardingPlan).delete()
        plan = OnboardingPlan(title="Test Plan")
        db_session.add(plan)
        db_session.commit()

        task = OnboardingTask(plan_id=plan.id, title="Test task", status="todo")
        db_session.add(task)
        db_session.commit()
        task_id = task.id

        response = client.post(f"/v1/onboarding/tasks/{task_id}/done")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

        # Verify task is marked done
        db_session.expire(task)
        updated_task = db_session.query(OnboardingTask).filter_by(id=task_id).first()
        assert updated_task.status == "done"
        assert updated_task.completed_at is not None

    def test_mark_done_task_not_found(self, client: TestClient, db_session: Session):
        """Test marking non-existent task returns 404."""
        from services.gateway.app.models.onboarding import OnboardingTask

        db_session.query(OnboardingTask).delete()
        db_session.commit()

        response = client.post("/v1/onboarding/tasks/99999/done")
        assert response.status_code == 404
        assert "task not found" in response.json()["detail"]


class TestListPlans:
    """Tests for GET /v1/onboarding/plans endpoint."""

    def test_list_plans_empty(self, client: TestClient, db_session: Session):
        """Test listing plans when none exist."""
        from services.gateway.app.models.onboarding import OnboardingPlan

        db_session.query(OnboardingPlan).delete()
        db_session.commit()

        response = client.get("/v1/onboarding/plans")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_plans_returns_all(self, client: TestClient, db_session: Session):
        """Test listing multiple plans."""
        from services.gateway.app.models.onboarding import OnboardingPlan

        # Clean and create plans
        db_session.query(OnboardingPlan).delete()
        plan1 = OnboardingPlan(title="Plan 1")
        plan2 = OnboardingPlan(title="Plan 2")
        plan3 = OnboardingPlan(title="Plan 3")
        db_session.add_all([plan1, plan2, plan3])
        db_session.commit()

        response = client.get("/v1/onboarding/plans")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

        # Check all plans are present
        titles = {p["title"] for p in data}
        assert titles == {"Plan 1", "Plan 2", "Plan 3"}

    def test_list_plans_ordered_by_id_desc(self, client: TestClient, db_session: Session):
        """Test that plans are ordered by id descending (newest first)."""
        from services.gateway.app.models.onboarding import OnboardingPlan

        # Clean and create plans
        db_session.query(OnboardingPlan).delete()
        plan1 = OnboardingPlan(title="Plan 1")
        plan2 = OnboardingPlan(title="Plan 2")
        plan3 = OnboardingPlan(title="Plan 3")
        db_session.add_all([plan1, plan2, plan3])
        db_session.commit()

        response = client.get("/v1/onboarding/plans")
        assert response.status_code == 200
        data = response.json()

        # Verify descending order (newest first)
        ids = [p["id"] for p in data]
        assert ids == sorted(ids, reverse=True)

    def test_list_plans_includes_status(self, client: TestClient, db_session: Session):
        """Test that returned plans include status field."""
        from services.gateway.app.models.onboarding import OnboardingPlan

        db_session.query(OnboardingPlan).delete()
        plan = OnboardingPlan(title="Test Plan", status="active")
        db_session.add(plan)
        db_session.commit()

        response = client.get("/v1/onboarding/plans")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "active"
        assert data[0]["title"] == "Test Plan"

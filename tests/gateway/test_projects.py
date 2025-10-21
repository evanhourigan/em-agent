"""Tests for projects endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


class TestListProjects:
    """Tests for GET /v1/projects endpoint."""

    def test_list_projects_empty(self, client: TestClient, db_session: Session):
        """Test listing projects when none exist."""
        from services.gateway.app.models.projects import Project

        # Clean database
        db_session.query(Project).delete()
        db_session.commit()

        response = client.get("/v1/projects")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_projects_returns_all(self, client: TestClient, db_session: Session):
        """Test listing all projects."""
        from services.gateway.app.models.projects import Project

        # Clean and create test projects
        db_session.query(Project).delete()
        db_session.add(Project(key="proj1", name="Project 1"))
        db_session.add(Project(key="proj2", name="Project 2"))
        db_session.add(Project(key="proj3", name="Project 3"))
        db_session.commit()

        response = client.get("/v1/projects")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert {p["key"] for p in data} == {"proj1", "proj2", "proj3"}

    def test_list_projects_excludes_soft_deleted(self, client: TestClient, db_session: Session):
        """Test that soft-deleted projects are excluded from listing."""
        from services.gateway.app.models.projects import Project

        # Clean and create projects
        db_session.query(Project).delete()
        active_project = Project(key="active", name="Active Project")
        deleted_project = Project(key="deleted", name="Deleted Project")
        deleted_project.soft_delete()  # Soft delete

        db_session.add(active_project)
        db_session.add(deleted_project)
        db_session.commit()

        response = client.get("/v1/projects")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["key"] == "active"


class TestCreateProject:
    """Tests for POST /v1/projects endpoint."""

    def test_create_project_success(self, client: TestClient, db_session: Session):
        """Test successful project creation."""
        from services.gateway.app.models.projects import Project

        # Clean database
        db_session.query(Project).delete()
        db_session.commit()

        payload = {
            "key": "test-project",
            "name": "Test Project"
        }

        response = client.post("/v1/projects", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "test-project"
        assert data["name"] == "Test Project"
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_project_duplicate_key(self, client: TestClient, db_session: Session):
        """Test that creating a project with duplicate key fails."""
        from services.gateway.app.models.projects import Project

        # Clean and create existing project
        db_session.query(Project).delete()
        db_session.add(Project(key="existing", name="Existing Project"))
        db_session.commit()

        payload = {
            "key": "existing",  # Duplicate key
            "name": "Another Project"
        }

        response = client.post("/v1/projects", json=payload)
        assert response.status_code == 409  # Conflict

    def test_create_project_validation_missing_key(self, client: TestClient):
        """Test validation requires key."""
        payload = {"name": "Test Project"}  # Missing key

        response = client.post("/v1/projects", json=payload)
        assert response.status_code == 422
        errors = response.json()["errors"]
        assert any(err["loc"] == ["body", "key"] for err in errors)

    def test_create_project_validation_missing_name(self, client: TestClient):
        """Test validation requires name."""
        payload = {"key": "test"}  # Missing name

        response = client.post("/v1/projects", json=payload)
        assert response.status_code == 422
        errors = response.json()["errors"]
        assert any(err["loc"] == ["body", "name"] for err in errors)

    def test_create_project_validation_empty_key(self, client: TestClient):
        """Test validation rejects empty key."""
        payload = {"key": "", "name": "Test Project"}

        response = client.post("/v1/projects", json=payload)
        assert response.status_code == 422

    def test_create_project_validation_empty_name(self, client: TestClient):
        """Test validation rejects empty name."""
        payload = {"key": "test", "name": ""}

        response = client.post("/v1/projects", json=payload)
        assert response.status_code == 422

    def test_create_project_validation_key_too_long(self, client: TestClient):
        """Test validation rejects key exceeding max length."""
        payload = {
            "key": "x" * 100,  # Exceeds 64 char limit
            "name": "Test Project"
        }

        response = client.post("/v1/projects", json=payload)
        assert response.status_code == 422

    def test_create_project_validation_name_too_long(self, client: TestClient):
        """Test validation rejects name exceeding max length."""
        payload = {
            "key": "test",
            "name": "x" * 300  # Exceeds 255 char limit
        }

        response = client.post("/v1/projects", json=payload)
        assert response.status_code == 422


class TestGetProject:
    """Tests for GET /v1/projects/{key} endpoint."""

    def test_get_project_success(self, client: TestClient, db_session: Session):
        """Test getting a specific project."""
        from services.gateway.app.models.projects import Project

        # Create project
        db_session.query(Project).delete()
        db_session.add(Project(key="test-project", name="Test Project"))
        db_session.commit()

        response = client.get("/v1/projects/test-project")
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "test-project"
        assert data["name"] == "Test Project"

    def test_get_project_not_found(self, client: TestClient, db_session: Session):
        """Test getting a non-existent project returns 404."""
        from services.gateway.app.models.projects import Project

        db_session.query(Project).delete()
        db_session.commit()

        response = client.get("/v1/projects/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_project_soft_deleted_not_found(self, client: TestClient, db_session: Session):
        """Test that soft-deleted projects return 404."""
        from services.gateway.app.models.projects import Project

        # Create and soft-delete project
        db_session.query(Project).delete()
        project = Project(key="deleted", name="Deleted Project")
        project.soft_delete()
        db_session.add(project)
        db_session.commit()

        response = client.get("/v1/projects/deleted")
        assert response.status_code == 404


class TestUpdateProject:
    """Tests for PUT /v1/projects/{key} endpoint."""

    def test_update_project_success(self, client: TestClient, db_session: Session):
        """Test successfully updating a project."""
        from services.gateway.app.models.projects import Project

        # Create project
        db_session.query(Project).delete()
        db_session.add(Project(key="test-project", name="Original Name"))
        db_session.commit()

        payload = {"name": "Updated Name"}
        response = client.put("/v1/projects/test-project", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "test-project"
        assert data["name"] == "Updated Name"

    def test_update_project_not_found(self, client: TestClient, db_session: Session):
        """Test updating non-existent project returns 404."""
        from services.gateway.app.models.projects import Project

        db_session.query(Project).delete()
        db_session.commit()

        payload = {"name": "Updated Name"}
        response = client.put("/v1/projects/nonexistent", json=payload)
        assert response.status_code == 404

    def test_update_project_validation_empty_name(self, client: TestClient, db_session: Session):
        """Test update validation rejects empty name."""
        from services.gateway.app.models.projects import Project

        db_session.query(Project).delete()
        db_session.add(Project(key="test", name="Test"))
        db_session.commit()

        payload = {"name": ""}
        response = client.put("/v1/projects/test", json=payload)
        assert response.status_code == 422


class TestDeleteProject:
    """Tests for DELETE /v1/projects/{key} endpoint."""

    def test_delete_project_success(self, client: TestClient, db_session: Session):
        """Test successfully soft-deleting a project."""
        from services.gateway.app.models.projects import Project

        # Create project
        db_session.query(Project).delete()
        db_session.add(Project(key="test-project", name="Test Project"))
        db_session.commit()

        response = client.delete("/v1/projects/test-project")
        assert response.status_code == 200

        # Verify project is soft-deleted
        project = db_session.query(Project).filter_by(key="test-project").first()
        assert project is not None  # Still exists in DB
        assert project.is_deleted  # But marked as deleted

    def test_delete_project_not_found(self, client: TestClient, db_session: Session):
        """Test deleting non-existent project returns 404."""
        from services.gateway.app.models.projects import Project

        db_session.query(Project).delete()
        db_session.commit()

        response = client.delete("/v1/projects/nonexistent")
        assert response.status_code == 404

    def test_delete_project_already_deleted(self, client: TestClient, db_session: Session):
        """Test deleting already soft-deleted project returns 404."""
        from services.gateway.app.models.projects import Project

        # Create and soft-delete project
        db_session.query(Project).delete()
        project = Project(key="deleted", name="Deleted Project")
        project.soft_delete()
        db_session.add(project)
        db_session.commit()

        response = client.delete("/v1/projects/deleted")
        assert response.status_code == 404

"""Tests for identities endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


class TestListIdentities:
    """Tests for GET /v1/identities endpoint."""

    def test_list_identities_empty(self, client: TestClient, db_session: Session):
        """Test listing identities when none exist."""
        from services.gateway.app.models.identities import Identity

        # Clean database
        db_session.query(Identity).delete()
        db_session.commit()

        response = client.get("/v1/identities")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_identities_returns_all(self, client: TestClient, db_session: Session):
        """Test listing all identities."""
        from services.gateway.app.models.identities import Identity

        # Clean and create test identities
        db_session.query(Identity).delete()
        db_session.add(Identity(external_type="github", external_id="user1"))
        db_session.add(Identity(external_type="slack", external_id="U123"))
        db_session.add(Identity(external_type="github", external_id="user2"))
        db_session.commit()

        response = client.get("/v1/identities")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

        # Check that all identities are returned
        external_ids = {i["external_id"] for i in data}
        assert external_ids == {"user1", "U123", "user2"}

    def test_list_identities_ordered_by_id(self, client: TestClient, db_session: Session):
        """Test that identities are ordered by id."""
        from services.gateway.app.models.identities import Identity

        # Clean and create identities
        db_session.query(Identity).delete()
        id1 = Identity(external_type="github", external_id="user1")
        id2 = Identity(external_type="slack", external_id="U123")
        id3 = Identity(external_type="github", external_id="user2")

        db_session.add(id1)
        db_session.add(id2)
        db_session.add(id3)
        db_session.commit()

        response = client.get("/v1/identities")
        assert response.status_code == 200
        data = response.json()

        # Verify order (should be ascending by id)
        ids = [i["id"] for i in data]
        assert ids == sorted(ids)


class TestCreateIdentity:
    """Tests for POST /v1/identities endpoint."""

    def test_create_identity_minimal_fields(self, client: TestClient, db_session: Session):
        """Test creating identity with only required fields."""
        from services.gateway.app.models.identities import Identity

        # Clean database
        db_session.query(Identity).delete()
        db_session.commit()

        payload = {
            "external_type": "github",
            "external_id": "testuser123"
        }

        response = client.post("/v1/identities", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["external_type"] == "github"
        assert data["external_id"] == "testuser123"
        assert data["user_id"] is None
        assert data["display_name"] is None
        assert data["meta"] is None
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_identity_all_fields(self, client: TestClient, db_session: Session):
        """Test creating identity with all fields."""
        from services.gateway.app.models.identities import Identity

        # Clean database
        db_session.query(Identity).delete()
        db_session.commit()

        payload = {
            "external_type": "slack",
            "external_id": "U12345",
            "user_id": 42,
            "display_name": "John Doe",
            "meta": '{"email": "john@example.com"}'
        }

        response = client.post("/v1/identities", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["external_type"] == "slack"
        assert data["external_id"] == "U12345"
        assert data["user_id"] == 42
        assert data["display_name"] == "John Doe"
        assert data["meta"] == '{"email": "john@example.com"}'

    def test_create_identity_duplicate_external(self, client: TestClient, db_session: Session):
        """Test that creating duplicate external_type+external_id fails."""
        from services.gateway.app.models.identities import Identity

        # Clean and create existing identity
        db_session.query(Identity).delete()
        db_session.add(Identity(external_type="github", external_id="user1"))
        db_session.commit()

        # Try to create duplicate
        payload = {
            "external_type": "github",
            "external_id": "user1"  # Duplicate
        }

        response = client.post("/v1/identities", json=payload)
        # Should fail with integrity error (503 or 500)
        # Note: Currently returns 503 due to global error handling
        assert response.status_code in [503, 500, 409]

    def test_create_identity_same_external_id_different_type(
        self, client: TestClient, db_session: Session
    ):
        """Test that same external_id is allowed for different external_type."""
        from services.gateway.app.models.identities import Identity

        # Clean and create identity
        db_session.query(Identity).delete()
        db_session.add(Identity(external_type="github", external_id="user1"))
        db_session.commit()

        # Create with same external_id but different type (should succeed)
        payload = {
            "external_type": "slack",  # Different type
            "external_id": "user1"     # Same ID
        }

        response = client.post("/v1/identities", json=payload)
        assert response.status_code == 201

    def test_create_identity_validation_missing_external_type(self, client: TestClient):
        """Test validation requires external_type."""
        payload = {"external_id": "user123"}  # Missing external_type

        response = client.post("/v1/identities", json=payload)
        assert response.status_code == 422
        errors = response.json()["errors"]
        assert any(err["loc"] == ["body", "external_type"] for err in errors)

    def test_create_identity_validation_missing_external_id(self, client: TestClient):
        """Test validation requires external_id."""
        payload = {"external_type": "github"}  # Missing external_id

        response = client.post("/v1/identities", json=payload)
        assert response.status_code == 422
        errors = response.json()["errors"]
        assert any(err["loc"] == ["body", "external_id"] for err in errors)

    def test_create_identity_validation_empty_external_type(self, client: TestClient):
        """Test validation rejects empty external_type."""
        payload = {
            "external_type": "",  # Empty
            "external_id": "user123"
        }

        response = client.post("/v1/identities", json=payload)
        assert response.status_code == 422

    def test_create_identity_validation_empty_external_id(self, client: TestClient):
        """Test validation rejects empty external_id."""
        payload = {
            "external_type": "github",
            "external_id": ""  # Empty
        }

        response = client.post("/v1/identities", json=payload)
        assert response.status_code == 422

    def test_create_identity_validation_external_type_too_long(self, client: TestClient):
        """Test validation rejects external_type exceeding max length."""
        payload = {
            "external_type": "x" * 33,  # Exceeds 32 char limit
            "external_id": "user123"
        }

        response = client.post("/v1/identities", json=payload)
        assert response.status_code == 422

    def test_create_identity_validation_external_id_too_long(self, client: TestClient):
        """Test validation rejects external_id exceeding max length."""
        payload = {
            "external_type": "github",
            "external_id": "x" * 129  # Exceeds 128 char limit
        }

        response = client.post("/v1/identities", json=payload)
        assert response.status_code == 422

    def test_create_identity_validation_display_name_too_long(self, client: TestClient):
        """Test validation rejects display_name exceeding max length."""
        payload = {
            "external_type": "github",
            "external_id": "user123",
            "display_name": "x" * 256  # Exceeds 255 char limit
        }

        response = client.post("/v1/identities", json=payload)
        assert response.status_code == 422

    def test_create_identity_optional_fields_can_be_null(
        self, client: TestClient, db_session: Session
    ):
        """Test that optional fields can be explicitly null."""
        from services.gateway.app.models.identities import Identity

        # Clean database
        db_session.query(Identity).delete()
        db_session.commit()

        payload = {
            "external_type": "github",
            "external_id": "user123",
            "user_id": None,
            "display_name": None,
            "meta": None
        }

        response = client.post("/v1/identities", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] is None
        assert data["display_name"] is None
        assert data["meta"] is None

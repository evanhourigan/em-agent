"""
Tests for incidents router.

Basic validation tests to ensure refactored endpoints work correctly.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from services.gateway.app.models.incidents import Incident, IncidentTimeline


class TestStartIncident:
    """Test incident creation endpoint."""

    def test_start_incident_success(self, client: TestClient, db_session: Session):
        """Test creating an incident successfully."""
        # Clean database
        db_session.query(IncidentTimeline).delete()
        db_session.query(Incident).delete()
        db_session.commit()

        payload = {
            "title": "Production API outage",
            "severity": "critical"
        }

        response = client.post("/v1/incidents", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Production API outage"
        assert data["status"] == "open"
        assert "id" in data

        # Verify incident was created
        incidents = db_session.query(Incident).all()
        assert len(incidents) == 1
        assert incidents[0].severity == "critical"

    def test_start_incident_minimal(self, client: TestClient, db_session: Session):
        """Test creating incident with minimal data."""
        # Clean database
        db_session.query(IncidentTimeline).delete()
        db_session.query(Incident).delete()
        db_session.commit()

        payload = {}

        response = client.post("/v1/incidents", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Untitled Incident"
        assert data["status"] == "open"

    def test_start_incident_invalid_severity(self, client: TestClient, db_session: Session):
        """Test that invalid severity returns validation error."""
        payload = {
            "title": "Test incident",
            "severity": "invalid"  # Not in allowed values
        }

        response = client.post("/v1/incidents", json=payload)

        # Pydantic validation returns 422
        assert response.status_code == 422


class TestAddNote:
    """Test adding notes to incidents."""

    def test_add_note_success(self, client: TestClient, db_session: Session):
        """Test adding a note to an incident."""
        # Clean database
        db_session.query(IncidentTimeline).delete()
        db_session.query(Incident).delete()
        db_session.commit()

        # Create incident
        incident = Incident(title="Test incident", status="open")
        db_session.add(incident)
        db_session.commit()
        db_session.refresh(incident)

        payload = {
            "text": "Identified root cause: memory leak",
            "author": "alice@example.com"
        }

        response = client.post(f"/v1/incidents/{incident.id}/note", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "timeline_id" in data

        # Verify timeline entry was created
        timeline = db_session.query(IncidentTimeline).filter_by(incident_id=incident.id).all()
        assert len(timeline) == 1
        assert timeline[0].text == "Identified root cause: memory leak"
        assert timeline[0].author == "alice@example.com"

    def test_add_note_empty_text(self, client: TestClient, db_session: Session):
        """Test that empty text returns validation error."""
        # Clean database
        db_session.query(IncidentTimeline).delete()
        db_session.query(Incident).delete()
        db_session.commit()

        incident = Incident(title="Test incident", status="open")
        db_session.add(incident)
        db_session.commit()
        db_session.refresh(incident)

        payload = {
            "text": "   "  # Whitespace only
        }

        response = client.post(f"/v1/incidents/{incident.id}/note", json=payload)

        # Pydantic validation returns 422
        assert response.status_code == 422

    def test_add_note_incident_not_found(self, client: TestClient, db_session: Session):
        """Test adding note to non-existent incident returns 404."""
        payload = {
            "text": "Test note"
        }

        response = client.post("/v1/incidents/99999/note", json=payload)

        assert response.status_code == 404


class TestListIncidents:
    """Test incidents listing endpoint."""

    def test_list_incidents_empty(self, client: TestClient, db_session: Session):
        """Test listing incidents when none exist."""
        # Clean database
        db_session.query(IncidentTimeline).delete()
        db_session.query(Incident).delete()
        db_session.commit()

        response = client.get("/v1/incidents")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_incidents_returns_incidents(self, client: TestClient, db_session: Session):
        """Test listing incidents returns all incidents."""
        # Clean database
        db_session.query(IncidentTimeline).delete()
        db_session.query(Incident).delete()
        db_session.commit()

        # Create test incidents
        inc1 = Incident(title="Incident 1", status="open", severity="high")
        inc2 = Incident(title="Incident 2", status="closed", severity="low")
        db_session.add_all([inc1, inc2])
        db_session.commit()

        response = client.get("/v1/incidents")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all("id" in inc for inc in data)
        assert all("title" in inc for inc in data)
        assert all("status" in inc for inc in data)


class TestCloseIncident:
    """Test incident closure endpoint."""

    def test_close_incident_success(self, client: TestClient, db_session: Session):
        """Test closing an incident."""
        # Clean database
        db_session.query(IncidentTimeline).delete()
        db_session.query(Incident).delete()
        db_session.commit()

        incident = Incident(title="Test incident", status="open")
        db_session.add(incident)
        db_session.commit()
        db_session.refresh(incident)

        response = client.post(f"/v1/incidents/{incident.id}/close")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == incident.id
        assert data["status"] == "closed"

        # Verify incident was closed
        db_session.refresh(incident)
        assert incident.status == "closed"
        assert incident.closed_at is not None

    def test_close_incident_not_found(self, client: TestClient, db_session: Session):
        """Test closing non-existent incident returns 404."""
        response = client.post("/v1/incidents/99999/close")

        assert response.status_code == 404


class TestSetSeverity:
    """Test incident severity update endpoint."""

    def test_set_severity_success(self, client: TestClient, db_session: Session):
        """Test setting incident severity."""
        # Clean database
        db_session.query(IncidentTimeline).delete()
        db_session.query(Incident).delete()
        db_session.commit()

        incident = Incident(title="Test incident", status="open", severity="low")
        db_session.add(incident)
        db_session.commit()
        db_session.refresh(incident)

        payload = {
            "severity": "critical"
        }

        response = client.post(f"/v1/incidents/{incident.id}/severity", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == incident.id
        assert data["severity"] == "critical"

        # Verify severity was updated
        db_session.refresh(incident)
        assert incident.severity == "critical"

    def test_set_severity_invalid(self, client: TestClient, db_session: Session):
        """Test that invalid severity returns validation error."""
        # Clean database
        db_session.query(IncidentTimeline).delete()
        db_session.query(Incident).delete()
        db_session.commit()

        incident = Incident(title="Test incident", status="open")
        db_session.add(incident)
        db_session.commit()
        db_session.refresh(incident)

        payload = {
            "severity": "invalid"
        }

        response = client.post(f"/v1/incidents/{incident.id}/severity", json=payload)

        # Pydantic validation returns 422
        assert response.status_code == 422

    def test_set_severity_not_found(self, client: TestClient, db_session: Session):
        """Test setting severity on non-existent incident returns 404."""
        payload = {
            "severity": "high"
        }

        response = client.post("/v1/incidents/99999/severity", json=payload)

        assert response.status_code == 404


class TestIncidentErrorHandling:
    """Test incident error handling paths."""

    def test_add_note_integrity_error(self, client: TestClient):
        """Test add_note handles database integrity errors."""
        from unittest.mock import patch, Mock
        from sqlalchemy.exc import IntegrityError

        with patch("services.gateway.app.api.v1.routers.incidents.get_sessionmaker") as mock_sm:
            mock_session = Mock()
            mock_session.get.return_value = Mock(id=1)  # Return fake incident
            mock_session.commit.side_effect = IntegrityError("", "", "")
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)
            mock_sm.return_value = Mock(return_value=mock_session)

            payload = {"text": "Test note"}
            response = client.post("/v1/incidents/1/note", json=payload)

            assert response.status_code == 409

    def test_add_note_operational_error(self, client: TestClient):
        """Test add_note handles database operational errors."""
        from unittest.mock import patch, Mock
        from sqlalchemy.exc import OperationalError

        with patch("services.gateway.app.api.v1.routers.incidents.get_sessionmaker") as mock_sm:
            mock_session = Mock()
            mock_session.get.return_value = Mock(id=1)
            mock_session.commit.side_effect = OperationalError("", "", "")
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)
            mock_sm.return_value = Mock(return_value=mock_session)

            payload = {"text": "Test note"}
            response = client.post("/v1/incidents/1/note", json=payload)

            assert response.status_code == 503

    def test_add_note_unexpected_error(self, client: TestClient):
        """Test add_note handles unexpected errors."""
        from unittest.mock import patch, Mock

        with patch("services.gateway.app.api.v1.routers.incidents.get_sessionmaker") as mock_sm:
            mock_session = Mock()
            mock_session.get.return_value = Mock(id=1)
            mock_session.commit.side_effect = RuntimeError("Unexpected")
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)
            mock_sm.return_value = Mock(return_value=mock_session)

            payload = {"text": "Test note"}
            response = client.post("/v1/incidents/1/note", json=payload)

            assert response.status_code == 500

    def test_list_incidents_operational_error(self, client: TestClient):
        """Test list_incidents handles database operational errors."""
        from unittest.mock import patch, Mock
        from sqlalchemy.exc import OperationalError

        with patch("services.gateway.app.api.v1.routers.incidents.get_sessionmaker") as mock_sm:
            mock_session = Mock()
            mock_session.query.side_effect = OperationalError("", "", "")
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)
            mock_sm.return_value = Mock(return_value=mock_session)

            response = client.get("/v1/incidents")

            assert response.status_code == 503

    def test_list_incidents_unexpected_error(self, client: TestClient):
        """Test list_incidents handles unexpected errors."""
        from unittest.mock import patch, Mock

        with patch("services.gateway.app.api.v1.routers.incidents.get_sessionmaker") as mock_sm:
            mock_session = Mock()
            mock_session.query.side_effect = RuntimeError("Unexpected")
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)
            mock_sm.return_value = Mock(return_value=mock_session)

            response = client.get("/v1/incidents")

            assert response.status_code == 500

    def test_close_incident_already_closed(self, client: TestClient):
        """Test closing an already-closed incident."""
        from unittest.mock import patch, Mock

        with patch("services.gateway.app.api.v1.routers.incidents.get_sessionmaker") as mock_sm:
            mock_incident = Mock(id=1, status="closed")
            mock_session = Mock()
            mock_session.get.return_value = mock_incident
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)
            mock_sm.return_value = Mock(return_value=mock_session)

            response = client.post("/v1/incidents/1/close")

            assert response.status_code == 200
            # Should not call commit since already closed
            mock_session.commit.assert_not_called()

    def test_close_incident_integrity_error(self, client: TestClient):
        """Test close_incident handles database integrity errors."""
        from unittest.mock import patch, Mock
        from sqlalchemy.exc import IntegrityError

        with patch("services.gateway.app.api.v1.routers.incidents.get_sessionmaker") as mock_sm:
            mock_incident = Mock(id=1, status="open")
            mock_session = Mock()
            mock_session.get.return_value = mock_incident
            mock_session.commit.side_effect = IntegrityError("", "", "")
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)
            mock_sm.return_value = Mock(return_value=mock_session)

            response = client.post("/v1/incidents/1/close")

            assert response.status_code == 409

    def test_close_incident_operational_error(self, client: TestClient):
        """Test close_incident handles database operational errors."""
        from unittest.mock import patch, Mock
        from sqlalchemy.exc import OperationalError

        with patch("services.gateway.app.api.v1.routers.incidents.get_sessionmaker") as mock_sm:
            mock_incident = Mock(id=1, status="open")
            mock_session = Mock()
            mock_session.get.return_value = mock_incident
            mock_session.commit.side_effect = OperationalError("", "", "")
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)
            mock_sm.return_value = Mock(return_value=mock_session)

            response = client.post("/v1/incidents/1/close")

            assert response.status_code == 503

    def test_close_incident_unexpected_error(self, client: TestClient):
        """Test close_incident handles unexpected errors."""
        from unittest.mock import patch, Mock

        with patch("services.gateway.app.api.v1.routers.incidents.get_sessionmaker") as mock_sm:
            mock_incident = Mock(id=1, status="open")
            mock_session = Mock()
            mock_session.get.return_value = mock_incident
            mock_session.commit.side_effect = RuntimeError("Unexpected")
            mock_session.__enter__ = Mock(return_value=mock_session)
            mock_session.__exit__ = Mock(return_value=None)
            mock_sm.return_value = Mock(return_value=mock_session)

            response = client.post("/v1/incidents/1/close")

            assert response.status_code == 500



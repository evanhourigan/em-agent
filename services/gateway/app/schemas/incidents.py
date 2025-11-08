"""
Pydantic schemas for incident endpoints.

These schemas provide:
- Input validation for incident requests
- Type safety and documentation
- Automatic error messages for invalid inputs
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, validator


class IncidentStartRequest(BaseModel):
    """Request schema for starting an incident."""

    title: str | None = Field(
        None,
        max_length=255,
        description="Incident title (defaults to 'Untitled Incident')",
    )
    severity: Literal["low", "medium", "high", "critical"] | None = Field(
        None, description="Incident severity level"
    )

    @validator("title", pre=True)
    def validate_title(cls, v):
        """Ensure title is not just whitespace."""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None  # Will use default "Untitled Incident"
        return v

    class Config:
        json_schema_extra = {
            "example": {"title": "Production API outage", "severity": "critical"}
        }


class IncidentAddNoteRequest(BaseModel):
    """Request schema for adding a note to an incident."""

    text: str = Field(..., min_length=1, max_length=5000, description="Note text")
    author: str | None = Field(None, max_length=255, description="Note author")

    @validator("text", pre=True)
    def validate_text(cls, v):
        """Ensure text is not just whitespace."""
        # Strip whitespace first
        if isinstance(v, str):
            v = v.strip()
        # min_length=1 will catch empty strings
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "text": "Identified root cause: memory leak in caching service",
                "author": "alice@example.com",
            }
        }


class IncidentSetSeverityRequest(BaseModel):
    """Request schema for setting incident severity."""

    severity: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="New severity level"
    )

    class Config:
        json_schema_extra = {"example": {"severity": "high"}}


class IncidentResponse(BaseModel):
    """Response schema for incident data."""

    id: int = Field(..., description="Incident ID")
    title: str = Field(..., description="Incident title")
    status: str = Field(..., description="Incident status (open, closed)")
    severity: str | None = Field(None, description="Incident severity")
    created_at: datetime | None = Field(None, description="When incident was created")
    closed_at: datetime | None = Field(None, description="When incident was closed")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 123,
                "title": "Production API outage",
                "status": "open",
                "severity": "critical",
                "created_at": "2025-01-20T10:30:00Z",
                "closed_at": None,
            }
        }


class IncidentStartResponse(BaseModel):
    """Response schema for starting an incident."""

    id: int = Field(..., description="New incident ID")
    status: str = Field(..., description="Incident status")
    title: str = Field(..., description="Incident title")

    class Config:
        json_schema_extra = {
            "example": {"id": 123, "status": "open", "title": "Production API outage"}
        }


class IncidentNoteResponse(BaseModel):
    """Response schema for adding a note."""

    ok: bool = Field(..., description="Whether the operation was successful")
    timeline_id: int = Field(..., description="ID of the created timeline entry")

    class Config:
        json_schema_extra = {"example": {"ok": True, "timeline_id": 456}}


class IncidentCloseResponse(BaseModel):
    """Response schema for closing an incident."""

    id: int = Field(..., description="Incident ID")
    status: str = Field(..., description="New status (closed)")

    class Config:
        json_schema_extra = {"example": {"id": 123, "status": "closed"}}


class IncidentSeverityResponse(BaseModel):
    """Response schema for setting severity."""

    id: int = Field(..., description="Incident ID")
    severity: str = Field(..., description="New severity")

    class Config:
        json_schema_extra = {"example": {"id": 123, "severity": "high"}}

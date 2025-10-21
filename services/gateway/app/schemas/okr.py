"""
Pydantic schemas for OKR (Objectives and Key Results) endpoints.

These schemas provide:
- Input validation for OKR requests
- Type safety and documentation
- Automatic error messages for invalid inputs
"""
from typing import Optional
from pydantic import BaseModel, Field, validator


class ObjectiveCreateRequest(BaseModel):
    """Request schema for creating an objective."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Objective title"
    )
    owner: Optional[str] = Field(
        None,
        max_length=255,
        description="Objective owner (e.g., team or person)"
    )
    period: Optional[str] = Field(
        None,
        max_length=64,
        description="Time period for the objective (e.g., 'Q1 2025', '2025')"
    )

    @validator('title', pre=True)
    def validate_title(cls, v):
        """Ensure title is not just whitespace."""
        # Strip whitespace first
        if isinstance(v, str):
            v = v.strip()
        # min_length=1 will catch empty strings
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Improve API performance by 50%",
                "owner": "Platform Team",
                "period": "Q1 2025"
            }
        }


class KeyResultCreateRequest(BaseModel):
    """Request schema for creating a key result."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Key result title"
    )
    target: Optional[float] = Field(
        None,
        description="Target value for the key result"
    )
    unit: Optional[str] = Field(
        None,
        max_length=64,
        description="Unit of measurement (e.g., '%', 'requests/sec', 'users')"
    )

    @validator('title', pre=True)
    def validate_title(cls, v):
        """Ensure title is not just whitespace."""
        # Strip whitespace first
        if isinstance(v, str):
            v = v.strip()
        # min_length=1 will catch empty strings
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Reduce API response time to <200ms",
                "target": 200,
                "unit": "ms"
            }
        }


class KeyResultProgressRequest(BaseModel):
    """Request schema for updating key result progress."""

    current: float = Field(
        ...,
        description="Current value for the key result"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "current": 180
            }
        }


class ObjectiveResponse(BaseModel):
    """Response schema for objective data."""

    id: int = Field(..., description="Objective ID")
    title: str = Field(..., description="Objective title")
    owner: Optional[str] = Field(None, description="Objective owner")
    period: Optional[str] = Field(None, description="Time period")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 123,
                "title": "Improve API performance by 50%",
                "owner": "Platform Team",
                "period": "Q1 2025"
            }
        }


class ObjectiveCreateResponse(BaseModel):
    """Response schema for creating an objective."""

    id: int = Field(..., description="New objective ID")
    title: str = Field(..., description="Objective title")

    class Config:
        json_schema_extra = {
            "example": {
                "id": 123,
                "title": "Improve API performance by 50%"
            }
        }


class KeyResultCreateResponse(BaseModel):
    """Response schema for creating a key result."""

    id: int = Field(..., description="New key result ID")

    class Config:
        json_schema_extra = {
            "example": {
                "id": 456
            }
        }


class KeyResultProgressResponse(BaseModel):
    """Response schema for updating key result progress."""

    ok: bool = Field(..., description="Whether the update was successful")

    class Config:
        json_schema_extra = {
            "example": {
                "ok": True
            }
        }

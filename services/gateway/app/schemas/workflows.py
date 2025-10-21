"""
Pydantic schemas for workflow endpoints.

These schemas provide:
- Input validation for workflow requests
- Type safety and documentation
- Automatic error messages for invalid inputs
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, validator


class WorkflowRunRequest(BaseModel):
    """Request schema for running a workflow."""

    rule: Optional[str] = Field(
        None,
        max_length=64,
        description="Rule name or kind for the workflow"
    )
    kind: Optional[str] = Field(
        None,
        max_length=64,
        description="Workflow kind (alternative to rule)"
    )
    subject: Optional[str] = Field(
        "n/a",
        max_length=255,
        description="Subject of the workflow (e.g., 'pr:123', 'deploy:service')"
    )
    action: Optional[str] = Field(
        None,
        max_length=64,
        description="Action to take (if not specified, will be determined by policy)"
    )
    payload: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional workflow context data"
    )

    @validator('subject')
    def validate_subject(cls, v):
        """Ensure subject is not just whitespace."""
        if v and not v.strip():
            # Return default instead of raising to avoid JSON serialization issues
            return "n/a"
        return v.strip() if v else "n/a"

    class Config:
        json_schema_extra = {
            "example": {
                "rule": "deploy",
                "subject": "deploy:api-service",
                "action": "allow",
                "payload": {
                    "version": "1.2.3",
                    "environment": "production"
                }
            }
        }


class WorkflowRunResponse(BaseModel):
    """Response schema for workflow run."""

    status: str = Field(..., description="Workflow status (queued, awaiting_approval, etc.)")
    id: Optional[int] = Field(None, description="Action log ID")
    action: Optional[str] = Field(None, description="Action taken")
    action_id: Optional[int] = Field(None, description="Approval ID if awaiting approval")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "queued",
                "id": 123,
                "action": "allow"
            }
        }


class WorkflowJobResponse(BaseModel):
    """Response schema for a single workflow job."""

    id: int = Field(..., description="Job ID")
    status: str = Field(..., description="Job status (queued, processing, done, failed)")
    rule_kind: Optional[str] = Field(None, description="Rule kind for this job")
    subject: Optional[str] = Field(None, description="Subject of the job")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 456,
                "status": "queued",
                "rule_kind": "deploy",
                "subject": "deploy:api-service"
            }
        }

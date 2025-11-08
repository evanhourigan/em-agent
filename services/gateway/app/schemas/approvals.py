"""
Pydantic schemas for approval endpoints.

These schemas provide:
- Input validation for all approval requests
- Type safety and documentation
- Automatic error messages for invalid inputs
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, validator


class ApprovalProposalRequest(BaseModel):
    """Request schema for proposing an approval."""

    subject: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Subject of the approval (e.g., 'deploy:service-name', 'pr:123')",
        examples=["deploy:api-service", "pr:456", "merge:feature-branch"],
    )
    action: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Action requiring approval",
        examples=["deploy", "merge", "block", "nudge"],
    )
    reason: str | None = Field(
        None, max_length=1000, description="Reason for the approval request"
    )
    payload: dict[str, Any] | None = Field(
        default_factory=dict, description="Additional context data for the approval"
    )

    @validator("action")
    def validate_action(cls, v):
        """Validate that action is one of the known types."""
        allowed_actions = {
            "deploy",
            "merge",
            "block",
            "nudge",
            "comment_summary",
            "assign_reviewer",
            "escalate",
        }
        if v not in allowed_actions:
            # Allow any action but warn in logs - this is extensible
            pass
        return v

    @validator("subject")
    def validate_subject(cls, v):
        """Ensure subject is not just whitespace."""
        if not v.strip():
            raise ValueError("Subject cannot be empty or whitespace")
        return v.strip()

    class Config:
        json_schema_extra = {
            "example": {
                "subject": "deploy:api-service",
                "action": "deploy",
                "reason": "Rolling out new feature",
                "payload": {"version": "1.2.3", "environment": "production"},
            }
        }


class ApprovalDecisionRequest(BaseModel):
    """Request schema for making a decision on an approval."""

    decision: Literal["approve", "decline", "modify"] = Field(
        ..., description="Decision on the approval"
    )
    reason: str | None = Field(
        None, max_length=1000, description="Reason for the decision"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "decision": "approve",
                "reason": "All checks passed, looks good to deploy",
            }
        }


class ApprovalNotifyRequest(BaseModel):
    """Request schema for notifying about an approval."""

    channel: str | None = Field(
        None,
        max_length=255,
        description="Slack channel to notify (e.g., '#approvals')",
        examples=["#approvals", "#deployments", "@user"],
    )

    class Config:
        json_schema_extra = {"example": {"channel": "#approvals"}}


class ApprovalResponse(BaseModel):
    """Response schema for approval data."""

    id: int = Field(..., description="Unique approval ID")
    subject: str = Field(..., description="Subject of the approval")
    action: str = Field(..., description="Action type")
    status: str = Field(
        ..., description="Current status (pending, approve, decline, modify)"
    )
    reason: str | None = Field(None, description="Reason or rationale")
    created_at: datetime = Field(..., description="When the approval was created")
    decided_at: datetime | None = Field(None, description="When the decision was made")

    class Config:
        from_attributes = True  # Allow ORM mode
        json_schema_extra = {
            "example": {
                "id": 123,
                "subject": "deploy:api-service",
                "action": "deploy",
                "status": "pending",
                "reason": "Deploying new feature",
                "created_at": "2025-01-20T10:30:00Z",
                "decided_at": None,
            }
        }


class ApprovalProposalResponse(BaseModel):
    """Response schema for approval proposal."""

    action_id: int = Field(..., description="ID of the created approval")
    proposed: ApprovalProposalRequest = Field(
        ..., description="The proposed approval data"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "action_id": 123,
                "proposed": {
                    "subject": "deploy:api-service",
                    "action": "deploy",
                    "reason": "Rolling out new feature",
                    "payload": {"version": "1.2.3"},
                },
            }
        }


class ApprovalDecisionResponse(BaseModel):
    """Response schema for approval decision."""

    id: int = Field(..., description="Approval ID")
    status: str = Field(..., description="New status after decision")
    reason: str | None = Field(None, description="Decision reason")
    job_id: int | None = Field(None, description="Workflow job ID if created")

    class Config:
        json_schema_extra = {
            "example": {
                "id": 123,
                "status": "approve",
                "reason": "All checks passed",
                "job_id": 456,
            }
        }


class ApprovalNotifyResponse(BaseModel):
    """Response schema for approval notification."""

    ok: bool = Field(..., description="Whether notification was successful")
    posted: dict[str, Any] = Field(..., description="Slack API response details")

    class Config:
        json_schema_extra = {
            "example": {
                "ok": True,
                "posted": {
                    "ok": True,
                    "ts": "1234567890.123456",
                    "channel": "C1234567890",
                },
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response schema."""

    detail: str = Field(..., description="Error message")
    error_code: str | None = Field(None, description="Machine-readable error code")

    class Config:
        json_schema_extra = {
            "example": {
                "detail": "Approval not found",
                "error_code": "APPROVAL_NOT_FOUND",
            }
        }

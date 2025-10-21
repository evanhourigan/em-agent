"""
Pydantic schemas for authentication endpoints.

These schemas provide:
- Input validation for login requests
- Type-safe token responses
- Documentation for auth API
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional


class LoginRequest(BaseModel):
    """Request schema for user login."""

    username: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Username or email"
    )
    password: str = Field(
        ...,
        min_length=1,
        description="User password"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "username": "user@example.com",
                "password": "securepassword123"
            }
        }


class TokenResponse(BaseModel):
    """Response schema for successful authentication."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: Optional[str] = Field(None, description="JWT refresh token for renewing access")
    token_type: str = Field(default="bearer", description="Token type (always 'bearer')")
    expires_in: int = Field(..., description="Token expiration time in seconds")

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 3600
            }
        }


class RefreshTokenRequest(BaseModel):
    """Request schema for refreshing an access token."""

    refresh_token: str = Field(..., description="Valid refresh token")

    class Config:
        json_schema_extra = {
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }


class UserInfo(BaseModel):
    """Response schema for current user information."""

    sub: str = Field(..., description="User subject/ID")
    email: Optional[str] = Field(None, description="User email")
    role: Optional[str] = Field(None, description="User role")
    auth_disabled: Optional[bool] = Field(None, description="Whether authentication is disabled")

    class Config:
        json_schema_extra = {
            "example": {
                "sub": "user@example.com",
                "email": "user@example.com",
                "role": "admin"
            }
        }

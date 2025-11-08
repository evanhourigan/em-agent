from datetime import datetime

from pydantic import BaseModel, Field


class IdentityCreate(BaseModel):
    external_type: str = Field(min_length=1, max_length=32)
    external_id: str = Field(min_length=1, max_length=128)
    user_id: int | None = None
    display_name: str | None = Field(default=None, max_length=255)
    meta: str | None = None


class IdentityOut(BaseModel):
    id: int
    external_type: str
    external_id: str
    user_id: int | None
    display_name: str | None
    meta: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class IdentityCreate(BaseModel):
    external_type: str = Field(min_length=1, max_length=32)
    external_id: str = Field(min_length=1, max_length=128)
    user_id: Optional[int] = None
    display_name: Optional[str] = Field(default=None, max_length=255)
    meta: Optional[str] = None


class IdentityOut(BaseModel):
    id: int
    external_type: str
    external_id: str
    user_id: Optional[int]
    display_name: Optional[str]
    meta: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProjectBase(BaseModel):
    key: Optional[str] = Field(None, min_length=1, max_length=64)
    name: Optional[str] = Field(None, min_length=1, max_length=255)


class ProjectCreate(ProjectBase):
    key: str
    name: str


class ProjectUpdate(ProjectBase):
    pass


class ProjectOut(BaseModel):
    id: int
    key: str
    name: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

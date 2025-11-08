from datetime import datetime

from pydantic import BaseModel, Field


class ProjectBase(BaseModel):
    key: str | None = Field(None, min_length=1, max_length=64)
    name: str | None = Field(None, min_length=1, max_length=255)


class ProjectCreate(ProjectBase):
    key: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)


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

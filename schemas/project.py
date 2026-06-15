from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


DEFAULT_PROJECT_NAME = "新对话"


class ProjectCreate(BaseModel):
    name: str = Field(default=DEFAULT_PROJECT_NAME, max_length=200)
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None


class ProjectRead(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemoryCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=200)
    value: str = Field(..., min_length=1)
    category: str = Field(default="semantic")
    importance: float = Field(default=0.7, ge=0, le=1)


class MemoryUpdate(BaseModel):
    key: Optional[str] = Field(None, min_length=1, max_length=200)
    value: Optional[str] = None
    category: Optional[str] = None
    importance: Optional[float] = Field(None, ge=0, le=1)
    archived: Optional[bool] = None

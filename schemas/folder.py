from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FolderRead(BaseModel):
    id: int
    name: str
    parent_id: Optional[int]
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    parent_id: Optional[int] = None
    sort_order: int = 0


class FolderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None


class AssignProjectBody(BaseModel):
    folder_id: Optional[int] = None


class SuggestBody(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=500)


class SuggestFolder(BaseModel):
    tmp_id: str
    name: str
    parent_tmp_id: Optional[str] = None
    sort_order: int = 0


class SuggestAssignment(BaseModel):
    project_id: int
    folder_tmp_id: Optional[str] = None


class SuggestResponse(BaseModel):
    folders: list[SuggestFolder]
    assignments: list[SuggestAssignment]
    rationale: Optional[str] = None


class ApplyTreeBody(BaseModel):
    folders: list[SuggestFolder]
    assignments: list[SuggestAssignment]

from typing import Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    project_id: int
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    project_id: int
    session_id: Optional[str]
    reply: str
    tool_calls_summary: Optional[list[str]] = None

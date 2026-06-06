from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class RetrievedFact(BaseModel):
    fact: str
    valid_at: str | None = None
    invalid_at: str | None = None
    score: float | None = None


class ToolTrace(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: str


class ChatResponse(BaseModel):
    reply: str
    retrieved_facts: list[RetrievedFact]
    tool_trace: list[ToolTrace] = Field(default_factory=list)

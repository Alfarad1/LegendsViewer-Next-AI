from typing import Any, Literal

from pydantic import BaseModel, Field

ObjectType = Literal["Site", "HistoricalFigure", "Entity"]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list)


class EntityLink(BaseModel):
    type: ObjectType
    id: int
    name: str
    route: str


class ToolResultPayload(BaseModel):
    """Structured payload returned by tools for the agent and frontend."""

    ok: bool
    message: str | None = None
    data: Any = None
    links: list[EntityLink] = Field(default_factory=list)

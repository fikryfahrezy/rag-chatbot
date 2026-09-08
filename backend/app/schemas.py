from typing import Literal

from pydantic import BaseModel, Field


class User(BaseModel):
    id: str
    name: str
    role: Literal["public", "sales", "manager", "admin"]
    region: str | None = None


class Citation(BaseModel):
    label: str
    detail: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    workspace: Literal["operations", "knowledge", "public"]


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = []
    provider: str
    model: str
    route: str


class ModelChoice(BaseModel):
    provider: Literal["demo", "ollama", "openai", "anthropic"]
    model: str = Field(min_length=1, max_length=120)


class ModelSettingsPayload(BaseModel):
    database_planner: ModelChoice
    database_answer: ModelChoice
    pdf_answer: ModelChoice


class DocumentOut(BaseModel):
    id: int
    filename: str
    visibility: str
    region: str | None
    chunks: int


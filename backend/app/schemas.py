from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Provider = Literal["ollama", "openai", "anthropic"]


class User(BaseModel):
    id: str
    name: str
    group: Literal["A", "B", "C", "ALL"]
    role: Literal["public", "sales", "manager", "employee", "admin"]
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
    provider: Provider
    model: str = Field(min_length=1, max_length=120)


class ModelSettingsPayload(BaseModel):
    database_planner: ModelChoice
    database_answer: ModelChoice
    pdf_answer: ModelChoice


class RegisteredModelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    provider: Provider
    model: str = Field(min_length=1, max_length=120)

    @field_validator("name", "model")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class RegisteredModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    provider: Provider
    model: str


class DocumentOut(BaseModel):
    id: int
    filename: str
    visibility: str
    region: str | None
    chunks: int

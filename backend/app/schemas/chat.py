from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    # Retrieval tuning (bounded; the authenticated user always scopes the search)
    limit: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.2, ge=0.0, le=1.0)

    @field_validator("message")
    @classmethod
    def reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be empty or whitespace-only")
        return value


class ChatSource(BaseModel):
    document_id: str | None
    chunk_id: str
    filename: str | None
    page_number: int | None
    score: float


class ChatResponse(BaseModel):
    message: str
    answer: str
    sources: list[ChatSource]

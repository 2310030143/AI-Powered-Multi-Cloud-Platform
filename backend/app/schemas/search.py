from uuid import UUID

from pydantic import BaseModel, Field

from app.models.models import CloudProvider


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=50)
    # Drop results scoring below this cosine similarity (0-1)
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    # Metadata filters (user_id is NEVER taken from the request — the
    # authenticated user always scopes the search)
    document_id: UUID | None = None
    mime_type: str | None = Field(default=None, min_length=1, max_length=255)
    source: CloudProvider | None = None


class SearchHit(BaseModel):
    score: float
    chunk_id: str | None
    chunk_index: int | None
    page_number: int | None
    content: str | None          # hydrated from PostgreSQL, not stored in Qdrant
    token_count: int | None
    document_id: str | None
    file_name: str | None
    mime_type: str | None
    source: str | None


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchHit]


class EmbedResponse(BaseModel):
    document_id: str
    status: str
    chunks_embedded: int
    model: str
    message: str | None = None

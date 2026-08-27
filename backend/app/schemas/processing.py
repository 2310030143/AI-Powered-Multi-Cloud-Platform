from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProcessResponse(BaseModel):
    document_id: str
    status: str
    message: str


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chunk_index: int
    page_number: int | None
    content: str
    token_count: int | None
    created_at: datetime


class ChunkListResponse(BaseModel):
    total: int
    items: list[ChunkRead]


class TableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    page_number: int | None
    table_index: int
    table_data: list
    row_count: int | None
    col_count: int | None
    created_at: datetime


class TableListResponse(BaseModel):
    total: int
    items: list[TableRead]


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_type: str
    status: str
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None

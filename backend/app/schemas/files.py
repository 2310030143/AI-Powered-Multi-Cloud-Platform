from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CloudFile(BaseModel):
    """Provider-neutral file representation (live from the cloud provider)."""
    provider: str
    file_id: str
    name: str
    mime_type: str | None = None
    size: int | None = None
    modified_at: datetime | None = None
    is_folder: bool = False
    parent_id: str | None = None


class DocumentRead(BaseModel):
    """A file tracked by the platform (metadata stored in the database)."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str
    external_file_id: str
    file_name: str
    file_type: str
    file_size: int | None
    mime_type: str | None
    source_path: str | None
    content_hash: str | None
    processing_status: str
    ocr_required: bool
    ocr_completed: bool
    embedding_completed: bool
    created_at: datetime
    modified_at: datetime


class DocumentListResponse(BaseModel):
    total: int
    items: list[DocumentRead]

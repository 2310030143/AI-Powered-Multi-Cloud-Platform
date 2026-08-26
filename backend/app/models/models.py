import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, BigInteger, Text, DateTime,
    ForeignKey, Enum, JSON, Boolean
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database.session import Base
import enum


def utcnow():
    return datetime.now(timezone.utc)


class CloudProvider(str, enum.Enum):
    google_drive = "google_drive"
    aws_s3 = "aws_s3"


class ProcessingStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class JobType(str, enum.Enum):
    text_extraction = "text_extraction"
    ocr = "ocr"
    table_extraction = "table_extraction"
    chunking = "chunking"
    embedding = "embedding"
    summarization = "summarization"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    cloud_accounts = relationship("ConnectedCloudAccount", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")


class ConnectedCloudAccount(Base):
    __tablename__ = "connected_cloud_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(Enum(CloudProvider), nullable=False)
    account_identifier = Column(String(255), nullable=False)  # email or bucket name
    # Tokens are stored as references to secret manager, not raw values
    access_token_ref = Column(String(512), nullable=True)
    refresh_token_ref = Column(String(512), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="cloud_accounts")


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(Enum(CloudProvider), nullable=False)
    external_file_id = Column(String(512), nullable=False)  # Drive file ID or S3 key
    file_name = Column(String(512), nullable=False)
    file_type = Column(String(50), nullable=False)  # pdf, docx, txt, etc.
    file_size = Column(BigInteger, nullable=True)
    source_path = Column(Text, nullable=True)
    mime_type = Column(String(255), nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)  # SHA-256 for dedup
    processing_status = Column(Enum(ProcessingStatus), default=ProcessingStatus.pending)
    ocr_required = Column(Boolean, default=False)
    ocr_completed = Column(Boolean, default=False)
    embedding_completed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    modified_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    tables = relationship("DocumentTable", back_populates="document", cascade="all, delete-orphan")
    processing_jobs = relationship("ProcessingJob", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)
    embedding_id = Column(String(255), nullable=True)  # ID in vector DB
    token_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    document = relationship("Document", back_populates="chunks")


class DocumentTable(Base):
    __tablename__ = "document_tables"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer, nullable=True)
    table_index = Column(Integer, nullable=False, default=0)
    table_data = Column(JSON, nullable=False)  # list of rows as dicts
    row_count = Column(Integer, nullable=True)
    col_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    document = relationship("Document", back_populates="tables")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    job_type = Column(Enum(JobType), nullable=False)
    status = Column(Enum(ProcessingStatus), default=ProcessingStatus.pending)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    document = relationship("Document", back_populates="processing_jobs")

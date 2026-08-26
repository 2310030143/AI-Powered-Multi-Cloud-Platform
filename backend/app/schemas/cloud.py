from datetime import datetime

from pydantic import BaseModel, Field


class GoogleConnectResponse(BaseModel):
    authorization_url: str
    message: str


class S3ConnectRequest(BaseModel):
    """Optional per-user S3-compatible credentials (Backblaze B2 / AWS S3 / MinIO).

    Any field left empty falls back to the server's S3_* environment variables.
    """
    access_key_id: str | None = Field(default=None, min_length=1)
    secret_access_key: str | None = Field(default=None, min_length=1)
    region: str | None = None
    endpoint_url: str | None = None
    bucket_name: str | None = Field(default=None, min_length=1)


class S3ConnectResponse(BaseModel):
    status: str
    provider: str
    bucket: str
    message: str | None = None


class ConnectionStatus(BaseModel):
    provider: str
    is_connected: bool
    account_identifier: str | None = None
    connected_at: datetime | None = None
    detail: str | None = None
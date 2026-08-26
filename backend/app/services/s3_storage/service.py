"""S3-compatible object storage operations.

Works with any S3-API provider — Backblaze B2 (free tier, our default),
AWS S3, MinIO, Cloudflare R2, ... — via ``endpoint_url``.
"""
import mimetypes
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.models import CloudProvider, ConnectedCloudAccount, User
from app.utils.logger import get_logger
from app.utils.security import decrypt_secret, encrypt_secret

settings = get_settings()
logger = get_logger(__name__)


def _guess_mime_type(name: str) -> str:
    mime, _ = mimetypes.guess_type(name)
    return mime or "application/octet-stream"


def _key_basename(key: str) -> str:
    return key.rstrip("/").rsplit("/", 1)[-1]


def _map_object(key: str, size: int | None, modified: datetime | None, prefix: str | None) -> dict:
    return {
        "provider": "s3",
        "file_id": key,
        "name": _key_basename(key),
        "mime_type": _guess_mime_type(key),
        "size": size,
        "modified_at": modified,
        "is_folder": False,
        "parent_id": prefix or None,
    }


class S3StorageService:
    """Thin wrapper over the S3 API returning provider-neutral file metadata."""

    def __init__(
        self,
        bucket_name: str,
        access_key_id: str,
        secret_access_key: str,
        region: str = "us-east-1",
        endpoint_url: str | None = None,
    ):
        self.bucket_name = bucket_name
        self.client = boto3.client(
            "s3",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region or "us-east-1",
            endpoint_url=endpoint_url or None,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
        )

    # ── error translation ──────────────────────────────────────────────────

    def _handle_client_error(self, exc: ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        message = exc.response.get("Error", {}).get("Message", str(exc))
        if code in ("NoSuchKey", "NoSuchBucket", "NotFound", "404"):
            raise HTTPException(status_code=404, detail=f"Not found in bucket '{self.bucket_name}': {message}")
        if code in ("AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "InvalidTokenId", "403"):
            raise HTTPException(
                status_code=400,
                detail=f"Credentials are not valid for bucket '{self.bucket_name}': {message}",
            )
        logger.error("S3 error %s: %s", code, message)
        raise HTTPException(status_code=502, detail=f"S3 storage error: {message}")

    # ── operations ─────────────────────────────────────────────────────────

    def validate(self) -> dict:
        """Check the bucket is reachable with the configured credentials."""
        try:
            self.client.head_bucket(Bucket=self.bucket_name)
        except ClientError as exc:
            self._handle_client_error(exc)
        except BotoCoreError as exc:
            raise HTTPException(status_code=502, detail=f"Could not reach the S3 endpoint: {exc}")
        return {"bucket": self.bucket_name}

    def list_files(self, folder_id: str = "", search: str | None = None, limit: int = 1000) -> list[dict]:
        """List objects under a prefix. ``folder_id`` is the S3 prefix;
        'folders' are the common prefixes under the delimiter."""
        prefix = (folder_id or "").lstrip("/")
        try:
            response = self.client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                Delimiter="/",
                MaxKeys=min(max(limit, 1), 1000),
            )
        except ClientError as exc:
            self._handle_client_error(exc)

        files: list[dict] = []
        for common in response.get("CommonPrefixes", []):
            p = common.get("Prefix", "")
            files.append({
                "provider": "s3",
                "file_id": p,
                "name": _key_basename(p) + "/",
                "mime_type": None,
                "size": None,
                "modified_at": None,
                "is_folder": True,
                "parent_id": prefix or None,
            })
        for obj in response.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue  # folder placeholder object
            if search and search.lower() not in key.lower():
                continue
            files.append(_map_object(key, obj.get("Size"), obj.get("LastModified"), prefix))
        return files

    def get_file(self, file_id: str) -> dict:
        try:
            response = self.client.head_object(Bucket=self.bucket_name, Key=file_id)
        except ClientError as exc:
            self._handle_client_error(exc)
        return {
            "provider": "s3",
            "file_id": file_id,
            "name": _key_basename(file_id),
            "mime_type": response.get("ContentType") or _guess_mime_type(file_id),
            "size": response.get("ContentLength"),
            "modified_at": response.get("LastModified"),
            "is_folder": False,
            "parent_id": "/".join(file_id.rstrip("/").split("/")[:-1]) or None,
        }

    def download_file(self, file_id: str) -> tuple[str, object, str]:
        """Return ``(filename, stream, content_type)`` — the stream is a
        botocore StreamingBody that can be fed to StreamingResponse."""
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=file_id)
        except ClientError as exc:
            self._handle_client_error(exc)
        return (
            _key_basename(file_id),
            response["Body"],
            response.get("ContentType") or _guess_mime_type(file_id),
        )

    def upload_file(self, filename: str, content: bytes, mime_type: str, folder_id: str | None = None) -> dict:
        """Upload ``content`` as ``filename`` under the ``folder_id`` prefix."""
        prefix = (folder_id or "").strip("/")
        key = f"{prefix}/{filename}" if prefix else filename
        content_type = mime_type or _guess_mime_type(filename)
        try:
            self.client.put_object(Bucket=self.bucket_name, Key=key, Body=content, ContentType=content_type)
            response = self.client.head_object(Bucket=self.bucket_name, Key=key)
        except ClientError as exc:
            self._handle_client_error(exc)
        return _map_object(key, response.get("ContentLength", len(content)), response.get("LastModified"), prefix)


def get_s3_service_for_user(db: Session, user: User) -> S3StorageService:
    """Resolve the S3 service for a user: their stored (encrypted) credentials
    if they connected a bucket, otherwise the server-level S3_* environment."""
    account = (
        db.query(ConnectedCloudAccount)
        .filter(
            ConnectedCloudAccount.user_id == user.id,
            ConnectedCloudAccount.provider == CloudProvider.s3,
            ConnectedCloudAccount.is_active.is_(True),
        )
        .first()
    )
    if account is not None:
        extra = account.extra_data or {}
        return S3StorageService(
            bucket_name=account.account_identifier,
            access_key_id=decrypt_secret(account.access_token_ref),
            secret_access_key=decrypt_secret(account.refresh_token_ref),
            region=extra.get("region") or settings.S3_REGION,
            endpoint_url=extra.get("endpoint_url") or settings.S3_ENDPOINT_URL or None,
        )

    if settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY and settings.S3_BUCKET_NAME:
        return S3StorageService(
            bucket_name=settings.S3_BUCKET_NAME,
            access_key_id=settings.S3_ACCESS_KEY_ID,
            secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            region=settings.S3_REGION,
            endpoint_url=settings.S3_ENDPOINT_URL or None,
        )

    raise HTTPException(
        status_code=400,
        detail="No S3-compatible storage is connected. POST /api/v1/cloud/s3/connect first, "
        "or configure S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY / S3_BUCKET_NAME.",
    )

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config.settings import get_settings
from app.database.session import get_db
from app.models.models import CloudProvider, ConnectedCloudAccount, User
from app.schemas.cloud import ConnectionStatus, S3ConnectRequest, S3ConnectResponse
from app.services.registry import get_connected_account
from app.services.s3_storage.service import S3StorageService
from app.utils.logger import get_logger
from app.utils.security import encrypt_secret

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)


@router.post("/connect", response_model=S3ConnectResponse)
def connect_s3(
    payload: S3ConnectRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Validate S3-compatible credentials and store them (encrypted) for the
    current user.

    Works with any S3-API provider — Backblaze B2 (free tier), AWS S3, MinIO.
    Fields left empty fall back to the server's S3_* environment variables.
    """
    payload = payload or S3ConnectRequest()
    access_key = payload.access_key_id or settings.S3_ACCESS_KEY_ID
    secret_key = payload.secret_access_key or settings.S3_SECRET_ACCESS_KEY
    region = payload.region or settings.S3_REGION
    endpoint_url = payload.endpoint_url or settings.S3_ENDPOINT_URL
    bucket = payload.bucket_name or settings.S3_BUCKET_NAME

    if not access_key or not secret_key or not bucket:
        raise HTTPException(
            status_code=400,
            detail="Missing S3 credentials — provide them in the request body, or configure "
            "S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY / S3_BUCKET_NAME on the server",
        )

    service = S3StorageService(
        bucket_name=bucket,
        access_key_id=access_key,
        secret_access_key=secret_key,
        region=region,
        endpoint_url=endpoint_url,
    )
    service.validate()  # raises 400/404/502 on failure

    account = get_connected_account(db, current_user, CloudProvider.s3)
    if account is None:
        account = ConnectedCloudAccount(user_id=current_user.id, provider=CloudProvider.s3)
        db.add(account)
    account.account_identifier = bucket
    account.access_token_ref = encrypt_secret(access_key)
    account.refresh_token_ref = encrypt_secret(secret_key)
    account.token_expires_at = None
    account.extra_data = {"endpoint_url": endpoint_url or "", "region": region}
    account.is_active = True
    db.commit()

    logger.info("S3-compatible storage connected for user %s (bucket=%s)", current_user.email, bucket)
    return S3ConnectResponse(
        status="connected",
        provider="s3",
        bucket=bucket,
        message="Credentials validated against the bucket and stored (encrypted).",
    )


@router.get("/status", response_model=ConnectionStatus)
def s3_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = get_connected_account(db, current_user, CloudProvider.s3)
    if account is not None:
        return ConnectionStatus(
            provider="s3",
            is_connected=True,
            account_identifier=account.account_identifier,
            connected_at=account.created_at,
        )
    if settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY and settings.S3_BUCKET_NAME:
        return ConnectionStatus(
            provider="s3",
            is_connected=True,
            account_identifier=settings.S3_BUCKET_NAME,
            detail="Connected via server-level S3_* environment credentials.",
        )
    return ConnectionStatus(
        provider="s3",
        is_connected=False,
        detail="Not connected. POST /api/v1/cloud/s3/connect with credentials.",
    )


@router.delete("/disconnect", response_model=ConnectionStatus)
def s3_disconnect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = get_connected_account(db, current_user, CloudProvider.s3)
    if account is not None:
        db.delete(account)
        db.commit()
        logger.info("S3 storage disconnected for user %s", current_user.email)
    return ConnectionStatus(provider="s3", is_connected=False)

"""Factory that resolves the right cloud service for a user + provider."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.models import CloudProvider, ConnectedCloudAccount, User
from app.services.google_drive.service import get_drive_service_for_account
from app.services.s3_storage.service import get_s3_service_for_user


def get_connected_account(
    db: Session, user: User, provider: CloudProvider
) -> ConnectedCloudAccount | None:
    return (
        db.query(ConnectedCloudAccount)
        .filter(
            ConnectedCloudAccount.user_id == user.id,
            ConnectedCloudAccount.provider == provider,
            ConnectedCloudAccount.is_active.is_(True),
        )
        .first()
    )


def get_cloud_service(db: Session, user: User, provider: CloudProvider):
    """Return a service object for the provider (GoogleDriveService or
    S3StorageService), raising HTTPException(400) when it isn't connected."""
    if provider == CloudProvider.google_drive:
        account = get_connected_account(db, user, provider)
        if account is None:
            raise HTTPException(
                status_code=400,
                detail="Google Drive is not connected. Start with GET /api/v1/cloud/google/connect.",
            )
        return get_drive_service_for_account(db, account)

    if provider == CloudProvider.s3:
        return get_s3_service_for_user(db, user)

    raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
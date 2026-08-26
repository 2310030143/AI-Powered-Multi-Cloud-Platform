from datetime import timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config.settings import get_settings
from app.database.session import get_db
from app.models.models import CloudProvider, ConnectedCloudAccount, User
from app.schemas.cloud import ConnectionStatus, GoogleConnectResponse
from app.services.google_drive.auth import (
    build_authorization_url,
    exchange_code_for_credentials,
    fetch_user_email,
)
from app.services.registry import get_connected_account
from app.utils.logger import get_logger
from app.utils.security import create_state_token, decode_state_token, encrypt_secret

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)


@router.get("/connect", response_model=GoogleConnectResponse)
def connect_google(current_user: User = Depends(get_current_user)):
    """Start the Google Drive OAuth flow.

    Returns the consent-screen URL. The signed ``state`` ties the browser
    round-trip back to the authenticated user.
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured on this server (missing GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)",
        )
    state = create_state_token(str(current_user.id), "google_connect")
    url = build_authorization_url(state)
    return GoogleConnectResponse(
        authorization_url=url,
        message="Open authorization_url in a browser, sign in with Google and grant access. "
        "Google then redirects back to the callback endpoint to finish the connection.",
    )


@router.get("/callback")
def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """OAuth 2.0 redirect target — exchanges the authorization code for tokens
    and stores them (encrypted) in the connected account record."""
    if error:
        raise HTTPException(status_code=400, detail=f"Google returned an error: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing 'code' or 'state' in the OAuth callback")

    user_id = decode_state_token(state, "google_connect")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired state — restart the connection from /api/v1/cloud/google/connect")
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state subject")

    user = db.get(User, user_uuid)
    if user is None:
        raise HTTPException(status_code=404, detail="User no longer exists")

    credentials = exchange_code_for_credentials(code)
    if credentials is None or not getattr(credentials, "token", None):
        raise HTTPException(status_code=400, detail="Google did not return an access token")

    email = fetch_user_email(credentials.token) or "unknown-account"

    account = get_connected_account(db, user, CloudProvider.google_drive)
    if account is None:
        account = ConnectedCloudAccount(user_id=user.id, provider=CloudProvider.google_drive)
        db.add(account)
    account.account_identifier = email
    account.access_token_ref = encrypt_secret(credentials.token)
    account.refresh_token_ref = encrypt_secret(getattr(credentials, "refresh_token", None))
    expiry = getattr(credentials, "expiry", None)
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    account.token_expires_at = expiry
    account.is_active = True
    db.commit()

    logger.info("Google Drive connected for user %s (%s)", user.email, email)
    return {"status": "connected", "provider": "google_drive", "account": email}


@router.get("/status", response_model=ConnectionStatus)
def google_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = get_connected_account(db, current_user, CloudProvider.google_drive)
    if account is None:
        return ConnectionStatus(
            provider="google_drive",
            is_connected=False,
            detail="Not connected. Start with GET /api/v1/cloud/google/connect.",
        )
    return ConnectionStatus(
        provider="google_drive",
        is_connected=True,
        account_identifier=account.account_identifier,
        connected_at=account.created_at,
    )


@router.delete("/disconnect", response_model=ConnectionStatus)
def google_disconnect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = get_connected_account(db, current_user, CloudProvider.google_drive)
    if account is not None:
        db.delete(account)
        db.commit()
        logger.info("Google Drive disconnected for user %s", current_user.email)
    return ConnectionStatus(provider="google_drive", is_connected=False)

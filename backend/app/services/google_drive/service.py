"""Google Drive operations (list / get / download / upload).

All methods return plain dicts in a provider-neutral shape so the API layer
can treat every cloud provider the same way:

    {
        "provider": "google_drive",
        "file_id": ..., "name": ..., "mime_type": ...,
        "size": ..., "modified_at": ..., "is_folder": ..., "parent_id": ...,
    }
"""
import io
from datetime import datetime, timezone

from fastapi import HTTPException
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.models import ConnectedCloudAccount
from app.utils.logger import get_logger
from app.utils.security import decrypt_secret, encrypt_secret

settings = get_settings()
logger = get_logger(__name__)

FOLDER_MIME = "application/vnd.google-apps.folder"

# Google-native documents must be exported to a real file format to be downloaded.
EXPORT_MAP = {
    "application/vnd.google-apps.document": ("application/pdf", "pdf"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", "csv"),
    "application/vnd.google-apps.presentation": ("application/pdf", "pdf"),
    "application/vnd.google-apps.drawing": ("image/png", "png"),
}


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _map_file(item: dict) -> dict:
    return {
        "provider": "google_drive",
        "file_id": item["id"],
        "name": item.get("name", ""),
        "mime_type": item.get("mimeType"),
        "size": int(item["size"]) if item.get("size") else None,
        "modified_at": _parse_datetime(item.get("modifiedTime")),
        "is_folder": item.get("mimeType") == FOLDER_MIME,
        "parent_id": (item.get("parents") or [None])[0],
    }


class GoogleDriveService:
    """Thin wrapper over the Drive v3 API."""

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = build(
                "drive", "v3", credentials=self.credentials, cache_discovery=False
            )
        return self._client

    def _execute(self, request):
        try:
            return request.execute()
        except HttpError as exc:
            code = exc.resp.status
            reason = exc._get_reason()
            if code == 404:
                raise HTTPException(status_code=404, detail=f"File not found on Google Drive: {reason}")
            if code in (401, 403):
                raise HTTPException(
                    status_code=400,
                    detail=f"Google Drive rejected the request — the account may need to be reconnected: {reason}",
                )
            logger.error("Google Drive API error %s: %s", code, reason)
            raise HTTPException(status_code=502, detail=f"Google Drive API error: {reason}")

    # ── operations ─────────────────────────────────────────────────────────

    def list_files(self, folder_id: str = "root", search: str | None = None, limit: int = 100) -> list[dict]:
        conditions = [f"'{folder_id}' in parents", "trashed = false"]
        if search:
            escaped = search.replace("\\", "\\\\").replace("'", "\\'")
            conditions.append(f"name contains '{escaped}'")
        result = self._execute(
            self.client.files().list(
                q=" and ".join(conditions),
                pageSize=min(max(limit, 1), 1000),
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, parents)",
                orderBy="folder, name",
            )
        )
        return [_map_file(item) for item in result.get("files", [])]

    def get_file(self, file_id: str) -> dict:
        item = self._execute(
            self.client.files().get(
                fileId=file_id,
                fields="id, name, mimeType, size, modifiedTime, parents",
            )
        )
        return _map_file(item)

    def download_file(self, file_id: str) -> tuple[str, bytes, str]:
        """Return ``(filename, content_bytes, content_type)``.

        Google-native documents (Docs/Sheets/Slides) are exported to an
        equivalent downloadable format first.
        """
        meta = self.get_file(file_id)
        mime = meta.get("mime_type") or "application/octet-stream"
        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if meta.get("size") and meta["size"] > max_bytes:
            raise HTTPException(status_code=413, detail=f"File exceeds the {settings.MAX_FILE_SIZE_MB} MB download limit")

        if mime in EXPORT_MAP:
            export_mime, extension = EXPORT_MAP[mime]
            request = self.client.files().export_media(fileId=file_id, mimeType=export_mime)
            filename = meta["name"] if "." in meta["name"] else f"{meta['name']}.{extension}"
            content_type = export_mime
        else:
            request = self.client.files().get_media(fileId=file_id)
            filename = meta["name"]
            content_type = mime

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return filename, buffer.getvalue(), content_type

    def upload_file(self, filename: str, content: bytes, mime_type: str, folder_id: str | None = None) -> dict:
        """Upload ``content`` as ``filename`` (optionally into ``folder_id``)."""
        body: dict = {"name": filename}
        if folder_id and folder_id != "root":
            body["parents"] = [folder_id]
        media = MediaIoBaseUpload(
            io.BytesIO(content), mimetype=mime_type or "application/octet-stream", resumable=False
        )
        item = self._execute(
            self.client.files().create(
                body=body,
                media_body=media,
                fields="id, name, mimeType, size, modifiedTime, parents",
            )
        )
        return _map_file(item)


def get_drive_service_for_account(db: Session, account: ConnectedCloudAccount) -> GoogleDriveService:
    """Build a Drive service from the account's encrypted tokens, refreshing
    the access token with Google when it has expired (persisting the new one)."""
    token = decrypt_secret(account.access_token_ref)
    refresh_token = decrypt_secret(account.refresh_token_ref)
    if not token and not refresh_token:
        raise HTTPException(status_code=400, detail="Stored Google Drive credentials are invalid — reconnect the account")

    credentials = Credentials(
        token=token or None,
        refresh_token=refresh_token or None,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=settings.GOOGLE_SCOPES,
    )

    if not credentials.valid and credentials.refresh_token:
        logger.info("Refreshing Google Drive token for %s", account.account_identifier)
        try:
            credentials.refresh(Request())
        except Exception as exc:
            logger.warning("Google token refresh failed: %s", exc)
            raise HTTPException(
                status_code=400,
                detail="Could not refresh the Google Drive access token — reconnect the account",
            )
        account.access_token_ref = encrypt_secret(credentials.token or "")
        expiry = credentials.expiry
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        account.token_expires_at = expiry
        db.commit()

    return GoogleDriveService(credentials)

"""Google OAuth 2.0 helpers for the Drive connector."""
from google_auth_oauthlib.flow import Flow

from app.config.settings import get_settings
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)


def _client_config() -> dict:
    return {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
        }
    }


def _build_flow() -> Flow:
    return Flow.from_client_config(
        _client_config(),
        scopes=settings.GOOGLE_SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )


def build_authorization_url(state: str) -> str:
    """Build the Google consent-screen URL. The signed ``state`` ties the
    browser round-trip back to the user who started the connection."""
    flow = _build_flow()
    authorization_url, _ = flow.authorization_url(
        access_type="offline",           # ask for a refresh token
        include_granted_scopes="true",
        prompt="consent",                # force refresh token on re-connects
        state=state,
    )
    return authorization_url


def exchange_code_for_credentials(code: str):
    """Exchange an authorization code for OAuth credentials."""
    flow = _build_flow()
    flow.fetch_token(code=code)
    return flow.credentials


def fetch_user_email(access_token: str) -> str | None:
    """Return the Google account email for an access token (best effort)."""
    import httpx

    try:
        response = httpx.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if response.status_code == 200:
            return response.json().get("email")
    except Exception as exc:  # network failures should not break the connection
        logger.warning("Could not fetch Google account email: %s", exc)
    return None

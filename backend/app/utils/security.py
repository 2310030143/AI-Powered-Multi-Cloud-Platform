"""Security helpers.

- Password hashing (bcrypt via passlib)
- JWT access tokens (python-jose)
- Short-lived signed OAuth state tokens
- Fernet encryption for cloud credentials stored in the database
"""
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config.settings import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ─── Passwords ────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


# ─── JWT access tokens ────────────────────────────────────────────────────────

def create_access_token(subject: str, expires_minutes: int | None = None) -> tuple[str, int]:
    """Return (token, expires_in_seconds)."""
    minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, minutes * 60


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


# ─── Signed OAuth state tokens ────────────────────────────────────────────────

def create_state_token(subject: str, purpose: str, expires_minutes: int = 10) -> str:
    """Short-lived signed token carried through the OAuth 'state' parameter."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "purpose": purpose,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_state_token(token: str, purpose: str) -> str | None:
    """Verify a state token and return its subject, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    if payload.get("purpose") != purpose:
        return None
    return payload.get("sub")


# ─── Secret encryption (cloud credentials at rest) ────────────────────────────

_ENCRYPTION_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    # Derive a stable Fernet key from SECRET_KEY (sha256 → 32-byte key)
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str | None) -> str:
    if not value:
        return ""
    return _ENCRYPTION_PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str:
    if not value:
        return ""
    if value.startswith(_ENCRYPTION_PREFIX):
        try:
            return _fernet().decrypt(value[len(_ENCRYPTION_PREFIX):].encode()).decode()
        except InvalidToken:
            return ""
    # Value was stored in plaintext (e.g. by an older version)
    return value
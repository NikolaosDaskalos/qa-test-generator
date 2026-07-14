"""Security primitives: JWT access and reset tokens, password hashing, and repository-token encryption."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import settings

logger = logging.getLogger(__name__)

password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))


ALGORITHM = "HS256"


def create_access_token(subject: str | Any, expires_delta: timedelta) -> str:
    """Return a signed JWT whose subject is ``subject``, expiring after ``expires_delta``."""
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> tuple[bool, str | None]:
    """Verify a password, returning ``(matched, upgraded_hash_or_None)``.

    The second element is a fresh hash when the stored one used an outdated
    scheme and should be persisted, otherwise ``None``.
    """
    return password_hash.verify_and_update(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a plaintext password with the preferred (Argon2) scheme."""
    return password_hash.hash(password)


def generate_password_reset_token(email: str) -> str:
    """Return a signed JWT scoping a password reset to ``email``, expiring per settings."""
    delta = timedelta(hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS)
    now = datetime.now(timezone.utc)
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode({"exp": exp, "nbf": now, "sub": email}, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password_reset_token(token: str) -> str | None:
    """Return the email a valid reset token was issued for, or ``None`` if invalid/expired."""
    try:
        decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return str(decoded_token["sub"])
    except InvalidTokenError:
        logger.warning("Password reset token verification failed")
        return None


def encrypt_repository_token(token: str) -> str:
    """Encrypt a repository access token with Fernet for storage at rest."""
    if not token:
        raise ValueError("Repository token cannot be empty")
    return Fernet(settings.repository_token_encryption_key).encrypt(token.encode()).decode()


def decrypt_repository_token(encrypted_token: str) -> str:
    """Decrypt a Fernet-encrypted repository token; raise ``ValueError`` if invalid."""
    try:
        return Fernet(settings.repository_token_encryption_key).decrypt(encrypted_token.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise ValueError("Repository token could not be decrypted") from exc

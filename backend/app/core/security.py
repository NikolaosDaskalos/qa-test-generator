from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import settings

password_hash = PasswordHash(
    (
        Argon2Hasher(),
        BcryptHasher(),
    )
)


ALGORITHM = "HS256"


def create_access_token(subject: str | Any, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    return password_hash.verify_and_update(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


def encrypt_repository_token(token: str) -> str:
    if not token:
        raise ValueError("Repository token cannot be empty")
    return (
        Fernet(settings.repository_token_encryption_key)
        .encrypt(token.encode())
        .decode()
    )


def decrypt_repository_token(encrypted_token: str) -> str:
    try:
        return (
            Fernet(settings.repository_token_encryption_key)
            .decrypt(encrypted_token.encode())
            .decode()
        )
    except (InvalidToken, ValueError) as exc:
        raise ValueError("Repository token could not be decrypted") from exc

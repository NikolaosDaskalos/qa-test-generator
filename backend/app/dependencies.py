"""Provide FastAPI dependencies for database, authentication, and Weaviate."""

import logging
from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session

from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.core.vector_db import WeaviateResources, get_weaviate_resources
from app.models.user import User
from app.persistence.repository_store import RepositoryStore
from app.rag.ingestor import DocumentIngestor
from app.schemas.authentication import TokenPayload
from app.services.repository_service import RepositoryService

logger = logging.getLogger(__name__)

reusable_oauth2 = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/login/access-token")


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and close it after the request."""
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]
WeaviateResourcesDep = Annotated[WeaviateResources, Depends(get_weaviate_resources)]


def get_repository_store(session: SessionDep) -> RepositoryStore:
    """Build the PostgreSQL store for Git repository records."""
    return RepositoryStore(session)


RepositoryStoreDep = Annotated[RepositoryStore, Depends(get_repository_store)]


def get_document_ingestor(weaviate_resources: WeaviateResourcesDep) -> DocumentIngestor:
    """Build a lazy repository document ingestor for one request."""
    return DocumentIngestor(weaviate_resources)


DocumentIngestorDep = Annotated[DocumentIngestor, Depends(get_document_ingestor)]


def get_repository_service(repository_store: RepositoryStoreDep, ingestor: DocumentIngestorDep) -> RepositoryService:
    """Compose the Git repository application service."""
    return RepositoryService(repository_store, ingestor)


RepositoryServiceDep = Annotated[RepositoryService, Depends(get_repository_service)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    """Authenticate an active user from a bearer token.

    Raises:
        HTTPException: If the token or associated user is invalid.

    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        logger.warning("Authentication rejected because the bearer token is invalid")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Could not validate credentials")
    user = session.get(User, token_data.sub)
    if not user:
        logger.warning("Authentication rejected because the token user was not found user_id=%s", token_data.sub)
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        logger.warning("Authentication rejected because the user is inactive user_id=%s", user.id)
        raise HTTPException(status_code=400, detail="Inactive user")
    logger.info("User authenticated user_id=%s", user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    """Require and return an authenticated superuser.

    Raises:
        HTTPException: If the current user lacks superuser privileges.

    """
    if not current_user.is_superuser:
        logger.warning("Superuser authorization denied user_id=%s", current_user.id)
        raise HTTPException(status_code=403, detail="The user doesn't have enough privileges")
    logger.info("Superuser authorization granted user_id=%s", current_user.id)
    return current_user

import uuid

from fastapi import APIRouter, status

from app.dependencies import CurrentUser, RepositorySessionServiceDep
from app.models.session import RepositorySession
from app.schemas.session import RepositorySessionCreate, RepositorySessionPublic, SessionHistoriesPublic, SessionHistoryPublic

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=RepositorySessionPublic, status_code=status.HTTP_201_CREATED)
def create_repository_session(
    *, repository_session_service: RepositorySessionServiceDep, current_user: CurrentUser, session_in: RepositorySessionCreate
) -> RepositorySession:
    return repository_session_service.create_session(session_in=session_in, user=current_user)


@router.get("/{repository_session_id}/history", response_model=SessionHistoriesPublic)
def read_repository_session_history(
    *, repository_session_service: RepositorySessionServiceDep, current_user: CurrentUser, repository_session_id: uuid.UUID
) -> SessionHistoriesPublic:
    history = repository_session_service.get_recent_history(repository_session_id=repository_session_id, user=current_user)
    return SessionHistoriesPublic(data=[SessionHistoryPublic.model_validate(message) for message in history])

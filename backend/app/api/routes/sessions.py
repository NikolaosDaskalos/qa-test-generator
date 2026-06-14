import json
import logging
import uuid
from collections.abc import Generator, Iterable

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse

from app.dependencies import CurrentUser, RAGPipelineDep, RepositorySessionServiceDep
from app.models.session import RepositorySession
from app.schemas.agent_stream import AgentStreamEvent
from app.schemas.session import RepositoryQuestionRequest, RepositorySessionCreate, RepositorySessionPublic, SessionHistoriesPublic, SessionHistoryPublic

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=RepositorySessionPublic, status_code=status.HTTP_201_CREATED)
def create_repository_session(
    *, repository_session_service: RepositorySessionServiceDep, current_user: CurrentUser, session_in: RepositorySessionCreate
) -> RepositorySession:
    return repository_session_service.create_session(session_in=session_in, user=current_user)


@router.post("/{repository_session_id}/questions")
def ask_repository_question(
    *,
    repository_session_service: RepositorySessionServiceDep,
    current_user: CurrentUser,
    rag_pipeline: RAGPipelineDep,
    repository_session_id: uuid.UUID,
    question_in: RepositoryQuestionRequest,
) -> StreamingResponse:
    """Stream a repository-grounded answer with file citations for an owned session."""
    events = repository_session_service.answer_question(
        repository_session_id=repository_session_id,
        user=current_user,
        question=question_in.question,
        pipeline=rag_pipeline,
    )
    return StreamingResponse(_to_sse(events), media_type="text/event-stream")


@router.get("/{repository_session_id}/history", response_model=SessionHistoriesPublic)
def read_repository_session_history(
    *, repository_session_service: RepositorySessionServiceDep, current_user: CurrentUser, repository_session_id: uuid.UUID
) -> SessionHistoriesPublic:
    history = repository_session_service.get_recent_history(repository_session_id=repository_session_id, user=current_user)
    return SessionHistoriesPublic(data=[SessionHistoryPublic.model_validate(message) for message in history])

def _to_sse(events: Iterable[AgentStreamEvent]) -> Generator[str, None, None]:
    """Serialize typed Agent Stream events as server-sent event frames.

    This is the only module that knows the wire format. The terminal ``Result``
    event closes a successful stream — there is no separate ``done`` frame. An
    unexpected mid-stream failure surfaces as a single out-of-band ``error`` frame
    (outside the typed vocabulary) rather than tearing down the connection.
    """
    try:
        for event in events:
            yield f"data: {event.model_dump_json()}\n\n"
    except Exception:
        logger.exception("Streaming answer failed")
        error = {"type": "error", "message": "An error occurred while generating the answer."}
        yield f"data: {json.dumps(error)}\n\n"


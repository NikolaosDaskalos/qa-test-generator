import json
import logging
import uuid
from collections.abc import Generator, Iterable

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse

from app.dependencies import CurrentUser, RepositorySessionServiceDep, SessionGraphDep
from app.models.session import RepositorySession
from app.schemas.agent_stream import AgentStreamEvent
from app.schemas.session import (
    CodingRunPublic,
    RepositoryQuestionRequest,
    RepositorySessionCreate,
    RepositorySessionPublic,
    RunPatchPublic,
    SessionHistoriesPublic,
    SessionHistoryPublic,
)

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
    session_graph: SessionGraphDep,
    repository_session_id: uuid.UUID,
    question_in: RepositoryQuestionRequest,
) -> StreamingResponse:
    """Infer the Request Intent and stream the routed Agent Stream for an owned session.

    The same entry point serves a repository-grounded answer, a Test-Generation Task,
    and the owner's human-in-the-loop decision on a reviewed patch; the unified graph's
    ``classify`` node decides the first two, while a ``decision`` resumes the suspended
    run that produced the patch. A fresh question gets its own checkpointer ``thread_id``;
    a decision reuses the paused run's own thread.
    """
    events = repository_session_service.stream_session(
        repository_session_id=repository_session_id,
        user=current_user,
        question=question_in.question,
        graph=session_graph,
        thread_id=str(uuid.uuid4()),
        decision=question_in.decision,
    )
    return StreamingResponse(_to_stream(events), media_type="text/event-stream")


@router.get("/{repository_session_id}/history", response_model=SessionHistoriesPublic)
def read_repository_session_history(
    *, repository_session_service: RepositorySessionServiceDep, current_user: CurrentUser, repository_session_id: uuid.UUID
) -> SessionHistoriesPublic:
    history = repository_session_service.get_recent_history(repository_session_id=repository_session_id, user=current_user)
    return SessionHistoriesPublic(data=[SessionHistoryPublic.model_validate(message) for message in history])

@router.get("/{repository_session_id}/runs/{coding_run_id}", response_model=CodingRunPublic)
def read_coding_run(
    *, repository_session_service: RepositorySessionServiceDep, current_user: CurrentUser, repository_session_id: uuid.UUID, coding_run_id: uuid.UUID
) -> CodingRunPublic:
    """Read an owned Coding Run's persisted state, review findings, and failure information.

    Serves the durable record after the ephemeral Agent Stream has closed, so a
    client that reloads or reconnects can recover the run's outcome.
    """
    run = repository_session_service.get_owned_run(repository_session_id=repository_session_id, coding_run_id=coding_run_id, user=current_user)
    return CodingRunPublic(
        id=run.id,
        status=run.status,
        failed_stage=run.failed_stage,
        failure_reason=run.failure_reason,
        review_findings=run.review_findings or [],
        diff=run.diff,
    )


@router.get("/{repository_session_id}/runs/{coding_run_id}/patch", response_model=RunPatchPublic)
def read_coding_run_patch(
    *, repository_session_service: RepositorySessionServiceDep, current_user: CurrentUser, repository_session_id: uuid.UUID, coding_run_id: uuid.UUID
) -> RunPatchPublic:
    """Read an owned Coding Run's persisted Test Patch content (canonical diff and proposals)."""
    run = repository_session_service.get_owned_run(repository_session_id=repository_session_id, coding_run_id=coding_run_id, user=current_user)
    return RunPatchPublic(
        coding_run_id=run.id,
        diff=run.diff or "",
        generated_files=run.generated_files or [],
        external_references=run.external_references or [],
    )


def _to_stream(events: Iterable[AgentStreamEvent]) -> Generator[str, None, None]:
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


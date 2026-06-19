"""Repository session routes: create/list sessions, stream agent turns, and read run results."""

import uuid

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse

from app.db.models import RepositorySession
from app.dependencies import CurrentUser, RepositorySessionServiceDep, SessionGraphDep
from app.schemas import (
    CodingRunPublic,
    RepositoryQuestionRequest,
    RepositorySessionCreate,
    RepositorySessionPublic,
    RepositorySessionsPublic,
    RunPatchPublic,
    SessionHistoriesPublic,
    SessionHistoryPublic,
)
from app.streaming import to_sse_frames

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=RepositorySessionPublic, status_code=status.HTTP_201_CREATED)
def create_repository_session(
    *, repository_session_service: RepositorySessionServiceDep, current_user: CurrentUser, session_in: RepositorySessionCreate
) -> RepositorySession:
    """Open a new session bound to a repository the caller can access."""
    return repository_session_service.create_session(session_in=session_in, user=current_user)


@router.get("", response_model=RepositorySessionsPublic)
def read_repository_sessions(
    *,
    repository_session_service: RepositorySessionServiceDep,
    current_user: CurrentUser,
    repository_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 100,
) -> RepositorySessionsPublic:
    """List the caller's Repository Sessions, optionally filtered by Repository."""
    return repository_session_service.list_sessions(user=current_user, repository_id=repository_id, skip=skip, limit=limit)


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

    The same entry point serves a repository-grounded answer, a Code Generation Task,
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
    return StreamingResponse(to_sse_frames(events), media_type="text/event-stream")


@router.get("/{repository_session_id}/history", response_model=SessionHistoriesPublic)
def read_repository_session_history(
    *, repository_session_service: RepositorySessionServiceDep, current_user: CurrentUser, repository_session_id: uuid.UUID
) -> SessionHistoriesPublic:
    """Return the recent message history of an owned session."""
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
        id=run.id, status=run.status, failed_stage=run.failed_stage, failure_reason=run.failure_reason, review_findings=run.review_findings or [], diff=run.diff
    )


@router.get("/{repository_session_id}/runs/{coding_run_id}/patch", response_model=RunPatchPublic)
def read_coding_run_patch(
    *, repository_session_service: RepositorySessionServiceDep, current_user: CurrentUser, repository_session_id: uuid.UUID, coding_run_id: uuid.UUID
) -> RunPatchPublic:
    """Read an owned Coding Run's persisted Test Patch content (canonical diff and proposals)."""
    run = repository_session_service.get_owned_run(repository_session_id=repository_session_id, coding_run_id=coding_run_id, user=current_user)
    return RunPatchPublic(
        coding_run_id=run.id, diff=run.diff or "", generated_files=run.generated_files or [], external_references=run.external_references or []
    )

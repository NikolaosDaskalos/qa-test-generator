"""Domain exceptions for the Repository Session workflow, free of transport concerns.

The Repository Session application service raises these instead of HTTP errors; they
are translated to HTTP responses at the API seam (see ``app.api.exception_handlers``).
The ``status_code`` attribute is metadata read only at that seam — the workflow never
references HTTP status codes directly. Repository ownership checks reuse the shared
``RepositoryError`` types so repository-not-found/forbidden responses stay identical.
"""

from http import HTTPStatus


class SessionError(Exception):
    """Base Repository Session workflow error carrying a sanitized, user-facing detail."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    detail: str = "Repository Session request failed"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail if detail is not None else type(self).detail
        super().__init__(self.detail)


class RepositorySessionNotFound(SessionError):
    """The requested Repository Session does not exist."""

    status_code = HTTPStatus.NOT_FOUND
    detail = "Repository Session not found"


class RepositorySessionAccessForbidden(SessionError):
    """The Repository Session exists but is not owned by the requesting user."""

    status_code = HTTPStatus.FORBIDDEN
    detail = "Not enough permissions"


class RepositoryNotReady(SessionError):
    """A session cannot be opened while its Repository is still being processed."""

    status_code = HTTPStatus.CONFLICT
    detail = "Repository is not ready"


class CodingRunNotFound(SessionError):
    """The requested Coding Run does not exist within the named session."""

    status_code = HTTPStatus.NOT_FOUND
    detail = "Coding Run not found"


class RunNotAwaitingDecision(SessionError):
    """The Coding Run is not paused awaiting a human-in-the-loop decision."""

    status_code = HTTPStatus.CONFLICT
    detail = "Coding Run is not awaiting a decision"

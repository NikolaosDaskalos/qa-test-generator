"""Domain exceptions for the Repository workflow, free of transport concerns.

The Repository application service raises these instead of HTTP errors; they are
translated to HTTP responses at the API seam (see ``app.api.exception_handlers``).
The ``status_code`` attribute is metadata read only at that seam — the workflow
never references HTTP status codes directly.
"""

from http import HTTPStatus


class RepositoryError(Exception):
    """Base Repository workflow error carrying a sanitized, user-facing detail."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    detail: str = "Repository request failed"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail if detail is not None else type(self).detail
        super().__init__(self.detail)


class RepositoryNotFound(RepositoryError):
    """The requested Repository does not exist."""

    status_code = HTTPStatus.NOT_FOUND
    detail = "Repository not found"


class RepositoryAccessForbidden(RepositoryError):
    """The Repository exists but is not owned by the requesting user."""

    status_code = HTTPStatus.FORBIDDEN
    detail = "Not enough permissions"


class InvalidRepositoryUrl(RepositoryError):
    """The supplied repository URL is empty, malformed, or an unsupported host."""

    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    detail = "Repository URL is not valid"


class DuplicateRepository(RepositoryError):
    """The user already registered an equivalent Repository."""

    status_code = HTTPStatus.CONFLICT
    detail = "Repository already exists"


class InvalidRepositoryCredential(RepositoryError):
    """The supplied token cannot access the Repository remote."""

    status_code = HTTPStatus.UNAUTHORIZED
    detail = "Token is invalid for repository"


class RepositoryProcessing(RepositoryError):
    """The Repository cannot be mutated while it is still being processed."""

    status_code = HTTPStatus.CONFLICT
    detail = "Repository cannot be deleted while processing"


class RepositoryDeletionFailed(RepositoryError):
    """Local, vector, or relational cleanup failed during deletion."""

    status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    detail = "Repository deletion failed"

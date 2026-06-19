"""Translate domain exceptions to HTTP responses at the API seam.

Workflows raise transport-free domain errors; these handlers map them to the
same ``{"detail": ...}`` body and status codes FastAPI uses for ``HTTPException``.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.errors.repository_errors import RepositoryError


def register_exception_handlers(app: FastAPI) -> None:
    """Register translators that map domain errors to HTTP responses."""

    @app.exception_handler(RepositoryError)
    async def _handle_repository_error(_request: Request, exc: RepositoryError) -> JSONResponse:
        return JSONResponse(status_code=int(exc.status_code), content={"detail": exc.detail})
